# InterviewArena 配置与部署指南

本文档集中说明 InterviewArena 的环境变量、登录安全、跨域访问、数据库升级、健康检查和生产部署要求。所有命令默认在项目根目录执行。

## 环境配置

后端配置模板位于 [`backend/.env.example`](../backend/.env.example)。首次运行时先复制模板：

```powershell
Copy-Item backend\.env.example backend\.env
```

常用配置如下：

| 配置项                      | 用途                                | 建议值或说明                                   |
| --------------------------- | ----------------------------------- | ---------------------------------------------- |
| `APP_ENV`                   | 当前运行环境                        | 本地使用 `development`，生产使用 `production`  |
| `DATABASE_URL`              | MySQL 连接地址                      | 指向已创建的 `interview_arena` 数据库          |
| `JWT_SECRET_KEY`            | 登录令牌签名密钥                    | 必须设置，且不少于 32 个字符                   |
| `JWT_EXPIRE_MINUTES`        | 登录有效期                          | 默认 `1440` 分钟                               |
| `DEEPSEEK_API_KEY`          | 模型 API 密钥                       | 使用面试与评估能力时必须配置                   |
| `DEEPSEEK_BASE_URL`         | DeepSeek 兼容 API 地址              | 默认 `https://api.deepseek.com`                |
| `DEEPSEEK_MODEL`            | 实际调用的模型名称                  | 填写当前账户可用模型                           |
| `REDIS_URL`                 | 短期记忆 Redis 连接地址             | 默认 `redis://127.0.0.1:6379/0`                |
| `AUTO_MIGRATE_ON_STARTUP`   | 启动后端时执行版本化迁移            | 本地可设为 `true`；生产建议设为 `false`        |
| `AUTH_COOKIE_SECURE`        | 控制登录 Cookie 的 Secure 属性      | 本地 HTTP 设为 `false`；生产 HTTPS 保持 `true` |
| `AUTH_COOKIE_SAMESITE`      | 登录与 CSRF Cookie 的 SameSite 策略 | 同站部署或本地开发通常使用 `lax`               |
| `CSRF_PROTECTION_ENABLED`   | 校验 Cookie 认证写请求的 CSRF 令牌  | 保持 `true`                                    |
| `CSRF_HEADER_NAME`          | 前端回传 CSRF 令牌的请求头名称      | 默认 `X-CSRF-Token`                            |
| `CORS_ALLOWED_ORIGINS`      | 允许携带 Cookie 访问 API 的前端来源 | 填写逗号分隔的精确来源，不能使用 `*`           |
| `CORS_ALLOWED_ORIGIN_REGEX` | 额外允许的来源正则表达式            | 没有明确需求时留空                             |

模型、记忆任务、超时、自主进化和文件目录等其他配置以 [`.env.example`](../backend/.env.example) 为准。不要提交真实 `.env`、模型密钥或数据库凭据。

## 本地开发配置

本地使用 HTTP 启动前后端时，至少确认以下设置：

```dotenv
APP_ENV=development
DATABASE_URL=mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/interview_arena?charset=utf8mb4
JWT_SECRET_KEY=replace_with_a_random_secret_of_at_least_32_characters
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=your_available_model
AUTH_COOKIE_SECURE=false
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

如果前端不通过 Vite 开发代理访问后端，可设置：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

修改前端环境变量后需要重新启动 Vite 开发服务器。

## Cookie、CSRF 与跨域访问

登录成功后，后端会把访问令牌写入 HttpOnly Cookie，并单独设置 CSRF Cookie。项目自带前端会自动携带 Cookie，并在写请求中回传 CSRF 请求头；自行开发客户端时也需要实现这两步。

本地通过 `http://127.0.0.1` 或 `http://localhost` 开发时必须使用 `AUTH_COOKIE_SECURE=false`。生产环境应使用 HTTPS、设置 `AUTH_COOKIE_SECURE=true`，并将 `CORS_ALLOWED_ORIGINS` 限制为实际前端域名。

如果生产环境中的前后端属于不同站点，还需要将 `AUTH_COOKIE_SAMESITE` 设为 `none`；浏览器只会在同时启用 `AUTH_COOKIE_SECURE=true` 时接受这种跨站 Cookie 配置。

排查登录状态无法保存或写请求返回 CSRF 错误时，依次检查：

1. 本地 HTTP 是否设置了 `AUTH_COOKIE_SECURE=false`。
2. 浏览器访问地址是否与 `CORS_ALLOWED_ORIGINS` 中的来源完全一致。
3. 前端请求是否允许携带 Cookie。
4. 写请求是否使用 `CSRF_HEADER_NAME` 指定的请求头回传 CSRF Cookie 值。

## 数据库初始化与升级

### 新环境

先创建数据库：

```sql
CREATE DATABASE interview_arena
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

然后创建基础表并执行全部版本化迁移：

```powershell
python backend\scripts\init_db.py
```

### 已有数据库

升级已有数据库时运行：

```powershell
python backend\scripts\migrate_v1.py
```

迁移记录保存在 `schema_migrations` 表中，重复执行时会跳过已经完成的版本；执行过程使用 MySQL 命名锁，避免多个后端实例同时修改表结构。

本地开发默认启用 `AUTO_MIGRATE_ON_STARTUP=true`，启动后端时会自动补齐迁移。生产环境建议采用以下顺序：

1. 备份数据库。
2. 在发布阶段单独运行 `python backend\scripts\migrate_v1.py`。
3. 设置 `AUTO_MIGRATE_ON_STARTUP=false` 后启动应用实例。
4. 请求 `/api/health/ready`，确认数据库、目录和后台任务运行器均已就绪。

## 健康检查

| 地址                | 用途         | 返回规则                                                                        |
| ------------------- | ------------ | ------------------------------------------------------------------------------- |
| `/api/health`       | 存活检查     | API 进程可响应时返回 HTTP 200 和 `{"status":"ok"}`                              |
| `/api/health/ready` | 服务就绪检查 | 检查配置、MySQL、上传目录、后台任务运行器和自主进化状态；关键检查失败时返回 503 |

`/api/health/ready` 会在未配置模型密钥或未启用可选的自主进化功能时标记对应项目为 `degraded`，但只有关键检查出现 `failed` 才会返回 HTTP 503。

PowerShell 中可以这样检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/health/ready
```

## 生产部署检查清单

- 使用独立且足够长的随机 `JWT_SECRET_KEY`。
- 使用受限的数据库账户，并在迁移前完成备份。
- 使用 HTTPS，并保持 `AUTH_COOKIE_SECURE=true`。
- 保持 CSRF 防护开启。
- 将 CORS 来源限制为实际前端域名，不要使用通配符。
- 在发布阶段显式执行数据库迁移，应用实例使用 `AUTO_MIGRATE_ON_STARTUP=false`。
- 不要把 `.env`、密钥、上传文件、缓存或本地测试报告提交到仓库。
- 面试、评估、记忆总结和自主进化可能产生模型调用费用，应根据实际模型配置控制使用。
- 发布后确认 `/api/health/ready` 没有返回关键检查失败。

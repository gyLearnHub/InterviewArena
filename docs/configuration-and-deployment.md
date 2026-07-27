<p align="center">
  <a href="../README.md">← 返回项目首页</a>
</p>

<h1 align="center">InterviewArena 使用、配置与部署指南</h1>

<p align="center">
  <strong>从第一次启动，到安全配置、数据库升级和生产发布的一站式说明</strong>
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#环境配置">环境配置</a> ·
  <a href="#cookiecsrf-与跨域访问">登录安全</a> ·
  <a href="#数据库初始化与升级">数据库</a> ·
  <a href="#健康检查">健康检查</a> ·
  <a href="#质量保障">质量保障</a> ·
  <a href="#生产部署检查清单">生产部署</a>
</p>

---

## 先看这里

根据当前目标直接进入对应章节：

<table>
  <tr>
    <td width="25%" valign="top">
      <strong>🚀 第一次运行</strong><br /><br />
      准备 Python、Node.js 和 MySQL，在本地启动完整前后端。<br /><br />
      <a href="#快速开始">前往快速开始 →</a>
    </td>
    <td width="25%" valign="top">
      <strong>🔐 登录异常</strong><br /><br />
      检查 Cookie、CSRF、HTTP 与跨域来源配置。<br /><br />
      <a href="#cookiecsrf-与跨域访问">查看登录安全 →</a>
    </td>
    <td width="25%" valign="top">
      <strong>🗄️ 升级数据库</strong><br /><br />
      为已有数据库执行版本化迁移，避免并发修改表结构。<br /><br />
      <a href="#数据库初始化与升级">查看升级流程 →</a>
    </td>
    <td width="25%" valign="top">
      <strong>🚢 准备上线</strong><br /><br />
      核对 HTTPS、密钥、迁移、CORS 和服务就绪状态。<br /><br />
      <a href="#生产部署检查清单">查看发布清单 →</a>
    </td>
  </tr>
</table>

## 技术栈

| 层级     | 主要技术                                                             |
| -------- | -------------------------------------------------------------------- |
| 前端     | Vue 3.5、Vue Router 4、TypeScript 6、Vite 6                          |
| 后端     | Python 3.11、FastAPI、Pydantic 2、Uvicorn、PyMySQL、HTTPX            |
| 数据     | MySQL 8+、Redis、本地文件存储、可选 Chroma 与本地 Embedding/Reranker |
| 测试     | pytest、Playwright                                                   |
| 代码质量 | Ruff、mypy strict、ESLint、Prettier、vue-tsc、Vite build             |
| CI       | GitHub Actions、OpenAPI contract 同步检查                            |

## 快速开始

<p align="center">
  <code>克隆项目</code> → <code>创建数据库</code> → <code>配置后端</code> → <code>启动 API</code> → <code>启动前端</code>
</p>

> [!TIP]
> 以下命令以 Windows PowerShell 为例。macOS/Linux 用户只需替换虚拟环境激活和文件复制命令。

### 1. 检查环境

| 类型 | 要求                                                          |
| ---- | ------------------------------------------------------------- |
| 必需 | Python 3.11+、Node.js 20+、MySQL 8+ 或兼容版本                |
| 必需 | 可访问的 DeepSeek 兼容模型 API                                |
| 可选 | Redis；不可用时，系统会从 MySQL 重建短期记忆                  |
| 可选 | LibreOffice；仅处理旧版 `.doc` 文件时需要，`.docx` 不需要转换 |

### 2. 获取代码

```powershell
git clone https://github.com/gyLearnHub/InterviewArena.git
cd InterviewArena
```

### 3. 创建数据库

```sql
CREATE DATABASE interview_arena
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

确保 `DATABASE_URL` 使用的账户对该数据库拥有建表、读写和变更权限。

### 4. 安装并配置后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

编辑 `backend/.env`，至少完成以下配置：

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

> [!IMPORTANT]
> 本地通过 HTTP 开发时必须设置 `AUTH_COOKIE_SECURE=false`，否则浏览器不会发送登录 Cookie。

初始化表结构并启动 API：

```powershell
python backend\scripts\init_db.py
python backend\main.py
```

| 后端入口     | 地址                                     |
| ------------ | ---------------------------------------- |
| API          | <http://127.0.0.1:8000/api>              |
| Swagger UI   | <http://127.0.0.1:8000/docs>             |
| OpenAPI JSON | <http://127.0.0.1:8000/openapi.json>     |
| 存活检查     | <http://127.0.0.1:8000/api/health>       |
| 就绪检查     | <http://127.0.0.1:8000/api/health/ready> |
| Prometheus 指标 | <http://127.0.0.1:8000/api/metrics>   |

### 5. 启动前端

另开一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 <http://127.0.0.1:5173>，注册账户、上传简历并创建第一场面试。Vite 开发代理会把 `/api` 请求转发到 `http://127.0.0.1:8000`。

> macOS/Linux：使用 `source .venv/bin/activate` 激活虚拟环境，并使用 `cp backend/.env.example backend/.env` 复制配置模板。

## 环境配置

完整模板位于 [`backend/.env.example`](../backend/.env.example)。建议先复制模板，再只修改当前环境需要的值。

### 核心服务

| 配置项                    | 用途                     | 建议值或说明                                  |
| ------------------------- | ------------------------ | --------------------------------------------- |
| `APP_ENV`                 | 当前运行环境             | 本地使用 `development`，生产使用 `production` |
| `DATABASE_URL`            | MySQL 连接地址           | 指向已创建的 `interview_arena` 数据库         |
| `MYSQL_POOL_SIZE`         | 单实例 MySQL 连接池上限  | 默认 `10`，按数据库连接额度和实例数调整        |
| `MYSQL_CONNECT_TIMEOUT_SECONDS` | MySQL 建连超时    | 默认 `5` 秒                                   |
| `MYSQL_READ_TIMEOUT_SECONDS`    | MySQL 读取超时    | 默认 `30` 秒                                  |
| `MYSQL_WRITE_TIMEOUT_SECONDS`   | MySQL 写入超时    | 默认 `30` 秒                                  |
| `JWT_SECRET_KEY`          | 登录令牌签名密钥         | 必须设置，且不少于 32 个字符                  |
| `JWT_EXPIRE_MINUTES`      | 登录有效期               | 默认 `1440` 分钟                              |
| `DEEPSEEK_API_KEY`        | 模型 API 密钥            | 使用面试与评估能力时必须配置                  |
| `DEEPSEEK_BASE_URL`       | DeepSeek 兼容 API 地址   | 默认 `https://api.deepseek.com`               |
| `DEEPSEEK_MODEL`          | 实际调用的模型名称       | 填写当前账户可用模型                          |
| `REDIS_URL`               | 短期记忆 Redis 连接地址  | 默认 `redis://127.0.0.1:6379/0`               |
| `AUTO_MIGRATE_ON_STARTUP` | 启动后端时执行版本化迁移 | 本地可设为 `true`；生产建议设为 `false`       |

### 登录与跨域

| 配置项                      | 用途                                | 建议值或说明                                   |
| --------------------------- | ----------------------------------- | ---------------------------------------------- |
| `AUTH_COOKIE_SECURE`        | 控制登录 Cookie 的 Secure 属性      | 本地 HTTP 设为 `false`；生产 HTTPS 保持 `true` |
| `AUTH_COOKIE_SAMESITE`      | 登录与 CSRF Cookie 的 SameSite 策略 | 同站部署或本地开发通常使用 `lax`               |
| `CSRF_PROTECTION_ENABLED`   | 校验 Cookie 认证写请求的 CSRF 令牌  | 保持 `true`                                    |
| `CSRF_HEADER_NAME`          | 前端回传 CSRF 令牌的请求头名称      | 默认 `X-CSRF-Token`                            |
| `CORS_ALLOWED_ORIGINS`      | 允许携带 Cookie 访问 API 的前端来源 | 填写逗号分隔的精确来源，不能使用 `*`           |
| `CORS_ALLOWED_ORIGIN_REGEX` | 额外允许的来源正则表达式            | 没有明确需求时留空                             |

### 本地与生产环境对照

| 项目                      | 本地 HTTP 开发                                | 生产 HTTPS                            |
| ------------------------- | --------------------------------------------- | ------------------------------------- |
| `APP_ENV`                 | `development`                                 | `production`                          |
| `AUTH_COOKIE_SECURE`      | `false`                                       | `true`                                |
| `AUTH_COOKIE_SAMESITE`    | 通常使用 `lax`                                | 同站使用 `lax`；真正跨站时使用 `none` |
| `CORS_ALLOWED_ORIGINS`    | `http://127.0.0.1:5173,http://localhost:5173` | 仅填写实际前端 HTTPS 来源             |
| `AUTO_MIGRATE_ON_STARTUP` | 可使用 `true`                                 | 建议使用 `false`，在发布阶段显式迁移  |
| `JWT_SECRET_KEY`          | 独立开发密钥，至少 32 个字符                  | 独立强随机密钥，不与其他环境共用      |

模型、记忆任务、超时、自主进化和文件目录等其他配置以 [`.env.example`](../backend/.env.example) 为准。

### 单实例与多副本存储

默认 `STORAGE_BACKEND=local` 只允许 `DEPLOYMENT_REPLICA_COUNT=1`。简历原文件、头像和本地
Chroma 数据都依赖当前主机磁盘，不能直接把这种配置扩成多个后端副本。

多副本部署必须满足：

1. 设置 `STORAGE_BACKEND=shared_filesystem` 和实际副本数
   `DEPLOYMENT_REPLICA_COUNT`。
2. 将 `SHARED_STORAGE_ROOT` 指向所有副本挂载的同一持久共享卷。
3. 将 `UPLOAD_DIR`、`AVATAR_UPLOAD_DIR` 配置为该共享卷内的绝对路径。
4. 保持 `CHROMA_ENABLED=false`；多副本场景以 MySQL 检索回退为准，不能共享本地
   Chroma PersistentClient 目录。

不满足以上约束时后端会拒绝启动，避免任务在另一个副本领取后读不到上传文件，或不同副本
返回不一致的头像和向量索引。后台任务通过 MySQL 租约竞争，同一任务只由持有租约的副本处理。

### 前端 API 地址

Vite 开发代理默认把 `/api` 请求转发到 `http://127.0.0.1:8000`。如果前端不通过该代理访问后端，可设置：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

修改前端环境变量后，需要重新启动 Vite 开发服务器。

## Cookie、CSRF 与跨域访问

登录请求成功后，后端会同时设置两类 Cookie：

| Cookie      | 浏览器脚本是否可读 | 作用                                       |
| ----------- | ------------------ | ------------------------------------------ |
| 登录 Cookie | 否，使用 HttpOnly  | 携带访问令牌，供后端识别当前用户           |
| CSRF Cookie | 是                 | 由前端读取，并在写请求的 CSRF 请求头中回传 |

项目自带前端已经自动处理 Cookie 和 CSRF 请求头。自行开发客户端时，需要同时允许请求携带 Cookie，并在写请求中回传 CSRF Cookie 值。

> [!WARNING]
> 启用 Cookie 认证后，`CORS_ALLOWED_ORIGINS` 不能使用 `*`。生产环境必须填写精确的前端来源。

如果生产环境中的前后端属于不同站点，需要将 `AUTH_COOKIE_SAMESITE` 设为 `none`；浏览器只会在同时启用 `AUTH_COOKIE_SECURE=true` 时接受这种跨站 Cookie 配置。

### 登录问题排查

登录状态无法保存或写请求返回 CSRF 错误时，按顺序检查：

1. 本地 HTTP 是否设置了 `AUTH_COOKIE_SECURE=false`。
2. 浏览器地址是否与 `CORS_ALLOWED_ORIGINS` 中的来源完全一致。
3. 前端请求是否允许携带 Cookie。
4. 写请求是否使用 `CSRF_HEADER_NAME` 指定的请求头回传 CSRF Cookie 值。
5. 修改环境变量后是否已经重启后端或 Vite。

## 模型数据与个人数据生命周期

- 第三方模型授权默认关闭。注册时可明确勾选，登录后也可在“设置 → 个性化 →
  模型与个人数据”中开启或撤回。
- 授权只覆盖生成简历解析、岗位匹配、面试提问与反馈所需的数据。发送前会对姓名、
  邮箱、手机号、证件号、地址和微信等直接标识符进行脱敏。
- 后台任务在实际调用模型前会再次校验当前授权版本；撤回后，尚未开始的新模型任务
  不会继续发送数据。
- 账户数据默认保留到用户主动删除相应记录或注销账户。设置页支持导出 JSON 数据副本；
  注销会校验当前密码，并清理 MySQL 记录、短期记忆、向量索引、头像和简历文件。
- 单独删除简历时，会同时清空历史面试中保存的该简历快照；相关历史反馈仍保留，但不再包含
  原简历结构化内容。
- 如果 Redis 或已启用的向量索引暂时不可用，注销会失败并保留账户数据，避免出现只删除
  一部分数据的假成功；恢复依赖后可重试。

## 数据库初始化与升级

| 使用场景   | 执行命令                               | 说明                       |
| ---------- | -------------------------------------- | -------------------------- |
| 新建环境   | `python backend\scripts\init_db.py`    | 创建基础表并执行全部迁移   |
| 已有数据库 | `python backend\scripts\migrate_v1.py` | 只执行尚未应用的版本化迁移 |

迁移记录保存在 `schema_migrations` 表中，重复执行时会跳过已经完成的版本。执行过程使用 MySQL 命名锁，避免多个后端实例同时修改表结构。

### 生产升级顺序

1. 备份数据库。
2. 在发布阶段运行 `python backend\scripts\migrate_v1.py`。
3. 设置 `AUTO_MIGRATE_ON_STARTUP=false`。
4. 启动应用实例。
5. 请求 `/api/health/ready`，确认数据库、目录和后台任务运行器均已就绪。

> [!NOTE]
> 本地开发默认启用 `AUTO_MIGRATE_ON_STARTUP=true`，启动后端时会自动补齐迁移。

## 健康检查

| 地址                | 用途              | 成功条件                                                |
| ------------------- | ----------------- | ------------------------------------------------------- |
| `/api/health`       | 存活检查          | API 进程可响应时返回 HTTP 200 和 `{"status":"ok"}`      |
| `/api/health/ready` | 服务就绪检查      | 配置、MySQL、上传目录和后台任务运行器等关键检查均未失败 |
| `/api/metrics`      | Prometheus 抓取   | 返回当前进程按路由模板聚合的请求量、状态码和耗时指标    |

PowerShell 中可以这样检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/health/ready
Invoke-WebRequest http://127.0.0.1:8000/api/metrics
```

每个 API 响应都会返回 `X-Request-ID`。客户端可以传入由字母、数字、点、下划线、
冒号或连字符组成且不超过 128 字符的 ID；非法或缺失时服务端会生成新 ID。访问日志
只记录请求 ID、方法、路由模板、状态码和耗时，不记录查询参数、Cookie 或请求体。

`/api/metrics` 使用路由模板作为标签，避免把用户 ID 等路径参数引入高基数指标。
指标保存在单个应用进程内；多实例部署应由 Prometheus 分别抓取并聚合。生产环境建议
在网关层只允许监控网络访问该地址。

### 就绪状态说明

| 状态       | 含义                                               | HTTP 结果 |
| ---------- | -------------------------------------------------- | --------- |
| `ok`       | 当前检查正常                                       | 200       |
| `degraded` | 可选能力未启用或模型密钥未配置，但核心服务仍可运行 | 200       |
| `failed`   | 数据库、目录或后台运行器等关键检查失败             | 503       |

## 质量保障

从项目根目录选择与当前改动匹配的检查：

| 检查范围 | 命令                                                                            | 适用场景                 |
| -------- | ------------------------------------------------------------------------------- | ------------------------ |
| 快速检查 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1`       | 日常开发和小范围修改     |
| 全量检查 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -Full` | 合并前或涉及前后端的修改 |
| 包含 E2E | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -E2E`  | 核心用户流程或发布前验证 |

首次运行 E2E 前，在 `frontend` 目录安装 Chromium：

```powershell
npx playwright install chromium --only-shell
```

GitHub Actions 会继续检查后端测试与类型、前端 lint/格式/类型/构建，以及 OpenAPI contract 是否同步。

## 运行注意事项

> [!CAUTION]
> 不要提交真实 `.env`、模型密钥、数据库凭据、上传文件、缓存或本地测试报告。

- 面试、评估、记忆总结和自主进化可能产生模型调用费用，请根据实际模型配置控制使用。
- Redis 是可选依赖；不可用时系统会从 MySQL 重建短期记忆，但响应时间可能增加。
- 生产环境应使用受限数据库账户，不要让应用账户拥有超出运行和迁移需求的权限。
- 修改环境变量后，需要重启对应的后端或前端进程。

## 生产部署检查清单

- [ ] `APP_ENV=production`
- [ ] 使用独立且足够长的随机 `JWT_SECRET_KEY`
- [ ] 数据库账户权限受限，迁移前已经完成备份
- [ ] 已启用 HTTPS，并保持 `AUTH_COOKIE_SECURE=true`
- [ ] CSRF 防护保持开启
- [ ] CORS 仅允许实际前端域名，没有使用通配符
- [ ] 已在发布阶段显式执行数据库迁移
- [ ] 应用实例使用 `AUTO_MIGRATE_ON_STARTUP=false`
- [ ] 单实例明确使用本地存储；多副本已配置同一共享卷并禁用本地 Chroma
- [ ] `MYSQL_POOL_SIZE × 副本数` 未超过数据库连接额度
- [ ] `.env`、密钥、上传文件、缓存和本地测试报告未进入仓库
- [ ] 已根据实际模型配置评估调用费用
- [ ] 已向用户展示第三方模型数据用途，且授权默认关闭、可撤回
- [ ] 已验证个人数据导出和账户注销流程
- [ ] `/api/health/ready` 没有返回关键检查失败
- [ ] 已运行与本次发布范围匹配的质量检查

---

<p align="center">
  <a href="../README.md">返回项目首页</a> ·
  <a href="#快速开始">回到快速开始</a> ·
  <a href="#生产部署检查清单">查看生产发布清单</a>
</p>

<p align="center">
  <img src=".github/assets/readme-hero.webp" width="100%" alt="一名候选人在 InterviewArena 中接受四位 AI 面试官的多轮模拟面试" />
</p>

<h1 align="center">InterviewArena</h1>

<p align="center">
  <strong>多 Agent 协作、长短期记忆与可观测 Harness 驱动的 AI 面试训练系统</strong>
</p>

<p align="center">
  不止完成一次模拟面试，而是让每轮表现成为下一次训练的上下文、证据与改进起点。
</p>

<p align="center">
  <a href="https://github.com/gyLearnHub/InterviewArena/actions/workflows/quality.yml"><img src="https://img.shields.io/github/actions/workflow/status/gyLearnHub/InterviewArena/quality.yml?branch=master&label=quality&style=flat-square" alt="Quality workflow" /></a>
  <a href="https://github.com/gyLearnHub/InterviewArena/actions/workflows/e2e.yml"><img src="https://img.shields.io/github/actions/workflow/status/gyLearnHub/InterviewArena/e2e.yml?branch=master&label=e2e&style=flat-square" alt="E2E workflow" /></a>
</p>

<p align="center">
  <a href="#核心优势">核心优势</a> ·
  <a href="#长短期记忆">长短期记忆</a> ·
  <a href="#训练闭环">训练闭环</a> ·
  <a href="#产品预览">产品预览</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#数据库升级">数据库升级</a> ·
  <a href="#健康检查">健康检查</a> ·
  <a href="#质量保障">质量保障</a>
</p>

## 核心优势

InterviewArena 的重点不是“接入一个模型然后连续出题”，而是把面试训练拆成可编排、可记忆、可评估、可恢复的完整 Agent 系统。

<table>
  <tr>
    <td width="33%" valign="top">
      <strong>🤝 多 Agent 分工编排</strong><br /><br />
      简历、技术、主管、HR 四类面试官拥有独立提示词、关注维度和结束策略；评估 Agent 与 Skill Runner 参与逐题、逐轮和最终总结，由统一编排器传递上下文。
    </td>
    <td width="33%" valign="top">
      <strong>🧠 分层的长短期记忆</strong><br /><br />
      短期记忆在单场面试中保留最近问答、滚动摘要和已完成轮次；长期记忆沉淀跨场表现与 Agent 经验。两层记忆分别控制时效和检索范围，再共同进入面试上下文。
    </td>
    <td width="33%" valign="top">
      <strong>🛡️ Agent Harness</strong><br /><br />
      Trace、规则校验、结构化输出验证、自动重试、降级和 Checkpoint 贯穿长流程；独立诊断页展示规则通过率、失败节点、重试记录与可恢复状态。
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <strong>📐 证据化多级评估</strong><br /><br />
      单题评价、轮次总结和综合报告三级汇总，保留维度得分、优缺点、建议与证据；报告额外展示评分覆盖率、得分来源和可信度状态。
    </td>
    <td width="33%" valign="top">
      <strong>🔁 可持续训练闭环</strong><br /><br />
      从逐题反馈或最终报告生成复盘收藏，追踪薄弱项练习进度；新的面试再次读取历史记忆，让训练从“重复做题”变成持续修正。
    </td>
    <td width="33%" valign="top">
      <strong>🧪 面试策略自动优化</strong><br /><br />
      系统从历史面试中学习，持续迭代面试官提示词、提问流程和质量规则，让提问针对性、岗位适配度和输出稳定性随训练积累逐步提升。每次迭代都需通过真实与合成样本验证，效果下降时自动回滚。
    </td>
  </tr>
</table>

## 长短期记忆

两层记忆解决的问题不同：短期记忆保证当前面试能够接着聊，长期记忆让下一场训练不必从零开始。系统不会把所有历史记录直接塞进 Prompt，而是按生命周期和使用场景控制上下文。

| 记忆层   | 主要内容                                                                 | 作用                                                   |
| -------- | ------------------------------------------------------------------------ | ------------------------------------------------------ |
| 短期记忆 | 最近问答、滚动摘要、已完成轮次、待追问方向和一致性标记                   | 跨轮承接回答，减少重复提问，及时发现前后矛盾           |
| 长期记忆 | 候选人的优势、薄弱项和表达偏好，以及面试官经验、Agent 经验和训练复盘结果 | 跨场个性化提问，持续追踪能力变化，复用已经验证过的经验 |

生成问题时，系统会结合当前面试的短期上下文和与本轮相关的长期记忆。这样既能接住刚才的回答，也能利用过去训练中已经确认的优势和薄弱项。

## 训练闭环

<p align="center">
  <img src=".github/assets/readme-training-flow.png" width="100%" alt="InterviewArena 从简历解析、岗位策略、短期上下文、多 Agent 面试、证据化评估、长期记忆到专项复盘的训练闭环，Harness 贯穿全流程" />
</p>

系统在单场面试中持续更新短期上下文，结束后再把评估结果沉淀为长期记忆和复盘任务，供下一次训练使用。

## 产品预览

<table>
  <tr>
    <td width="50%" align="center">
      <img src=".github/assets/readme-dashboard.webp" alt="InterviewArena 工作台，展示综合表现、四轮能力、薄弱项和复盘收藏" />
      <br />
      <strong>训练工作台</strong><br />综合表现、四轮能力、薄弱项与复盘任务集中呈现
    </td>
    <td width="50%" align="center">
      <img src=".github/assets/readme-interview.webp" alt="InterviewArena 技术面界面，展示多轮进度、问答和即时评分" />
      <br />
      <strong>多轮模拟面试</strong><br />面试进度、上下文问答、逐题评分和追问方向同步更新
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src=".github/assets/readme-report.webp" alt="InterviewArena 面试复盘报告，展示综合评分和报告可信度" />
      <br />
      <strong>证据化面试复盘</strong><br />综合结论、四轮得分、评分覆盖率和得分来源清晰可查
    </td>
    <td width="50%" align="center">
      <img src=".github/assets/readme-memories.webp" alt="InterviewArena 长期记忆页面，展示薄弱项、优势和回答偏好" />
      <br />
      <strong>长期记忆管理</strong><br />沉淀薄弱项、优势与表达偏好，支持后续个性化训练
    </td>
  </tr>
</table>

> 截图来自当前 Vue 前端的实际页面；其中账户、岗位、评分等数据为演示数据。

## 系统架构

<p align="center">
  <img src=".github/assets/readme-architecture.png" width="100%" alt="InterviewArena 分层系统架构：Vue 3、FastAPI、面试编排器、四类 Agent、评估、技能、Memory RAG、Harness、安全进化以及数据与模型基础设施" />
</p>

### 技术栈

| 层级 | 主要技术                                                             |
| ---- | -------------------------------------------------------------------- |
| 前端 | Vue 3.5、Vue Router 4、TypeScript 6、Vite 6                          |
| 后端 | Python 3.11、FastAPI、Pydantic 2、Uvicorn、PyMySQL、HTTPX            |
| 数据 | MySQL 8+、Redis、本地文件存储、可选 Chroma 与本地 Embedding/Reranker |
| 测试 | pytest、Playwright                                                   |
| 质量 | Ruff、mypy strict、ESLint、Prettier、vue-tsc、Vite build             |
| CI   | GitHub Actions、OpenAPI contract 同步检查                            |

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 20+
- MySQL 8+ 或兼容版本
- 可选：Redis。用于短期记忆缓存；不可用时系统会从 MySQL 重建上下文
- 可访问的 DeepSeek 兼容模型 API
- 可选：处理旧版 `.doc` 文件时需要本机安装 LibreOffice；`.docx` 不需要转换

### 2. 获取代码

```powershell
git clone https://github.com/gyLearnHub/InterviewArena.git
cd InterviewArena
```

### 3. 准备 MySQL

先在 MySQL 中创建数据库：

```sql
CREATE DATABASE interview_arena
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

确保 `DATABASE_URL` 使用的账户对该数据库拥有建表、读写和变更权限。

### 4. 启动后端

以下命令以 PowerShell 为例：

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

初始化表结构并启动 API：

```powershell
python backend\scripts\init_db.py
python backend\main.py
```

后端默认地址：

- API：<http://127.0.0.1:8000/api>
- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

### 5. 启动前端

另开一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 <http://127.0.0.1:5173>，注册账户、上传简历并创建第一场面试。Vite 开发代理会把 `/api` 请求转发到 `http://127.0.0.1:8000`。

> macOS/Linux 用户可将虚拟环境激活命令替换为 `source .venv/bin/activate`，并使用 `cp backend/.env.example backend/.env`。

## 配置说明

完整模板位于 [`backend/.env.example`](backend/.env.example)。常用配置如下：

| 配置项                      | 用途                                | 本地开发建议                                   |
| --------------------------- | ----------------------------------- | ---------------------------------------------- |
| `APP_ENV`                   | 当前运行环境                        | 本地使用 `development`，生产使用 `production`  |
| `DATABASE_URL`              | MySQL 连接地址                      | 指向已创建的 `interview_arena` 数据库          |
| `JWT_SECRET_KEY`            | 登录令牌签名密钥                    | 必须设置，且不少于 32 个字符                   |
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

登录成功后，后端会把访问令牌写入 HttpOnly Cookie，并单独设置 CSRF Cookie。项目自带前端会自动携带 Cookie，并在写请求中回传 CSRF 请求头；自行开发客户端时也需要实现这两步。

本地通过 `http://127.0.0.1` 或 `http://localhost` 开发时必须使用 `AUTH_COOKIE_SECURE=false`。生产环境应使用 HTTPS、设置 `AUTH_COOKIE_SECURE=true`，并将 `CORS_ALLOWED_ORIGINS` 限制为实际前端域名。

如果生产环境中的前后端属于不同站点，还需要将 `AUTH_COOKIE_SAMESITE` 设为 `none`；浏览器只会在同时启用 `AUTH_COOKIE_SECURE=true` 时接受这种跨站 Cookie 配置。

如果前端不通过 Vite 代理访问后端，可设置：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## 数据库升级

新环境使用 `python backend\scripts\init_db.py` 创建基础表并执行全部版本化迁移。已有数据库只需运行：

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

## 质量保障

从项目根目录选择对应的检查方式：

| 检查范围 | 命令                                                                            |
| -------- | ------------------------------------------------------------------------------- |
| 快速检查 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1`       |
| 全量检查 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -Full` |
| 包含 E2E | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -E2E`  |

首次运行 E2E 前，需要在 `frontend` 目录执行 `npx playwright install chromium --only-shell`。

## 运行注意事项

- 不要提交真实 `.env`、模型密钥、数据库凭据、上传文件、缓存或本地测试报告。
- 面试、评估、记忆总结和自主进化可能产生模型调用费用，请根据实际模型配置控制使用。
- 生产环境应使用独立的强随机 `JWT_SECRET_KEY`、受限数据库账户和 HTTPS，并保持 `AUTH_COOKIE_SECURE=true`、CSRF 防护开启以及精确的 CORS 来源白名单。

## 从一次真实练习开始

如果你正在准备技术面试，可以按照 [快速开始](#快速开始) 跑完一场多轮练习。用过之后，欢迎把不自然的提问、评分偏差或缺失的面试场景提交到 [Issues](https://github.com/gyLearnHub/InterviewArena/issues)。真实使用中发现的问题，最能帮助项目继续改进。

觉得 InterviewArena 有用，可以点一个 Star，或者把它分享给同样在准备面试的人。想直接参与开发，也欢迎提交 Pull Request。

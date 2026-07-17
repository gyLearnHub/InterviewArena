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
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Vue-3.5-42B883?style=flat-square&logo=vuedotjs&logoColor=white" alt="Vue 3.5" />
  <img src="https://img.shields.io/badge/FastAPI-0.136-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI 0.136" />
  <img src="https://img.shields.io/badge/MySQL-8%2B-4479A1?style=flat-square&logo=mysql&logoColor=white" alt="MySQL 8+" />
</p>

<p align="center">
  <a href="#核心优势">核心优势</a> ·
  <a href="#长短期记忆">长短期记忆</a> ·
  <a href="#训练闭环">训练闭环</a> ·
  <a href="#产品预览">产品预览</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#快速开始">快速开始</a> ·
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
      <strong>🧪 有安全门的自主进化</strong><br /><br />
      可选实验链路结合真实与合成样本、影子评估、Hard Gates、多轮裁判和观察窗口；质量下降时支持回滚，且默认关闭以避免意外模型调用。
    </td>
  </tr>
</table>

### 不是装饰性的“智能化”

- **动态提问策略**：结合短期问答、历史记忆、核心主题覆盖、简历项目轮换和剩余时间决定主问题、追问与结束时机，并避免重复问题。
- **任务化与中断恢复**：简历解析、面试操作、短期记忆同步、长期记忆总结和自主进化都有明确状态；回答草稿、心跳、互斥锁、重试与 Checkpoint 降低长流程中断损失。
- **从训练到运营的完整视图**：工作台、历史详情、通知、复盘收藏、长期记忆和 Harness 状态页共同覆盖训练与运行诊断。
- **工程契约与质量门禁**：FastAPI OpenAPI 自动生成前端 TypeScript Contract，并通过 Ruff、mypy、pytest、ESLint、Prettier、vue-tsc、Vite Build 与 Playwright 持续校验。

## 长短期记忆

两层记忆解决的问题不同：短期记忆保证当前面试能够接着聊，长期记忆让下一场训练不必从零开始。系统不会把所有历史记录直接塞进 Prompt，而是按生命周期和使用场景控制上下文。

| 记忆层   | 保存内容                                                                 | 生命周期与存储                                                                | 直接收益                                                   |
| -------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 短期记忆 | 最近问答、滚动摘要、已完成轮次、待追问方向、一致性标记和相关证据         | Redis 按用户和面试隔离，支持 TTL、版本校验和 Token 预算压缩；MySQL 是重建来源 | 跨轮承接回答，减少重复提问，及时发现前后矛盾               |
| 长期记忆 | 候选人的优势、薄弱项和表达偏好，以及面试官经验、Agent 经验和训练复盘结果 | MySQL 持久化，默认支持 BM25，可选 Chroma、Embedding 与 Reranker               | 跨场个性化提问，持续追踪能力变化，复用已经验证过的面试经验 |

生成问题时，系统会同时使用当前面试的短期快照和按场景检索出的长期记忆。最近回答保留必要原文，较早内容压成滚动摘要，跨场信息只取相关条目，因此上下文更集中，Token 消耗也更可控。Redis 不可用时，短期记忆会从 MySQL 重建并进入降级状态；面试结束后，临时快照被清理，值得保留的结果再异步沉淀为长期记忆。

## 训练闭环

<p align="center">
  <img src=".github/assets/readme-training-flow.png" width="100%" alt="InterviewArena 从简历解析、岗位策略、短期上下文、多 Agent 面试、证据化评估、长期记忆到专项复盘的训练闭环，Harness 贯穿全流程" />
</p>

1. **建立上下文**：异步解析 `.doc` / `.docx` 简历，结合目标岗位、难度、时长和长期记忆形成面试策略。
2. **多 Agent 推进**：四类面试官按轮次分工，短期记忆持续汇总最近问答和已完成轮次；每次回答即时进入结构化评估。
3. **让结果继续产生价值**：综合报告沉淀为长期记忆、薄弱项与复盘收藏，再回流到下一场面试，形成持续训练循环。

> Harness 不是流程末尾的日志模块，而是覆盖提问、评估、记忆与任务执行的可靠性底座。

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

- **主请求链路**：Vue 3 SPA 通过带 Cookie Auth 与 CSRF 防护的 FastAPI API 进入面试编排器。
- **智能编排层**：四类面试 Agent、Evaluation、Skill Runner 与 Memory RAG 共享受控上下文，但保持职责与输出契约独立。
- **可靠性层**：Harness 包围智能链路，统一记录 Trace、规则、结构验证、重试、降级和 Checkpoint；运行状态可在前端独立查看。
- **记忆与数据层**：Redis 保存单场面试的短期快照，MySQL 保存业务数据和可重建来源；长期记忆默认使用 BM25，并可选接入 Chroma、本地 Embedding 与 Reranker。
- **安全进化旁路**：自主进化不进入默认请求路径，候选策略必须经过合成样本、影子评估、Hard Gates 和观察窗口后才能激活。

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
DATABASE_URL=mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/interview_arena?charset=utf8mb4
JWT_SECRET_KEY=replace_with_a_random_secret_of_at_least_32_characters
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=your_available_model
AUTH_COOKIE_SECURE=false
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

| 配置项                               | 用途                             | 本地开发建议                            |
| ------------------------------------ | -------------------------------- | --------------------------------------- |
| `DATABASE_URL`                       | MySQL 连接地址                   | 指向已创建的 `interview_arena` 数据库   |
| `JWT_SECRET_KEY`                     | 登录令牌签名密钥                 | 必须设置，且不少于 32 个字符            |
| `DEEPSEEK_API_KEY`                   | 模型 API 密钥                    | 使用面试与评估能力时必须配置            |
| `DEEPSEEK_BASE_URL`                  | DeepSeek 兼容 API 地址           | 默认 `https://api.deepseek.com`         |
| `DEEPSEEK_MODEL`                     | 实际调用的模型名称               | 填写当前账户可用模型                    |
| `AUTH_COOKIE_SECURE`                 | 是否仅通过 HTTPS 发送认证 Cookie | 本地 HTTP 使用 `false`，生产使用 `true` |
| `CORS_ALLOWED_ORIGINS`               | 允许携带凭据的前端来源           | 默认包含本地 Vite 地址                  |
| `AUTO_MIGRATE_ON_STARTUP`            | 后端启动时是否执行迁移           | 本地可保持 `true`，生产建议 `false`     |
| `MEMORY_ENABLED_DEFAULT`             | 新用户是否默认启用长期记忆       | 默认 `true`                             |
| `REDIS_URL`                          | 短期记忆 Redis 连接地址          | 默认 `redis://127.0.0.1:6379/0`         |
| `SHORT_MEMORY_TTL_SECONDS`           | 短期记忆过期时间                 | 默认 `604800`，即 7 天                  |
| `SHORT_MEMORY_RECENT_QA_LIMIT`       | 短期记忆保留的最近问答数量       | 默认 `5`                                |
| `SHORT_MEMORY_TOKEN_BUDGET`          | 短期记忆上下文 Token 预算        | 默认 `8000`                             |
| `SHORT_MEMORY_REDIS_TIMEOUT_SECONDS` | Redis 读写超时                   | 默认 `1` 秒，超时后从 MySQL 降级重建    |
| `CHROMA_ENABLED`                     | 是否尝试启用 Chroma 向量索引     | 默认 `false`                            |
| `EMBEDDING_MODEL_PATH`               | 可选本地嵌入模型路径             | 不使用本地模型时留空                    |
| `RERANKER_MODEL_PATH`                | 可选本地重排模型路径             | 不使用本地模型时留空                    |
| `EVOLUTION_ENABLED`                  | 是否启用自主进化任务             | 默认 `false`                            |

如果前端不通过 Vite 代理访问后端，可设置：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## 质量保障

### 一键质量检查

从项目根目录运行快速检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1
```

快速模式会完成 OpenAPI/TypeScript contract 生成、变更后端文件的 Ruff 检查、快速后端测试，以及前端 lint、格式、类型和构建检查。

全量检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -Full
```

全量模式包括：

- `ruff check backend`
- `mypy` strict
- 全部 `pytest backend/tests`
- `npm run lint`
- `npm run format:check`
- `npm run typecheck`
- `npm run build`

### E2E 测试

前端 E2E 使用 Playwright，并通过 API mock 验证关键页面流程，因此不需要启动真实后端或 MySQL。

首次运行时安装 Chromium：

```powershell
cd frontend
npx playwright install chromium --only-shell
npm run test:e2e
```

也可以从根目录运行包含 E2E 的完整本地门禁：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -E2E
```

### API Contract

只重新生成 FastAPI OpenAPI 和前端 TypeScript contract：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\generate-openapi.ps1
```

生成物位于 `frontend/src/generated/`。CI 会检查生成物是否与后端路由保持一致。

## 目录结构

```text
InterviewArena/
├─ backend/
│  ├─ app/
│  │  ├─ agents/                 四类面试官与综合评估 Agent
│  │  ├─ api/                    FastAPI 路由
│  │  ├─ autonomous_evolution/   自主进化实验流程
│  │  ├─ harness/                Trace、规则、校验与恢复
│  │  ├─ repositories/           MySQL 数据访问
│  │  ├─ services/               面试、评估、记忆与文件服务
│  │  └─ skills/                 Agent 技能目录与执行器
│  ├─ scripts/                   初始化、迁移与 OpenAPI 导出
│  └─ tests/                     后端测试
├─ database/                     MySQL 初始化 SQL
├─ frontend/
│  ├─ e2e/                       Playwright E2E
│  └─ src/
│     ├─ assets/                 产品插画与图标
│     ├─ generated/              OpenAPI 与 TypeScript contract
│     ├─ router/                 前端路由
│     └─ views/                  工作台、面试、复盘、记忆等页面
├─ scripts/                      根目录质量检查与生成脚本
├─ .github/workflows/            Quality 与 E2E CI
└─ pyproject.toml                pytest、mypy 与 Ruff 配置
```

## 运行注意事项

- 不要提交真实 `.env`、模型密钥、数据库凭据、上传文件、缓存或本地测试报告。
- `.doc` 简历需要 LibreOffice 转换为 `.docx`；无法安装 LibreOffice 时请直接上传 `.docx`。
- 面试、评估、记忆总结和自主进化都可能产生模型调用费用，请根据实际模型配置控制使用。
- 自主进化默认关闭；确认调用成本、观察窗口和回滚策略后再设置 `EVOLUTION_ENABLED=true`。
- 本地默认允许后端启动时执行迁移；生产环境建议在发布阶段显式迁移，并设置 `AUTO_MIGRATE_ON_STARTUP=false`。
- 生产环境必须使用独立强随机 `JWT_SECRET_KEY`、受限数据库账户、HTTPS，并保持 `AUTH_COOKIE_SECURE=true`。

## 从一次真实练习开始

如果你正在准备技术面试，可以按照 [快速开始](#快速开始) 跑完一场多轮练习。用过之后，欢迎把不自然的提问、评分偏差或缺失的面试场景提交到 [Issues](https://github.com/gyLearnHub/InterviewArena/issues)。真实使用中发现的问题，最能帮助项目继续改进。

觉得 InterviewArena 有用，可以点一个 Star，或者把它分享给同样在准备面试的人。想直接参与开发，也欢迎提交 Pull Request。

---

<p align="center">
  让每一轮模拟面试都留下可以继续训练的证据。
</p>

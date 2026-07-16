<p align="center">
  <img src=".github/assets/readme-hero.webp" width="100%" alt="一名候选人在 InterviewArena 中接受四位 AI 面试官的多轮模拟面试" />
</p>

<h1 align="center">InterviewArena</h1>

<p align="center">
  <strong>由四位 AI 面试官驱动的多轮模拟面试训练平台</strong>
</p>

<p align="center">
  从简历深挖、技术面、主管面到 HR 面，用逐题反馈、长期记忆与专项复盘形成持续训练闭环。
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
  <a href="#产品预览">产品预览</a> ·
  <a href="#训练流程">训练流程</a> ·
  <a href="#核心能力">核心能力</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#质量保障">质量保障</a>
</p>

## 项目简介

InterviewArena 是一个前后端分离的 AI 面试练习系统。它不只负责“出题”，而是围绕一次完整面试训练持续工作：解析候选人简历，组织多轮面试，给出逐题评分和追问建议，生成带证据覆盖说明的综合报告，再把长期薄弱项沉淀为可检索记忆与复盘任务。

系统内置四类面试官：

| 轮次   | 关注重点                         | 代表色 |
| ------ | -------------------------------- | ------ |
| 简历面 | 项目真实性、个人贡献、经历完整度 | 蓝色   |
| 技术面 | 技术基础、方案设计、工程取舍     | 紫色   |
| 主管面 | 协作推动、问题处理、管理潜力     | 橙色   |
| HR 面  | 求职动机、职业规划、岗位匹配     | 粉色   |

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

## 训练流程

```mermaid
flowchart LR
    A["上传并解析简历"] --> B["配置岗位与面试策略"]
    B --> C["简历面"]
    C --> D["技术面"]
    D --> E["主管面"]
    E --> F["HR 面"]
    F --> G["综合评估"]
    G --> H["记忆沉淀"]
    H --> I["薄弱项复盘与专项再练"]
```

1. 上传 `.doc` 或 `.docx` 简历，系统异步解析结构化经历与项目。
2. 选择目标岗位、求职目标、难度、时长和面试轮次。
3. AI 面试官根据简历、岗位信息和历史记忆进行提问与追问。
4. 每次回答都会得到维度评分、优势、不足、证据和下一步建议。
5. 完成后生成四轮评分、能力画像、综合结论和报告可信度说明。
6. 薄弱项、优势和回答偏好进入长期记忆，可继续生成复盘收藏或专项训练。

## 核心能力

### 面试训练

- **四类面试官协作**：简历、技术、主管与 HR 面试官分别使用独立提示词、轮次策略和评价标准。
- **动态追问**：根据当前回答的证据完整度和评分结果决定追问方向。
- **逐题即时反馈**：展示维度得分、做得好的地方、优先改进项和建议回答方向。
- **中断恢复**：回答草稿、任务心跳、重试与检查点机制用于降低长流程中断带来的损失。

### 评估与成长

- **综合面试报告**：汇总四轮表现、优势、不足、改进建议、岗位匹配和录用建议。
- **报告可信度**：展示完成轮次、有效回答、逐题评分覆盖率与各轮得分来源。
- **长期候选人记忆**：沉淀稳定优势、重复薄弱项和回答偏好，并支持状态与索引管理。
- **复盘训练闭环**：从逐题评价或综合报告生成复盘收藏，再围绕薄弱项开启专项面试。

### 工程与运行

- **前后端 API Contract**：FastAPI OpenAPI 自动导出为前端 TypeScript contract，并在 CI 中校验同步状态。
- **任务化长流程**：简历解析、面试操作、记忆处理和自主进化均有独立任务状态与恢复逻辑。
- **运行诊断 Harness**：记录执行 Trace、规则校验、重试、降级和检查点，便于定位 Agent 流程问题。
- **自主进化实验**：支持合成样本、影子评估和观察窗口；该能力默认关闭，避免意外产生额外模型调用。

## 系统架构

```mermaid
flowchart TB
    Browser["浏览器"] --> Vue["Vue 3 + Vite SPA"]
    Vue -->|"/api · Cookie Auth · CSRF"| FastAPI["FastAPI API"]

    subgraph Backend["后端领域模块"]
        FastAPI --> Auth["认证与用户偏好"]
        FastAPI --> Resume["简历解析与管理"]
        FastAPI --> Interview["多轮面试编排"]
        FastAPI --> Evaluation["逐题与综合评估"]
        FastAPI --> Memory["记忆检索与生命周期"]
        FastAPI --> Dashboard["工作台、历史、通知与复盘"]
        Interview --> Agents["简历 / 技术 / 主管 / HR Agents"]
        Interview --> Harness["Trace · 规则 · 重试 · 检查点"]
    end

    Resume --> Files["本地简历与头像文件"]
    Auth --> MySQL[("MySQL")]
    Resume --> MySQL
    Interview --> MySQL
    Evaluation --> MySQL
    Memory --> MySQL
    Dashboard --> MySQL

    Resume --> LLM["DeepSeek 兼容 API"]
    Agents --> LLM
    Evaluation --> LLM
    Memory --> LLM
    Memory -.->|可选向量索引| Chroma[("Chroma")]
    Memory -.->|可选本地模型| LocalModels["Embedding / Reranker"]
```

### 技术栈

| 层级 | 主要技术                                                      |
| ---- | ------------------------------------------------------------- |
| 前端 | Vue 3.5、Vue Router 4、TypeScript 6、Vite 6                   |
| 后端 | Python 3.11、FastAPI、Pydantic 2、Uvicorn、PyMySQL、HTTPX     |
| 数据 | MySQL 8+、本地文件存储、可选 Chroma 与本地 Embedding/Reranker |
| 测试 | pytest、Playwright                                            |
| 质量 | Ruff、mypy strict、ESLint、Prettier、vue-tsc、Vite build      |
| CI   | GitHub Actions、OpenAPI contract 同步检查                     |

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 20+
- MySQL 8+ 或兼容版本
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

| 配置项                    | 用途                             | 本地开发建议                            |
| ------------------------- | -------------------------------- | --------------------------------------- |
| `DATABASE_URL`            | MySQL 连接地址                   | 指向已创建的 `interview_arena` 数据库   |
| `JWT_SECRET_KEY`          | 登录令牌签名密钥                 | 必须设置，且不少于 32 个字符            |
| `DEEPSEEK_API_KEY`        | 模型 API 密钥                    | 使用面试与评估能力时必须配置            |
| `DEEPSEEK_BASE_URL`       | DeepSeek 兼容 API 地址           | 默认 `https://api.deepseek.com`         |
| `DEEPSEEK_MODEL`          | 实际调用的模型名称               | 填写当前账户可用模型                    |
| `AUTH_COOKIE_SECURE`      | 是否仅通过 HTTPS 发送认证 Cookie | 本地 HTTP 使用 `false`，生产使用 `true` |
| `CORS_ALLOWED_ORIGINS`    | 允许携带凭据的前端来源           | 默认包含本地 Vite 地址                  |
| `AUTO_MIGRATE_ON_STARTUP` | 后端启动时是否执行迁移           | 本地可保持 `true`，生产建议 `false`     |
| `MEMORY_ENABLED_DEFAULT`  | 新用户是否默认启用长期记忆       | 默认 `true`                             |
| `CHROMA_ENABLED`          | 是否尝试启用 Chroma 向量索引     | 默认 `false`                            |
| `EMBEDDING_MODEL_PATH`    | 可选本地嵌入模型路径             | 不使用本地模型时留空                    |
| `RERANKER_MODEL_PATH`     | 可选本地重排模型路径             | 不使用本地模型时留空                    |
| `EVOLUTION_ENABLED`       | 是否启用自主进化任务             | 默认 `false`                            |

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

---

<p align="center">
  让每一轮模拟面试都留下可以继续训练的证据。
</p>

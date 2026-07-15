# InterviewArena

InterviewArena 是一个前后端分离的 AI 多轮面试练习项目。后端使用 FastAPI + MySQL，前端使用 Vue 3 + Vite，支持简历上传解析、多轮面试、历史记录、通知、记忆检索、质量追踪和运行诊断能力。

## 技术栈

- 后端：Python 3.11、FastAPI、Pydantic、PyMySQL、python-docx
- 前端：Vue 3、Vue Router、Vite
- 数据库：MySQL，初始化脚本在 `database/init_mysql.sql`
- 质量检查：ruff、mypy、pytest、ESLint、Prettier、vue-tsc、Vite build、Playwright
- CI：GitHub Actions，配置在 `.github/workflows/quality.yml` 和 `.github/workflows/e2e.yml`

## 目录结构

```text
backend/                 FastAPI 后端、业务服务、仓储、测试和脚本
database/                MySQL 初始化 SQL
frontend/                Vue/Vite 前端
scripts/                 本地质量检查和 OpenAPI 生成脚本
pyproject.toml           Python 测试、类型检查和 lint 配置
```

## 环境要求

- Python 3.11+
- Node.js 20+
- MySQL 8+ 或兼容版本

## 后端启动

1. 安装依赖：

```powershell
python -m pip install -r backend\requirements-dev.txt
```

生产环境只需要运行依赖时可以安装：

```powershell
python -m pip install -r backend\requirements.txt
```

2. 创建环境变量文件：

```powershell
Copy-Item backend\.env.example backend\.env
```

至少需要调整 `DATABASE_URL`、`JWT_SECRET_KEY`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。本地 HTTP 开发通常保持 `AUTH_COOKIE_SECURE=false`。

3. 初始化数据库：

```powershell
python backend\scripts\init_db.py
```

4. 启动 API：

```powershell
python backend\main.py
```

默认地址是 `http://127.0.0.1:8000`，接口前缀是 `/api`。

## 前端启动

```powershell
cd frontend
npm ci
npm run dev
```

Vite 默认运行在 `http://127.0.0.1:5173`，开发代理会把 `/api` 转发到 `http://127.0.0.1:8000`。如果前后端不在同一代理下运行，可以设置 `VITE_API_BASE_URL`。

## 常用质量检查

从项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1
```

默认模式会生成 OpenAPI/前端 API contract、对变更的后端 Python 文件跑 ruff、跑一组快速后端测试，并对前端执行 lint、格式检查、typecheck 和构建。

全量检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -Full
```

全量模式会跑 `ruff check backend`、`mypy`、全部 `pytest backend/tests`、前端 lint、格式检查、typecheck 和前端构建。

只重新生成 OpenAPI/TypeScript contract：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\generate-openapi.ps1
```

生成物位于 `frontend/src/generated/`。

## E2E 测试

前端 E2E 使用 Playwright。当前用例会 mock `/api` 请求，主要验证前端页面流程，不需要启动真实后端或 MySQL。

首次运行或本机缺少浏览器时，先安装 Chromium：

```powershell
cd frontend
npx playwright install chromium --only-shell
```

单独运行 E2E：

```powershell
cd frontend
npm run test:e2e
```

从项目根目录运行包含 E2E 的完整本地门禁：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -E2E
```

默认 `scripts\quality.ps1` 不跑 E2E，适合日常快速检查；修改关键前端流程、E2E 用例或准备发布前再跑 `-E2E`。

## CI

GitHub Actions 会在 push 到 `main`/`master` 或创建 PR 时运行：

- 后端：安装 `backend/requirements-dev.txt`，验证 OpenAPI contract，同步检查 ruff、mypy、pytest
- 前端：`npm ci` 后执行 `npm run lint`、`npm run format:check`、`npm run typecheck` 和 `npm run build`

E2E 工作流位于 `.github/workflows/e2e.yml`。它可以在 GitHub Actions 页面手动触发，也会在 PR 修改前端源码、E2E 用例、Playwright 配置或前端依赖时运行。工作流会安装 Playwright Chromium，失败或取消以外的运行会上传 `playwright-report` 和 `test-results` 方便排查。

## 注意事项

- 不要提交真实 `.env`、上传文件、构建产物、缓存目录或本地测试报告；这些已经在 `.gitignore` 中忽略。
- `backend/requirements.txt` 是运行依赖，`backend/requirements-dev.txt` 是开发和测试依赖。
- 自主进化默认关闭；确认模型调用成本和运行策略后，可设置 `EVOLUTION_ENABLED=true` 启用。
- 本地默认在后端启动时执行迁移，测试环境会跳过；生产环境建议在发布流程中显式执行迁移，并设置 `AUTO_MIGRATE_ON_STARTUP=false`。
- 发布前应在生产环境配置独立的 `JWT_SECRET_KEY`、数据库凭据和模型 API 密钥，并保持 `AUTH_COOKIE_SECURE=true`。

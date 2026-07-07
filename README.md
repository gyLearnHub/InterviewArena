# InterviewArena

InterviewArena 是一个前后端分离的 AI 多轮面试练习项目。后端使用 FastAPI + MySQL，前端使用 Vue 3 + Vite，支持简历上传解析、多轮面试、历史记录、通知、记忆检索、质量追踪和演进/回放相关能力。

## 技术栈

- 后端：Python 3.11、FastAPI、Pydantic、PyMySQL、python-docx
- 前端：Vue 3、Vue Router、Vite
- 数据库：MySQL，初始化脚本在 `database/init_mysql.sql`
- 质量检查：ruff、mypy、pytest、vue-tsc、Vite build
- CI：GitHub Actions，配置在 `.github/workflows/quality.yml`

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

默认模式会生成 OpenAPI/前端 API contract、对变更的后端 Python 文件跑 ruff、跑一组快速后端测试，并对前端执行 typecheck 和构建。

全量检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quality.ps1 -Full
```

全量模式会跑 `ruff check backend`、`mypy`、全部 `pytest backend/tests`、前端 typecheck 和前端构建。

只重新生成 OpenAPI/TypeScript contract：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\generate-openapi.ps1
```

生成物位于 `frontend/src/generated/`。

## CI

GitHub Actions 会在 push 到 `main`/`master` 或创建 PR 时运行：

- 后端：安装 `backend/requirements-dev.txt`，验证 OpenAPI contract，同步检查 ruff、mypy、pytest
- 前端：`npm ci` 后执行 `npm run typecheck` 和 `npm run build`

## 注意事项

- 不要提交真实 `.env`、上传文件、构建产物、缓存目录或本地测试报告；这些已经在 `.gitignore` 中忽略。
- `backend/requirements.txt` 是运行依赖，`backend/requirements-dev.txt` 是开发和测试依赖。
- 后端启动时会按配置执行迁移；测试环境会跳过启动迁移。
- 前端构建输出里有多张较大的 PNG，首屏性能优化可以作为后续任务处理。

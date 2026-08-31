# StudyFlow Memory

反馈记忆驱动的课程学习恢复 Agent。面向高校学生重复性课程学习场景，把用户每一次反馈（时长偏好、讲解偏好、知识薄弱点、恢复经验、复习节奏）沉淀为**可检索、可确认、可撤销、可复用**的结构化学习记忆，在后续相似任务中自动检索并复用，实现「越用越适配」的个性化学习体验。

- 后端：FastAPI + Agent（OpenAI 兼容 Tool Calling）+ 反馈记忆子系统 + SQLite
- 前端：Vue 3 + TypeScript + Vite
- 部署：Docker Compose + Nginx

---

## 目录

- [主要技术栈](#主要技术栈)
- [目录结构](#目录结构)
- [环境配置](#环境配置)
- [本地运行](#本地运行)
- [Docker 部署](#docker-部署)
- [接口概览](#接口概览)
- [测试与评测](#测试与评测)
- [文档索引](#文档索引)

---

## 主要技术栈

### 后端（`backend/`，Python ≥ 3.11）

| 模块         | 技术                                        | 说明                                                         |
| ------------ | ------------------------------------------- | ------------------------------------------------------------ |
| Web 框架     | FastAPI + Uvicorn                           | 异步 Web 服务，自动生成 Swagger 文档                         |
| 数据校验     | Pydantic v2（`pydantic-settings`）          | 请求/响应 Schema 与 `.env` 配置加载                          |
| ORM / 数据库 | SQLAlchemy 2.0 + SQLite                     | 数据持久化，默认库文件 `data/studyflow.db`                   |
| 迁移         | Alembic（已配置）                           | 配置见 `backend/alembic.ini`；当前建表通过 `Base.metadata.create_all()` 完成 |
| LLM 接入     | OpenAI 兼容 Chat Completions + Tool Calling | 通过 `infrastructure/llm/` 适配，业务层不绑定具体供应商      |
| HTTP 客户端  | httpx                                       | 调用模型服务                                                 |
| 测试         | pytest                                      | 99 个后端测试                                                |

### 前端（`frontend/`）

| 模块 | 技术                                              |
| ---- | ------------------------------------------------- |
| 框架 | Vue 3 + TypeScript                                |
| 构建 | Vite                                              |
| 依赖 | `vue-router`、`pinia`（已在 `package.json` 声明） |

### 部署

- Docker + Docker Compose（后端与前端两个服务）
- Nginx 托管前端构建产物

---

## 目录结构

```text
studyflow-memory-jingwei-main/
├─ README.md
├─ .env.example                环境变量模板
├─ docker-compose.yml          容器编排
│
├─ backend/                    FastAPI 后端
│  ├─ pyproject.toml           Python 依赖与打包配置
│  ├─ alembic.ini              Alembic 配置
│  ├─ mock_server.py           本地开发启动入口（uvicorn）
│  ├─ app/
│  │  ├─ main.py               FastAPI 应用入口（路由注册、CORS、异常处理）
│  │  ├─ api/                  HTTP 接口层（routes/ + dependencies.py）
│  │  ├─ agents/               Agent 编排（orchestrator.py）、5 个工具、提示词
│  │  ├─ memory/               记忆子系统（retriever / ranker / writer / policy / extractor / review_schedule）
│  │  ├─ domain/               领域实体、值对象、仓储接口
│  │  ├─ application/          用例层（use_cases/）
│  │  ├─ infrastructure/       database / models / repositories / llm / telemetry
│  │  ├─ schemas/              API 输入输出模型
│  │  └─ evaluation/           评测场景与指标
│  └─ tests/                   unit/ 与 integration/ 测试
│
├─ frontend/                   Vue 3 前端
│  ├─ package.json
│  ├─ vite.config.ts
│  └─ src/
│     ├─ main.ts               应用入口
│     ├─ App.vue               根组件
│     ├─ views/                页面（Today / Understanding / Recovery / MemoryCenter / Evaluation）
│     ├─ components/           可复用组件（TaskCard / MemoryCard / MemoryReference 等）
│     └─ services/             后端 API 封装（api / agent / memories / evaluation）
│
├─ data/                       SQLite 数据文件与种子数据
├─ scripts/                    评测与数据脚本（run_evaluation / bench_* / user_testing 等）
├─ infra/                      Dockerfile 与 Nginx 配置
└─ docs/                       项目文档（接口、架构、评测等）
```

---

## 环境配置

### 后端 `.env`

复制 `.env.example` 为 `.env`，按需填写：

```env
APP_ENV=development
DATABASE_URL=sqlite:///../data/studyflow.db
LLM_BASE_URL=https://api.openai-next.com/v1
LLM_API_KEY=
LLM_MODEL=gemini-3.7-flash
LLM_MAX_RETRIES=2
REQUEST_TIMEOUT_SECONDS=120
```

各字段说明：

| 变量                      | 必填 | 默认值                         | 说明                                                         |
| ------------------------- | ---- | ------------------------------ | ------------------------------------------------------------ |
| `LLM_BASE_URL`            | 是   | 无                             | OpenAI 兼容接口地址；未带 `/v1` 时后端会自动补上 `/v1`       |
| `LLM_API_KEY`             | 是   | 无                             | 模型密钥。缺失时接口明确返回 `503 model_not_configured`，不会静默降级为规则结果 |
| `LLM_MODEL`               | 否   | `gpt-5.6-terra`（代码内默认）  | 模型名。`.env.example` 推荐 `gemini-3.7-flash`               |
| `LLM_MAX_RETRIES`         | 否   | `2`                            | 429 / 502 / 503 / 504 / 超时 / 网络错误的供应商重试次数      |
| `REQUEST_TIMEOUT_SECONDS` | 否   | `120`                          | 单次模型请求超时（秒），覆盖工具调用 + 最终结构化输出的慢响应 |
| `DATABASE_URL`            | 否   | 项目根目录 `data/studyflow.db` | 数据库连接串。未设置时由 `config.py` 依据 `PROJECT_ROOT` 自动生成绝对路径；`.env.example` 示例为 `sqlite:///../data/studyflow.db`（相对 `backend/` 解析到同一文件）。Docker 内固定为 `sqlite:////app/data/studyflow.db` |
| `APP_ENV`                 | 否   | 无                             | 环境标记，当前未参与业务逻辑                                 |

> 密钥仅保存在本地 `.env`，已写入 `.gitignore`，请勿提交到仓库。

### 前端环境变量

前端通过 `VITE_API_BASE_URL` 指定后端地址，未设置时默认 `http://localhost:8000`（见 `frontend/src/services/api.ts`）。

---

## 本地运行

### 0. 前置依赖

- Python ≥ 3.11
- Node.js ≥ 18（推荐 20+）与 npm

### 1. 启动后端

```bash
cd backend
python -m venv .venv
# Windows（PowerShell）
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -e .
python mock_server.py
```

`mock_server.py` 是本地开发入口，等价于 `uvicorn app.main:app --host 127.0.0.1 --port 8000`。启动后：

- 健康检查：`http://127.0.0.1:8000/health` → `{"status":"ok"}`
- Swagger 文档：`http://127.0.0.1:8000/docs`

> 不使用 `mock_server.py` 也可以直接运行 `uvicorn app.main:app --reload`（需在 `backend/` 目录下）。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认地址 `http://localhost:5173`。后端已配置 CORS，允许 `localhost:5173` / `127.0.0.1:5173` 及预览地址 `4173` 访问。

### 3. 验证

在 Swagger 或前端提交一个计划请求（示例见 `docs/api.md`），确认 `/agent/plan` 返回任务与记忆引用。

---

## Docker 部署

### 一键启动

```bash
docker compose up --build
```

启动后：

| 服务          | 容器端口 | 宿主机访问                                 |
| ------------- | -------- | ------------------------------------------ |
| 后端 API      | 8000     | `http://localhost:8000`（Swagger `/docs`） |
| 前端（Nginx） | 80       | `http://localhost:5173`                    |

### 说明

- **后端镜像**（`infra/Dockerfile.backend`）：基于 `python:3.11-slim`，`pip install .` 安装依赖，`uvicorn app.main:app` 启动，端口 8000。

- **前端镜像**（`infra/Dockerfile.frontend`）：多阶段构建，`npm install && npm run build` 后用 Nginx 托管 `dist/`。

- **数据持久化**：`docker-compose.yml` 将宿主机 `data/` 挂载到容器 `/app/data/`，数据库文件 `studyflow.db` 不会随容器销毁丢失。

- **健康检查**：后端服务配置了 `/health` 探针（10s 间隔，5 次重试）。

- **PyPI 镜像**：后端构建默认使用清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple`，可在构建前通过环境变量覆盖：

  ```bash
  export PIP_INDEX_URL="https://pypi.org/simple"   # Linux/macOS
  $env:PIP_INDEX_URL = "https://pypi.org/simple"   # PowerShell
  docker compose build backend
  ```

---

## 接口概览

后端共开放 12 个接口，完整字段与示例见 [`docs/api.md`](docs/api.md)。

| 方法   | 路径                    | 用途                                  |
| ------ | ----------------------- | ------------------------------------- |
| GET    | `/health`               | 服务健康检查                          |
| POST   | `/agent/plan`           | 生成/调整学习计划                     |
| POST   | `/agent/check`          | 复述—关联—迁移三级理解检验            |
| POST   | `/agent/recover`        | 按阻塞类型生成恢复动作                |
| POST   | `/feedback`             | 提交反馈并沉淀 confirmed/pending 记忆 |
| POST   | `/memories`             | 创建记忆                              |
| GET    | `/memories`             | 按用户/课程/知识点等过滤记忆          |
| GET    | `/memories/{memory_id}` | 查看单条记忆                          |
| PATCH  | `/memories/{memory_id}` | 确认/拒绝/修改/撤销记忆               |
| DELETE | `/memories/{memory_id}` | 软删除记忆（保留审计记录）            |
| POST   | `/evaluation/compare`   | 有记忆/无记忆计划对照                 |
| GET    | `/metrics`              | Token、延迟与记忆引用汇总             |

---

## 测试与评测

### 后端测试

```bash
cd backend
pip install -e .
pytest
```

共 99 个测试，位于 `backend/tests/unit/` 与 `backend/tests/integration/`。单元测试使用 `httpx.MockTransport` 注入假模型适配器，不消耗真实模型额度。

### 评测脚本

| 脚本                               | 用途                                          |
| ---------------------------------- | --------------------------------------------- |
| `scripts/run_evaluation.py`        | 有/无记忆对照评测（支持 `--mock` 零依赖跑通） |
| `scripts/bench_cost_comparison.py` | 记忆注入 vs 完整历史注入的 Token 成本对照     |
| `scripts/bench_sqlite_latency.py`  | 100 / 1000 / 5000 条记忆下的检索延迟基准      |
| `scripts/user_testing.py`          | 真实用户测试                                  |

详细评测方法见 [`docs/evaluation.md`](docs/evaluation.md)。

---

## 文档索引

| 文档                                                     | 内容                                           |
| -------------------------------------------------------- | ---------------------------------------------- |
| [`docs/api.md`](docs/api.md)                             | 接口详情、模型调用流程、失败响应、记忆引用规则 |
| [`docs/project-structure.md`](docs/project-structure.md) | 目录与代码架构说明                             |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)               | 数据模型                                       |
| [`docs/evaluation.md`](docs/evaluation.md)               | 评测方法与指标                                 |
| [`docs/user_testing.md`](docs/user_testing.md)           | 用户测试说明                                   |

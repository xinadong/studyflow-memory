# StudyFlow Memory 项目目录与代码架构说明

> 文档版本：v1.0  
> 适用项目：StudyFlow Memory 反馈记忆驱动的课程学习恢复 Agent  
> 根目录：`D:\黑客松`

## 1. 文档目的

这份文档说明项目的目录结构、代码职责、模块依赖和开发规范，帮助新成员在不阅读全部源码的情况下快速理解项目，并知道新代码应该放在哪里。

项目采用前后端分离结构：

- 前端使用 Vue 3 + TypeScript，负责页面、交互、状态和 API 调用；
- 后端使用 FastAPI，负责 Agent 编排、学习业务、记忆系统、数据持久化和指标统计；
- SQLite 用于 MVP 阶段的任务、反馈、记忆和评测数据；
- LLM 通过 OpenAI 兼容接口接入，但业务层不直接依赖具体模型供应商。

## 2. 总体目录树

```text
D:\黑客松\
├─ README.md                         项目入口说明
├─ .gitignore                        Git 忽略规则
├─ .env.example                      环境变量模板
├─ docker-compose.yml                本地容器编排
│
├─ backend/                          FastAPI 后端
│  ├─ pyproject.toml                 Python 项目与依赖配置
│  ├─ alembic.ini                    数据库迁移配置
│  ├─ app/
│  │  ├─ main.py                     FastAPI 应用入口
│  │  ├─ api/                        HTTP 接口层
│  │  │  ├─ dependencies.py          依赖注入定义
│  │  │  └─ routes/                  路由模块
│  │  │     ├─ agent.py              计划、理解检验、恢复接口
│  │  │     ├─ feedback.py           用户反馈接口
│  │  │     ├─ memories.py           记忆管理接口
│  │  │     ├─ evaluation.py         对照评测接口
│  │  │     └─ metrics.py             运行指标接口
│  │  ├─ core/                       全局基础设施
│  │  │  ├─ config.py                环境配置
│  │  │  ├─ logging.py               日志配置
│  │  │  ├─ exceptions.py            异常定义
│  │  │  └─ security.py              安全辅助函数
│  │  ├─ domain/                     领域层
│  │  │  ├─ entities/                业务实体
│  │  │  ├─ value_objects/           值对象和枚举
│  │  │  └─ repositories/            仓储接口
│  │  ├─ application/                应用层
│  │  │  └─ use_cases/               用例编排
│  │  ├─ agents/                     Agent 层
│  │  │  ├─ orchestrator.py          Agent 主编排器
│  │  │  ├─ state.py                 Agent 状态
│  │  │  ├─ tools/                   可调用工具
│  │  │  └─ prompts/                 提示词模板
│  │  ├─ memory/                     反馈记忆子系统
│  │  ├─ infrastructure/             外部适配和持久化
│  │  │  ├─ database.py              数据库连接
│  │  │  ├─ models/                  ORM 数据模型
│  │  │  ├─ repositories/             仓储实现
│  │  │  ├─ llm/                     大模型适配器
│  │  │  └─ telemetry/               Token 和延迟统计
│  │  ├─ schemas/                    API 输入输出模型
│  │  └─ evaluation/                 评测场景和指标
│  └─ tests/                         后端测试
│     ├─ unit/                       单元测试
│     ├─ integration/                集成测试
│     └─ fixtures/                   测试数据
│
├─ frontend/                         Vue 3 前端
│  ├─ package.json                   前端依赖和脚本
│  ├─ vite.config.ts                 Vite 配置
│  ├─ tsconfig.json                  TypeScript 配置
│  ├─ index.html                     前端 HTML 入口
│  ├─ public/                        不参与编译的静态资源
│  └─ src/
│     ├─ main.ts                     Vue 应用入口
│     ├─ App.vue                     根组件
│     ├─ router/                     页面路由
│     ├─ layouts/                    页面布局
│     ├─ views/                      页面级组件
│     ├─ components/                 可复用业务组件
│     ├─ stores/                     Pinia 状态管理
│     ├─ services/                   后端 API 服务
│     ├─ types/                      TypeScript 类型
│     ├─ utils/                      前端工具函数
│     └─ assets/                     图片、样式等资源
│
├─ data/                             数据文件
│  ├─ seed/                          演示用初始数据
│  └─ fixtures/                      测试夹具
├─ scripts/                          开发和评测脚本
├─ infra/                            Docker 和 Nginx 配置
└─ docs/                             项目文档
```

## 3. 后端架构

后端按照以下依赖方向组织：

```text
HTTP Route
    ↓
Application Use Case
    ↓
Domain + Memory Policy + Agent Orchestrator
    ↓
Repository / LLM / Telemetry Adapter
    ↓
SQLite、模型 API、日志和指标系统
```

依赖规则：

1. `api` 可以依赖 `application` 和 `schemas`，不能直接操作数据库；
2. `application` 可以依赖 `domain`、记忆策略和抽象接口；
3. `domain` 不依赖 FastAPI、SQLAlchemy 或具体模型 SDK；
4. `infrastructure` 实现 domain 中定义的仓储接口；
5. Agent 工具只能执行单一动作，不直接修改数据库；
6. 所有外部模型调用必须经过 `infrastructure/llm/adapter.py`；
7. 业务逻辑应该放在用例、领域服务或记忆服务中，而不是路由函数里。

### 3.1 `backend/app/main.py`

FastAPI 应用入口，负责：

- 创建 `FastAPI` 实例；
- 注册路由；
- 注册全局异常处理器；
- 配置 CORS；
- 配置启动和关闭生命周期；
- 暴露 `/health` 健康检查接口。

不应该在这里编写任务拆解、记忆检索或模型提示词逻辑。

### 3.2 `backend/app/api/`

HTTP 适配层。路由函数只做四件事：

1. 接收请求；
2. 使用 Pydantic Schema 校验参数；
3. 调用 Application Use Case；
4. 转换并返回响应。

#### 路由职责

| 文件 | 接口范围 |
| --- | --- |
| `routes/agent.py` | `/agent/plan`、`/agent/check`、`/agent/recover` |
| `routes/feedback.py` | `/feedback` |
| `routes/memories.py` | `/memories` 的查询、确认、修改和删除 |
| `routes/evaluation.py` | `/evaluation/compare` |
| `routes/metrics.py` | `/metrics` |

### 3.3 `backend/app/schemas/`

定义接口输入和输出格式，不放业务规则。

建议的 Schema：

- `PlanRequest` / `PlanResponse`
- `UnderstandingCheckRequest` / `UnderstandingCheckResponse`
- `RecoveryRequest` / `RecoveryResponse`
- `FeedbackCreateRequest` / `FeedbackResponse`
- `MemoryResponse` / `MemoryUpdateRequest`
- `EvaluationCompareRequest` / `EvaluationCompareResponse`

Schema 字段使用 `snake_case`，对外 JSON 保持稳定，内部实体不要直接作为 API 响应返回。

### 3.4 `backend/app/application/use_cases/`

应用用例是业务流程的入口，每个文件对应一个完整用户动作。

| 文件 | 业务职责 |
| --- | --- |
| `plan_learning.py` | 读取学习状态和相关记忆，生成或调整微任务 |
| `check_understanding.py` | 执行复述、关联、迁移三级理解检验 |
| `recover_learning.py` | 处理“我卡住了”，生成并记录恢复动作 |
| `process_feedback.py` | 分类反馈，生成候选记忆并决定是否需要确认 |
| `manage_memories.py` | 确认、编辑、撤销和删除记忆 |
| `evaluate_memory.py` | 执行有记忆/无记忆对照实验 |

用例负责协调多个模块，但不应该包含 SQL 语句或完整 Prompt 文本。

### 3.5 `backend/app/domain/`

领域层表达项目最稳定的业务概念。

#### 实体

- `Task`：一次课程学习微任务；
- `Memory`：一条可检索、可确认、可撤销的用户记忆；
- `Feedback`：用户对计划、解释或恢复动作的反馈；
- `LearningSession`：一次从任务开始到完成/中断/恢复的学习会话。

#### 值对象

- `MemoryType`：任务偏好、解释偏好、知识状态、恢复经验、复习安排；
- `TaskStatus`：待开始、进行中、已完成、已暂停、已取消；
- `UnderstandingLevel`：复述、关联、迁移。

#### 仓储接口

`domain/repositories/` 只定义抽象操作，例如：

- `MemoryRepository.find_relevant(...)`
- `MemoryRepository.save_candidate(...)`
- `MemoryRepository.confirm(...)`
- `MemoryRepository.delete(...)`
- `TaskRepository.get_current_state(...)`
- `FeedbackRepository.create(...)`

具体 SQLite 实现放在 `infrastructure/repositories/`。

### 3.6 `backend/app/agents/`

负责把大模型组织成受约束的 Agent，而不是让模型直接控制系统。

#### `orchestrator.py`

负责：

- 组装当前任务上下文；
- 接收记忆检索结果；
- 选择和调用工具；
- 校验模型结构化输出；
- 返回 `used_memory_ids` 和解释信息；
- 记录 Token 和模型耗时。

#### `tools/`

每个工具只执行一个动作：

| 文件 | 工具职责 |
| --- | --- |
| `get_learning_state.py` | 查询当前课程、任务和知识状态 |
| `split_learning_task.py` | 将目标拆为 15-30 分钟微任务 |
| `adjust_learning_plan.py` | 根据用户反馈重排或缩小任务 |
| `generate_understanding_question.py` | 生成一轮理解检验问题 |
| `generate_recovery_action.py` | 生成一个低压力恢复动作 |

工具必须有明确输入、输出和错误结果；模型不能绕过工具直接写数据库。

#### `prompts/`

只存提示词模板，不存用户私密数据。运行时由 Agent 组装任务信息和经过筛选的记忆。

### 3.7 `backend/app/memory/`

这是本项目最重要的业务子系统，负责反馈记忆的完整生命周期。

| 文件 | 职责 |
| --- | --- |
| `extractor.py` | 从用户反馈中提取明确偏好、推断偏好和候选经验 |
| `retriever.py` | 按课程、任务类型、知识点和阻塞类型检索记忆 |
| `ranker.py` | 按相关性、确认状态、置信度和新鲜度排序 |
| `writer.py` | 保存候选记忆、确认记忆和来源信息 |
| `policy.py` | 处理自动保存、确认、冲突、撤销和删除规则 |

记忆类型：

- `task_preference`
- `explanation_preference`
- `knowledge_state`
- `recovery_experience`
- `review_schedule`

每轮最多向 Agent 注入 3-5 条相关记忆，并返回实际使用的 `used_memory_ids`。

### 3.8 `backend/app/infrastructure/`

基础设施层负责所有外部依赖。

- `database.py`：SQLAlchemy Engine、Session 和事务管理；
- `models/`：ORM 表模型；
- `repositories/`：实现 domain 中定义的仓储接口；
- `llm/client.py`：HTTP 层模型客户端；
- `llm/adapter.py`：统一模型调用接口，屏蔽供应商差异；
- `telemetry/token_tracker.py`：记录输入、记忆和输出 Token；
- `telemetry/latency_tracker.py`：记录检索、模型和总耗时。

### 3.9 `backend/app/evaluation/`

用于验证记忆是否真正有效：

- `scenarios.py`：20 个以上固定测试场景；
- `runner.py`：执行有记忆和无记忆两组实验；
- `metrics.py`：计算召回率、误用率、正确应用率、Token 和延迟。

## 4. 前端架构

### 4.1 页面层 `frontend/src/views/`

页面负责组合组件和调用 Store，不把复杂业务逻辑写在模板中。

- `TodayView.vue`：输入课程目标、展示推荐微任务；
- `UnderstandingView.vue`：展示三级理解检验和回答反馈；
- `RecoveryView.vue`：展示阻塞原因和恢复动作；
- `MemoryCenterView.vue`：管理记忆；
- `EvaluationView.vue`：展示 Token、延迟和记忆命中结果。

### 4.2 组件层 `frontend/src/components/`

组件只负责单一可复用的 UI 片段：

- `TaskCard.vue`：任务卡片和调整入口；
- `MemoryReference.vue`：显示本轮使用的记忆及原因；
- `UnderstandingQuestion.vue`：问题、回答和反馈；
- `RecoveryAction.vue`：恢复建议的接受、修改和拒绝；
- `MemoryCard.vue`：记忆详情、状态和操作按钮。

### 4.3 状态层 `frontend/src/stores/`

使用 Pinia 管理跨页面状态，建议拆分为：

- `task.ts`：当前任务和计划；
- `learningSession.ts`：学习会话和理解阶段；
- `memory.ts`：记忆列表和当前引用记忆；
- `evaluation.ts`：评测结果和指标。

组件内部的短暂 UI 状态不必放入 Store。

### 4.4 API 层 `frontend/src/services/`

统一封装后端请求：

- `api.ts`：基础 HTTP 客户端和 API 地址；
- `agent.ts`：计划、理解检验和恢复接口；
- `memories.ts`：记忆查询、确认、修改和删除；
- `evaluation.ts`：对照实验和指标查询。

组件不直接调用 `fetch` 或 `axios`，统一通过 service 层访问后端。

### 4.5 类型层 `frontend/src/types/`

定义与后端 Schema 对应的 TypeScript 类型，例如：

- `task.ts`
- `memory.ts`
- `feedback.ts`
- `evaluation.ts`

类型字段与 API JSON 保持一致，避免使用 `any`。

## 5. 核心业务流程与代码位置

### 5.1 生成学习计划

```text
TodayView.vue
  → services/agent.ts
  → POST /agent/plan
  → api/routes/agent.py
  → application/use_cases/plan_learning.py
  → memory/retriever.py
  → agents/orchestrator.py
  → agents/tools/split_learning_task.py
  → infrastructure/llm/adapter.py
  → 返回任务、理由和 used_memory_ids
```

计划调整的核心规则放在 `plan_learning.py` 和领域对象中，路由不实现规则。

### 5.2 处理用户反馈并形成记忆

```text
前端提交反馈
  → POST /feedback
  → routes/feedback.py
  → application/use_cases/process_feedback.py
  → memory/extractor.py
  → memory/policy.py
  → memory/writer.py
  → infrastructure/repositories/memory_repository.py
```

明确表达的偏好可以自动保存；模型推断出的偏好必须生成待确认候选记忆。

### 5.3 理解检验

核心代码位置：

- 请求模型：`schemas/agent.py`；
- 接口：`api/routes/agent.py`；
- 用例：`application/use_cases/check_understanding.py`；
- 题目生成工具：`agents/tools/generate_understanding_question.py`；
- 解释偏好检索：`memory/retriever.py`；
- 题目提示词：`agents/prompts/socratic_check.txt`；
- 知识状态持久化：`infrastructure/repositories/`。

### 5.4 学习恢复

核心代码位置：

- 页面：`frontend/src/views/RecoveryView.vue`；
- 接口：`api/routes/agent.py`；
- 用例：`application/use_cases/recover_learning.py`；
- 恢复工具：`agents/tools/generate_recovery_action.py`；
- 恢复经验检索：`memory/retriever.py`；
- 恢复经验写入：`memory/writer.py`。

### 5.5 记忆删除与准确性保证

删除流程必须经过：

```text
MemoryCenterView.vue
  → services/memories.ts
  → routes/memories.py
  → application/use_cases/manage_memories.py
  → memory/policy.py
  → memory repository
```

删除后检索器必须过滤 `active = false` 的记忆，不能继续把已删除记忆注入 Agent。

## 6. 数据与持久化建议

MVP 使用 SQLite + SQLAlchemy。建议至少包含以下表：

| 表 | 作用 |
| --- | --- |
| `tasks` | 课程学习任务和计划版本 |
| `learning_sessions` | 一次学习会话的状态 |
| `feedback_events` | 用户的原始反馈和操作 |
| `memories` | 候选、确认、撤销和删除状态 |
| `knowledge_states` | 知识点理解层级和证据 |
| `evaluation_runs` | 对照评测运行记录 |
| `agent_runs` | Token、延迟和记忆引用记录 |

所有需要修改的数据都通过事务提交；模型调用失败时不能留下“已完成”的任务状态。

## 7. 设计模式建议

### 7.1 分层架构 / 六边形架构

用 `api → application → domain → infrastructure` 隔离业务和外部依赖。这样更换 LLM、数据库或前端时，不需要修改核心业务规则。

### 7.2 Repository Pattern

领域层只依赖仓储接口，SQLite 的具体实现放在基础设施层，便于单元测试时替换为内存仓储。

### 7.3 Adapter Pattern

通过 `LLMAdapter` 屏蔽 OpenAI 兼容 API 的具体请求格式。将来更换模型时，只改 `infrastructure/llm/`。

### 7.4 Strategy Pattern

记忆排序可以使用不同策略：

- 结构化精确匹配；
- 课程和知识点匹配；
- 恢复经验相似度匹配。

由 `memory/ranker.py` 根据场景选择策略。

### 7.5 Application Service Pattern

每个用户动作由一个用例服务负责，例如 `PlanLearningUseCase`、`ProcessFeedbackUseCase`。避免把业务流程散落在路由、组件和工具中。

### 7.6 轻量状态机

学习会话可以使用状态机管理：

```text
created → planned → learning → checking → completed
                         ↓
                      blocked → recovering → learning
```

非法状态转换应在领域层被拒绝。

## 8. 命名与代码规范

### Python

- 文件和函数：`snake_case`；
- 类：`PascalCase`；
- 常量：`UPPER_SNAKE_CASE`；
- 公共函数必须写类型注解；
- API 输入输出使用 Pydantic Model；
- 异步 I/O 函数使用 `async def`；
- 不使用 `Any` 隐藏类型问题；
- 每个模块保持单一职责；
- 推荐 Ruff、Pytest 和 Mypy。

### TypeScript / Vue

- 组件文件：`PascalCase.vue`；
- 服务和 Store：`camelCase.ts`；
- 类型和接口：`PascalCase`；
- 事件名使用动词，例如 `memory-confirmed`；
- API 请求集中在 `services/`；
- 页面负责组合，组件负责展示和局部交互；
- 推荐 ESLint、Prettier 和 `vue-tsc`。

### Git

提交信息使用：

```text
feat: add memory retrieval service
fix: prevent deleted memories from retrieval
test: cover recovery memory policy
docs: explain backend architecture
chore: update dependencies
```

## 9. 测试组织

### 单元测试 `backend/tests/unit/`

测试不依赖真实模型和真实数据库，重点覆盖：

- 记忆过滤和排序；
- 明确反馈与推断反馈的确认策略；
- 记忆冲突和删除；
- 任务时长调整；
- 学习状态转换；
- 评测指标计算。

### 集成测试 `backend/tests/integration/`

使用临时 SQLite 数据库，验证：

- API 到用例的完整链路；
- 记忆保存后能被下一次任务检索；
- 删除后不再被 Agent 使用；
- Token 和延迟指标被正确记录。

### 测试夹具 `backend/tests/fixtures/` 和 `data/fixtures/`

放置固定的 BFS、DFS、拓扑排序和栈表达式求值场景，不在测试中依赖线上模型输出。

## 10. 本地开发方式

### 启动后端

```powershell
cd D:\黑客松
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```

或在后端目录启动：

```powershell
cd D:\黑客松\backend
..\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

### 启动前端

```powershell
cd D:\黑客松\frontend
npm install
npm run dev
```

### 健康检查

浏览器访问：`http://localhost:8000/health`

预期返回：

```json
{"status":"ok"}
```

## 11. 新增代码放置规则

遇到新需求时按以下顺序判断：

1. 是 HTTP 输入输出格式？放 `schemas/`；
2. 是接口入口？放 `api/routes/`；
3. 是完整用户动作？放 `application/use_cases/`；
4. 是稳定业务概念或规则？放 `domain/`；
5. 是记忆生命周期逻辑？放 `memory/`；
6. 是 Agent 单一动作？放 `agents/tools/`；
7. 是模型、数据库或外部服务适配？放 `infrastructure/`；
8. 是页面？放 `frontend/src/views/`；
9. 是可复用 UI？放 `frontend/src/components/`；
10. 是跨页面状态？放 `frontend/src/stores/`。

不要把同一段业务规则同时复制到前端、路由和 Agent Prompt 中；规则应有唯一的后端业务来源。

# StudyFlow Memory API

## 运行配置

复制项目根目录 `.env.example` 为 `.env`，填入已轮换的新密钥：

```env
LLM_BASE_URL=https://api.openai-next.com/v1
LLM_API_KEY=<仅保存在本地，不要提交>
LLM_MODEL=gemini-3.7-flash
LLM_MAX_RETRIES=2
REQUEST_TIMEOUT_SECONDS=120
```

模型接口采用 OpenAI 兼容的 `POST /v1/chat/completions` 和 Tool Calling。
后端会自动给未带 `/v1` 的地址补上 `/v1`。API Key 缺失、模型服务不可用、
模型返回非法 JSON 或调用未授权工具时，接口明确返回失败，不会降级成规则 Agent。
默认单次模型请求超时为120秒，以覆盖工具调用加最终结构化输出的慢响应；可在本地
`.env` 中按供应商情况通过 `REQUEST_TIMEOUT_SECONDS` 调整。

安装并启动：

```powershell
cd D:\黑客松\backend
..\.venv\Scripts\python.exe -m pip install -e .
..\.venv\Scripts\python.exe mock_server.py
```

Docker 启动：

```powershell
docker compose up --build
```

Compose 会把宿主机 `data/` 挂载到容器 `/app/data/`，容器内数据库为
`/app/data/studyflow.db`。

后端镜像默认使用清华 PyPI 镜像以避免部分网络环境下载依赖超时；可在执行构建前设置
`PIP_INDEX_URL` 覆盖，例如：

```powershell
$env:PIP_INDEX_URL = "https://pypi.org/simple"
docker compose build backend
```

Swagger：`http://127.0.0.1:8000/docs`。

`mock_server.py` 这个名字只表示给前端联调使用的本地启动入口；Agent 接口仍会调用
`.env` 中配置的真实模型，并不是模型 Mock。单元测试使用 `httpx.MockTransport`，不会
消耗真实模型额度。

## 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查 |
| POST | `/agent/plan` | 生成或调整微任务计划 |
| POST | `/agent/check` | 复述—关联—迁移理解检验 |
| POST | `/agent/recover` | 根据阻塞类型生成恢复动作 |
| POST | `/feedback` | 写入反馈并产生 confirmed/pending 记忆 |
| POST | `/memories` | 创建记忆（前端管理和测试使用） |
| GET | `/memories` | 按用户、课程、知识点等过滤 |
| GET | `/memories/{id}` | 查看单条记忆 |
| PATCH | `/memories/{id}` | 确认、拒绝、修改或撤销 |
| DELETE | `/memories/{id}` | 用户软删除，保留审计记录 |
| POST | `/evaluation/compare` | 有记忆/无记忆计划对照 |
| GET | `/metrics` | Token、延迟和记忆引用汇总 |

`POST /feedback` 兼容两种方式：

- 前端已明确知道类型时传 `feedback_type` 和 `explicit`，后端按字段写入；
- 只提交自然语言 `content` 时，后端调用模型分类为受控的记忆类型、显式程度、
  置信度和阻塞类型，再由服务端代码写库。模型只生成候选结构，不能直接操作数据库。

自然语言分类失败时返回标准模型失败响应，不写入反馈或记忆。
知识状态不通过该接口写入；如需更新知识状态，请提交 `/agent/check` 的用户答案。

## 记忆引用

Agent 三个响应都返回 `retrieved_memory_ids`、`used_memory_ids` 和
`candidate_memory_ids`。只有 `confirmed` 记忆可以进入 `used_memory_ids` 并影响结果；
`pending` 只能作为候选展示。

理解检验支持三种已确认解释偏好：示例优先、定义优先和图示优先；只有实际改变本轮问题
引导方式的记忆才会进入 `used_memory_ids`。

## Agent Tool Calling 流程

1. `/agent/plan`、`/agent/check` 或 `/agent/recover` 读取最多 5 条相关记忆；
2. 只有 `confirmed` 记忆进入可直接影响结果的上下文，`pending` 只作为候选；
3. 第一次模型调用强制 `tool_choice=required`；
4. 模型只能选择当前接口允许的 5 个服务端工具之一；
5. 后端使用 Pydantic 校验工具参数，执行工具后把结果以 `role=tool` 回传模型；
6. 最终模型必须返回约定 JSON；支持裸 JSON、Markdown JSON 围栏和文本中唯一完整的 JSON 对象；
7. 若最终 JSON 或必需字段无效，只进行一次格式修复请求，优先使用 JSON Mode；供应商拒绝
   JSON Mode 时，同一次修复机会改用严格文本提示；修复仍失败则返回 `invalid_model_output`；
8. 成功和失败轨迹均写入 SQLite `agent_runs`，包括模型、工具、Token、耗时、供应商重试和
   `format_repair_count`。

模型最多发生 5 次工具调用；429、502、503、504、超时和网络错误最多重试 2 次。格式修复
不属于供应商网络重试，每次 Agent 最多执行一次。

## 模型失败响应

示例（HTTP 502；未配置模型时为 HTTP 503）：

```json
{
  "detail": {
    "code": "provider_unavailable",
    "message": "模型调用失败",
    "retry_count": 2
  }
}
```

常见 `code`：`model_not_configured`、`provider_timeout`、
`provider_unavailable`、`provider_rejected`、`invalid_provider_response`、
`invalid_tool_arguments`、`unknown_tool`、`invalid_model_output`。

## 跨域

允许 Vite 默认开发/预览地址：`localhost:5173`、`127.0.0.1:5173`、
`localhost:4173`、`127.0.0.1:4173`。

## 指标

`GET /metrics` 除原有 Token、延迟、记忆 ID 外，还返回成功/失败次数、模型、状态、
操作计数、重试次数、错误码和工具调用轨迹，并提供检索和模型耗时的 P50/P95 及记忆
召回/使用/候选数量。`evaluation_with_memory` 与
`evaluation_without_memory` 会单独计数。完整轨迹只保存在后端 SQLite 和该指标接口中，
三个 Agent 业务响应不会返回内部工具轨迹。

`memory_tokens` 是后端根据实际注入决策上下文的 confirmed 记忆文本长度进行的本地
估算值；pending 和未实际使用的召回记忆不计入该字段。`input_tokens` 和
`output_tokens` 优先使用模型供应商返回的 `usage`。

理解检验响应中的 `level` 是本轮提问层级，`assessed_level` 是模型根据答案给出的
形成性理解层级。只有提供答案且 `assessed_level` 合法时，后端才会更新知识状态。
计划请求命中当前课程和知识点的低层级知识状态时，会在解释中追加“前置提醒”；该提醒
不会伪装成记忆引用，也不会进入无记忆评测模式。

失败运行同样保存模型、输入/输出 Token（失败时输入为本地估算）、模型耗时、重试次数、
错误码和已执行工具轨迹，便于区分服务不可用与业务校验失败。

## 示例

```json
POST /agent/plan
{
  "user_id": "demo",
  "course": "数据结构与算法",
  "goal": "学习图的 BFS",
  "available_minutes": 25,
  "task_type": "study",
  "knowledge_point": "BFS"
}
```

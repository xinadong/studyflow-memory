# StudyFlow Memory API

## 结构化时长、版本替代与使用证据

`/feedback`、`POST /memories` 和 `PATCH /memories/{id}` 支持以下字段：

| 字段 | 含义 | 约束 |
| --- | --- | --- |
| `preferred_minutes` | 首选任务时长 | 1 至 240 分钟，可选 |
| `max_minutes` | 任务时长上限 | 1 至 240 分钟，可选，不代表必须排满 |

首选不能超过上限。明确数值优先于原文字；编辑时可传 `null` 清除字段。仅修改原文字会重新识别时长；只修改一个数值字段时，保留另一个字段。

未明确提供数值时，后端保守识别“首选15分钟”“最多30分钟”“半小时以内”“二十分钟”“20min”等表达。含多个不明确选项、下限要求或矛盾数值的文本不作猜测，标为 `duration_source=unresolved`，不用于时长规划。用户可在个人中心补充数值。旧数据启动时补充并回填字段，原文保留。

计划时长由可用时间、首选时长（未设置时默认25分钟）和上限共同约束。各字段先按适用范围和新旧顺序选取；未触发的上限属于“检索到但未采用”，不会算成改变安排的使用证据。

### 同范围偏好替代

新的已确认时长偏好会归档同一用户、范围、课程、知识点、任务类型下的旧时长偏好；解释偏好也按相同边界替代。新建时长偏好是整组设置的替换，需要保留首选与上限时应一起提交；不同范围不会互相归档。

待确认内容不会先替换有效偏好，确认后才归档冲突旧版本。编辑内容或时长字段会创建新 ID，旧记录保留原文、结构化字段与历史使用计数，通过 `supersedes_id` / `replaced_by_id` 回溯。编辑为待确认状态时，原已确认版本继续有效，直至新版本确认。新记录写入与旧记录归档在同一事务内完成，失败时全部回滚。

被替代的版本不能直接重新确认为有效；可编辑当前版本或新建偏好。删除当前版本不会自动恢复已归档旧版本。

### 使用证据

计划、理解检验与恢复响应增加 `memory_evidence`，每项包含：

- `memory`：本轮引用时的记忆快照，包含 ID、原文、范围、结构化时长和确认状态。
- `decision`：`used`（实际采用）、`retrieved_not_used`（检索但未采用）、`pending`（待确认）。
- `reason`：由后端实际选择规则生成的原因，不由模型编造。

时长证据示例：“本次使用了你确认的首选15分钟偏好，结合可用60分钟，实际安排15分钟。”页面可打开原始记忆，分别查看生成时快照与当前记录；若已归档替代，可继续打开替代版本。

证据随本轮响应展示，本次未新增历史规划报告查询功能。重开页面恢复的是已保存任务，不会伪造上次生成时的使用证据。

## 运行配置

复制项目根目录 `.env.example` 为 `.env`，填入已轮换的新密钥：

```env
LLM_BASE_URL=https://api.openai-next.com/v1
LLM_API_KEY=<仅保存在本地，不要提交>
LLM_MODEL=gemini-3.7-flash
LLM_MAX_RETRIES=2
REQUEST_TIMEOUT_SECONDS=120
AUTH_SESSION_DAYS=30
DEMO_EMAIL=demo@studyflow.local
DEMO_PASSWORD=<仅保存在本地，不要提交>
```

## 账号与会话

- `POST /auth/register` 和 `POST /auth/login` 成功后设置 HttpOnly、SameSite=Lax 的会话 Cookie。
- `POST /auth/logout` 会在服务端撤销会话；`GET /auth/me` 返回当前账号。
- 除 `/health` 和认证接口外，业务接口均要求登录。任务、记忆、反馈、知识状态、Agent 运行和指标都按服务端会话中的账号隔离，客户端提交的 `user_id` 不决定归属。
- 配置 `DEMO_EMAIL` 与 `DEMO_PASSWORD` 后，启动时会确保 ID 为 `demo-user` 的演示账号存在。历史数据库中的任务、记忆、反馈、知识状态和 Agent 审计记录会一次性归并到该账号。

模型接口采用 OpenAI 兼容的 `POST /v1/chat/completions` 和 Tool Calling。
后端会自动给未带 `/v1` 的地址补上 `/v1`。API Key 缺失、模型服务不可用、
模型返回非法 JSON 或调用未授权工具时，接口明确返回失败，不会降级成规则 Agent。
默认单次模型请求超时为120秒，以覆盖工具调用加最终结构化输出的慢响应；可在本地
`.env` 中按供应商情况通过 `REQUEST_TIMEOUT_SECONDS` 调整。

安装并启动：

```powershell
cd backend
python -m pip install -e .
python mock_server.py
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


## 任务与复习持久化

任务接口不调用模型。任务归属由登录会话决定，客户端不再传入 `user_id`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/tasks` | 读取当前账号未删除的任务，包含完成状态和复习日期 |
| POST | `/tasks` | 保存当前账号的任务或用户明确确认的复习安排 |
| PATCH | `/tasks/{task_id}` | 更新状态：`pending`、`active`、`completed`、`deferred` |
| DELETE | `/tasks/{task_id}` | 软删除；重新加载和 Agent 学习状态查询均不返回该任务 |

保存示例：

```json
{
  "id": "client-generated-unique-id",
  "course": "数据结构",
  "title": "BFS · 对话后复习",
  "description": "根据本轮理解检验安排复习",
  "task_type": "review",
  "knowledge_point": "BFS",
  "duration_minutes": 15,
  "due_at": "2027-01-02T19:30:00+08:00"
}
```

客户端生成唯一 ID，同一 ID、相同内容重试不会重复插入；ID 已存在但内容不同或属于其他用户时返回 `409`。复习任务必须提供带时区的 `due_at`，后端按 UTC 存储和返回，前端按本地时间显示。

完成任务时提交 `{"status":"completed"}`。前端等待保存成功后才显示已完成或退出；失败时保留当前任务并显示错误。应用启动时重新读取 `/tasks`，恢复完成状态和复习安排，未来复习单独展示。任务删除也先保存后更新页面，避免重开页面后复活。

后端首次启动会为旧任务表补充可空的 `due_at` 字段，保留原有记录；旧记录没有保存过的复习日期无法自动恢复。更新前仅保存在浏览器中的复习任务不会自动导入，请重新确认添加。

### 手工验收

1. 启动后端并打开前端，使用演示账号登录。
2. 生成或添加真实任务，在专注页点击完成；也可在伴学达到完成条件后选择完成并退出。
3. 关闭标签页再重新打开，确认任务仍为已完成。
4. 在伴学结束时确认添加复习，关闭标签页再重新打开，确认首页“已保存的复习安排”仍显示相同日期和任务。
5. 停止后端再尝试完成任务或保存复习，确认页面提示失败而不是显示成功；恢复后端后可重试。

以上验证不会把界面预览任务写入数据库。恢复调整中的时长和顺延状态持久化不在本次修改范围内。


## 偏好使用方式与保存范围

- **仅本次使用**：首页将临时文字通过 `/agent/plan` 的 `temporary_preference` 传入。它只覆盖该次任务偏好，不生成反馈或记忆记录；生成成功后前端清除待用偏好，失败时保留以便重试。
- **伴学临时提示**：`/agent/check` 的 `hint_preference` 优先于已保存解释偏好，仅作用于该次请求；不会自动写入长期偏好。理解检验仍按既有逻辑记录知识状态，这与保存解释偏好不同。
- **保存为长期偏好**：仅在用户明确选择保存时调用 `/feedback`，包含 `scope`。明确选择的任务或解释偏好传 `explicit: true`；其他候选内容仍须确认后才应用。

`scope` 可取：

| 范围 | 值 | 必需上下文 | 适用边界 |
| --- | --- | --- | --- |
| 全局 | `global` | 用户 | 同一用户的所有课程与知识点；后端清空课程和知识点字段 |
| 课程 | `course` | 用户、课程 | 同一课程的知识点；后端清空知识点字段 |
| 知识点 | `knowledge_point` | 用户、课程、知识点 | 同一课程中的指定知识点 |

检索先按用户和范围过滤；已确认优先，同为已确认时按“知识点 → 课程 → 全局”排序。本次明确选择优先于已保存偏好，未确认、归档、拒绝或删除的内容不会直接使用。响应中的 `used_memory_ids` 不会把临时选择算作长期记忆使用。

旧数据库启动时补充 `scope` 字段，已有知识点的记录保持知识点范围，其余保持课程范围；不会自动扩大为全局。未传 `scope` 的旧客户端继续沿用原有课程／知识点边界。

长期偏好可在个人中心查看适用范围、修改内容、归档或删除。任务流和伴学中的保存选项完成后恢复为“仅本次使用”，防止把下一次临时选择继续保存。个人中心的“记录新偏好”专门用于新增长期偏好，需要明确范围。

验收建议：保存一条全局 40 分钟偏好，再保存一条课程 20 分钟偏好和知识点 10 分钟偏好，检查各范围下的规划时长；临时指定 15 分钟时只影响本次，下一次恢复已保存偏好。伴学中仅本次选择提示方式后，个人中心不应新增解释偏好；明确保存后才应新增，并能看到对应范围。

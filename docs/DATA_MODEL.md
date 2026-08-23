# StudyFlow Memory 数据模型

SQLite 默认文件为 `D:\黑客松\data\studyflow.db`，由 SQLAlchemy 在应用启动时创建。

## 表

- `memories`：15 个记忆字段，`active=False` 表示软删除；
- `feedback_events`：用户原始反馈和是否明确表达；
- `tasks`：计划生成的微任务；
- `knowledge_states`：形成性理解反馈，不代表永久能力判断；
- `agent_runs`：每次 Agent 的 Token、检索/模型延迟、记忆 ID、模型状态和工具轨迹。

### `agent_runs` 审计字段

- `operation` / `user_id` / `model` / `status`
- `input_tokens` / `memory_tokens` / `output_tokens`
- `retrieval_latency_ms` / `model_latency_ms`
- `retrieved_memory_ids` / `used_memory_ids`
- `tool_calls` / `retry_count`
- `error_code` / `error_message`
- `user_acceptance` / `created_at`

旧版 SQLite 在应用启动时会非破坏性增加 Tool Calling 轨迹列，不删除已有记录。

评测运行使用 `evaluation_with_memory` 和 `evaluation_without_memory` 两个 operation，
不写入正式 `tasks` 表，但会保留运行指标用于对照。

## 状态规则

- `pending`：可召回、只能作为候选；
- `confirmed`：可直接影响计划、解释和恢复动作；
- `rejected`：用户拒绝，不参与检索；
- `archived`：用户撤销，保留记录，不参与检索；
- 普通删除使用 `active=False`，仓储 `delete()` 仅用于物理清理测试。

# StudyFlow Memory 记忆数据契约

## 1. 目的

本文件是记忆模块的协作标准，统一领域实体、枚举、仓储接口、API Schema 和 Agent 检索语义。前端、后端、评测代码必须从 `backend/app/` 导入定义，不得在各自模块重新定义字段或枚举值。

## 2. 记忆类型

`MemoryType` 位于 `backend/app/domain/value_objects/memory_type.py`：

| 枚举 | 值 | 含义 |
| --- | --- | --- |
| `TASK_PREFERENCE` | `task_preference` | 任务时长、拆分粒度、提醒强度 |
| `EXPLANATION_PREFERENCE` | `explanation_preference` | 示例、定义、图示优先 |
| `KNOWLEDGE_STATE` | `knowledge_state` | 课程、知识点、理解层级、薄弱点 |
| `RECOVERY_EXPERIENCE` | `recovery_experience` | 阻塞类型、恢复动作、是否有效 |
| `REVIEW_SCHEDULE` | `review_schedule` | 用户和知识点的复习安排 |

其他共享枚举：

- `ConfirmationStatus`：`pending`、`confirmed`、`rejected`、`archived`；
- `BlockType`：`time`、`too_hard`、`distraction`、`fatigue`。

所有枚举继承 `str, Enum`，序列化时使用小写字符串值。

## 3. Memory 实体

文件：`backend/app/domain/entities/memory.py`

实体字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `str` | UUID 主键，自动生成 |
| `user_id` | `str` | 用户标识 |
| `memory_type` | `MemoryType` | 记忆类型 |
| `course` | `str` | 课程名称 |
| `task_type` | `str \| None` | 任务类型 |
| `knowledge_point` | `str \| None` | 知识点 |
| `block_type` | `BlockType \| None` | 阻塞原因 |
| `content` | `str` | 记忆内容 |
| `source_feedback` | `str \| None` | 来源反馈 |
| `confidence` | `float` | 自动限制在 `[0, 1]` |
| `confirmation_status` | `ConfirmationStatus` | 默认 `pending` |
| `active` | `bool` | 软删除标记，默认 `True` |
| `created_at` | `datetime` | UTC 创建时间 |
| `last_used_at` | `datetime \| None` | 最近使用时间 |
| `use_count` | `int` | 使用次数 |

`memory.is_usable` 是检索硬过滤的唯一规则：`active=True` 且状态为 `pending` 或 `confirmed` 时可用；`rejected`、`archived` 或 `active=False` 时不可用。

## 4. pending 与 confirmed

- 用户明确说出的偏好可以直接创建为 `confirmed`；
- 模型从行为推断出的偏好创建为 `pending`；
- `pending` 可以被召回，用于向用户展示候选记忆；
- `pending` 的文本不得进入 Agent 决策 Prompt，也不得直接改变计划、解释方式或恢复动作；
- 用户确认后才更新为 `confirmed`；
- `rejected` 和 `archived` 不参与检索。

检索结果必须区分：

- `retrieved_memory_ids`：本轮召回的全部可用记忆；
- `used_memory_ids`：真正影响 Agent 输出的 confirmed 记忆；
- `candidate_memory_ids`：召回但仅供用户确认的 pending 记忆。

仅仅被召回的 confirmed 记忆不自动算作 `used_memory_ids`。只有实际改变工具参数、
解释方式或恢复动作的记忆才标记为 used。

## 5. 仓储接口

文件：`backend/app/domain/repositories/memory_repository.py`

```python
add(memory) -> Memory
get(memory_id) -> Memory | None
list(filters: MemoryFilter | None = None) -> list[Memory]
update(memory_id, changes: MemoryUpdate) -> Memory | None
delete(memory_id) -> bool
find_by_filter(filters) -> Memory | None
```

`MemoryFilter` 的字段为 `None` 时表示不过滤。`MemoryUpdate` 的字段为 `None` 时表示不修改；MVP 阶段不支持通过 `None` 清空可空字段。

## 6. 删除语义

- 普通用户删除：使用 `active=False`，保留记录和审计信息；
- 用户撤销记忆：使用 `confirmation_status=ARCHIVED`；
- 用户拒绝候选：使用 `confirmation_status=REJECTED`；
- 仓储 `delete()` 是物理删除能力，仅用于测试或彻底清理，不作为普通用户接口。

## 7. API Schema

文件：`backend/app/schemas/memory.py`

- `MemoryOut`：记忆响应；
- `MemoryCreate`：创建候选或确认记忆；
- `MemoryUpdate`：部分更新；
- `MemoryList`：列表和总数；
- `MemoryFilterQuery`：HTTP 查询过滤条件。

HTTP 层使用 Pydantic，领域层使用 dataclass，二者通过字段转换连接。

## 8. 检索和排序

文件：`backend/app/memory/retriever.py`、`ranker.py`

1. 先按用户、课程、任务类型、知识点和阻塞类型做结构化过滤；
2. 过滤 `is_usable=False` 的记忆；
3. 确认记忆优先于候选记忆；
4. 按置信度、最近使用时间和使用次数排序；
5. 每轮最多返回5条；
6. 返回召回、直接使用和候选三组 ID。

## 9. 协作边界

- 前端只使用 Schema 字段展示记忆，不重复定义枚举；
- 后端实现仓储、写入链路和 API，必须复用领域实体；
- 检索/评测代码使用 `MemoryRepository` 和 `retrieve_memories`，不得绕过 `is_usable`。

## 10. 验证

在 `backend` 目录运行：

```powershell
..\.venv\Scripts\python.exe verify_contract.py
..\.venv\Scripts\python.exe -m unittest tests.unit.test_memory_contract
```

后续 SQLite 仓储必须复用同一接口，并通过相同测试场景。

# StudyFlow 记忆检索评测文档

> 作者：C 角色　|　更新：2026-08-26
> 评测对象：B 已实现的记忆检索链路（`app/memory/retriever.py` + `ranker.py` + `policy.py`）
> 评测代码：`backend/app/evaluation/` + `scripts/run_evaluation.py`（C 新增，未改动 B 的任何代码）

---

## 1. 评测目标

用 **20 个脚本化场景（6 类）** 验证记忆检索在真实调用路径下行为正确，并给出三项可量化指标，支撑「有记忆 vs 无记忆」对照与答辩。

| 指标 | 定义 | 目标 |
| --- | --- | --- |
| 召回率（recall） | 应检索到的相关记忆中被 `retrieved` 命中的比例 | ≥ 90% |
| 误用率（misuse rate） | `used`（直接影响输出的记忆）中「不该用却用了」的比例 | ≤ 10% |
| 确认应用率（confirmation-application） | 应应用的 confirmed 记忆中被 `used` 命中的比例 | ≥ 85% |

辅助统计：平均记忆 token（用 B 的 `estimate_tokens`，`len//4`）、平均检索耗时（毫秒）。

---

## 2. 指标口径（与代码一致）

```
召回率        = |expected_retrieved ∩ actual_retrieved| / |expected_retrieved|
误用率        = |actual_used − expected_used| / |actual_used|        （actual_used 为空时记 0）
确认应用率    = |expected_used ∩ actual_used| / |expected_used|      （expected_used 为空时记 100%）
```

- 期望集用记忆的 `content` 作稳定标识（`Memory.id` 是运行时 UUID，不能跨运行比较）。
- 每个场景对 `retrieved / used / candidates` 做**精确集合比对**（不是只算比例），所以任一场景的召回/误用/确认应用会严格落在 100%/0%/100%。

---

## 3. 关键语义（写评测必须对，答辩要能讲清）

1. **只有 `confirmed` 记忆能直接影响 Agent 输出**（进 `used`）。
2. **`pending` 记忆能被召回，但只进 `candidates`**，不影响输出——评测里「pending 被召回但没被使用」是**正确行为**，不是误用。
3. `retrieved = used ∪ candidates`，且二者不相交。
4. 排序：confirmed 优先 → confidence 降序 → 最近使用 → use_count。
5. `is_usable = active 且 status ∈ {pending, confirmed}`；soft-delete（active=False）、rejected、archived 一律不召回。
6. 结构化过滤（user_id / course / task_type / knowledge_point / block_type / memory_type）为**精确匹配**；课程级通用偏好（knowledge_point 为空）由编排层另路匹配，本评测验证的是契约级精确语义。
7. **「used」有两层语义**：检索层（`retrieve_memories`）里 `used` = 所有 retrieved 中的 confirmed；编排层（`plan/check/recover`）会再用 `select_used_memories` 把 `used` 收窄为「真正改变了工具参数/输出的记忆」——`plan` 只认含「N分钟」时长的任务偏好（影响任务时长）、`check` 只认能识别出讲解风格的偏好、`recover` 只取第一条恢复经验。20 场景测的是检索层契约；`--real` 的 `memory_count`（=len(used_memory_ids)）反映的是编排层语义。

---

## 4. 场景清单（20 个，覆盖 6 类）

| # | 场景 id | 类别 | 期望行为 |
| --- | --- | --- | --- |
| 1 | bfs_confirmed_preferences_used | 同课程同任务 | 已确认的任务/讲解偏好全部召回并进 used |
| 2 | bfs_pending_is_candidate | 同课程同任务 | pending 记忆召回但只进 candidates，不进 used |
| 3 | limit_caps_to_three | 同课程同任务 | limit=3 只取置信度最高的前 3 条 confirmed |
| 4 | token_budget_only_first_fits | 同课程同任务 | token 预算=1 时只保留第一条，第二条被跳过 |
| 5 | toposort_filter_excludes_bfs | 同课程不同知识点 | 学拓扑排序不召回 BFS 的薄弱点/偏好 |
| 6 | generic_course_preference_no_kp | 同课程不同知识点 | 不带 knowledge_point 命中课程级通用偏好，不跨课程 |
| 7 | task_type_exact_match | 同课程不同知识点 | task_type 精确匹配，复习偏好不与学习偏好混淆 |
| 8 | block_type_filter | 同课程不同知识点 | block_type 精确匹配，疲劳型/难度型恢复经验分开 |
| 9 | cross_course_no_knowledge_leak | 不同课程同偏好 | 高数学习不召回数据结构课程的知识点 |
| 10 | same_type_diff_course | 不同课程同偏好 | 同是讲解偏好也不跨课程召回 |
| 11 | user_isolation | 不同课程同偏好 | user_id 隔离，只召回当前用户的记忆 |
| 12 | conflict_newer_ranks_first | 冲突偏好 | 同置信度时新的偏好排前，limit=1 时旧偏好被挤出 |
| 13 | conflict_old_soft_deleted | 冲突偏好 | 旧偏好被软删除后不再召回，仅新偏好生效 |
| 14 | conflict_old_archived | 冲突偏好 | 旧偏好被归档后不再召回，仅新偏好生效 |
| 15 | soft_deleted_not_retrieved | 已删除/失效记忆 | 软删除记忆即使 confidence 更高也不召回 |
| 16 | rejected_not_retrieved | 已删除/失效记忆 | 被明确拒绝的记忆不再召回 |
| 17 | archived_not_retrieved | 已删除/失效记忆 | 已归档的记忆不再召回 |
| 18 | empty_repo_cold_start | 无相关记忆（冷启动） | 空仓库 retrieved 为空，走默认策略 |
| 19 | wrong_course_cold_start | 无相关记忆（冷启动） | 只存在其他课程的回忆，当前课程冷启动为空 |
| 20 | wrong_user_cold_start | 无相关记忆（冷启动） | 只有其他用户的记忆，当前用户冷启动为空 |

每个场景的完整定义（seed 记忆、filter、精确期望集）见 `backend/app/evaluation/scenarios.py`。

---

## 5. 如何运行

在项目根目录 `G:\华为计算机大赛\黑客松\黑客松` 下执行（需 Python ≥ 3.11，mock 模式零第三方依赖）：

```bash
# mock：直调检索器 + InMemory 仓库，秒级跑完，不依赖模型/后端
python scripts/run_evaluation.py --mock

# 输出 JSON 报告（便于归档/自动化）
python scripts/run_evaluation.py --mock --json

# real：端到端有/无记忆对照（需先启动后端并配置 LLM API）
python scripts/run_evaluation.py --real --base-url http://localhost:8000
```

**退出码**：`0` = 20 场景全部通过且三指标达标；`1` = 存在失败场景或指标未达标。

运行前脚本会先做「场景定义自洽性校验」（重复 content、期望集不满足 `retrieved = used ∪ candidates`、期望引用不存在的记忆等都会在跑之前被拦下）。

---

## 6. 有/无记忆对照（端到端）

`--real` 模式调用 B 已实现的 `POST /evaluation/compare`，对一组代表性目标各做一次「有记忆 / 无记忆」规划，输出：

- `without_memory` / `with_memory` 两份完整规划结果；
- `delta`：记忆带来的差异（使用记忆条数、记忆 token、时长差）。

用于演示「反馈记忆让规划更个性化」的定性/定量证据。运行前提：后端已启动、LLM API 已配置、当前用户已有历史记忆。

---

## 7. 评测结论归档（2026-08-25 实测）

运行 `python scripts/run_evaluation.py --mock`，20/20 全部通过：

| 指标 | 实测 | 目标 | 达标 |
| --- | --- | --- | --- |
| 通过场景 | 20/20 | — | ✅ |
| 宏平均召回率 | 100.00% | ≥ 90% | ✅ |
| 宏平均误用率 | 0.00% | ≤ 10% | ✅ |
| 宏平均确认应用率 | 100.00% | ≥ 85% | ✅ |
| 平均记忆 token | 1.6 | — | — |
| 平均检索耗时 | 0.0 ms | — | — |

JSON 报告确认 `all_passed: true`、`targets_met: true`，20 个场景 `failures` 均为空数组。

结论：六类 20 场景对 retrieved/used/candidates 做精确集合比对全部一致，证明 B 的检索引擎在确定性契约场景下行为正确。

### 7.1 端到端 --real 实测（2026-08-25）

`--real` 已在本机后端（`python -m uvicorn app.main:app`，SQLite + 真调 LLM）跑通：3/3 目标全部返回 200 OK，`without_memory` / `with_memory` 两份规划与 `delta` 均正常输出。

三轮调试过程（记录根因，供理解设计）：

1. 空仓库：`with_memory` 检索为空，`delta` 全 0——正确控制结果。
2. 预置「不含时长」的偏好：`retrieved_memory_ids` 已非空（检索正确），但 `used_memory_ids` 仍空、`memory_count` 仍 0——`plan()` 只把含「N分钟」的任务偏好算 used（§3 第 7 条）。
3. 预置「带时长」的任务偏好：`used=1`、`memory_count=1`、`memory_tokens=3`，个性化说明出现。

最终归档（`--reset` 清空后写入 3 条干净记忆，逐例 used=1）：

| 目标（course / kp） | 无记忆时长 | 有记忆时长 | 时长差 | used | memory_tokens | 个性化说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 学习图的 BFS（数据结构 / BFS，偏好40min，可用25） | 25 | 25 | 0 | 1 | 3 | ✅ 你通常偏好40分钟，但本次只有25分钟可用 |
| 学习拓扑排序（数据结构 / 拓扑排序，偏好50min，可用30） | 25 | 30 | **+5** | 1 | 3 | ✅ 你通常偏好50分钟，但本次只有30分钟可用 |
| 理解极限的定义（高数 / 极限，偏好35min，可用25） | 25 | 25 | 0 | 1 | 3 | ✅ 你通常偏好35分钟，但本次只有25分钟可用 |

结论：

- 端到端「有记忆 vs 无记忆」对照打通，三例 `explanation` 均出现个性化时长说明，记忆被 used（`memory_count=1`）。
- **拓扑排序是最有力证据**：`available=30` 时，无记忆版本 LLM 默认只排 25 分钟；有记忆版本用上「偏好 50 分钟」→ 排满 30 分钟，`delta.duration_minutes=+5`——记忆确实改变了规划时长。
- 另两例因 `available=25` 封顶，时长差为 0，差异体现在个性化文案与 `memory_count`/`memory_tokens`。
- 备注：模型延迟波动大（单次调用 5.2s~127.9s，api.openai-next.com 中转站不稳定），曾因此把 `run_evaluation.py --real` 的客户端超时从 120s 调到默认 300s（可用 `--timeout` 覆盖）。

```bash
python scripts/seed_evaluation_memories.py --reset   # 清空并写入 3 条干净记忆
python scripts/run_evaluation.py --real --base-url http://127.0.0.1:8000
```

### 7.2 §8.1 记忆成本 / §8.2 对话速度（已归档到参赛文档）

这两项（方案 §8.1 / §8.2）的实测结果已归档进 `参赛文档-评测部分.md` §2 / §3，本文件不再重复维护：

- **§8.2 对话速度**：`scripts/bench_sqlite_latency.py`，文件级真实 SQLite，100/1000/5000 条三档 P95 全达标（5000 条时 SQLite 检索 64.63ms、本地处理 6.44ms）。
- **§8.1 记忆成本**：`scripts/bench_cost_comparison.py`，记忆注入恒 5 条 / 14 token，完整历史注入随反馈事件数线性增长，节省 84.9%~98.5%。

```bash
backend\.venv-local\Scripts\python.exe scripts\bench_sqlite_latency.py --scales 100,1000,5000 --iter 300
backend\.venv-local\Scripts\python.exe scripts\bench_cost_comparison.py
```

---

## 8. 边界与协作约定

- **检索归 B，评测归 C**：评测代码只调 B 的 `retrieve_memories`，不自己实现检索。
- 若某场景失败或指标不达标，**记录具体场景 → 反馈给 B 调整 retriever/ranker**，C 不改 B 的代码。
- 用户测试（md 8.4，5-10 人）与参赛文档评测部分，基于本评测数据继续完成，由 C 主笔。

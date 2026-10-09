# feature/ai-theme-julia-domain-adapter-v1 与 Julia_core 交互功能：重叠核查

> **方式**：只读（`git show` / `git grep` / `ls-tree`，设置了 `GIT_OPTIONAL_LOCKS=0`），没有切换分支，没有 fetch，没有改任何文件
> **整理**：Mira（Claude），2026-10-07
>
> **对象**：
> - ai_theme_app 分支 `feature/ai-theme-julia-domain-adapter-v1`：HEAD `e1f1b9ad`，与 main 的分叉点 `08fc1a68`（2026-07-10）；**只在本地**，没有推送到远端
> - ai_theme_app `main` / `origin/main` = `ddc9442e`
> - Julia_core `origin/main` = `e6f9777`（2026-10-06）。本地当前检出的分支是 `243-id-integrity`；本次核查读的是 `origin/main`

---

## 0. 结论

1. **ai_theme_app 的 main 上没有任何 Julia 集成代码。** `mcp_server/`、`julia_domain_adapter/`、`strategy_knowledge/`、`frontend/src/*/julia`、`golden/2026-07-14` 在 main 上都是 0 个文件，全部只存在于这条本地分支上。
2. **Julia_core 的 main 在运行时依赖这条分支。** 它通过写死的路径 `/Users/admin/Desktop/ai_theme_app`，在进程内 import 这条分支上的 `mcp_server`，并读取这条分支上的策略卡。所以桌面工作区**不是闲置的**：它是 Julia 市场能力当前实际在用的代码来源。删掉、清理或切换桌面工作区，Julia 的市场工具和研究交接都会断。
3. **重叠有三类**：
   - 分支内部有两套给 Julia 用的接口（MCP 工具和领域适配器 HTTP），其中快照和预警两项功能重复；
   - Julia 通过这条分支运行的是一份分叉的 ai_theme_app 旧代码，与 main 并行；
   - 分支上的 `strategy_knowledge`（策略卡 + 26 条硬规则）是一套与 v0.6.4 并行的策略规则来源，而且已经有语义冲突。

---

## 1. 分支上与 Julia 相关的内容

| 模块 | 内容 | 时间 |
|---|---|---|
| `mcp_server/`（11 个文件） | 13 个 MCP 工具：`review_market_snapshot`、`list_active_alerts`、`explain_decision`、`query_theme_status`、`market_context_snapshot`、`market_workbench_review`、`market_stock_history`、`market_stock_auction`、`market_theme_constituents`、`market_theme_capital`、`market_regime_read`、`subscribe_agent_channel` 等；DecisionEnvelope v1.1 | 8/05–8/08 |
| `stock_processing_service/application/services/julia_domain_adapter/` + `ports/julia_domain_adapter_http.py` | 领域适配器 HTTP 门面：`market_snapshot`、`market_alerts` 两个操作；降级与来源语义；契约故障矩阵；AT-R0～R8，最后到“冻结候选” | 8/26 |
| `strategy_knowledge/` | L0 登记表；12 张策略卡（主线识别、题材周期、弱转强、竞价确认、仓位……）；`rules/hard_rules.json`（26 条）；`soft_heuristics.json`；研究编译器；文档切片 | 8/07–9/11 |
| `frontend/src/components/julia/`、`services/julia/` | Julia Copilot 前端 | 8/01 |
| `golden/2026-07-14/` | Case001 黄金认知轨迹（与 `julia_core@2846e6c` 联合冻结） | 8/07–9/11 |
| `docs/integration/JULIA_*`、`docs/architecture/JULIA_MCP_INTEGRATION_ARCHITECTURE_v1/v1.1` | 集成文档 | — |

## 2. Julia_core 侧如何调用（origin/main）

| 位置 | 调用方式 | 依赖分支上的什么 |
|---|---|---|
| `julia_core/capability/providers/ai_theme/adapter.py:104–111` | 把 `/Users/admin/Desktop/ai_theme_app` 插入 `sys.path`，然后 `from mcp_server.server import MCP_TOOLS`，**在进程内**直接调用工具函数 | `mcp_server/`（main 上没有） |
| `julia_core/mcp_client/client.py:93` | 同样 `from mcp_server.server import MCP_TOOLS`（`query_theme_status`、`list_active_alerts`、`review_market_snapshot`） | 同上 |
| `julia_core/capability/financial/research/handoff.py:30–41` | 读取策略卡：先找 `glm-workspace/ai_theme_app/strategy_knowledge/cards`（main 上不存在），找不到就退回 `/Users/admin/Desktop/ai_theme_app/strategy_knowledge/cards` | `strategy_knowledge/cards`（main 上没有） |
| `julia_agent_server.py:36` | `CLAUDE_MD = /Users/admin/Desktop/ai_theme_app/CLAUDE.md` | 桌面工作区里的文件 |
| `julia_core/capability/providers/ai_theme/adapter.py:23–34` | 能力 → 工具映射：`market.snapshot.read`、`market.alert.query`、`market.decision.explain`、`market.stock.history`、`market.regime.read` 等 10 项 | 与分支上的 `MCP_TOOLS` 名称一一对应 |

**Julia_core 没有调用领域适配器 HTTP。** 在 origin/main 的非测试代码里，搜索 `domain_adapter`、`DomainAdapter`、`adapter/v1` 都没有命中。

---

## 3. 重叠点

### O-1　同一条分支里有两套给 Julia 用的市场接口

| 功能 | MCP 工具（8/05） | 领域适配器 HTTP（8/26，AT-R8 冻结候选） |
|---|---|---|
| 市场快照 | `review_market_snapshot` / `market_context_snapshot` | `MarketSnapshotOperation` |
| 预警 | `list_active_alerts` | `MarketAlertsOperation` |
| 调用方 | **Julia_core 在用**（进程内 import） | **没有调用方** |
| 降级 / 来源语义 | 没有统一定义 | 有（stale / partial / unavailable / error） |

后做的、规范的那套（适配器）没人用；先做的那套（MCP 工具，进程内 import，绕过网络边界）反而是 Julia 实际在用的。快照和预警这两项功能，是两个生产者。

### O-2　Julia 运行的是一份分叉的 ai_theme_app 旧代码

- MCP 工具在进程内 import 的是分支上的 `stock_processing_service.application.services.analyst_workbench.*`，包括 `snapshot`、`intelligence_exporter`、`market_context_exporter`、`snapshot_validator`。
- `research_tools.py` 直接 `asyncpg` 写 SQL。
- 这些代码以 7/10 的 main 为基础，又经过分支自己的修改，**落后 main 67 个提交**。

后果：
- 我们这轮审计和纠偏计划针对的是 `main@ddc9442`。Julia 看到的市场数据，来自另一份代码，不在纠偏范围里。
- 例如 P0B 要修的“虚构市场快照”“未来函数”，即使在 main 上修好了，**Julia 也拿不到修复**，除非这条分支合并或重做。
- 分支上的 `analyst_workbench` 和 main 上的同名模块已经各自演化，同名不等于同一份逻辑。

### O-3　两套并行的策略规则来源

分支上的 `strategy_knowledge` 由 Julia 的研究交接（`handoff.py`）读取。它和 v0.6.4 是**两套独立维护的策略规则**：

| 项 | strategy_knowledge（9/11，v2.0） | v0.6.4（10/06，Owner 已批准，未冻结） |
|---|---|---|
| 来源 | 同一批《投资策略》笔记（交易体系、竞价、找牛股、涨停、题材跟踪、弱转强） | 同一批 |
| 硬规则 | 26 条，例如 HR-008 “大盘好 + 板块也涨时，龙头分歧绝不能买”；HR-016 “冰点切忌操作”；HR-024 “竞价量 ½ + 高开 3%–5%” | 对应 R3、R8、CS-06 p6 等 |
| 主线身份 | 卡片写“主线身份低频确认，确认后做周期跟踪，不做日重判”；状态可从 `mainline_confirmed` 降到 `logic_only_market_rejects` | OP-03、OP-18：删除了 DEGRADED；身份失效只在逻辑被证伪或长期失去认可时才发生 |
| 来源分级、OP 决策、作用域拆分 | 没有 | 有（tier、R1–R10 的 A–E 组、九项语义决策） |

**重叠**：两边大部分规则出自同一批原文，内容相近。
**风险**：
- 两份规则没有对账机制。Tony 以后改 v0.6.4，Julia 的研究交接读到的仍然是 9/11 的卡片。
- 已经能看到的冲突：主线身份会随市场认可下降而“降级”，这正是 v0.6.4 有意删除的 DEGRADED 语义。
- 26 条硬规则里有没有 v0.6.4 已经撤回或改写的内容，例如 OP-12 被动分歧、OP-20 退潮期，本次**没有逐条比对**。

### O-4　黄金案例绑定了两个仓库的特定版本

`golden/2026-07-14` 是和 `julia_core@2846e6c`、`ai_theme_app@3c65a1f` 一起冻结的回归基线，9/11 又按“策略卡 v2.0”重新定了基线。它同时依赖分支上的代码和策略卡。分支一旦变动，这个回归基线就会失效。

---

## 4. 对当前工作的影响

1. **“桌面工作区已经不是开发工作区”这件事，需要和 Julia 的运行依赖一起处理。** 它不再用于开发没有问题，但目前 **Julia 在运行时离不开它**。在 Julia_core 改掉写死的路径之前，不能删除、清理或切换这个工作区的分支。另外，这条分支只在本地，没有远端备份。
2. **纠偏计划 v0.2 的范围里没有 Julia 这条消费链。** 计划的 P0H 列出的消费者是复盘、日复盘 V2、前端、Notion，**没有 Julia**。修好 main 之后，Julia 依然走旧代码。
3. **策略规则需要定唯一来源。** 是让 `strategy_knowledge` 从 v0.6.4 派生，还是废弃、只保留 v0.6.4？这是 Tony 的决定。

---

## 5. 需要 Tony 决定的事（本次不做任何改动）

| # | 决定 | 选项 |
|---|---|---|
| D-1 | 这条本地分支 227 个提交的去向 | 推到远端存档 / 打标签 / 拆出有用部分并入 main |
| D-2 | Julia 访问 ai_theme_app 走哪条路 | 进程内 MCP（现状）/ 领域适配器 HTTP（已冻结候选，规范，但还没接）/ 其他 |
| D-3 | Julia 读取的代码以哪个为准 | 继续用分支上的旧代码 / 迁到 main（需要先把集成代码并入 main） |
| D-4 | 策略规则的唯一来源 | v0.6.4 为唯一来源，`strategy_knowledge` 从它派生或废弃 / 两者并存并定期对账 |
| D-5 | 是否把“Julia 消费链”加进纠偏计划 v0.3 的消费者清单和切换顺序 | 是 / 否 |

在 D-1～D-3 定下来之前，建议**保持桌面工作区和这条分支原样不动**。

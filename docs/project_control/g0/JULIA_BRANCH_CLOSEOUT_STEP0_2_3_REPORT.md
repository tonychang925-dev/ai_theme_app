# Julia 分支收口：第 0 / 2 / 3 步报告

> **范围**：Tony 2026-10-07 的三条指令。第 0 步：推送备份分支；第 2 步：只读核实正式 brain 的代码来源；第 3 步：第 1 步分类清单，做完后停下等审。
> **方式**：只读。没有切换分支，没有 prune，没有 fetch，没有改任何仓库文件。
> **整理**：Mira（Claude），2026-10-07
> **附件**：`julia_branch_file_classification.tsv`，共 1242 行，三列：category、relation_to_main、path

---

## 第 0 步：推送备份分支 —— **未完成，需要 Tony 本人执行**

| 尝试 | 结果 |
|---|---|
| 从本会话以 push 权限挂载 `tonychang925-dev/ai_theme_app` | 被拒：`push_check: refused`。Claude GitHub App 没有给这个账号或仓库安装 |
| 通过 Mac 上的命令行执行 `git ls-remote` / `git push` | 代理返回 `HTTP 403 from proxy after CONNECT`，这条通道到不了 github.com |

没有推送，也没有在云端克隆。仓库状态和之前完全一样。

**Tony 在自己的终端执行（只推，不改任何本地内容）：**

```bash
cd /Users/admin/glm-workspace/ai_theme_app
git push origin e1f1b9ad1e44af0edaba9543bc4868ae42f2382f:refs/heads/archive/julia-domain-adapter-v1-20261007
git ls-remote origin refs/heads/archive/julia-domain-adapter-v1-20261007
# 期望输出：e1f1b9ad1e44af0edaba9543bc4868ae42f2382f  refs/heads/archive/julia-domain-adapter-v1-20261007
```

- 这里推的是**提交 SHA**，不是分支名，所以不会建立上游跟踪，也不会改动桌面 worktree 的任何配置。
- 体积预估：增量里约有 130 MB 的 `analyst_data`（858 个文件）。最大的单文件是 `logs/jyhf_cdp_service.log.1`（11.1 MB）和 `docs/architecture/集合竞价.pdf`（10.2 MB），都低于 GitHub 单文件 100 MB 的硬限制，但会收到超过 50 MB 的警告。**推断**推送可以成功，只是会比较慢。
- 另一条路：安装 Claude GitHub App（https://github.com/apps/claude/installations/select_target ），或者在 claude.ai 的连接器里重新连接 GitHub，之后由我来推。

---

## 第 2 步：正式 brain 实际加载哪一份 ai_theme_app —— 供写入 #204 / #206 的已知限制

### 2.1 确认（直接读文件或 git 得到）

| # | 事实 |
|---|---|
| C-1 | `~/julia_release/rd1_v1/ai_theme_app` 的 HEAD 是 `bc34e973686d7f78b0e9c3efd67b433f0901f21a`（detached，2026-09-23，PR #414 的合并提交），是 `main` 的祖先，落后 `main@ddc9442` 26 个提交 |
| C-2 | 这份 release 副本里**没有 `mcp_server/`**，**没有 `strategy_knowledge/cards`**，也没有 `tmp/analyst_workbench` |
| C-3 | `~/julia_release/rd1_v1/julia_core` 的 HEAD 是 `e6f9777`，等于 Julia_core 的 `origin/main` |
| C-4 | release 版 `adapter.py` 的写法：先遍历路径列表 `[Desktop, release 旁的 ai_theme_app]`，每一项存在就执行 `sys.path.insert(0, p)`；然后 `from mcp_server.server import MCP_TOOLS` |
| C-5 | `mcp_server/` 只存在于桌面 worktree，也就是分支 `feature/ai-theme-julia-domain-adapter-v1` @ `e1f1b9ad`。这条分支只在本地，没有任何远端备份 |
| C-6 | `analyst_workbench` 下的 `intelligence_exporter`、`market_context_exporter`、`snapshot_validator` 这三个模块，release（`bc34e97`）里**没有**，桌面分支里有；`snapshot` 两边都有 |
| C-7 | release 里的 `stock_processing_service/__init__.py` 存在，所以它是常规包（regular package），不是命名空间包 |
| C-8 | release 版 `handoff.py` 读取策略卡的顺序：环境变量 `STRATEGY_CARD_DIR` → `<release>/ai_theme_app/strategy_knowledge/cards` → 退回 `/Users/admin/Desktop/ai_theme_app/strategy_knowledge/cards` |
| C-9 | MCP 工具对 `stock_processing_service` 的 import 写在**函数体内**（`alerts.py:55/62/71`、`snapshot.py:58/66/82`、`market_context.py:40`、`workbench_review.py:40/46`），属于延迟加载，调用时才执行 |
| C-10 | 工具读取数据的根目录是 `dirname×3(mcp_server/tools/x.py)`，也就是桌面根目录，读的是 `Desktop/tmp/analyst_workbench/<date>`。目前最新的日期是 2026-09-24 |

### 2.2 推断（只来自代码，没有核对运行中进程的 `sys.path`、PYTHONPATH、工作目录、`STRATEGY_CARD_DIR` 和符号链接）

| # | 推断 | 依据 |
|---|---|---|
| I-1 | `sys.path` 的最终顺序是 **release 的 ai_theme_app 在前，桌面在后**（Tony 的判断是对的：后插入的排在前面） | C-4 |
| I-2 | `mcp_server` **从桌面加载**，因为 release 里没有 | C-2、C-5，再加上 I-1 |
| I-3 | `stock_processing_service` **从 release（`bc34e97`）加载**，不是从桌面。原因有两点：它在 release 里存在，而且排在前面；它是常规包，子模块只在自己的 `__path__` 里查找，不会再退到桌面去找 | C-7，再加上 I-1 |
| I-4 | 所以正式 brain 跑的是**混合体**：工具层是桌面分支 7–9 月的代码，业务层是 release `bc34e97`。**既不是纯 release，也不是纯桌面** | I-2、I-3 |
| I-5 | 下面四个工具一旦被调用，**大概率在调用时抛 `ImportError`**（或者被工具自己的 try/except 吞掉，变成错误响应）：`review_market_snapshot`、`list_active_alerts`、`market_context_snapshot`、`market_workbench_review`。对应的 Julia 能力是 `market.snapshot.read`、`market.alert.query`、`market.intelligence.observe` 等 | C-6、C-9，再加上 I-3 |
| I-6 | `research_tools`（直接用 asyncpg）、`query_theme_status`、`explain_decision`、`subscribe_agent_channel` 不依赖那三个缺失的模块，**可能正常工作** | 只读了 import，没有逐个运行验证 |
| I-7 | 工具读取的盘后数据来自 `Desktop/tmp/analyst_workbench`，最新到 2026-09-24。之后没有新数据，只会给出旧数据或空结果 | C-10 |
| I-8 | 如果没有设置 `STRATEGY_CARD_DIR`，策略卡读的是**桌面的 12 张 v2.0 卡**（9/11 版本） | C-2、C-8 |

### 2.3 对 #204 / #206 的含义（建议写入“已知限制”的措辞）

> rd1_v1 正式 brain 的运行时代码身份不完整。除了已登记的 `ai_theme_app@bc34e97` 和 `julia_core@e6f9777`，它在运行时还依赖本机的 `/Users/admin/Desktop/ai_theme_app`（分支 `feature/ai-theme-julia-domain-adapter-v1` @ `e1f1b9ad`，仅本地，未进入任何发布记录）。具体依赖三项：
> - `mcp_server` 工具层；
> - 策略卡（未设置 `STRATEGY_CARD_DIR` 时）；
> - `tmp/analyst_workbench` 数据。
>
> 此外，工具层与 `bc34e97` 的业务层版本不匹配，推断快照、预警、市场上下文、工作台复核四个工具调用失败。以上为代码推断，尚未在运行中的进程上验证。

**要把“推断”升级为“确认”，需要的验证（只读，Tony 授权后可以做）：**
1. 在正式 brain 进程所在环境执行 `python -c "import mcp_server, stock_processing_service; print(mcp_server.__file__, stock_processing_service.__file__)"`，工作目录和环境变量与生产一致；
2. 查看启动脚本或 plist 中的 PYTHONPATH 和 `STRATEGY_CARD_DIR`；
3. 查看 Julia 日志里这四个工具最近的调用结果，或者在只读模式下调用一次 `review_market_snapshot`。

---

## 第 3 步：桌面分支相对 main 的文件分类清单

**口径**：比较分支 `e1f1b9ad` 与 merge-base `08fc1a68`、`main@ddc9442` 三方。

- BRANCH_ADDED：只有分支有；
- BRANCH_ONLY_CHANGED：分支改了，main 自分叉以来没动；
- BOTH_CHANGED：两边都改了，合并时会冲突。

非 ASCII 路径已用 `core.quotepath=false` 校正。

### 3.1 总览

| 类别 | 含义 | 文件数 | 与 main 的关系 |
|---|---|---|---|
| **A** JULIA_INTEGRATION | `mcp_server/`、`julia_domain_adapter/` 和对应的 HTTP port、前端 `julia/`、JULIA 集成文档 | 58 | 全部 BRANCH_ADDED |
| **B** STRATEGY_KNOWLEDGE | `strategy_knowledge/`：12 张卡、`hard_rules.json`（26 条）、软启发式规则、研究编译器 | 30 | 全部 BRANCH_ADDED |
| **C** GOLDEN_COGNITIVE | `golden/2026-07-14/` 等黄金轨迹 | 19 | 全部 BRANCH_ADDED |
| **D** WORKBENCH / REVIEW / CAPITAL / OTHER | 分析师工作台、复盘、资金、采集、前端、测试、脚本 | 237 | 173 新增，60 仅分支修改，**4 双方修改** |
| **E** ANALYST_DATA | `analyst_data/` 下的数据文件（约 130 MB） | 855（另外 3 个归在别的类别，总计 858） | 全部 BRANCH_ADDED |
| **F** DOCS_OTHER | 其余文档 | 43 | 40 新增，3 仅分支修改 |
| 合计 | | 1242 | |

### 3.2 会冲突的 4 个文件（D 类，BOTH_CHANGED）

| 文件 | 说明 |
|---|---|
| `stock_processing_service/api_app.py` | 预警循环开关 `SPS_ENABLE_W2S_ALERT_LOOP` 就在这个文件里，main 这边后来也改过 |
| `stock_processing_service/application/jobs/build_post_market_recap_job.py` | 复盘主任务，是纠偏计划 P0A-03 的对象 |
| `stock_processing_service/tests/integration/test_build_post_market_recap_job.py` | 上面那个任务的测试 |
| `web_app_service/main.py` | Web 入口 |

### 3.3 仅分支修改的 60 + 3 个文件（main 没动，但分支的修改没进 main）

按区域汇总（完整清单见 TSV）：

| 区域 | 代表文件 | 风险 |
|---|---|---|
| `database_service/` | `gateway.py`、`postgres_manager.py`、`build_hot_money_trading_activity.py` | **高**。共享数据层，也在纠偏计划 P0A-03 的授权路径里 |
| `analyst_workbench/` | `snapshot`、`session`、`draft`、`report_composer`、`emotion_review_builder`、`chart_review_builder` | **高**。与 main 上的同名模块已经分别演化，第 2 步 I-3 的 ImportError 就源于这里 |
| `market_metrics/` | `service.py`、`contracts.py`、`board_pool_provider.py` | 中 |
| 采集 | `collection_orchestrator`、`collection_task_registry`、`collection_task_runners`、`collection_job_manager`、eastmoney / ths / rate-limited 客户端 | 中 |
| 复盘 | `post_market_daily_review_v2_builder.py`、`generate_post_market_derived_data.py`、`limit_up_board_recalculator.py` | 中。属于纠偏计划的消费者 |
| 前端 | `api.ts`、`RecapPage`、`WorkbenchSectionsPanel`、analyst 组件、`package.json` | 低到中 |
| 生成物 | `frontend/public/api/emotion-*.json`、`analyst-charts/*.json`、`tsconfig.app.tsbuildinfo` | 低。这些是构建产物或数据快照，**不应合并** |
| 测试 | `test_workbench_*`、`test_mainline_registry.py`、`test_rate_limited_http_client.py`、`test_p4_phase0_contracts.py` | 跟着对应的源文件走 |
| 文档（F 类） | `Phase_4.5.4_设计文档.md`、`分析师工作台设计方案.md`、`TEST_REPORT.md` | 低 |

### 3.4 D 类新增文件（173 个）的分布

`stock_processing_service/application/services` 51 个，`tests/unit` 41 个，`tests/contracts` 24 个，`frontend/public/api` 10 个，`tests/fixtures` 6 个，`frontend/src/components` 4 个，其余是 `scripts/` 下的探针和工具脚本。

### 3.5 不应进入 git 历史的大文件或生成物

- `logs/jyhf_cdp_service.log.1`（11.1 MB）：日志文件，而且已经被提交进分支；
- `docs/architecture/集合竞价.pdf`（10.2 MB）和其他策略 PDF：策略原文，属于 CS 来源，建议放在仓库外统一管理；
- E 类 `analyst_data/`（约 130 MB）：数据，不是代码；
- `tsconfig.app.tsbuildinfo`、`frontend/public/api/*.json`：构建产物。

### 3.6 Mira 对分类的初步意见（不是决定，等 Tony 审）

| 类别 | 初步倾向 |
|---|---|
| A | 取决于 D-2（Julia 走 MCP 还是适配器 HTTP）。无论选哪条，都要在 main 上**重新基于 main 的业务层**接线，不能原样搬过去，否则会把第 2 步的版本错配带进 main |
| B | 取决于 D-4。我的倾向是 v0.6.4 作为唯一来源，策略卡从它派生。不建议原样并入 |
| C | 跟着 A、B 的决定走。现在的基线绑定的是旧代码，迁移后必须重新定基线 |
| D | 逐项挑选（cherry-pick）。4 个冲突文件和 `database_service`、`analyst_workbench` 应该放进纠偏计划，一起处理，不要单独合并 |
| E、生成物、日志、PDF | 只保留在存档分支里，不进 main |
| F | 有价值的设计文档可以单独迁移 |

---

## 关于“能不能把 glm-workspace 合并到桌面工作区”

**我不建议。** 方向应该反过来：单一工作区的终点是 `glm-workspace/ai_theme_app`（`main`）。

1. **`main` 才是事实来源。** 它和远端一致（`ddc9442`），也是这几轮审计和纠偏计划的对象。桌面分支落后 67 个提交，起点停在 7/10。
2. 把 `main` 合进桌面分支，得到的是一条“227 + 67”的混合分支，还要解决冲突。合完之后它仍然只是一条功能分支，不会成为 `main`，工作区也还是两个。
3. 桌面目录本身只是 glm 仓库的一个链接 worktree，不是独立仓库。所谓“合并到桌面”，实际上是在同一个仓库里换一条分支来工作，并不能消灭第二个工作区。

**建议的收口顺序**（每一步都需要 Tony 单独批准）：
1. 备份：第 0 步，推送存档分支；
2. 迁移：按本清单把 A / B / D 中需要的部分，基于 `main` 重新做进来；
3. 改指向：把 Julia_core 写死的 3–4 处路径和 release 配置改为指向 main 或 release 副本；
4. 验证：确认 Julia 的工具在新路径下可用；
5. 最后才移除桌面 worktree。

在第 3 步完成之前，桌面 worktree **保持原样，不能动**。

---

## 状态

```text
第 0 步  = 本会话无法执行（GitHub App 未安装 / 设备代理 403）→ 等 Tony 本人推送，或者授权 App 后由我推送
第 2 步  = 完成。确认 10 项，推断 8 项；核心结论：正式 brain 跑的是“桌面工具层 + release 业务层”的混合体
第 3 步  = 完成。1242 个文件，分为 A–F 六类；4 个文件会冲突
下一步  = 停下，等 Tony 审第 3 步的清单
```

---

## 勘误 E-1（2026-10-07 11:50）：第 2 步 I-1 / I-3 / I-5 推断有误

**错误**：I-1 认为 release 的 ai_theme_app 会被插到 `sys.path` 最前面，这忽略了 `adapter.py` 中的条件 `p not in sys.path`。正式 brain 由启动脚本 `start-brain-18089` 把 `JULIA_MARKET_ROOT` 写进 PYTHONPATH（第 42–43 行），所以运行时 release 路径**已经在** `sys.path` 里，适配器不会再插它；只有桌面路径会被 `insert(0)`，于是桌面排在最前。ChatGPT 对 PID 70567 的运行环境和 import 解析做了实测，结果是 `mcp_server`、`stock_processing_service`、`core` 都来自桌面，`market_public` 来自 release。我认可这个结论。

**修正后的结论**：
- 在“MCP 工具先于 market_public 触发 SPS import”的情况下（也就是实测的情形）：MCP 路径上的 SPS 和 core 都来自桌面，那四个工具**不会**报 ImportError（撤回 I-5）。
- **新的风险，属于推断，需要运行时验证**：`market_public/private/market_analysis.py:144` 会在函数内延迟 import `stock_processing_service...knowledge_evidence`。同一个进程里，`stock_processing_service` 包只解析一次，**哪条路径先触发 import，就决定整个进程生命周期内 SPS 来自哪里**：
  - MCP 先触发：market_public 的分析也会执行桌面版的 `knowledge_evidence`。它与 `bc34e97` 版有 131 行 diff，所以 release 的 market_public 实际跑的是桌面的业务代码。
  - market_public 先触发：SPS 被固定为 release 版，之后 MCP 工具缺三个模块，报 ImportError（I-5 的情形）。
- 不论哪种顺序，#204 的运行时身份都不闭合；具体表现取决于进程启动后的调用顺序。全新进程上的 import 测试只能反映其中一种顺序。

## 勘误 E-2（2026-10-07 12:05）：旧 MCP 路径在正式进程里很可能没有被激活

我查了正式入口的调用链。ChatGPT 对 PID 70567 做了运行现场核查，结果与之一致。

**正式入口**：`voice_api/server.py` → `routes.py` → `julia_core.public` → `conversation.py`，"market" 只绑定 `MarketPublicFactory` / `MarketPublicProviderAdapter`。

**旧路径**：`server_v2_1.py`、`shared_orchestration.py` 和 `MCPToolAdapter` 都还留在 release 代码里，但没有被正式入口 import。`create_ai_theme_provider` 和 `research_workflow`（读策略卡）也没有调用方。

**现场证据**：
- 正式的 `JULIA_BRAIN_ROOT` 是 `rd1_v1/assistant`。
- 只用正式 PYTHONPATH 做干净解析，`stock_processing_service` 和 `core` 都来自 release，`mcp_server` 找不到。
- 日志中 `MCPToolAdapter` 和"Market Brain 调用失败"的命中数都是 0。
- `lsof` 中桌面路径的命中数也是 0。这一项只能作参考，因为 Python import 完源码就会关闭文件句柄。

**修正结论**：
- 正式 18089 当前**大概率是 release 单源运行**。E-1 里描述的混源，只有在旧适配器被调用时才会发生，目前没有证据表明它被激活过。
- 对 #204 / #206 的含义要改：从“运行时身份不闭合”降级为“**release 中保留了一条一旦被调用就会把桌面目录插入 `sys.path` 的危险遗留路径**”。这条路径必须在 G0 中删除或硬禁用，并加上启动自检：所有已加载模块的 `__file__` 都必须位于 release 根目录下，否则拒绝启动。
- G0 工期估计：**1.5–2.5 个工作日**。

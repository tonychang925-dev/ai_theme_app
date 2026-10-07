# Development Master Plan v0.2 — 审计意见

> **审计对象**：`docs/project_control/AI_THEME_APP_STRATEGY_ARCHITECTURE_DRIFT_CORRECTION_DEVELOPMENT_MASTER_PLAN_v0.2.md`
> - SHA256 `2cb7d6024b857351594d7451e056687ca31f3210a670ee86f7c724a5d3e69f32`，2199 行，与声明一致
> **方式**：先逐行比对 v0.1 → v0.2 的差异，再回到代码和两份清单，核对 v0.2 新增的依赖关系。只读。
> **审计人**：Mira（Claude），2026-10-07

---

## 0. 结论

**v0.1 审计提出的 A-1、A-2、B-1～B-4、C-2、C-3 全部已落实，而且落实的方式是改依赖关系图（DAG）和验收条件，不只是改文字。**

逐项核对如下：

| 编号 | 落实位置 |
|---|---|
| A-1 | P0C-01 / 02 增加“硬隔离规则”；新增 P0-C 出口门 `MARKET_REGIME_REPLAY_DIFF = ZERO`、`OTO_REPLAY_DIFF = ZERO`；明确禁止把候选映射成 `is_strong_hotspot` |
| A-2 | 新增 P0B-05；P0E-01 拆成 01a / 01b；P0G 改为依赖 P0E-01a；§19.3 单列弱转强线 |
| B-1 | P0A-01 改为“基线 + 棘轮”，点名沿用 `test_canonical_metrics_migration_guard.py` |
| B-2 | P0A-02 改为“登记表 + 钉住测试 + PR 清单”，并明确写出“不要求自动识别新规则” |
| B-3 | `market_regime_fact_context_builder.py` 移入 P0B-01 / 02 |
| B-4 | 新增 P0D-00 和关口 O-02；标注时看不到未来结果；不确定的样本保留为“不确定” |
| C-2 | 授权路径中列出了 `database_service/gateway.py` |
| C-3 | §20 写明审查方不能是实施会话 |

**但 v0.2 还缺一块：除 EARLY 以外的周期层纠偏没有任何任务承接。** 新的弱转强线恰恰建立在这一层上。我建议补上这一项后，再批准 P0-A。补的位置在 P0-B / P0-C，不影响 P0-A 的内容，所以也可以先批准 P0-A，同时要求在 P0-B 开工前把它补进计划。

---

## 1. 我上一轮的错误（C-1）

上一轮 C-1 我写的是“`Desktop/ai_theme_app` 不是 git 仓库”。**这句是错的。**

我这次核对的结果：
- `Desktop/ai_theme_app/.git` 是一个**文件**，内容为 `gitdir: /Users/admin/glm-workspace/ai_theme_app/.git/worktrees/ai_theme_app`。也就是说，它是 `glm-workspace` 仓库的**链接工作区（worktree）**。
- 它当前所在的分支是 `feature/ai-theme-julia-domain-adapter-v1`，HEAD 为 `e1f1b9ad1e44af0edaba9543bc4868ae42f2382f`。
- 主仓库的 `main` 和 `origin/main` 都是 `ddc9442e88c5bf6f5248bfb141e74472c48eb25a`。

v0.2 的文件头写法是对的。

另外提醒一点：我们这几天写的审计和规划文档，都放在这个 worktree 的 `docs/` 下面。它们是一条功能分支上的**未跟踪文件**，不在 git 里。实施从 `origin/main` 开新分支时，这些文档不会自动带过去。如果要让实施会话能读到它们，需要单独决定放在哪里（例如另开一个只放文档的提交）。

---

## 2. 新发现：除 EARLY 以外的周期层纠偏没有任务承接（A 级）

### 2.1 现状

在 v0.2 中搜索 `SubjectCycleJudgement`、`score→state`、`fade_watch`、`CATCH_UP`、`ENDED`：除了“残差 `start` 不能当 EARLY”以外，**没有命中**。

两份清单里的周期层问题，在计划中的归属如下：

| 清单编号 | 问题 | v0.2 中的归属 |
|---|---|---|
| L3-01 / R1 DR-003 | 分数到阈值就换状态（60 / 65 / 75） | **无**（P0D-02 只替换“初期”） |
| L3-03 | `fade_watch → repair` 这条边，v0.6.4 中不存在 | **无** |
| L3-05 | 状态词汇：本地有 `fade_watch / fade_confirmed / dead / seed`，v0.6.4 有 FADE / CATCH_UP / ENDED，没有对应关系 | **无** |
| L3-08 / L3-09 | 周期状态未知时，`_playability` 默认“可交易 standard” | **无**（P0B-03 只处理大盘和情绪的未知） |
| L4-02 | 已确认主线的状态为 unknown 时，被标成“无人工确认主线” | **无** |
| v0.6.4 T13 | 补涨只在第 2 次分歧之后出现 | **无** |

### 2.2 为什么现在必须补

1. **弱转强线建立在这一层上。** P0G-03 要求“已确认主线 × 分歧 → 修复”，而分歧和修复就是由 `SubjectCycleJudgementService` 按分数阈值给出的。v0.2 在 P0G-03 里写了“分数推出的周期标签不能自动当成 canonical”，但**没有任何任务负责让它变得可以当成 canonical**。结果是：弱转强线做完 P0G-03 之后，只能停在“POLICY_UNFROZEN”。
2. **P0E-01a 的验收条件无法判定。** 它要求“题材 FADE 否决弱转强”，但代码里没有 FADE 这个状态，只有 `fade_watch` 和 `fade_confirmed`。哪一个算 FADE，或者两个都算，是一个语义映射问题，要先定下来。
   - 另外，弱转强评分现在把 `fade_watch` 打 75 分，高于分歧的 55 分（`w2s_candidate_service.py:194–205`）。映射不定下来，这条也没法判断是否违规。
3. **L3-08 / 09 是“缺失 → 可交易”，和 P0-B 修的是同一类问题。** 它现在之所以没有爆发，是因为许可层只吃已确认主线。等 P0E-01b 打开候选通路以后，它就会生效。

### 2.3 建议

**(1) 新增 P0B-06：周期层缺失即关闭。** 与 P0B-03 同批。
- 范围：`layer_b_lifecycle_adapter.py:63–64`、`:116` 的“未知 → 可交易”，以及 `mainline_environment_engine.py` 对 unknown 状态的错误标签。
- 只改缺失和未知的处理，不改状态判定。

**(2) 新增 P0C-03：周期词汇映射（需要 Owner 决定）。**
- 实施方先列出本地状态和 v0.6.4 状态的对应表，并附上每个本地状态在历史数据中的出现频次和典型样本。涉及的本地状态有：`seed`、`start`、`fermentation`、`acceleration`、`climax`、`divergence`、`repair`、`fade_watch`、`fade_confirmed`、`dead`。
- Tony 决定以下几件事：
  - `fade_watch` 对应 DIVERGENCE、FADE，还是另设一个观察子状态；
  - `fade_confirmed` 和 `dead` 是否分别对应 FADE 和 ENDED；
  - CATCH_UP 是否需要在本地补出；
  - `fade_watch → repair` 这条边是保留还是删除。
- **这一项是 P0E-01a 和 P0G-03 的前置条件。**
- 这一项**只需要做映射，不需要等 OP-06**：它不涉及“初期”的定义。

**(3) 新增 P0C-04（或并入 P0G-03 的前置）：分歧 / 修复判定的权威说明。**
- 弱转强需要的“分歧 → 修复”，目前由阈值 60 / 65 决定，这些阈值都是 POLICY_UNFROZEN。
- 计划需要明确一件事：在 OP-06 类似的回放和 Owner 决定完成之前，弱转强是**接受“POLICY_UNFROZEN 的分歧 / 修复标签 + 可审计的证据链”继续推进**，还是**也需要像 EARLY 一样先做回放和 Owner 决定**。
- 这是一个 Owner 选择。不写清楚的话，P0G-03 的实施方会在“停下来问”和“自己决定”之间两难。

修改后的依赖关系：

```text
P0-B（含新增 P0B-06）
   ├─→ P0C-01 → P0C-02 → P0D-00 → …（EARLY 线，不变）
   └─→ P0C-03 周期词汇映射【Owner】
            ├─→ P0E-01a
            └─→ P0C-04 分歧 / 修复权威【Owner 选择】→ P0G-03
```

---

## 3. 小问题

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| m-1 | §1 输入表 | 列入了 v0.1 的审计哈希，但审计结论本身是针对 v0.1 的 | 本审计（v0.2）落定后也补进表格，方便追溯 |
| m-2 | P0B-05 验收 | “候选数量可能下降，属于预期修正”，这一点是对的；但没有要求记录下降了多少 | 要求在回放中报告修正前后每天的候选数，以及被剔除的候选和原因，避免掩盖其他问题 |
| m-3 | Gate O-01 | 预警开关写成了二选一 | 合理。我同意推荐项 `DISABLE_UNTIL_P0B04_VERIFIED`。这仍然是 Tony 的运维决定，Claude 不会替你改配置 |

---

## 4. 状态

```text
v0.1 审计意见            = 全部落实
新增 A 级问题            = 1（除 EARLY 以外的周期层纠偏没有任务承接）
对 P0-A 的影响           = 无。P0-A 可以先批准
建议                    = 批准 v0.2 的 P0-A；在 P0-B 开工前，把 P0B-06、P0C-03、P0C-04 补进计划（v0.3）
运维                    = 同意先关闭弱转强预警循环，等 P0B-04 合并验证后再打开（Tony 决定）
```

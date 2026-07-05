# TEST CASE SPEC — M8.phase0

## 1. 测试层级与阻塞规则

执行顺序固定为：

```text
UT Knowledge/Evidence
-> UT Context/Cognition/Thesis
-> IT Notion Dual Layer
-> IT Shadow Replay
-> Existing DailyReviewV2/Notion Regression
```

- `TC-M8P0-T01-*` 失败时阻断全部后续测试。
- `TC-M8P0-T02-*` 失败时阻断 Notion 与 Replay。
- Notion 或 Replay 失败时不得进入七日阶段门禁。
- 所有测试使用真实业务对象与历史 snapshot 形状，禁止 mock 核心认知结果。

## 2. 需求覆盖矩阵

| TC-ID | Task | Level | Priority | 场景 | Acceptance |
|---|---|---|---|---|---|
| TC-M8P0-T01-01 | M8.phase0-T01 | UT | P0 | Bundle 正常构建与稳定 hash | ACPT-M8P0-001 |
| TC-M8P0-T01-02 | M8.phase0-T01 | UT | P0 | Evidence 映射及缺失语义 | ACPT-M8P0-002 |
| TC-M8P0-T02-01 | M8.phase0-T02 | UT | P0 | Context/Cognition/Thesis 主路径 | ACPT-M8P0-003 |
| TC-M8P0-T02-02 | M8.phase0-T02 | UT | P0 | 无足够证据时拒绝 unsupported thesis | ACPT-M8P0-003 |
| TC-M8P0-T03-01 | M8.phase0-T03 | IT | P1 | 同输入 replay hash 一致 | ACPT-M8P0-004 |
| TC-M8P0-T03-02 | M8.phase0-T03 | IT | P1 | 空/非法输入 fail closed | ACPT-M8P0-004 |
| TC-M8P0-T04-01 | M8.phase0-T04 | IT | P0 | 三种 render mode | ACPT-M8P0-005 |
| TC-M8P0-T04-02 | M8.phase0-T04 | IT | P0 | cognition 失败回退 legacy | ACPT-M8P0-005 |
| TC-M8P0-T05-01 | M8.phase0-T05 | RT | P1 | 七日 replay 与兼容回归 | ACPT-M8P0-006 |

## 3. 用例

### TC-M8P0-T01-01 — Bundle 稳定构建

- 输入：同一 trade_date、as_of、recap_doc 两次。
- 执行：`MarketKnowledgeBundleBuilder.build`。
- 预期：bundle ID/hash 一致；coverage 和 producer lineage 非空；输入对象未被修改。
- 失败：重算业务字段、hash 漂移、静默丢模块。

### TC-M8P0-T01-02 — Evidence 缺失语义

- 输入：包含 engine/theme 数据但缺失资金模块的 Bundle。
- 执行：`MarketEvidenceAdapter.build`。
- 预期：已有判断均有 EvidenceRef；缺失资金状态为 missing，不生成资金净额 0。
- 失败：用 `0`/`--` 伪装事实，或 EvidenceRef 缺失。

### TC-M8P0-T02-01 — 最小认知闭环

- 输入：禁止交易、主线可观察的 Evidence Snapshot。
- 执行：CLOSE Context -> Cognition -> Thesis。
- 预期：核心 Thesis、情景和权限均引用 Evidence；Hypothesis 包含 deadline/falsifier；内部状态码不进入展示文本。
- 失败：自由编造结论或缺引用。

### TC-M8P0-T02-02 — 证据不足

- 输入：coverage 不足且无关键 evidence。
- 执行：Thesis 构建。
- 预期：返回 unavailable diagnostics 或“无法判定”，不生成确定性命题。
- 失败：生成无引用 Thesis。

### TC-M8P0-T03-01 — Replay 确定性

- 输入：同一历史 snapshot payload。
- 执行：两次 `MarketCognitionReplay.run`。
- 预期：Bundle/Evidence/Context/Thesis hash 全部一致；正式 Decision 输入输出未变。

### TC-M8P0-T03-02 — Replay 失败隔离

- 输入：空 payload、缺 trade_date、错误 schema。
- 执行：Replay。
- 预期：结构化 failed diagnostics；不返回 ready Thesis。

### TC-M8P0-T04-01 — Notion 三模式

- 输入：有效 legacy blocks 与 ready Thesis。
- 执行：分别以三种模式渲染。
- 预期：legacy_only 与原输出一致；shadow 不发布首页；dual_layer 先 Thesis 后原证据。

### TC-M8P0-T04-02 — Notion 回退

- 输入：非法/缺失 Thesis。
- 执行：dual_layer 渲染。
- 预期：输出与 legacy_only 一致，不出现空认知标题。

### TC-M8P0-T05-01 — 七日阶段门禁

- 输入：7/2、7/3 与至少 5 个历史 snapshot fixture。
- 执行：replay + regression。
- 预期：unsupported claim、future leak、Decision diff、旧证据减少均为 0。

## 4. 必跑命令

```bash
.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_knowledge_evidence.py
.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_cognition.py
.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_notion_dual_layer.py
.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_m8_phase0_replay.py
.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_post_market_daily_review_v2_builder.py stock_processing_service/tests/unit/test_notion_post_market_recap_publisher.py
```

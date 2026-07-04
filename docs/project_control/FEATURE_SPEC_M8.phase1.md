# FEATURE SPEC — M8.phase1 Cognitive Validation

## Task M8.phase1-T01 — Validation Contract

### 子功能分解

- `F-T01-01` 枚举：输入 label/failure type；校验固定枚举；非法值拒绝；证据为异常类型。
- `F-T01-02` Record：输入各层 hash、confidence、reason、outcome、refs；输出 frozen record；缺字段 fail fast；证据为 record hash。
- `F-T01-03` Temporal Guard：输入 thesis as_of/reality available_at；要求前者严格早于后者；未来泄漏拒绝；证据为时间字段。

接口：`MarketThesisValidationRecordBuilder.build(...)`。
回滚：删除新增契约，不影响 Phase 0。

## Task M8.phase1-T02 — Append-only Dataset

### 子功能分解

- `F-T02-01` 年/月目录路由；输入 verification date；输出确定路径；非法日期拒绝。
- `F-T02-02` 原子 append；新记录 create-only；重复 hash skip；冲突拒绝。
- `F-T02-03` Dataset Reader；按日期读取；校验 schema/hash；损坏记录 fail fast。
- `F-T02-04` Manifest Integrity；扫描 immutable records，核对记录数、聚合 hash 与 manifest hash；manifest 为可重建索引，不作为事实真源。

接口：`MarketThesisValidationDataset.append/read/list_records/refresh_manifest/verify_manifest`。
回滚：停止 writer，保留 immutable records。

## Task M8.phase1-T03 — Verification Workflow

### 子功能分解

- `F-T03-01` Yesterday Thesis Source；只接受已冻结 Thesis/hash。
- `F-T03-02` Today Reality；只接受 verification time 前可用 Evidence。
- `F-T03-03` Reviewer Verdict；显式录入 label/reason/failure type，禁止模型自动确认为 Ground Truth。

接口：`MarketThesisVerificationService.verify(...)`。
回滚：停止录入，不修改既有记录。

## Task M8.phase1-T04 — Metrics

### 子功能分解

- `F-T04-01` Binary Accuracy；只统计 YES/NO。
- `F-T04-02` Brier；YES=1、NO=0、PARTIAL=0.5，排除 UNVERIFIABLE。
- `F-T04-03` ECE；固定 bin，输出样本数与误差。
- `F-T04-04` Timing Offset / Delay Accuracy；统计实际兑现相对目标验证日的交易日偏移，区分方向错误与时点错误。

接口：`MarketThesisValidationMetrics.compute(records)`。
回滚：重新计算，不修改原记录。

## Task M8.phase1-T05 — 20-day Shadow

### 子功能分解

- `F-T05-01` 每日生成待验证项。
- `F-T05-02` 次日验证与审计。
- `F-T05-03` 每日 replay/metrics，20 日后阶段验收，持续积累至 100 日。

禁止：Belief、Learning、Memory、Decision 写入。

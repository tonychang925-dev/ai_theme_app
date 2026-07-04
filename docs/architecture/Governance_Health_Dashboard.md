# AI Theme App Governance Health Dashboard

> 版本：v1.0
> 状态：Measurement Bootstrap
> 总体基线：Architecture Baseline v4.0
> 数据原则：No measurement, no green

---

## 0. 状态定义

| 状态 | 含义 |
|---|---|
| GREEN | 指标已自动或可复现测量，且达到门槛 |
| AMBER | 已测量但接近/超过警戒线，或已有整改计划 |
| RED | P0 门禁失败、连续超限、无 Owner 或无回滚 |
| GRAY | 尚未接入数据，不能判断 |

总体状态不能优于任一 P0 Governance 指标的最差状态。

---

## 1. Current Executive View

> 截止：2026-07-04
> 当前总体状态：`GRAY — KPI automation not yet implemented`

| 维度 | 状态 | 当前值 | 目标 | 说明 |
|---|---|---:|---:|---|
| Baseline Status | GREEN | FROZEN | FROZEN | v4.0 已正式冻结 |
| Stable Core Object Count | GREEN | 5 | <=5 | 以当前基线文档计数，待接 Schema Registry |
| Review SLA | GRAY | N/A | L2<=2d, L3<=3d | 尚无运行样本 |
| ADR Queue | GRAY | N/A | 无超时 P0 | 尚未接自动队列 |
| Replay Coverage | GRAY | N/A | Gold 100% | Phase 0 尚未建立统一基准 |
| Evidence Lineage Coverage | GRAY | N/A | 100% | Evidence Adapter 尚未实现 |
| Thesis Evidence Coverage | GRAY | N/A | 100% | Thesis 尚未实现 |
| Quality Propagation | GRAY | N/A | 100% | Quality audit 尚未实现 |
| Freeze Violations | GREEN* | 0 observed | 0 | 当前为文档审计，未自动化 |
| Phase 0 Scope Leakage | GREEN* | 0 observed | 0 | 尚无 Phase 0 实现 PR |
| Shadow Aging | GRAY | N/A | 0 overdue | 尚未进入 Shadow |
| Governance Blocking Ratio | GRAY | N/A | <10% | 尚无 Review 数据 |

`GREEN*` 表示人工可见状态，不等同于自动门禁已完成。

---

## 2. Health Domains

### 2.1 Architecture Integrity

| KPI | 计算方式 | GREEN | AMBER | RED |
|---|---|---:|---:|---:|
| Stable Core Object Count | Schema Registry 顶层 Core 数 | <=5 | 6 | >6 |
| Duplicate Producer Count | 同语义 ACTIVE producer 数 - 1 | 0 | 1 且有整改 | >=1 无整改 |
| Unowned P0/P1 Capability | 无 Owner capability 数 | 0 | 1 临时 Owner | >=1 无 Owner |
| Baseline Change Count | 冻结期顶层变更数 | 0 | 紧急且有 ADR | 未批准变更 |

### 2.2 Review Flow

| KPI | GREEN | AMBER | RED |
|---|---:|---:|---:|
| L2 Median Decision Time | <=2 工作日 | >2 且 <=3 | >3 |
| L3 Median Decision Time | <=3 工作日 | >3 且 <=5 | >5 |
| Review Timeout Count | 0 | 1 | >1 |
| ADR Queue P0 Aging | 0 超期 | 1 超期 | >1 超期 |
| Governance Blocking Ratio | <10% | 10%-20% | >20% |

### 2.3 Migration Safety

| KPI | GREEN | AMBER | RED |
|---|---:|---:|---:|
| Replacement without Shadow | 0 | — | >0 |
| Unexplained P0 Shadow Diff | 0 | — | >0 |
| Rollback Drill Success | 100% | 单次失败已修复 | 无可用回滚 |
| Shadow Aging | 0 overdue | 有 Owner/期限 | 无 Owner |
| Deprecated Aging | 0 overdue | 有豁免 | 无计划 |

### 2.4 Cognition Quality

| KPI | GREEN | AMBER | RED |
|---|---:|---:|---:|
| Evidence Lineage Coverage | 100% | 98%-<100% | <98% |
| Thesis Evidence Coverage | 100% | 98%-<100% | <98% |
| Unsupported Claim | 0 | — | >0 |
| Quality Propagation Compliance | 100% | 98%-<100% | <98% |
| Replay Success — Gold | 100% | — | <100% |
| Replay Success — Rolling | >=98% | 95%-<98% | <95% |

### 2.5 Phase 0 Delivery Health

| KPI | GREEN | AMBER | RED |
|---|---:|---:|---:|
| Scope Leakage | 0 | 1 已移出 | >1 |
| Active L3 ADR | <=1 | 2 | >2 |
| Active L2 Changes | <=3 | 4 | >4 |
| Notion Homepage Direct Value | 100% tasks mapped | 90%-<100% | <90% |
| Legacy Report Regression | 0 | — | >0 |

---

## 3. Overall Health Algorithm

```text
if any P0 metric == RED:
    overall = RED
elif any domain has 2+ AMBER:
    overall = AMBER
elif measured_coverage < 80%:
    overall = GRAY
else:
    overall = GREEN
```

`measured_coverage`：

```text
number of KPI with reproducible value
/
number of required KPI
```

不得将 GRAY 当作 GREEN。

---

## 4. Data Sources

| 数据 | 建议来源 |
|---|---|
| Core Object Count | Schema Registry |
| Producer/Owner/Criticality | Capability Registry |
| Review SLA | PR/ADR timestamps |
| ADR Queue | ADR Index/status |
| Shadow/Deprecated Aging | Migration/Deprecation Register |
| Replay | Replay runner JSON |
| Evidence Coverage | Evidence validator |
| Thesis Coverage | Thesis claim validator |
| Quality Propagation | Quality audit |
| Freeze Violation | changed files + accepted ADR mapping |
| Scope Leakage | Phase 0 task -> Notion homepage mapping |

---

## 5. Automation Contract

建议日级产物：

```json
{
  "generated_at": "ISO-8601",
  "baseline": "v4.0",
  "overall_status": "GRAY",
  "measured_coverage": 0.0,
  "domains": {
    "architecture_integrity": {},
    "review_flow": {},
    "migration_safety": {},
    "cognition_quality": {},
    "phase0_delivery": {}
  },
  "violations": [],
  "owners": {},
  "source_artifacts": []
}
```

文件：

```text
tmp/architecture_kpi_daily.json
tmp/governance_health_daily.json
docs/project_control/reports/governance-health-YYYY-MM.md
```

---

## 6. Chief Architect View

Dashboard 首页只显示：

```text
Architecture Health
Review SLA
ADR Queue
Replay Coverage
Evidence Coverage
Freeze Violations
Phase 0 Scope Leakage
Top 3 Actions
```

示例格式：

```text
Architecture Health      GRAY
Review SLA               GRAY
ADR Queue                GRAY
Replay Coverage          GRAY
Evidence Coverage        GRAY
Freeze Violations        0 observed
Phase 0 Scope Leakage    0 observed

Top Actions:
1. 建立 Replay gold set
2. 接入 Capability Registry
3. 生成首份自动 KPI JSON
```

---

## 7. Review Cadence

每日：

- Freeze violation；
- Replay；
- Evidence/Thesis coverage；
- Phase 0 scope。

每周：

- Review SLA；
- ADR queue；
- Shadow/Deprecated aging；
- Blocking ratio。

每月：

- Stable Core count；
- Capability ownership；
- KPI 趋势；
- Governance 流程是否需要简化。

---

## 8. Health Escalation

RED：

1. 停止扩大 Shadow/Migration；
2. 指定 Owner；
3. 建立 P0/P1 修复任务；
4. 必要时回到 `legacy_only`；
5. ARB 只处理该故障，不讨论新增能力。

AMBER：

1. 记录原因和期限；
2. 不阻塞无关 Phase 0 任务；
3. 连续两周期 AMBER 升级 Review。

GRAY：

1. 建立测量，不做结果推断；
2. 不因“未发现问题”标记 GREEN。

---

## 9. Dashboard Anti-Patterns

禁止：

- 手工填 GREEN 代替自动证据；
- 删除失败 Replay 提高成功率；
- 降低 required source 提高 Quality；
- 关闭 Shadow diff 告警降低差异数；
- 将等待业务实现计入 Governance blocking；
- 用 ADR 数量衡量架构质量。

---

## 10. Initial Automation Backlog

1. 从 Capability Registry 生成 Owner/Criticality 指标；
2. 从 Schema Registry 生成 Core Object Count；
3. 从 ADR metadata 生成 Queue/Aging；
4. 从 replay JSON 生成 Coverage/Success；
5. 从 Evidence validator 生成 Lineage Coverage；
6. 从 Thesis validator 生成 Claim Coverage；
7. 从 Git diff + ADR mapping 检查 Freeze Violation；
8. 生成日级 JSON 和月度 Markdown。

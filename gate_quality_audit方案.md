# gate_quality_audit方案

# 一、先定目标：`gate_quality_audit` 要解决什么问题

这套审计器不是重新生成 gate，而是回答 5 个问题：

1. 这条 gate 的 **must 是否过泛**
2. 它和相邻题材 **是否容易串召回**
3. 它在真实新闻测试里 **误召回是否偏高**
4. 它的 gate 结构 **是否稳定、是否偏题**
5. 它应该：
    - 直接保留
    - 轻修
    - 重做
    - 人工复核

所以它本质上是一个 **质量诊断与分流系统**。

---

# 二、建议新增 3 张表

## 1. `gate_quality_audit`

每个题材一条总诊断记录。

```
createtableifnotexists gate_quality_audit (
  id bigserialprimarykey,
  subject_key textnotnull,
  subject_name textnotnull,
  strategy_type textnotnulldefault'',

  must_countintnotnulldefault0,
  should_countintnotnulldefault0,
  not_countintnotnulldefault0,

  generic_must_scorenumeric(8,4)notnulldefault0,
  specificity_scorenumeric(8,4)notnulldefault0,
  separability_scorenumeric(8,4)notnulldefault0,
  coverage_scorenumeric(8,4)notnulldefault0,
  confusability_scorenumeric(8,4)notnulldefault0,
  stability_scorenumeric(8,4)notnulldefault0,
  overall_scorenumeric(8,4)notnulldefault0,

  must_shared_rationumeric(8,4)notnulldefault0,
  must_title_align_scorenumeric(8,4)notnulldefault0,
  evidence_diversity_scorenumeric(8,4)notnulldefault0,
  not_effectiveness_scorenumeric(8,4)notnulldefault0,

  risk_level textnotnulldefault'',
  risk_flags jsonbnotnulldefault'[]'::jsonb,
  suggested_action textnotnulldefault'',
  top_confused_subjects jsonbnotnulldefault'[]'::jsonb,
  notes textnotnulldefault'',

  audit_version textnotnulldefault'gate_audit.v1',
  created_at timestamptznotnulldefault now(),
  updated_at timestamptznotnulldefault now(),

unique (subject_key)
);
```

---

## 2. `gate_neighbor_confusion`

每个题材和近邻题材一条关系记录。

```
createtableifnotexists gate_neighbor_confusion (
  id bigserialprimarykey,
  subject_key textnotnull,
  subject_name textnotnull,
  neighbor_subject_key textnotnull,
  neighbor_subject_name textnotnull,

  must_overlap_countintnotnulldefault0,
  must_overlap_terms jsonbnotnulldefault'[]'::jsonb,
  should_overlap_countintnotnulldefault0,
  should_overlap_terms jsonbnotnulldefault'[]'::jsonb,

  title_similaritynumeric(8,4)notnulldefault0,
  ontology_similaritynumeric(8,4)notnulldefault0,
  gate_similaritynumeric(8,4)notnulldefault0,

  confusion_scorenumeric(8,4)notnulldefault0,
  conflict_reason jsonbnotnulldefault'[]'::jsonb,

  created_at timestamptznotnulldefault now()
);
```

---

## 3. `gate_match_backtest_stats`

把真实新闻匹配测试结果回流到 gate。

```
createtableifnotexists gate_match_backtest_stats (
  id bigserialprimarykey,
  subject_key textnotnull,
  subject_name textnotnull,

  total_hit_countintnotnulldefault0,
  true_positive_countintnotnulldefault0,
  false_positive_countintnotnulldefault0,
  false_negative_countintnotnulldefault0,

  precision_scorenumeric(8,4)notnulldefault0,
  recall_scorenumeric(8,4)notnulldefault0,
  f1_scorenumeric(8,4)notnulldefault0,

  common_confused_subjects jsonbnotnulldefault'[]'::jsonb,
  common_false_positive_events jsonbnotnulldefault'[]'::jsonb,

  created_at timestamptznotnulldefault now(),
  updated_at timestamptznotnulldefault now(),

unique (subject_key)
);
```

---

# 三、`gate_quality_audit` 的核心评分设计

下面这 6 个分最重要。

---

## 1. `generic_must_score`

衡量 must 是否过泛。

### 核心逻辑

如果 must 词在全库里反复出现，它就不够像“门禁锚点”。

### 算法建议

先统计全库每个 must 的出现次数：

```
term_subject_freq(term) = 包含该 must 的题材数
```

然后对单个题材：

```
generic_must_score =
  avg( min(1.0, log(1 + term_subject_freq(term)) / log(1 + max_freq)) )
```

### 解释

- 越接近 1，说明 must 越泛
- 越接近 0，说明 must 越专

### 风险 flag

- `GENERIC_MUST`
- `MUST_TOO_COMMON`

---

## 2. `specificity_score`

衡量 gate 的专属性，和 `generic_must_score` 相反。

### 简化公式

```
specificity_score = 1 - generic_must_score
```

也可以加入 title 对齐：

```
specificity_score =
  0.7 * (1 - generic_must_score)
+ 0.3 * must_title_align_score
```

---

## 3. `separability_score`

衡量和近邻题材能不能区分开。

### 算法建议

对每个题材找 topN 近邻题材，然后比较：

- must 重叠率
- should 重叠率
- not 是否具备排斥作用

```
must_jaccard = |must_a ∩ must_b| / |must_a ∪ must_b|
should_jaccard = |should_a ∩ should_b| / |should_a ∪ should_b|
```

近邻越像、重叠越高，`separability_score` 越低。

### 结果解释

- 高分：边界清晰
- 低分：容易串题材

### 风险 flag

- `LOW_SEPARABILITY`
- `NEIGHBOR_COLLISION`

---

## 4. `coverage_score`

衡量 must 的证据覆盖是否足够广。

你脚本里 gate 依赖抽样知识块、children、events、knowledge_terms。

所以需要看 must 是否只来自单一证据面。

### 建议统计

对每个 must，检查它在这些来源中是否出现：

- core
- related
- signal
- children
- events

### 简化评分

```
coverage_score = 覆盖来源种类数 / 5
```

### 风险 flag

- `LOW_EVIDENCE_DIVERSITY`
- `SINGLE_SOURCE_GATE`

---

## 5. `confusability_score`

衡量在真实新闻测试中，这条 gate 是否老是误召回。

### 来源

直接用你的全量题材新闻匹配测试回流。

### 公式建议

```
confusability_score =
  false_positive_count / max(total_hit_count, 1)
```

也可以混入近邻冲突：

```
confusability_score =
  0.6 * false_positive_rate
+ 0.4 * neighbor_confusion_score
```

### 风险 flag

- `HIGH_FALSE_POSITIVE`
- `FREQUENT_CONFUSION`

---

## 6. `stability_score`

衡量 gate 重跑是否稳定。

你现在脚本有采样、有事件截取、有 knowledge_texts 抽样。

这意味着 gate 有漂移风险。

### 做法

对每个题材做 3 次重跑，改变：

- knowledge sample
- events sample
- children 采样顺序

然后计算 must 重叠率：

```
stability_score = 平均两两 must Jaccard
```

### 风险 flag

- `UNSTABLE_MUST`
- `ANCHOR_DRIFT`

---

# 四、还要补 4 个派生分

这 4 个不是主分，但很重要。

---

## 1. `must_title_align_score`

衡量 must 和题材名称是否真正对齐。

你脚本 prompt 里已经强调“题材名称是首要语义约束”，但还缺程序复核。

### 建议打分

按以下规则累计：

- must 直接包含题材名核心词：+1
- must 与 concept 高度一致：+1
- must 与 children/core entities 对齐：+1

归一到 0~1。

---

## 2. `must_shared_ratio`

```
must_shared_ratio = 共享 must 数 / must_count
```

如果大部分 must 都是共享词，风险极高。

---

## 3. `evidence_diversity_score`

比 coverage 更细一点，强调 must 的来源是否多样。

---

## 4. `not_effectiveness_score`

衡量 not 是否真的有边界作用。

### 算法建议

看近邻题材独有术语中，有多少被纳入当前题材的 not。

如果 not 完全无法排斥近邻，分就低。

---

# 五、总分和分级建议

## `overall_score`

建议这样算：

```
overall_score =
  0.22 * specificity_score
+ 0.22 * separability_score
+ 0.18 * coverage_score
+ 0.18 * (1 - confusability_score)
+ 0.10 * stability_score
+ 0.10 * must_title_align_score
```

---

## 风险分级

### A 档：必须重做

满足任一：

- overall_score < 0.45
- specificity_score < 0.35
- separability_score < 0.35
- confusability_score > 0.60

### B 档：半自动回炉

- overall_score 0.45 ~ 0.65
- 有明显 risk_flags，但不是灾难级

### C 档：轻修

- overall_score 0.65 ~ 0.80

### D 档：保留

- overall_score >= 0.80

---

# 六、`suggested_action` 建议枚举

```
KEEP
LIGHT_FIX
REBUILD
MANUAL_REVIEW
```

### 触发规则

- `KEEP`：高分、低冲突
- `LIGHT_FIX`：主要是 should/not 轻修
- `REBUILD`：must 过泛、近邻冲突严重
- `MANUAL_REVIEW`：高价值题材但模型多次不稳定

---

# 七、批量处理脚本框架建议

建议新建：

## `gate_quality_audit.py`

### 输入

- `subject_gates/*.json`
- 题材基础信息
- 全量新闻匹配测试结果
- 可选：题材 ontology/profile 文件

### 输出

- `gate_quality_audit.jsonl`
- `gate_neighbor_confusion.jsonl`
- `gate_quality_report.md`

---

## 脚本结构建议

```
classGateAuditLoader:
defload_gates(...)
defload_match_results(...)
defload_subject_profiles(...)

classGateStaticAuditor:
defbuild_global_term_freq(...)
defscore_generic_must(...)
defscore_specificity(...)
defscore_title_align(...)
defscore_coverage(...)

classGateNeighborAuditor:
defbuild_subject_embeddings(...)
deffind_neighbors(...)
defcompute_neighbor_overlap(...)
defcompute_separability(...)

classGateBacktestAuditor:
defaggregate_match_stats(...)
defcompute_confusability(...)

classGateStabilityAuditor:
defrerun_sampling(...)
defcompute_stability(...)

classGateAuditReporter:
defmerge_scores(...)
defassign_risk_level(...)
defassign_suggested_action(...)
defwrite_jsonl(...)
defwrite_markdown_report(...)
```

---

# 八、首版处理流程建议

## Step 1：加载全部 gate

读取：

- must
- should
- not
- strategy_type
- semantic_type
- source_type

## Step 2：全库词频统计

构建：

- must 全库频次
- should 全库频次

## Step 3：静态分打分

输出：

- generic_must_score
- specificity_score
- must_title_align_score
- coverage_score

## Step 4：近邻分析

对每个题材找 top10 近邻题材，输出：

- must_overlap
- should_overlap
- confusion_score

## Step 5：回流真实测试结果

聚合每个题材：

- TP / FP / FN
- precision / recall / F1
- 常见混淆题材

## Step 6：稳定性抽检

优先对：

- A/B 档
- 热门主线题材
做多次重跑

## Step 7：输出总表

写入 `gate_quality_audit`

---

# 九、首版风险 flags 清单

建议固定这些：

```
GENERIC_MUST
MUST_TOO_COMMON
LOW_SEPARABILITY
NEIGHBOR_COLLISION
LOW_EVIDENCE_DIVERSITY
SINGLE_SOURCE_GATE
HIGH_FALSE_POSITIVE
FREQUENT_CONFUSION
UNSTABLE_MUST
ANCHOR_DRIFT
STRATEGY_TYPE_SUSPECT
WEAK_NOT_BOUNDARY
TITLE_NOT_ALIGNED
```

---

# 十、报告输出建议

## 1. 总报告

输出：

- 635 条 gate 的分布
- A/B/C/D 档数量
- top20 高风险题材
- top20 误召回最多题材
- top20 近邻冲突最严重题材

## 2. 单题材诊断卡

每条高风险题材显示：

- must / should / not
- 风险 flags
- top confused subjects
- 建议动作

---

# 十一、你现在最该先实现哪一版

我建议你先做 **v1 审计器**，只做这 5 项：

1. `generic_must_score`
2. `specificity_score`
3. `separability_score`
4. `confusability_score`
5. `overall_score + risk_level`

先别一上来做 stability 全量重跑，那会慢。

---

# 十二、和你现有脚本的衔接点

你当前生成脚本里已经有足够多的信息可复用：

- `strategy_type`
- `semantic_type`
- `must/should/not`
- `evidence_refs`
- `primary_anchor / secondary_anchor` 的来源逻辑
- `hard_fail` 规则。

所以审计器不需要大改生成器，先作为**后处理层**挂上去就行。
# Broad Theme Risk Control
`泛主题风险治理`

## 1. 背景
- 泛词题材本身不必然有问题，真正的风险在于它们在运行时会通过 `event_subject_map + structured_theme_match + direct_theme_name_hit + v1_fallback` 被抬成高置信 `MATCH`。
- 5/31 的真实事故已经证明，`A股全球第一 / 新疆自贸区 / 深海经济` 这类题材会在这条链路上产生错配。
- 因此治理目标不是删除泛词题材，而是阻止泛题材裸直命中自动放行。

## 2. 核心原则
- `direct_theme_name_hit` 只做候选召回，不做最终放行。
- `MATCH` 必须满足 `hard_anchor + action_terms + entity_boundary`。
- `P0` 题材默认 `review-first`，但不是永久禁用题材。
- 对 `P0` 来说，裸 `direct_theme_name_hit` 不能直接 `MATCH`。

## 3. 风险分层
### P0
必须优先收紧，但不是禁用题材。
- `VR`
- `AI产业链五大核心`
- `农业新质生产力`
- `汽车国企`
- `A股全球第一`

### P1
宽题材，但先观察。
- `物流`
- `宁德产业链`
- `国企改革`

### P2
暂时观察。
- `原子级制造`
- `季戊四醇产业链`
- `中美芬太尼合作`

## 4. 运行时门禁
### 4.1 裸直命中规则
- `P0 + direct_theme_name_hit + 缺少 hard_anchor/action_terms/entity_boundary`
  - `HUMAN_REVIEW`
- `P0 + hard_anchor + action_terms + entity_boundary`
  - 可以 `MATCH`

### 4.2 v2 前置条件
- `P0` 题材如果没有 `theme_profile_v2 accepted_candidate`
- 且 `runtime_source = v1_fallback`
- 且 `match_reason = direct_theme_name_hit`
- 则不能直接 `MATCH`，只能 `HUMAN_REVIEW`

## 5. Reason Code
建议统一拆分为：
- `broad_theme_direct_hit_review`
- `broad_theme_missing_hard_anchor`
- `broad_theme_missing_action_terms`
- `broad_theme_v1_fallback_review`

## 6. Hard-negative 设计
每个 `P0` 至少 3 条：
- 泛词误召回
- 邻近题材误召回
- 历史错配 / 模拟错配

### VR
- AI眼镜新闻不得误配 VR
- AR/MR 头显不得裸误配 VR
- 游戏/娱乐内容新闻不得误配 VR

### AI产业链五大核心
- 单一大模型应用不得误配
- 单一算力新闻不得误配 umbrella 题材
- AI政策泛表述不得误配

### 农业新质生产力
- 普通乡村振兴不得误配
- 农产品价格 / 粮食安全不得误配
- 普通农机新闻不得误配，除非出现智能化 / 无人化 / 产业化动作

### 汽车国企
- 普通新能源汽车政策不得误配
- 普通车企销量不得误配
- 普通国企改革不得误配，必须是国企车企改革动作

### A股全球第一
- 行业排名 / 全球领先 / 国内第一 等口号不得裸触发
- 产业链新闻不得因“第一/领先”误配
- 企业宣传类新闻不得误配

## 7. 日报 Watchlist
日报必须输出题材级明细，不只输出总数。

建议字段：
- `subject_key`
- `theme_name`
- `risk_tier`
- `match_count`
- `review_count`
- `direct_theme_name_hit_count`
- `v1_fallback_direct_hit_count`
- `bad_count`
- `top_bad_examples`
- `suggested_action`

## 8. 执行阶段
### Phase BTRC-1: Broad Theme Risk Audit
- 产出 `P0/P1/P2` 清单
- 统计每个题材的 `runtime_source / direct_hit / v1_fallback / bad_count / review_count`

### Phase BTRC-2: P0 runtime guard
- 先加运行时门禁
- 让 `P0` 裸直命中只能进复核，不直接 `MATCH`

### Phase BTRC-3: P0 hard-negative
- 每个 `P0` 补至少 3 条 hard-negative
- 纳入 validator

### Phase BTRC-4: P0 v2 accepted_candidate
- 先补：
  - `VR`
  - `AI产业链五大核心`
  - `农业新质生产力`
  - `汽车国企`
  - `A股全球第一`

### Phase BTRC-5: 日报 watchlist
- 输出题材级明细
- `bad_count > 0` 再进入 delta repair

## 9. 验收指标
- `P0 direct_theme_name_hit_bad_count = 0`
- `P0 v1_fallback_direct_hit_bad_count = 0`
- `P0 target_wrong_theme_residual_count = 0`
- `P0 bad_count > 0` 立即触发 delta repair
- `P0 v1_fallback_direct_hit_count > 0` 且 `match_count > 0` 必须进入复核

## 10. 回滚原则
- 只回滚单个 `P0` 的 runtime 规则或 `v2` 补丁
- 不影响其他题材
- 不影响 feed dedupe
- 不影响 quarantine 机制

## 11. 当前优先级
### 先修 `P0`
- `VR`
- `AI产业链五大核心`
- `农业新质生产力`
- `汽车国企`
- `A股全球第一`

### 先观察 `P1`
- `物流`
- `宁德产业链`
- `国企改革`

### 暂不动 `P2`
- `原子级制造`
- `季戊四醇产业链`
- `中美芬太尼合作`


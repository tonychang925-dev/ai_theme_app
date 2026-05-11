# 研选荐股 — 问题背景、方案探索与总结

> 2026-05-11

---

## 一、问题背景

### 1.1 目标

实现"研选荐股"功能：输入一篇研报/新闻文本，自动推荐相关股票。对标财联社"研选"栏目的荐股能力。

**典型输入示例：**

> 【研选】公司多项AI算力光纤光缆产品取得突破性进展，并已完成800G高速光模块批量出货；光纤行业进入量价齐升的历史大周期，公司一季度实现业绩与盈利能力显著改善。

> 我国日均词元调用量飙涨超千倍，算力租赁千亿大市场来了。机构建议关注国产算力基础设施产业链4大细分领域，这家公司积极参与了全国多个算力中心建设，另一家为智谱AI提供底层算力支持。

### 1.2 已有基础设施

| 数据层 | 内容 | 规模 |
|--------|------|------|
| `theme_gate_profile` | JYHF题材画像：概念名、门控词（must/strong/negative）、搜索文本 | 4,000+ 题材 |
| `theme_stock_map` | 题材→股票映射，含关系类型（leader/core/member） | 31,562 条 |
| `stock_lightspots` | 股票亮点句（JYHF原始数据） | 51,686 条 / 4,288 只 |
| `stock_facts` | 结构化事实（DeepSeek从detail_html提取） | 51,362 条 / 1,722 只 |
| `stock_profile_ext` | 股票embedding向量（text2vec-base-chinese, 768维） | 已有 |
| `subject_stock_detail_staging` | 股票详情：定位(remark)、详情HTML | 已有 |
| `ThemeMatchEngine` | 现有题材匹配引擎（Dense Recall + Rerank + Gate + LLM Judge） | 96% top-1准确率 |

### 1.3 核心约束

- 不修改已有组件代码
- 不允许降级/兜底处理（必须真实LLM调用）
- LLM调用次数尽可能少
- 能处理JYHF主题映射覆盖不全的情况

---

## 二、探索过的方案

### 方案A：从零构建 stock_facts → embedding 匹配

**思路：** 先提取所有股票的 stock_facts，生成 embedding，再与新闻事件做语义匹配。

**过程：**
1. 发现 stock_facts 仅覆盖 1,722/5,135 只股票（DeepSeek API 提取，51,362 条）
2. 尝试用本地 Qwen2.5 1.5B（Q5_K_M量化）替代 DeepSeek 提取 facts
   - 测了 detail_html 输入：每只仅提取2条，类型错分（"白酒龙头"标为main_business），95秒/只
   - 测了 lightspots 输入：同样差，速度无改善
3. 尝试纯规则从 lightspots 提取：噪声太大（"液体金字塔"→产品）

**结论：** Qwen2.5 1.5B 能力不足以做结构化事实提取。规则提取精度太低。

---

### 方案B：lightspots 直接替代 stock_facts 做 embedding

**思路：** 跳过 stock_facts，直接用 stock_lightspots 生成 profile_text → embedding → 语义匹配。

**验证：** 对同一只股票，分别用 stock_facts 和 lightspots 生成 embedding，对比余弦相似度和最近邻。

| 指标 | 结果 |
|------|------|
| 同股票两者embedding余弦相似度 | 0.80-0.87 |
| Top-5 至少3个重合 | 73% |
| Top-5 至少1个重合 | 100% |

**结论：** lightspots 可以替代 stock_facts 做语义匹配。覆盖可从 1,722 提升到 4,288。但整体匹配链路仍需从零构建。

---

### 方案C：利用已有 theme_stock_map 查表（最终采用方向）

**思路：** JYHF 已经做好了题材→股票映射。不需要从零做 embedding 匹配。流程简化为：

```
研报文本 → LLM提取主题 → 查theme_stock_map → 候选股票 → LLM核查 → 精选输出
```

**实现：** `StockRecommendService`（新增模块，不修改已有代码）

**架构演进：**

| 版本 | LLM调用 | 核心问题 |
|------|---------|---------|
| v1 逐只核查 | 1提取 + 21核查 = 22次 | LLM调用过多 |
| v2 批量核查 | 1提取 + 1批量 = 2次 | max_tokens=600截断JSON |
| v3 fix截断 | 2次（max_tokens=2000） | 算力事件结果偏到"算力租赁" |
| v4 fix提取偏置 | 2次 | 提取正确（国产算力），但优刻得/紫光不在该主题映射中 |
| v5 加token分词匹配 | 2次 | 分词引入大量噪声（"AI"匹配到"AI光纤"等无关主题） |
| v6 加STOP词过滤 | 2次 | 仍无法解决语义鸿沟 |

---

### 方案D：早期数据探索（被否）

| 探索 | 结论 |
|------|------|
| Qwen2.5 1.5B 替代 DeepSeek 提取 facts | 质量太差，不可用 |
| 纯规则从 lightspots 提取 facts | 噪声太多 |
| lightspots 直接做 embedding 匹配 | 方向可行但链路需重建 |
| `theme_master` 表 | 已废弃，实际用 `theme_gate_profile` + `theme_profile_ext` |

---

## 三、方案对比

| 维度 | A: stock_facts embedding | B: lightspots embedding | C: theme_stock_map查表 |
|------|--------------------------|-------------------------|----------------------|
| 股票覆盖 | 需先提取facts（1722→3413缺口） | 4,288只 | 5,151只（全量） |
| 匹配方式 | 语义embedding | 语义embedding | 精确查表+LLM核查 |
| LLM调用 | 3386次（每只提取facts） | 0（纯embedding） | 2次 |
| API成本 | ~27元（DeepSeek） | 0 | ~0.002元 |
| 精度 | 依赖提取质量 | 依赖embedding质量 | 依赖JYHF映射质量 |
| 可解释性 | 低（向量相似度） | 低 | 高（可追溯主题→股票映射链） |
| 能否找到映射遗漏股 | 能（语义匹配） | 能（语义匹配） | **不能**（依赖映射表） |

---

## 四、结论

### 4.1 已验证可行

**2次LLM调用 + theme_stock_map查表架构**，在 JYHF 映射覆盖好的情况下运行良好：

- **AI光纤事件：** 全链路跑通。LLM提取"AI算力光纤光缆, 光纤行业量价齐升" → 匹配"光纤光缆"主题 → 21只候选 → Gate → LLM核查 → 7只精选（长飞光纤、亨通光电、中天科技、烽火通信、通鼎互联、永鼎股份、天邑股份）。7只全是光纤光缆核心标的。

- **算力事件：** 方向正确。早期版本被标题"算力租赁"带偏，修复提取prompt后正确提取"国产算力" → 匹配"国产算力"主题 → 浪潮信息、中科曙光、拓维信息等国产算力核心标的。**但优刻得(688158)和紫光股份(000938)未被命中。**

### 4.2 未解决的卡点

**JYHF `theme_stock_map` 数据覆盖不完全。** 优刻得和紫光股份不在"国产算力"主题映射中——它们分布在"云服务"、"上海智算中心"、"AI一体机"等其它主题下，且都是 member 级别。

**文本描述与股票证据之间存在语义鸿沟。** 研报写"积极参与全国多个算力中心建设"，优刻得的lightspots/remark写的是"中立第三方云计算服务商"——语义高度相关但字面不匹配。ILIKE无法跨过这个鸿沟。尝试用token分词扩大匹配范围则引入大量噪声（"AI"匹配到"AI光纤"等无关主题）。

### 4.3 架构定位

当前 `StockRecommendService` 是一个**确定性查表+LLM精排**的荐股引擎：
- 优点：快（2次LLM，~10秒）、可解释、不修改已有代码
- 局限：只能找到 JYHF 映射表里已有的主题→股票关联
- 适用：主题映射覆盖良好的事件

---

## 五、下一步方案建议

### 5.1 补全语义匹配层

在现有查表路径之外，增加一条**语义召回路径**：

```
现有: search_intents → ILIKE匹配theme_gate_profile → theme_stock_map → 候选池A
新增: search_intents → embedding(search_intents) vs stock_profile_ext → 候选池B
合并: A ∪ B → Gate排序 → LLM核查 → 精选
```

候选池B通过 embedding 余弦相似度直接召回与搜索意图语义相关的股票，不经过主题映射表。可解决"算力中心建设 → 优刻得（云计算服务商）"这类语义匹配。

### 5.2 增强 LLM 提取 Prompt 质量

当前 prompt 偏简单。可考虑使用 few-shot 示例引导 LLM 提取更精准的 search_intents。

### 5.3 提升主题匹配覆盖率

对 JYHF 主题数据进行质量检查，识别"该有但未映射"的股票，补充到 `theme_stock_map` 中。

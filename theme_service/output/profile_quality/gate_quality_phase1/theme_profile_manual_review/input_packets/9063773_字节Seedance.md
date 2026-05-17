# Theme Profile V2 Manual Review Packet

## Subject
- subject_key: `9063773`
- subject_name: `字节Seedance`
- priority_score: `38.99`
- false_positive_risk: `0.4425`
- nearby_overlap_score: `0.0`
- nearby_subject_keys: ``

## Required Review Goal
请精读资料，为该题材生成高质量 `theme_profile_v2`。不要直接复用旧 `must/should/not`。

### Hard Rules
1. 供应链、供应商、产业链、制造、生产、合作、参股、订单、客户、物流、包装、上游、下游等泛词不能进入 `must_terms`、`aliases`、`entity_anchors`、`domain_anchors`。
2. 泛词只能进入 `support_terms`、`weak_terms` 或 `no_anchor_terms`。
3. 必须给出 `negative_terms` 或 `confusion_subject_keys`。
4. 必须写 `boundary_rules`，明确哪些情况不得匹配本题材。
5. 如果资料不足，输出 `status=needs_review`。

## Old Gate / Profile
```json
{
  "concept": "字节Seedance",
  "semantic_type": "技术合作与接入事件",
  "strategy_type": "event_driven",
  "quality": "weak",
  "must_terms": "[\"AIDC广告代理合作接入\"]",
  "strong_terms": "[\"AIDC广告代理合作接入\", \"字节Seedance\"]",
  "should_terms": "[\"广告代理\", \"AIDC\", \"合作\", \"接入\"]",
  "not_terms": "[]",
  "negative_terms": "[]",
  "core_anchors": "[\"AIDC广告代理合作接入\", \"字节Seedance\"]",
  "supporting_entities": "[\"广告代理\", \"AIDC\", \"合作\", \"接入\"]"
}
```

## Audit Signals
```json
{
  "generic_anchor_ratio": 0.5,
  "must_generic_count": 1,
  "alias_generic_count": 0,
  "anchor_count": 1,
  "negative_count": 0,
  "must_generic_terms": [
    "AIDC广告代理合作接入"
  ],
  "alias_generic_terms": [],
  "no_anchor_candidates": [
    "AIDC广告代理合作接入",
    "合作"
  ]
}
```

## Detail / Summary
reason_short:


summary:
字节Seedance介绍 Seedance2.0是字节跳动旗下即梦 AI（原剪映 Dreamina）于2026 年 2 月 7 日正式发布的导演级 AI 视频生成模型，由字节 Seed 研究团队研发，旨在解决 AI 视频长期存在的声音、连贯性、智能性三大痛点，将 AI 视频创作从 “素材级” 推向 “叙事级”，已集成到豆包 AI、剪映等字节系应用中，对标 OpenAI Sora、Runway Gen-2，在中文语境理解与文化适配方面具有显著本土优势。 一、基本定位与核心参数

rerank_text:
题材名：字节Seedance 题材摘要：字节Seedance介绍 Seedance2.0是字节跳动旗下即梦 AI（原剪映 Dreamina）于2026 年 2 月 7 日正式发布的导演级 AI 视频生成模型，由字节 Seed 研究团队研发，旨在解决 AI 视频长期存在的声音、连贯性、智能性三大痛点，将 AI 视频创作从 “素材级” 推向 “叙事级”，已集成到豆包 AI、剪映等字节系应用中，对标 OpenAI Sora、Runway Gen-2，在中文语境理解与文化适配方面具有显著本土优势。 一、基本定位与核心参数 核心锚点：AIDC广告代理合作接入，字节Seedance 代表实体：广告代理，AIDC，合作，接入

detail_html excerpt:
<p style="text-align: center;"><strong>字节Seedance介绍</strong></p><p style="text-align: center;"><img src="https://super-data-middle-platform.oss-cn-beijing.aliyuncs.com/image/2026/02/10/3cde3c63-2826-49f4-aced-18bb35e3aec3.png" alt="" data-href="" style=""></p><p>Seedance2.0是字节跳动旗下即梦 AI（原剪映 Dreamina）于2026 年 2 月 7 日正式发布的导演级 AI 视频生成模型，由字节 Seed 研究团队研发，旨在解决 AI 视频长期存在的声音、连贯性、智能性三大痛点，将 AI 视频创作从 “素材级” 推向 “叙事级”，已集成到豆包 AI、剪映等字节系应用中，对标 OpenAI Sora、Runway Gen-2，在中文语境理解与文化适配方面具有显著本土优势。</p><p>一、基本定位与核心参数</p><p>Seedance2.0 由字节跳动 Seed 团队（即梦 AI 平台）研发，原生支持 2K 分辨率，最高可导出 4K 视频，生成时长覆盖 4-15 秒，部分场景支持 60 秒多镜头一镜到底。该模型实现四模态融合输入，包括文本、图片（0-5 张）、视频和音频，能精准解析复杂剧本，还原情绪氛围与分镜构图，核心定位为导演级 AI 视频生成工具，专注多镜头叙事与音画同步，让普通用户也能轻松制作电影感视频。</p><p>二、五大核心技术突破（解决 AI 视频三大痛点）</p><p>1. 原生音画同步（解决 “声画割裂”）</p><p>Seedance2.0 实现视频与音频同步生成，而非后期添加，支持高保真对话、环境音效与配乐，彻底解决了 AI 视频常见的声画割裂问题。其口型精准对齐技术让角色唇部动作与语音完美匹配，表情与语气同步，同时支持多语言语音，中文发音自然流畅，无机械感，大幅提升了视频的真实感与沉浸感。</p><p>2. 多镜头叙事（解决 “PPT 感”）</p><p>该模型能够自动生成符合逻辑的场景序列，镜头间视觉一致性强，角色与场景特征稳定，避免了传统 AI 视频的 PPT 感。它支持复杂分镜与运镜，包括推、拉、摇、移等电影级运镜方式，实现电影级表达，同时突破首尾帧限制，可按用户提示生成连续镜头，支持视频 “接着拍”，让视频创作更具连贯性与叙事性。</p><p>3. 全能参考系统（解决 “可控性差”）</p><p>Seedance2.0 的全能参考系统大幅提升了生成可控性，参考图像可精准还原构图、角色细节、风格氛围，参考视频可学习镜头语言、动作风格，参考音频可匹配节奏与情绪，实现 “音画合一”。这一系统让创作者能够精准复刻特效、运镜、动作与剪辑，创意更可控，满足专业创作需求。</p><p>4. 物理动态模拟（提升真实感）</p><p>模型在物理动态模拟方面实现显著提升，复杂物理运动模拟更自然，如水流、布料、毛发等物理效果更符合现实逻辑，角色动作流畅，避免 “僵尸舞” 现象，大幅提升了视频的真实感与可信度。它能理解物理规律，如花瓣飘落的方向和风向一致，物体的重力表现合理，同时理解因果关系，角色动作之间有逻辑上的承接。</p><p>5. 智能编辑能力（提升创作效率）</p><p>Seedance2.0 具备强大的智能编辑能力，支持视频补全与衔接，可对已有视频进行平滑延长与镜头衔接，还能进行内容编辑，包括角色更替、场景修改、片段删减 / 增加。生成与编辑一体化的设计支持局部修改、原生续写与图层编辑，大幅降低废片率，解决行业长期痛点，让视频创作更高效。</p><p>三、三大核心生成模式</p><p>1. 文生视频</p><p>用户输入文字描述，即可直接生成高质量、逻辑连贯的短视频，适用于创意灵感快速呈现、剧本可视化、营销内容制作等场景，让文字创意快速转化为视觉内容，提升创作效率。</p><p>2. 图生视频</p><p>上传图片即可生成动态视频，保留原图风格与细节，适用于静态 IP 动态化、插画 / 漫画转视频、产品展示等场景，让静态内容动起来，拓展内容呈现形式，为 IP 变现提供新路径。</p><p>3. 参考生成</p><p>融合多模态参考（图文音视频）生成新视频，适用于影视续集创作、IP 改编、风格迁移等场景，创作者可利用已有素材生成新内容，实现 IP 二次变现，降低创作成本。</p><p>四、应用场景与商业化价值</p><p>1. 内容创作领域</p><p>AI 漫剧 / 短剧：掌阅科技泡漫平台、德才股份奇想无限等率先接入，批量生产漫剧内容，实现 “双击收入模型”，按生成条数向字节付费调用，向 C 端收取会员费。</p><p>影视 IP 焕新：上海电影等合作，将经典 IP 通过 Seedance2.0 生成 4K 续作，共享广告收入，播放量破亿带动 IP 二次变现。</p><p>广告营销：蓝色光标等数字营销公司用于广告创意制作，成本降低 90%，效率提升 10 倍，大幅提升广告制作效率与效果。</p><p>2. 个人创作场景</p><p>在个人创作场景中，Seedance2.0 让短视频创作更简单，普通用户 “一句话 + 几张图” 即可生成电影感视频，同时支持数字人内容生成，口型与语音完美同步，还能快速制作教学视频、知识科普短片，满足个人多样化创作需求。</p><p>3. 商业服务模式</p><p>Seedance2.0 采用多种商业服务模式，包括调用付费，按生成条数 / 时长向字节付费，如掌阅科技；分成模式，与内容平台按流量 / 收入分成，如万兴科技插件分成；B 端定制，为企业提供 AI 视频生成解决方案，如德才股份的 “漫剧 AI 工坊”，满足不同客户的需求。</p><p><br></p>

## Stock Pool Top30
```json
[
  {
    "trade_date": "2026-05-15",
    "stock_id": "603598",
    "stock_name": "引力传媒",
    "rank_order": 1,
    "pct_chg": "9.9900",
    "is_leader": true
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300442",
    "stock_name": "润泽科技",
    "rank_order": 2,
    "pct_chg": "2.8000",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "000681",
    "stock_name": "视觉中国",
    "rank_order": 3,
    "pct_chg": "2.0500",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300058",
    "stock_name": "蓝色光标",
    "rank_order": 4,
    "pct_chg": "1.7900",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "002400",
    "stock_name": "省广集团",
    "rank_order": 5,
    "pct_chg": "1.6000",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "603466",
    "stock_name": "风语筑",
    "rank_order": 6,
    "pct_chg": "1.4200",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "603533",
    "stock_name": "掌阅科技",
    "rank_order": 7,
    "pct_chg": "1.2600",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300624",
    "stock_name": "万兴科技",
    "rank_order": 8,
    "pct_chg": "1.2600",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "688039",
    "stock_name": "当虹科技",
    "rank_order": 9,
    "pct_chg": "1.1400",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "001330",
    "stock_name": "博纳影业",
    "rank_order": 10,
    "pct_chg": "0.5500",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300364",
    "stock_name": "中文在线",
    "rank_order": 11,
    "pct_chg": "0.2500",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "605287",
    "stock_name": "德才股份",
    "rank_order": 12,
    "pct_chg": "-0.1900",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "601595",
    "stock_name": "上海电影",
    "rank_order": 13,
    "pct_chg": "-0.4000",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300166",
    "stock_name": "东方国信",
    "rank_order": 14,
    "pct_chg": "-0.6800",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300182",
    "stock_name": "捷成股份",
    "rank_order": 15,
    "pct_chg": "-0.6900",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "301085",
    "stock_name": "亚康股份",
    "rank_order": 16,
    "pct_chg": "-1.1200",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "300383",
    "stock_name": "光环新网",
    "rank_order": 17,
    "pct_chg": "-1.9400",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "600589",
    "stock_name": "大位科技",
    "rank_order": 18,
    "pct_chg": "-2.5000",
    "is_leader": false
  },
  {
    "trade_date": "2026-05-15",
    "stock_id": "600673",
    "stock_name": "东阳光",
    "rank_order": 19,
    "pct_chg": "-4.0000",
    "is_leader": false
  }
]
```

## Recent Matched Events
```json
[]
```

## Output Schema
请按三步输出：

1. 题材理解报告
2. 术语分层
3. 标准 `theme_profile_v2` JSON

标准 JSON 字段：
`subject_key, subject_name, aliases, entity_anchors, domain_anchors, product_anchors, technology_anchors, event_action_terms, must_terms, strong_terms, should_terms, support_terms, weak_terms, no_anchor_terms, negative_terms, confusion_subject_keys, boundary_rules, evidence_refs, source_blocks, quality_score, quality_flags, eval_metrics, version, status`

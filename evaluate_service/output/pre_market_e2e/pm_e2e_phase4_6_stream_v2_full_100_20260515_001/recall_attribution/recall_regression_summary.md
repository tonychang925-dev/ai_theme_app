# Phase 4.6 Recall Miss Attribution Report

**Run**: `pm_e2e_phase4_6_stream_v2_full_100_20260515_001`
**Date**: 2026-05-19
**Total events**: 100

## Summary

- **Primary hits**: 57
- **HUMAN_REVIEW**: 14
- **UNKNOWN decisions**: 4
- **MATCH but recall@5 miss**: 25
- **Total recall miss samples**: 43

## Root Cause Distribution

| Root Cause | Count | % |
|---|---|---|
| matcher_recall_gap | 20 | 46.5% |
| role_guard_overstrict | 9 | 20.9% |
| reasonable_human_review | 5 | 11.6% |
| neighbor_map_incomplete | 5 | 11.6% |
| profile_v2_too_narrow | 3 | 7.0% |
| gold_alias_incomplete | 1 | 2.3% |

## Recall Miss by Gold Theme

| Gold Theme | Miss Count | HUMAN_REVIEW | UNKNOWN | MATCH but miss |
|---|---|---|---|---|
| AI/AR眼镜 | 13 | 9 | 1 | 3 |
| 卫星互联 | 8 | 2 | 1 | 5 |
| 海洋经济 | 5 | 0 | 0 | 5 |
| 可控核聚变 | 4 | 0 | 1 | 3 |
| 光刻胶 | 4 | 0 | 0 | 4 |
| 稀土永磁 | 3 | 1 | 0 | 2 |
| 液冷数据中心 | 3 | 1 | 0 | 2 |
| 对日制裁 | 2 | 1 | 1 | 0 |
| SpaceX | 1 | 0 | 0 | 1 |

## High-Frequency Recall Miss Themes (≥2)

### AI/AR眼镜 (13 misses)

- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 2025年1月3日，1月3日电，美国专利及商标局官网显示，英伟达公开了一项AR眼镜专利（US20250004275A1），名为“无背光增强现实数字全息技术”...
- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 24日讯，鸿海宣布，将携手Porotech进军AR眼镜市场...
- `HUMAN_REVIEW` | (none) | reasonable_human_review | 2024年12月10日，10日讯，三星内部正积极推进名为Infinite的扩展现实（XR）项目，计划在明年1月召开的Galaxy Unpacked发布会上公开展...
- `WRONG_MATCH` | 著名IP | role_guard_overstrict | 2024年11月20日，云天励飞战略投资闪极科技 后者将推国内首款量产AI拍摄眼镜...
- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 2024年9月18日，科技公司Snap在美国加利福尼亚州圣莫尼卡举办的2024Snap全球生态合作伙伴大会上，发布旗下第五代SpectaclesAR眼镜...
- `WRONG_MATCH` | 显示面板 | matcher_recall_gap | 2024年9月3日，近日，行者X-lens AR骑行镜开售，该款骑行镜配备OLED微显示屏，支持触控交互，售价699元...
- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 2024年8月26日，小米已开发出一款AI眼镜，并将尽快推向市场...
- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 消息面上，据媒体报道，北京多屏未来科技有限公司已于近日完成数百万美元的A轮融资...
- `HUMAN_REVIEW` | (none) | reasonable_human_review | 2024年8月19日，Rokid官微8月19日预告：9月7日空降北京，Rokid开发者沙龙暨新品体验会开启报名...
- `WRONG_MATCH` | 苹果MR | matcher_recall_gap | 2024年8月15日，有“国产版Vision Pro头显”之称的Vision SE，今年7月30日通过了新版本的3C认证，制造商为深圳市亿境虚拟现实技术有限公司...
- `UNKNOWN` | (none) | matcher_recall_gap | 国家统计局：7月虚拟现实设备产品产量增长55.7%...
- `HUMAN_REVIEW` | (none) | reasonable_human_review | 2024年8月14日，**字节跳动旗下XR头显厂商PICO已经确认，其下一代头显产品将于2024年8月20日在国内发布...
- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 2024年8月13日，**近日，扎克伯格在 SPC 黑客松活动上的一场对谈分享，不限于 AI 、AR、创业以及团队管理等经验...

### 卫星互联 (8 misses)

- `HUMAN_REVIEW` | (none) | role_guard_overstrict | 上交所公告，为了落实中国证监会《关于在科创板设置科创成长层 增强制度包容性适应性的意见》，进一步规范科技型企业适用科创板第五套上市标准，支持尚未形成一定收入规模...
- `UNKNOWN` | (none) | matcher_recall_gap | 中国航天今年已完成近90次发射，刷新历史纪录，其中商业发射占比显著提升...
- `WRONG_MATCH` | 蓝箭航天IPO | matcher_recall_gap | 蓝箭航天副总裁张静茹告诉《科创板日报》记者，蓝箭航天供应链600余家供应商覆盖全国90余城，民企占比近70%、国企30%...
- `HUMAN_REVIEW` | (none) | profile_v2_too_narrow | 在文昌国际航天城，年产1000颗卫星的超级工厂即将投产，可实现“卫星出厂即发射”的无缝衔接；目前20余家产业链上下游企业已签约落户，火箭研发、卫星制造、发射测控...
- `WRONG_MATCH` | 蓝箭航天IPO | matcher_recall_gap | 12月3日中午，朱雀三号遥一运载火箭在东风商业航天创新试验区发射升空，按程序完成了飞行任务，火箭二级进入预定轨道，火箭一子级回收失败...
- `WRONG_MATCH` | SpaceX | matcher_recall_gap | 从中国航天科技集团一院获悉，由该院抓总研制的我国首艘火箭网系回收海上平台于近日被命名为“领航者”并成功交付，标志着该院在可重复使用运载火箭技术链条上完成了重要一...
- `WRONG_MATCH` | 太空旅游 | gold_alias_incomplete | 据国家航天局消息，该局已于近期设立商业航天司，相关业务正在逐步开展，标志着我国商业航天产业迎来专职监管机构（新闻来源：央视新闻）...
- `WRONG_MATCH` | 蓝箭航天IPO | matcher_recall_gap | 北京蓝箭航天朱雀三号运载火箭首飞计划已进入最后准备阶段，计划于本周六即11月29日首飞...

### 海洋经济 (5 misses)

- `WRONG_MATCH` | 深海经济 | neighbor_map_incomplete | 浙江省十四届人大常委会第二十一次会议近日审议并通过《浙江省海洋经济高质量发展促进条例》（以下简称《条例》）...
- `WRONG_MATCH` | 深海经济 | matcher_recall_gap | 10月24日，中共中央举行新闻发布会介绍和解读党的二十届四中全会精神...
- `WRONG_MATCH` | 深海经济 | neighbor_map_incomplete | 深圳市海洋发展局8月28日下午联合招商局港口集团股份有限公司、中集海工智能创新中心等龙头企业，在2025深圳（国际）通用人工智能大会暨产业博览会“Agent＋场...
- `WRONG_MATCH` | 深海经济 | neighbor_map_incomplete | 国家发展改革委区域协调发展司副司长马维晨表示，按照中央财经委员会第六次会议部署，国家发展改革委正与相关部门一道着手“十五五”海洋经济发展规划以及相关领域专项规划...
- `WRONG_MATCH` | 深海经济 | neighbor_map_incomplete | 国家发展改革委区域协调发展司副司长马维晨表示，按照中央财经委员会第六次会议部署，国家发展改革委正与相关部门一道着手“十五五”海洋经济发展规划以及相关领域专项规划...

### 可控核聚变 (4 misses)

- `WRONG_MATCH` | A股全球第一 | neighbor_map_incomplete | 特朗普旗下的媒体企业——特朗普媒体与科技集团，同意以全股票交易方式与核聚变能源企业TAE科技公司合并，交易总价值超60亿美元...
- `UNKNOWN` | (none) | matcher_recall_gap | 国际能源署预测，到 2030年，全球核聚变市场规模有望接近5000亿美元(3.5万亿元人民币)...
- `WRONG_MATCH` | 乌克兰重建 | role_guard_overstrict | 《中国国家原子能机构和法国原子能和替代能源委员会第十五个和平利用核能合作议定书》中提及将加强核基础研究、核技术应用、核聚变技术等合作...
- `WRONG_MATCH` | 首发经济大全 | matcher_recall_gap | 开展燃烧等离子体物理研究、实现产出能量大于消耗能量、演示聚变能发电……11月24日上午，在位于安徽合肥未来大科学城的紧凑型聚变能实验装置（BEST）主机大厅，中...

### 光刻胶 (4 misses)

- `WRONG_MATCH` | 半导体设备 | matcher_recall_gap | 消息面上，11月20-21日，2025·光刻胶及集成电路材料先进技术和产业应用研讨会将举行，主题“光刻突围 材聚绍兴”...
- `WRONG_MATCH` | 半导体设备 | matcher_recall_gap | 11月20-21日，2025·光刻胶及集成电路材料先进技术和产业应用研讨会将举行，主题“光刻突围 材聚绍兴”...
- `WRONG_MATCH` | PCB印制电路板 | matcher_recall_gap | 据百川盈孚，因下游PCB行业需求持续增长，国内光引发剂多种牌号价格走高...
- `WRONG_MATCH` | 半导体设备 | matcher_recall_gap | 据“中国光谷”消息，光谷企业近日在半导体专用光刻胶领域实现重大突破:武汉太紫微光电科技有限公司推出的T150 A光刻胶产品，已通过半导体工艺量产验证，实现配方全...

### 稀土永磁 (3 misses)

- `WRONG_MATCH` | 中美芬太尼合作 | matcher_recall_gap | 据央视新闻报道，当地时间10月30日中午，国家主席在韩国釜山同美国总统特朗普举行会晤...
- `HUMAN_REVIEW` | (none) | profile_v2_too_narrow | 包钢股份公告称，根据公司2022年年度股东大会审议通过的稀土精矿价格调整机制及计算公式，公司拟将2025年第四季度稀土精矿关联交易价格调整为不含税26205元/...
- `WRONG_MATCH` | 深海经济 | matcher_recall_gap | 商务部、海关总署发布公告2025年第56号，公布对部分稀土设备和原辅料相关物项实施出口管制的决定，根据《中华人民共和国出口管制法》《中华人民共和国对外贸易法》《...

### 液冷数据中心 (3 misses)

- `WRONG_MATCH` | 人工智能硬件 | reasonable_human_review | 英伟达首席财务官表示，数据中心芯片需求较此前预测的5000亿美元有所增长...
- `WRONG_MATCH` | 人工智能硬件 | matcher_recall_gap | 第五届国际AIDC液冷供应链干人峰会暨·国际数据中心液冷市场趋势分析会将于12月18日-19日召开...
- `HUMAN_REVIEW` | (none) | reasonable_human_review | 《科创板日报》15日讯，由于AI新平台Rubin与下一代Feynman平台功耗或高达2000W以上，现有散热方案无法应对，消息称英伟达要求供应商开发全新“微通道...

### 对日制裁 (2 misses)

- `UNKNOWN` | (none) | matcher_recall_gap | 据新华社，外交部发言人林剑12月1日表示，日本在口头上搪塞敷行，在行动上一意孤行，中方对此绝不接受...
- `HUMAN_REVIEW` | (none) | profile_v2_too_narrow | 据媒体披露，中方已做好对日实质反制准备...

## Actionable Fix Items

Total actionable: 38

### gold_in_top5_but_not_primary_investigate_rerank (10 cases)

- `pm_case_0021`: 2024年9月3日，近日，行者X-lens AR骑行镜开售，该款骑行镜配备OLED微显示屏，支持触控交互，售价699元... → **matcher_recall_gap**
- `pm_case_0029`: 2024年8月15日，有“国产版Vision Pro头显”之称的Vision SE，今年7月30日通过了新版本的3C认证，制造商为深圳市亿境虚拟现实技术有限公司... → **matcher_recall_gap**
- `pm_case_0049`: 开展燃烧等离子体物理研究、实现产出能量大于消耗能量、演示聚变能发电……11月24日上午，在位于安徽合肥未来大科学城的紧凑型聚变能实验装置（BEST）主机大厅，中... → **matcher_recall_gap**
- `pm_case_0061`: 据央视新闻报道，当地时间10月30日中午，国家主席在韩国釜山同美国总统特朗普举行会晤... → **matcher_recall_gap**
- `pm_case_0064`: 商务部、海关总署发布公告2025年第56号，公布对部分稀土设备和原辅料相关物项实施出口管制的决定，根据《中华人民共和国出口管制法》《中华人民共和国对外贸易法》《... → **matcher_recall_gap**
- `pm_case_0071`: 消息面上，11月20-21日，2025·光刻胶及集成电路材料先进技术和产业应用研讨会将举行，主题“光刻突围 材聚绍兴”... → **matcher_recall_gap**
- `pm_case_0072`: 11月20-21日，2025·光刻胶及集成电路材料先进技术和产业应用研讨会将举行，主题“光刻突围 材聚绍兴”... → **matcher_recall_gap**
- `pm_case_0077`: 据“中国光谷”消息，光谷企业近日在半导体专用光刻胶领域实现重大突破:武汉太紫微光电科技有限公司推出的T150 A光刻胶产品，已通过半导体工艺量产验证，实现配方全... → **matcher_recall_gap**
- `pm_case_0083`: 12月3日中午，朱雀三号遥一运载火箭在东风商业航天创新试验区发射升空，按程序完成了飞行任务，火箭二级进入预定轨道，火箭一子级回收失败... → **matcher_recall_gap**
- `pm_case_0091`: 第五届国际AIDC液冷供应链干人峰会暨·国际数据中心液冷市场趋势分析会将于12月18日-19日召开... → **matcher_recall_gap**

### review_role_guard_threshold (7 cases)

- `pm_case_0003`: 2025年1月3日，1月3日电，美国专利及商标局官网显示，英伟达公开了一项AR眼镜专利（US20250004275A1），名为“无背光增强现实数字全息技术”... → **role_guard_overstrict**
- `pm_case_0006`: 24日讯，鸿海宣布，将携手Porotech进军AR眼镜市场... → **role_guard_overstrict**
- `pm_case_0017`: 2024年9月18日，科技公司Snap在美国加利福尼亚州圣莫尼卡举办的2024Snap全球生态合作伙伴大会上，发布旗下第五代SpectaclesAR眼镜... → **role_guard_overstrict**
- `pm_case_0023`: 2024年8月26日，小米已开发出一款AI眼镜，并将尽快推向市场... → **role_guard_overstrict**
- `pm_case_0024`: 消息面上，据媒体报道，北京多屏未来科技有限公司已于近日完成数百万美元的A轮融资... → **role_guard_overstrict**
- `pm_case_0033`: 2024年8月13日，**近日，扎克伯格在 SPC 黑客松活动上的一场对谈分享，不限于 AI 、AR、创业以及团队管理等经验... → **role_guard_overstrict**
- `pm_case_0078`: 上交所公告，为了落实中国证监会《关于在科创板设置科创成长层 增强制度包容性适应性的意见》，进一步规范科技型企业适用科创板第五套上市标准，支持尚未形成一定收入规模... → **role_guard_overstrict**

### investigate_why_gold_not_in_dense_or_sparse_recall (6 cases)

- `pm_case_0037`: 2025年12月25日，据美国《空天部队》杂志网站12月19日报道，美国太空军下属的太空发展局当天宣布，向4家公司授予价值35亿美元的合同，用于采购总共72颗导... → **matcher_recall_gap**
- `pm_case_0066`: 10月24日，中共中央举行新闻发布会介绍和解读党的二十届四中全会精神... → **matcher_recall_gap**
- `pm_case_0075`: 据百川盈孚，因下游PCB行业需求持续增长，国内光引发剂多种牌号价格走高... → **matcher_recall_gap**
- `pm_case_0081`: 蓝箭航天副总裁张静茹告诉《科创板日报》记者，蓝箭航天供应链600余家供应商覆盖全国90余城，民企占比近70%、国企30%... → **matcher_recall_gap**
- `pm_case_0084`: 从中国航天科技集团一院获悉，由该院抓总研制的我国首艘火箭网系回收海上平台于近日被命名为“领航者”并成功交付，标志着该院在可重复使用运载火箭技术链条上完成了重要一... → **matcher_recall_gap**
- `pm_case_0087`: 北京蓝箭航天朱雀三号运载火箭首飞计划已进入最后准备阶段，计划于本周六即11月29日首飞... → **matcher_recall_gap**

### review_dense_sparse_recall_for_subject (4 cases)

- `pm_case_0030`: 国家统计局：7月虚拟现实设备产品产量增长55.7%... → **matcher_recall_gap**
- `pm_case_0045`: 国际能源署预测，到 2030年，全球核聚变市场规模有望接近5000亿美元(3.5万亿元人民币)... → **matcher_recall_gap**
- `pm_case_0055`: 据新华社，外交部发言人林剑12月1日表示，日本在口头上搪塞敷行，在行动上一意孤行，中方对此绝不接受... → **matcher_recall_gap**
- `pm_case_0080`: 中国航天今年已完成近90次发射，刷新历史纪录，其中商业发射占比显著提升... → **matcher_recall_gap**

### align_marine_economy_vs_deepsea_economy (4 cases)

- `pm_case_0065`: 浙江省十四届人大常委会第二十一次会议近日审议并通过《浙江省海洋经济高质量发展促进条例》（以下简称《条例》）... → **neighbor_map_incomplete**
- `pm_case_0067`: 深圳市海洋发展局8月28日下午联合招商局港口集团股份有限公司、中集海工智能创新中心等龙头企业，在2025深圳（国际）通用人工智能大会暨产业博览会“Agent＋场... → **neighbor_map_incomplete**
- `pm_case_0068`: 国家发展改革委区域协调发展司副司长马维晨表示，按照中央财经委员会第六次会议部署，国家发展改革委正与相关部门一道着手“十五五”海洋经济发展规划以及相关领域专项规划... → **neighbor_map_incomplete**
- `pm_case_0069`: 国家发展改革委区域协调发展司副司长马维晨表示，按照中央财经委员会第六次会议部署，国家发展改革委正与相关部门一道着手“十五五”海洋经济发展规划以及相关领域专项规划... → **neighbor_map_incomplete**

### expand_profile_v2_anchors_or_alias (3 cases)

- `pm_case_0056`: 据媒体披露，中方已做好对日实质反制准备... → **profile_v2_too_narrow**
- `pm_case_0063`: 包钢股份公告称，根据公司2022年年度股东大会审议通过的稀土精矿价格调整机制及计算公式，公司拟将2025年第四季度稀土精矿关联交易价格调整为不含税26205元/... → **profile_v2_too_narrow**
- `pm_case_0082`: 在文昌国际航天城，年产1000颗卫星的超级工厂即将投产，可实现“卫星出厂即发射”的无缝衔接；目前20余家产业链上下游企业已签约落户，火箭研发、卫星制造、发射测控... → **profile_v2_too_narrow**

### review_role_guard_for_this_subject (2 cases)

- `pm_case_0010`: 2024年11月20日，云天励飞战略投资闪极科技 后者将推国内首款量产AI拍摄眼镜... → **role_guard_overstrict**
- `pm_case_0047`: 《中国国家原子能机构和法国原子能和替代能源委员会第十五个和平利用核能合作议定书》中提及将加强核基础研究、核技术应用、核聚变技术等合作... → **role_guard_overstrict**

### strengthen_nuclear_fusion_profile_neighbor_map (1 cases)

- `pm_case_0044`: 特朗普旗下的媒体企业——特朗普媒体与科技集团，同意以全股票交易方式与核聚变能源企业TAE科技公司合并，交易总价值超60亿美元... → **neighbor_map_incomplete**

### add_satellite_internet_gold_alias_to_profile (1 cases)

- `pm_case_0085`: 据国家航天局消息，该局已于近期设立商业航天司，相关业务正在逐步开展，标志着我国商业航天产业迎来专职监管机构（新闻来源：央视新闻）... → **gold_alias_incomplete**

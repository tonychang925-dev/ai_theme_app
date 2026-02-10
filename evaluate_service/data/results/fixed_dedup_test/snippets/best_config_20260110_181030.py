#!/usr/bin/env python3
# 最佳判重引擎配置
# 基于测试结果生成
# 测试准确率: 85.7%
# 配置ID: config_sensitive
# 描述: 高敏感度配置（易于检测重复）

OPTIMIZED_DEDUP_CONFIG = {
  "thresholds": {
    "exact_match": 1.0,
    "inclusion_match": 0.6,
    "semantic_similarity": 0.55,
    "event_overlap": 0.5,
    "auto_merge": 0.65,
    "suggest_merge": 0.5,
    "keep_separate": 0.3
  },
  "weights": {
    "name_similarity": 0.35,
    "keyword_overlap": 0.35,
    "industry_match": 0.2,
    "semantic_similarity": 0.1
  },
  "strategies": {
    "enable_exact_match": true,
    "enable_inclusion_check": true,
    "enable_semantic_analysis": true,
    "enable_event_overlap": true,
    "use_jieba": true,
    "cache_enabled": true
  }
}

# 使用方法:
# 1. 在ThemeDiscoveryEngine中使用:
#    from theme_service.deduplication_engine import ThemeDeduplicationEngine
#    dedup_engine = ThemeDeduplicationEngine(config=OPTIMIZED_DEDUP_CONFIG)
#    discovery_engine.set_dedup_engine(dedup_engine)
#
# 2. 或者在EnhancedThemeDiscoveryEngine中设置:
#    config = {
#        'fast_track_threshold': 0.95,
#        'dedup_config': OPTIMIZED_DEDUP_CONFIG
#    }
#    discovery_engine = EnhancedThemeDiscoveryEngine(config=config)

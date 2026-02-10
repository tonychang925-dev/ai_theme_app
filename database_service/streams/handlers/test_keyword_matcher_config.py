# test_keyword_matcher_config.py
TEST_CONFIG = {
    'match_threshold': 0.2,  # 降低匹配阈值
    'max_results': 10,
    'min_keyword_matches': 1,  # 降低最小匹配要求
    'use_database_tags': True,
    'enable_analyst_logic': False,
    'classification_first': False,
    'enable_fuzzy_match': True,
    'fuzzy_threshold': 0.5,
    'keyword_weight': 0.6,
    'name_weight': 0.2,
    'heat_weight': 0.2,
    'precision_mode': 'normal',
    # AI相关配置
    'ai_keywords_weight': 0.7,
    'event_keywords_weight': 0.3,
    'use_ai_keywords_first': True,
    'ai_confidence_boost': 0.2,
    'enable_category_inference': True,
    'category_match_threshold': 1  # 降低分类匹配要求
}
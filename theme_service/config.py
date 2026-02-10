"""
主题发现引擎配置
"""

class DiscoveryConfig:
    """发现引擎配置"""
    
    # ==================== 算法配置 ====================
    
    # 算法类型映射
    ALGORITHM_TYPES = {
        'major': 'keyword',
        'normal': 'keyword'
    }
    
    # 通用算法配置
    ALGORITHM_COMMON_CONFIG = {
        'use_database_tags': True,      # 使用数据库中的tags关键词
        'keyword_weight': 0.6,          # 关键词权重
        'name_weight': 0.2,             # 名称权重
        'heat_weight': 0.2,             # 热度权重
        'enable_fuzzy_match': True,     # 启用模糊匹配
        'fuzzy_threshold': 0.6          # 模糊匹配阈值
    }
    
    # Major事件算法配置（高精度）
    MAJOR_ALGORITHM_CONFIG = {
        **ALGORITHM_COMMON_CONFIG,
        'match_threshold': 0.7,         # 高阈值
        'max_results': 10,              # 最多返回结果数
        'min_keyword_matches': 3,       # 最少关键词匹配数
        'require_name_match': True,     # 要求名称匹配
        'enable_analyst_logic': True,   # 启用分析师逻辑
        'classification_first': True,   # 先分类后匹配
        'precision_mode': 'high'        # 高精度模式
    }
    
    # Normal事件算法配置（中精度）
    NORMAL_ALGORITHM_CONFIG = {
        **ALGORITHM_COMMON_CONFIG,
        'match_threshold': 0.5,         # 中阈值
        'max_results': 15,              # 最多返回结果数
        'min_keyword_matches': 2,       # 最少关键词匹配数
        'require_name_match': False,    # 不要求名称匹配
        'enable_analyst_logic': False,  # 简化逻辑
        'classification_first': False,  # 直接匹配
        'precision_mode': 'normal'      # 中精度模式
    }
    
    # 算法配置映射
    ALGORITHM_CONFIGS = {
        'major': MAJOR_ALGORITHM_CONFIG,
        'normal': NORMAL_ALGORITHM_CONFIG
    }
    
    # ==================== 业务处理配置 ====================
    
    BUSINESS_CONFIG = {
        # 置信度阈值
        'confidence_thresholds': {
            'major': 0.7,      # Major事件置信度阈值
            'normal': 0.5      # Normal事件置信度阈值
        },
        
        # 候选池配置
        'candidate_pool': {
            'max_size': 100,
            'ttl_hours': 24,
            'cleanup_interval_minutes': 60,
            'min_confidence': 0.4,
            'max_themes_per_event': 5
        },
        
        # 处理配置
        'processing': {
            'enable_multiple_matches': True,
            'max_processing_time_ms': 3000,
            'enable_fallback': True,      # 启用降级处理
            'batch_size': 10              # 批量处理大小
        }
    }
    
    # ==================== 分类配置 ====================
    
    CLASSIFICATION_CONFIG = {
        'min_level1_score': 0.5,
        'max_level1_candidates': 3,
        'max_level2_candidates': 10,
        'enable_category_filter': True,
        'category_keyword_weights': {
            'level1': 1.0,
            'level2': 0.8,
            'level3': 0.6
        }
    }
    
    # ==================== 关键词提取配置 ====================
    
    KEYWORD_EXTRACTION_CONFIG = {
        'max_event_keywords': 30,     # 事件最多提取关键词数
        'max_theme_keywords': 50,     # 题材最多提取关键词数
        'min_keyword_length': 2,      # 最小关键词长度
        'stop_words': {               # 停用词列表
            '的', '了', '在', '是', '和', '与', '及', '对', '为', '有',
            '也', '都', '就', '但', '而', '且', '或', '还', '又', '更',
            '这', '那', '此', '该', '各', '每', '某', '本'
        }
    }
    
    # ==================== 数据库字段映射 ====================
    
    DATABASE_FIELD_MAPPING = {
        'theme': {
            'code': 'code',
            'name': 'name',
            'level1_category': 'level1_category',
            'level2_category': 'level2_category',
            'level3_category': 'level3_category',
            'keywords': 'keywords',
            'tags': 'tags',
            'heat_score': 'heat_score',
            'category1_code': 'category1_code',
            'category2_code': 'category2_code',
            'category3_code': 'category3_code',
            'description': 'description'
        },
        'category': {
            'code': 'category_code',
            'name': 'category_name',
            'level': 'category_level',
            'parent_code': 'parent_code',
            'keywords': 'keywords',
            'description': 'description'
        },
        'event': {
            'id': 'event_id',
            'title': 'title',
            'content': 'content',
            'event_type': 'event_type',
            'source': 'source',
            'publish_time': 'publish_time'
        }
    }
    
    # ==================== 性能优化配置 ====================
    
    PERFORMANCE_CONFIG = {
        'cache_enabled': True,
        'cache_ttl_seconds': 300,
        'index_build_batch_size': 1000,
        'parallel_processing': True,
        'max_concurrent_matches': 10
    }
# test_fixed_transformer.py
"""
验证修复后的 TransformerSemanticMatcher
"""

import os
import sys
import warnings
warnings.filterwarnings('ignore')

# 🔥 关键：在导入任何东西之前设置
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

print("🚀 验证修复后的 TransformerSemanticMatcher")
print("=" * 50)

# 测试数据
themes = [
    {
        'code': 'AVIATION',
        'name': '航空航天',
        'keywords': ['航天', '航空', '飞机', '火箭'],
        'description': '航空航天科技产业',
        'level2_category': '高端制造',
        'level3_category': '航空航天装备'
    },
    {
        'code': 'CHIP',
        'name': '半导体芯片', 
        'keywords': ['芯片', '半导体', '集成电路'],
        'description': '半导体与集成电路产业',
        'level2_category': '信息技术',
        'level3_category': '集成电路'
    }
]

event = {
    'title': '国产大飞机C919首飞成功',
    'content': '中国自主研发的大型客机C919完成首次商业飞行',
    'keywords': ['大飞机', 'C919', '航空', '首飞']
}

try:
    # 重新导入，确保环境变量生效
    import importlib
    if 'theme_service.matchers.semantic_matcher' in sys.modules:
        importlib.reload(sys.modules['theme_service.matchers.transformer_matcher'])
    
    from theme_service.matchers.semantic_matcher import TransformerSemanticMatcher
    
    print("✅ 成功导入 TransformerSemanticMatcher")
    
    # 创建匹配器
    config = {
        'model_name': 'shibing624/text2vec-base-chinese',
        'semantic_threshold': 0.5,
        'max_results': 5,
        'device': 'cpu'
    }
    
    print(f"\n🛠️  配置: {config}")
    
    matcher = TransformerSemanticMatcher(config)
    
    # 初始化
    print("\n🔄 初始化...")
    matcher.initialize(themes)
    
    # 检查模型状态
    print(f"\n📊 模型状态:")
    print(f"   模型对象: {type(matcher.model)}")
    print(f"   使用transformers方式: {hasattr(matcher, '_use_transformers') and matcher._use_transformers}")
    print(f"   主题向量数量: {len(matcher.theme_embeddings)}")
    
    # 匹配
    print("\n🔍 匹配测试...")
    results = matcher.match(event)
    
    print(f"\n🎯 结果 ({len(results)} 个):")
    for r in results:
        print(f"  - {r.theme_name}: {r.match_score:.3f} (关键词: {r.matched_keywords})")
    
    # 特别检查航空航天匹配
    if results and '航空' in results[0].theme_name:
        print(f"\n✅ 成功匹配航空航天相关题材!")
        print(f"   分数: {results[0].match_score:.3f}")
        
        if results[0].match_score > 0.8:
            print("🎯 高相似度匹配，语义理解有效！")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
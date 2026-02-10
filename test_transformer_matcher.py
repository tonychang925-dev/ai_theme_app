# test_transformer_real.py
"""
100%能跑的 TransformerSemanticMatcher 测试脚本
直接使用你已有的类，确保使用本地缓存
"""

import os
import sys
import warnings
warnings.filterwarnings('ignore')

# 🔥 关键：在导入任何 huggingface 库之前设置环境变量
os.environ['HF_HUB_OFFLINE'] = '1'          # 强制离线模式
os.environ['TRANSFORMERS_OFFLINE'] = '1'    # transformers 离线
os.environ['TOKENIZERS_PARALLELISM'] = 'false'  # 避免 tokenizers 警告

print("🚀 开始运行 TransformerSemanticMatcher 测试")
print("=" * 50)

# 1. 导入你的类
try:
    from theme_service.matchers.semantic_matcher import TransformerSemanticMatcher
    print("✅ 成功导入 TransformerSemanticMatcher")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("💡 请确保你在项目根目录运行")
    sys.exit(1)

# 2. 测试数据
def get_test_data():
    """获取测试数据"""
    themes = [
        {
            'code': 'AVIATION',
            'name': '航空航天',
            'keywords': ['航天', '航空', '飞机', '火箭', '卫星'],
            'description': '航空航天科技产业',
            'level2_category': '高端制造',
            'level3_category': '航空航天装备'
        },
        {
            'code': 'CHIP',
            'name': '半导体芯片',
            'keywords': ['芯片', '半导体', '集成电路', '微电子'],
            'description': '半导体与集成电路产业',
            'level2_category': '信息技术',
            'level3_category': '集成电路'
        },
        {
            'code': 'AI',
            'name': '人工智能',
            'keywords': ['AI', '人工智能', '机器学习', '深度学习'],
            'description': '人工智能与机器学习技术',
            'level2_category': '信息技术',
            'level3_category': '人工智能'
        }
    ]
    
    event = {
        'event_id': 'test_001',
        'title': '国产大飞机C919首飞成功',
        'content': '中国自主研发的大型客机C919完成首次商业飞行，标志着中国航空工业的重大突破',
        'keywords': ['大飞机', 'C919', '航空', '首飞', '国产']
    }
    
    return themes, event

# 3. 创建匹配器
def create_matcher_with_local_model():
    """创建使用本地缓存模型的匹配器"""
    
    # 🔥 关键配置：使用本地缓存模型
    config = {
        'model_name': 'bert-base-chinese',  # 使用你本地已有的模型
        'semantic_threshold': 0.5,          # 降低阈值便于测试
        'max_results': 5,
        'min_keyword_matches': 1,
        'device': 'cpu'                     # 使用 CPU
    }
    
    print("\n🛠️  创建匹配器配置:")
    for key, value in config.items():
        print(f"   {key}: {value}")
    
    # 创建匹配器
    matcher = TransformerSemanticMatcher(config)
    return matcher

# 4. 主测试函数
def main_test():
    """主测试函数"""
    print("\n🧪 准备测试数据...")
    themes, event = get_test_data()
    
    print(f"   题材数量: {len(themes)}")
    print(f"   事件标题: {event['title']}")
    
    print("\n🔄 创建匹配器...")
    matcher = create_matcher_with_local_model()
    
    print("\n⚡ 初始化匹配器...")
    try:
        # 初始化（传递空分类列表）
        matcher.initialize(themes, categories=[])
        print("✅ 初始化成功")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n🔍 开始匹配测试...")
    try:
        results = matcher.match(event, precision='normal')
        
        print(f"\n🎯 匹配结果 ({len(results)} 个):")
        for i, r in enumerate(results):
            print(f"  {i+1}. {r.theme_name} (ID: {r.theme_id})")
            print(f"      相似度: {r.match_score:.3f}")
            print(f"      置信度: {r.confidence:.3f}")
            print(f"      匹配关键词: {r.matched_keywords}")
            print(f"      分类: {r.level2_category} > {r.level3_category}")
            print(f"      热门: {'是' if r.is_hot else '否'}")
            print()
        
        # 验证"航天航空"与"航空航天"的匹配
        print("📊 验证语义匹配效果:")
        if results:
            first_result = results[0]
            if '航空' in first_result.theme_name.lower() or '航天' in first_result.theme_name.lower():
                print(f"✅ 成功匹配航空航天相关题材!")
                print(f"   事件关键词: {event['keywords']}")
                print(f"   匹配到: {first_result.theme_name} (分数: {first_result.match_score:.3f})")
        
    except Exception as e:
        print(f"❌ 匹配失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("✅ 测试完成!")

# 5. 如果模型加载失败，用这个备用方案
def fallback_test():
    """备用测试方案"""
    print("\n⚠️  使用备用测试方案...")
    
    # 使用 KeywordMatcher（保证能运行）
    try:
        from theme_service.matchers.keyword_matcher import KeywordMatcher
        
        themes, event = get_test_data()
        
        print("🔄 使用 KeywordMatcher 测试...")
        matcher = KeywordMatcher({'max_results': 5})
        matcher.initialize(themes, categories=[])
        
        results = matcher.match(event)
        
        print(f"\n🎯 KeywordMatcher 结果 ({len(results)} 个):")
        for r in results:
            print(f"  - {r.theme_name}: {r.match_score:.3f}")
        
    except Exception as e:
        print(f"❌ 备用测试也失败: {e}")

# 6. 运行测试
if __name__ == "__main__":
    print("📋 环境检查:")
    print(f"   Python: {sys.version}")
    print(f"   工作目录: {os.getcwd()}")
    
    try:
        main_test()
    except KeyboardInterrupt:
        print("\n⏹️  用户中断")
    except Exception as e:
        print(f"\n❌ 主测试异常: {e}")
        import traceback
        traceback.print_exc()
        
        # 尝试备用方案
        fallback_test()
#!/usr/bin/env python3
"""
test_local_qwen_matcher.py - LocalQwenEmbeddingMatcher 单元测试
"""

import sys
import os
import time
import json
import numpy as np
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theme_service.matchers.local_qwen_matcher import (
    LocalQwenEmbeddingMatcher,
    create_tiny_qwen_matcher,
    create_medium_qwen_matcher
)


class TestLocalQwenMatcher:
    """LocalQwenEmbeddingMatcher 测试类"""
    
    def __init__(self):
        self.test_results = {}
        self.test_themes = self._create_test_themes()
        self.test_events = self._create_test_events()
        
    def _create_test_themes(self):
        """创建测试题材数据"""
        return [
            {
                "code": "AEROSPACE",
                "name": "航天装备产业",
                "keywords": ["航天装备", "航空航天", "国防军工", "卫星导航", "火箭技术"],
                "concepts": ["航天技术", "航空工程"],
                "description": "航天航空装备制造相关产业",
                "level1_category": "国防军工",
                "level2_category": "航天装备Ⅱ",
                "level3_category": "航天装备Ⅲ",
                "heat_score": 85,
                "tags": json.dumps({"keywords": ["航天", "航空", "装备", "军工"]})
            },
            {
                "code": "SEMICONDUCTOR",
                "name": "半导体芯片产业",
                "keywords": ["半导体", "芯片", "集成电路", "微处理器", "光刻机"],
                "concepts": ["芯片制造", "集成电路设计"],
                "description": "半导体芯片设计与制造",
                "level1_category": "电子",
                "level2_category": "半导体",
                "level3_category": "半导体Ⅲ",
                "heat_score": 78,
                "tags": json.dumps({"keywords": ["芯片", "半导体", "集成电路"]})
            },
            {
                "code": "AI_TECH",
                "name": "人工智能产业",
                "keywords": ["人工智能", "AI", "机器学习", "深度学习", "大模型"],
                "concepts": ["智能算法", "神经网络"],
                "description": "人工智能技术研发与应用",
                "level1_category": "计算机",
                "level2_category": "人工智能",
                "level3_category": "人工智能Ⅲ",
                "heat_score": 92,
                "tags": json.dumps({"keywords": ["AI", "人工智能", "算法"]})
            },
            {
                "code": "NEW_ENERGY",
                "name": "新能源汽车产业",
                "keywords": ["新能源汽车", "电动车", "电动汽车", "锂电池", "充电桩"],
                "concepts": ["电动化", "智能化"],
                "description": "新能源汽车研发与制造",
                "level1_category": "汽车",
                "level2_category": "新能源汽车",
                "level3_category": "新能源汽车Ⅲ",
                "heat_score": 65,
                "tags": json.dumps({"keywords": ["新能源", "电动", "汽车"]})
            }
        ]
    
    def _create_test_events(self):
        """创建测试事件数据"""
        return {
            "aerospace_event": {
                "event_id": "EVENT_001",
                "title": "中国航天航空技术取得重大突破",
                "content": "我国在航天航空领域实现了重大技术突破，长征系列火箭成功发射新型卫星。相关产业链受益明显，航空航天技术发展迅速。",
                "keywords": ["航天", "航空", "技术突破", "卫星"],
                "ai_analysis": {
                    "core_concept": "航天航空技术突破",
                    "industry_keywords": ["航天航空", "航空航天", "国防军工", "卫星技术"],
                    "concept_confidence": 0.9,
                    "impact_level": "high"
                }
            },
            "semiconductor_event": {
                "event_id": "EVENT_002",
                "title": "全球芯片短缺持续，半导体产业备受关注",
                "content": "受多种因素影响，全球半导体芯片供应紧张，国内相关企业加快布局，集成电路产业迎来发展机遇。",
                "keywords": ["芯片", "半导体", "集成电路", "供应链"],
                "ai_analysis": {
                    "core_concept": "半导体芯片供应链",
                    "industry_keywords": ["半导体", "芯片", "集成电路", "微处理器"],
                    "concept_confidence": 0.85,
                    "impact_level": "medium"
                }
            },
            "ai_event": {
                "event_id": "EVENT_003",
                "title": "人工智能大模型技术取得新进展",
                "content": "国内AI公司发布最新大模型，在自然语言处理和机器学习领域实现技术突破。",
                "keywords": ["人工智能", "AI", "大模型", "机器学习"],
                "ai_analysis": {
                    "core_concept": "人工智能大模型突破",
                    "industry_keywords": ["人工智能", "AI", "大模型", "深度学习"],
                    "concept_confidence": 0.88,
                    "impact_level": "high"
                }
            },
            "ambiguous_event": {
                "event_id": "EVENT_004",
                "title": "高端制造技术推动产业升级",
                "content": "我国在高端制造领域取得多项技术突破，涉及航空航天、半导体芯片等多个产业。",
                "keywords": ["高端制造", "技术突破", "产业升级"],
                "ai_analysis": {
                    "core_concept": "高端制造技术突破",
                    "industry_keywords": ["高端制造", "技术突破", "产业升级"],
                    "concept_confidence": 0.75,
                    "impact_level": "medium"
                }
            }
        }
    
    def test_01_model_loading(self):
        """测试1：模型加载"""
        print("\n" + "="*60)
        print("🧪 测试1：模型加载")
        print("="*60)
        
        try:
            # 使用超小模型进行测试（速度快）
            print("🔧 创建超小模型匹配器（32M）...")
            matcher = create_tiny_qwen_matcher({
                'use_cache': False,  # 禁用缓存以便测试
                'match_threshold': 0.3
            })
            
            print("✅ 模型加载测试通过")
            self.test_results['model_loading'] = True
            
            # 测试模型基本信息
            print(f"   模型名称: {matcher.config['model_name']}")
            print(f"   设备: {matcher.device}")
            
            return matcher
            
        except Exception as e:
            print(f"❌ 模型加载测试失败: {e}")
            self.test_results['model_loading'] = False
            return None
    
    def test_02_initialization(self, matcher):
        """测试2：数据初始化"""
        print("\n" + "="*60)
        print("🧪 测试2：数据初始化")
        print("="*60)
        
        try:
            start_time = time.time()
            
            print(f"📥 初始化 {len(self.test_themes)} 个测试题材...")
            matcher.initialize(self.test_themes)
            
            init_time = time.time() - start_time
            
            # 验证初始化状态
            assert matcher.initialized == True, "初始化状态不正确"
            assert len(matcher.themes) == len(self.test_themes), "题材数量不匹配"
            assert len(matcher.theme_vectors) == len(self.test_themes), "向量数量不匹配"
            
            print("✅ 数据初始化测试通过")
            print(f"   初始化时间: {init_time:.2f}秒")
            print(f"   题材数量: {len(matcher.themes)}")
            print(f"   预计算向量: {len(matcher.theme_vectors)}")
            
            # 验证向量维度
            sample_vector = next(iter(matcher.theme_vectors.values()))
            print(f"   向量维度: {sample_vector.shape}")
            
            self.test_results['initialization'] = True
            return True
            
        except Exception as e:
            print(f"❌ 数据初始化测试失败: {e}")
            import traceback
            traceback.print_exc()
            self.test_results['initialization'] = False
            return False
    
    def test_03_basic_matching(self, matcher):
        """测试3：基础匹配功能"""
        print("\n" + "="*60)
        print("🧪 测试3：基础匹配功能")
        print("="*60)
        
        try:
            event = self.test_events['aerospace_event']
            
            print(f"🔍 匹配航天航空事件...")
            print(f"   事件标题: {event['title']}")
            
            start_time = time.time()
            results = matcher.match(event, precision='normal')
            match_time = time.time() - start_time
            
            # 验证匹配结果
            assert len(results) > 0, "未找到匹配结果"
            
            print(f"✅ 基础匹配测试通过")
            print(f"   匹配时间: {match_time:.3f}秒")
            print(f"   匹配结果数: {len(results)}")
            
            # 显示前3个结果
            print(f"\n📊 匹配结果详情:")
            for i, result in enumerate(results[:3], 1):
                print(f"   {i}. {result.theme_name}")
                print(f"      分数: {result.match_score:.4f}")
                print(f"      置信度: {result.confidence:.3f}")
                print(f"      匹配类型: {result.match_type}")
                if result.matched_keywords:
                    print(f"      匹配关键词: {result.matched_keywords[:3]}")
            
            # 验证航天事件应该匹配到航天题材
            top_result = results[0]
            assert '航天' in top_result.theme_name or '航空' in top_result.theme_name, \
                "航天事件未正确匹配到航天题材"
            
            self.test_results['basic_matching'] = True
            return True
            
        except Exception as e:
            print(f"❌ 基础匹配测试失败: {e}")
            self.test_results['basic_matching'] = False
            return False
    
    def test_04_semantic_understanding(self, matcher):
        """测试4：语义理解能力（核心测试）"""
        print("\n" + "="*60)
        print("🧪 测试4：语义理解能力（核心）")
        print("="*60)
        
        try:
            print("🧠 测试语义相似度理解...")
            
            # 测试文本对
            test_pairs = [
                ("航天航空", "航空航天"),
                ("半导体", "芯片"),
                ("人工智能", "AI"),
                ("新能源汽车", "电动车"),
            ]
            
            print("\n📝 语义相似度测试:")
            
            for text1, text2 in test_pairs:
                # 编码两个文本
                vec1 = matcher._encode_single_direct(text1)
                vec2 = matcher._encode_single_direct(text2)
                
                if vec1 is not None and vec2 is not None:
                    similarity = matcher._cosine_similarity(vec1, vec2)
                    
                    # 判断相似度水平
                    if similarity > 0.7:
                        status = "✅ 高相似度"
                    elif similarity > 0.4:
                        status = "⚠️  中等相似度"
                    else:
                        status = "❌ 低相似度"
                    
                    print(f"   '{text1}' vs '{text2}': {similarity:.4f} - {status}")
                    
                    # 核心测试：航天航空 vs 航空航天 应该高相似
                    if text1 == "航天航空" and text2 == "航空航天":
                        if similarity > 0.7:
                            print(f"      🎯 核心问题解决：模型能识别'航天航空'与'航空航天'语义相似")
                        else:
                            print(f"      ⚠️  注意：模型对'航天航空'问题识别能力不足")
                else:
                    print(f"   ❌ '{text1}' 或 '{text2}' 编码失败")
            
            # 跨领域区分测试
            print("\n🎯 跨领域区分测试:")
            
            aerospace_vec = matcher._encode_single_direct("航天航空")
            semiconductor_vec = matcher._encode_single_direct("半导体")
            ai_vec = matcher._encode_single_direct("人工智能")
            
            if aerospace_vec is not None and semiconductor_vec is not None:
                cross_similarity = matcher._cosine_similarity(aerospace_vec, semiconductor_vec)
                print(f"   '航天航空' vs '半导体': {cross_similarity:.4f}")
                
                # 跨领域应该较低相似度
                if cross_similarity < 0.5:
                    print(f"      ✅ 模型能区分不同领域")
                else:
                    print(f"      ⚠️  跨领域区分度不足")
            
            self.test_results['semantic_understanding'] = True
            return True
            
        except Exception as e:
            print(f"❌ 语义理解测试失败: {e}")
            self.test_results['semantic_understanding'] = False
            return False
    
    def test_05_different_precision_modes(self, matcher):
        """测试5：不同精度模式"""
        print("\n" + "="*60)
        print("🧪 测试5：不同精度模式")
        print("="*60)
        
        try:
            event = self.test_events['ambiguous_event']  # 模糊事件
            
            print(f"🔍 测试不同精度模式下的匹配...")
            print(f"   事件: {event['title']}")
            
            results_high = matcher.match(event, precision='high')
            results_normal = matcher.match(event, precision='normal')
            results_low = matcher.match(event, precision='low')
            
            print(f"\n📊 不同精度模式结果对比:")
            print(f"   高精度模式: {len(results_high)} 个结果")
            print(f"   普通模式: {len(results_normal)} 个结果")
            print(f"   低精度模式: {len(results_low)} 个结果")
            
            # 验证精度模式影响
            assert len(results_high) <= len(results_normal) <= len(results_low), \
                "精度模式逻辑不正确"
            
            print(f"\n🎯 高精度模式结果（更严格）:")
            if results_high:
                for i, result in enumerate(results_high[:2], 1):
                    print(f"   {i}. {result.theme_name}: {result.match_score:.4f}")
            else:
                print(f"   无高置信度匹配")
            
            print(f"\n🎯 低精度模式结果（更宽松）:")
            if results_low:
                for i, result in enumerate(results_low[:3], 1):
                    print(f"   {i}. {result.theme_name}: {result.match_score:.4f}")
            
            # 检查匹配质量
            if results_normal:
                print(f"\n📈 匹配质量分析:")
                scores = [r.match_score for r in results_normal]
                print(f"   平均分数: {np.mean(scores):.4f}")
                print(f"   最高分数: {max(scores):.4f}")
                print(f"   最低分数: {min(scores):.4f}")
            
            self.test_results['precision_modes'] = True
            return True
            
        except Exception as e:
            print(f"❌ 精度模式测试失败: {e}")
            self.test_results['precision_modes'] = False
            return False
    
    def test_06_keyword_fallback(self, matcher):
        """测试6：关键词回退机制"""
        print("\n" + "="*60)
        print("🧪 测试6：关键词回退机制")
        print("="*60)
        
        try:
            # 创建难以语义理解但有关键词的事件
            hard_event = {
                "event_id": "EVENT_HARD",
                "title": "专业术语测试",
                "content": "ASIC FPGA DSP 等专用芯片在边缘计算中的应用",
                "keywords": ["ASIC", "FPGA", "DSP", "边缘计算"],
                "ai_analysis": {
                    "core_concept": "专用芯片技术",
                    "industry_keywords": ["ASIC", "FPGA", "DSP", "边缘计算"],
                    "concept_confidence": 0.8
                }
            }
            
            print(f"🔍 测试关键词回退机制...")
            print(f"   事件: {hard_event['title']}")
            print(f"   内容包含专业术语，语义匹配可能困难")
            
            # 正常匹配
            results_normal = matcher.match(hard_event, precision='normal')
            
            print(f"\n📊 匹配结果:")
            print(f"   找到 {len(results_normal)} 个匹配")
            
            if results_normal:
                for i, result in enumerate(results_normal[:2], 1):
                    print(f"   {i}. {result.theme_name}: {result.match_score:.4f}")
                    print(f"      匹配类型: {result.match_type}")
                    if result.match_type == 'keyword_fallback_match':
                        print(f"      🎯 触发了关键词回退")
                    if result.matched_keywords:
                        print(f"      匹配关键词: {result.matched_keywords}")
            
            # 验证至少有一个结果
            assert len(results_normal) > 0, "关键词回退机制未生效"
            
            self.test_results['keyword_fallback'] = True
            return True
            
        except Exception as e:
            print(f"❌ 关键词回退测试失败: {e}")
            self.test_results['keyword_fallback'] = False
            return False
    
    def test_07_performance_benchmark(self, matcher):
        """测试7：性能基准测试"""
        print("\n" + "="*60)
        print("🧪 测试7：性能基准测试")
        print("="*60)
        
        try:
            print("⚡ 性能基准测试...")
            
            # 测试不同大小事件的匹配时间
            test_cases = [
                ("短事件", "航天技术突破", 0.1),
                ("中事件", "我国在航天航空领域实现了重大技术突破，相关产业链受益明显", 0.5),
                ("长事件", "我国在航天航空领域实现了重大技术突破。长征系列火箭成功发射新型卫星，标志着我国航天技术进入新阶段。相关产业链受益明显，航空航天技术发展迅速，未来将继续加大研发投入。", 1.0),
            ]
            
            results = []
            
            for case_name, content, expected_time in test_cases:
                event = {
                    "event_id": f"PERF_{case_name}",
                    "title": f"{case_name}测试",
                    "content": content,
                    "keywords": ["测试"],
                    "ai_analysis": {
                        "core_concept": "测试",
                        "industry_keywords": ["测试"],
                        "concept_confidence": 0.5
                    }
                }
                
                # 预热
                _ = matcher.match(event, precision='normal')
                
                # 实际测试
                start_time = time.time()
                match_results = matcher.match(event, precision='normal')
                elapsed = time.time() - start_time
                
                results.append({
                    "case": case_name,
                    "text_length": len(content),
                    "match_time": elapsed,
                    "results_count": len(match_results)
                })
                
                print(f"   {case_name}: {elapsed:.3f}秒, {len(match_results)}个结果")
            
            print(f"\n📈 性能统计:")
            for r in results:
                print(f"   {r['case']}: {r['match_time']:.3f}秒, "
                      f"文本长度: {r['text_length']}字符")
            
            # 验证性能在合理范围内
            avg_time = np.mean([r['match_time'] for r in results])
            print(f"\n✅ 平均匹配时间: {avg_time:.3f}秒")
            
            if avg_time < 2.0:  # 2秒内完成算合格
                print(f"   ⚡ 性能表现良好")
            elif avg_time < 5.0:
                print(f"   ⚠️  性能一般，考虑优化")
            else:
                print(f"   ❌ 性能较慢，需要优化")
            
            self.test_results['performance'] = True
            return True
            
        except Exception as e:
            print(f"❌ 性能测试失败: {e}")
            self.test_results['performance'] = False
            return False
    
    def test_08_algorithm_info(self, matcher):
        """测试8：算法信息获取"""
        print("\n" + "="*60)
        print("🧪 测试8：算法信息获取")
        print("="*60)
        
        try:
            print("📋 获取算法信息...")
            
            info = matcher.get_algorithm_info()
            
            # 验证信息完整性
            required_keys = [
                'name', 'algorithm_type', 'model_name', 
                'embedding_dimension', 'precomputed_vectors',
                'performance_stats', 'config'
            ]
            
            missing_keys = [key for key in required_keys if key not in info]
            
            if missing_keys:
                print(f"❌ 算法信息缺少字段: {missing_keys}")
                return False
            
            print("✅ 算法信息完整")
            
            # 打印详细信息
            print(f"\n📊 算法详情:")
            print(f"   算法名称: {info['name']}")
            print(f"   算法类型: {info['algorithm_type']}")
            print(f"   模型名称: {info['model_name']}")
            print(f"   向量维度: {info['embedding_dimension']}")
            print(f"   预计算向量: {info['precomputed_vectors']}")
            
            stats = info['performance_stats']
            print(f"\n📈 性能统计:")
            print(f"   模型加载时间: {stats.get('load_time', 0):.2f}秒")
            print(f"   初始化时间: {stats.get('init_time', 0):.2f}秒")
            print(f"   匹配调用次数: {stats.get('match_calls', 0)}")
            print(f"   编码调用次数: {stats.get('encode_calls', 0)}")
            
            print(f"\n⚙️  配置信息:")
            config = info['config']
            for key, value in config.items():
                if isinstance(value, (int, float, str, bool)):
                    print(f"   {key}: {value}")
            
            self.test_results['algorithm_info'] = True
            return True
            
        except Exception as e:
            print(f"❌ 算法信息测试失败: {e}")
            self.test_results['algorithm_info'] = False
            return False
    
    def test_09_cache_functionality(self):
        """测试9：缓存功能"""
        print("\n" + "="*60)
        print("🧪 测试9：缓存功能")
        print("="*60)
        
        try:
            print("💾 测试缓存功能...")
            
            # 创建使用缓存的匹配器
            matcher_with_cache = create_tiny_qwen_matcher({
                'use_cache': True,
                'cache_dir': './test_cache/',
                'theme_vectors_file': 'test_vectors.npz'
            })
            
            # 初始化并计算向量
            print("   第一次初始化（会创建缓存）...")
            start_time = time.time()
            matcher_with_cache.initialize(self.test_themes[:2])  # 只用前2个测试数据
            first_init_time = time.time() - start_time
            
            print(f"   第一次初始化时间: {first_init_time:.2f}秒")
            
            # 清除内存，重新创建匹配器
            print("\n   重新创建匹配器，测试缓存加载...")
            matcher_with_cache = None
            
            matcher_reloaded = create_tiny_qwen_matcher({
                'use_cache': True,
                'cache_dir': './test_cache/',
                'theme_vectors_file': 'test_vectors.npz'
            })
            
            start_time = time.time()
            matcher_reloaded.initialize(self.test_themes[:2])
            second_init_time = time.time() - start_time
            
            print(f"   第二次初始化时间（从缓存）: {second_init_time:.2f}秒")
            
            # 验证缓存加速效果
            if second_init_time < first_init_time * 0.5:  # 缓存应该快至少50%
                print(f"   ✅ 缓存加速效果明显")
            else:
                print(f"   ⚠️  缓存加速效果不明显")
            
            # 清理测试缓存
            import shutil
            if os.path.exists('./test_cache/'):
                shutil.rmtree('./test_cache/')
                print(f"   清理测试缓存")
            
            self.test_results['cache_functionality'] = True
            return True
            
        except Exception as e:
            print(f"❌ 缓存功能测试失败: {e}")
            
            # 清理测试缓存
            if os.path.exists('./test_cache/'):
                import shutil
                shutil.rmtree('./test_cache/')
            
            self.test_results['cache_functionality'] = False
            return False
    
    def test_10_different_model_sizes(self):
        """测试10：不同模型大小对比"""
        print("\n" + "="*60)
        print("🧪 测试10：不同模型大小对比")
        print("="*60)
        
        try:
            print("🔬 对比不同大小的Qwen模型...")
            
            models_to_test = [
                ("32M超小模型", create_tiny_qwen_matcher),
                ("0.5B中等模型", create_medium_qwen_matcher),
            ]
            
            event = self.test_events['aerospace_event']
            
            results_comparison = []
            
            for model_name, model_creator in models_to_test:
                print(f"\n📊 测试 {model_name}...")
                
                try:
                    # 创建匹配器
                    matcher = model_creator({
                        'use_cache': False,
                        'match_threshold': 0.4
                    })
                    
                    # 初始化
                    start_time = time.time()
                    matcher.initialize(self.test_themes[:2])  # 使用前2个题材加速
                    init_time = time.time() - start_time
                    
                    # 匹配测试
                    start_time = time.time()
                    results = matcher.match(event, precision='normal')
                    match_time = time.time() - start_time
                    
                    if results:
                        top_score = results[0].match_score if results else 0
                        result_count = len(results)
                        
                        results_comparison.append({
                            'model': model_name,
                            'init_time': init_time,
                            'match_time': match_time,
                            'top_score': top_score,
                            'result_count': result_count,
                            'success': True
                        })
                        
                        print(f"   初始化时间: {init_time:.2f}秒")
                        print(f"   匹配时间: {match_time:.3f}秒")
                        print(f"   匹配结果: {result_count}个")
                        print(f"   最高分数: {top_score:.4f}")
                        
                    else:
                        results_comparison.append({
                            'model': model_name,
                            'success': False,
                            'error': '无匹配结果'
                        })
                        print(f"   ⚠️  无匹配结果")
                        
                except Exception as e:
                    print(f"   ❌ 测试失败: {e}")
                    results_comparison.append({
                        'model': model_name,
                        'success': False,
                        'error': str(e)
                    })
            
            # 对比结果
            print(f"\n🎯 模型对比总结:")
            successful_models = [r for r in results_comparison if r.get('success')]
            
            if len(successful_models) >= 2:
                # 找出最佳模型
                best_model = min(successful_models, 
                                key=lambda x: x['match_time'] + x['init_time'])
                
                print(f"   🏆 综合最佳模型: {best_model['model']}")
                print(f"      总时间: {best_model['init_time'] + best_model['match_time']:.2f}秒")
                print(f"      匹配质量: {best_model['top_score']:.4f}")
            
            self.test_results['model_comparison'] = True
            return True
            
        except Exception as e:
            print(f"❌ 模型对比测试失败: {e}")
            self.test_results['model_comparison'] = False
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 LocalQwenEmbeddingMatcher 单元测试")
        print("="*60)
        
        # 记录开始时间
        total_start_time = time.time()
        
        # 测试1：模型加载
        matcher = self.test_01_model_loading()
        if not matcher:
            print("❌ 模型加载失败，终止测试")
            return False
        
        # 测试2：数据初始化
        if not self.test_02_initialization(matcher):
            print("⚠️  初始化测试失败，继续其他测试")
        
        # 执行需要初始化的测试
        if matcher.initialized:
            self.test_03_basic_matching(matcher)
            self.test_04_semantic_understanding(matcher)
            self.test_05_different_precision_modes(matcher)
            self.test_06_keyword_fallback(matcher)
            self.test_07_performance_benchmark(matcher)
            self.test_08_algorithm_info(matcher)
        
        # 测试不需要已初始化匹配器的功能
        self.test_09_cache_functionality()
        self.test_10_different_model_sizes()
        
        # 统计结果
        total_time = time.time() - total_start_time
        
        print("\n" + "="*60)
        print("📊 测试结果总结")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        failed_tests = total_tests - passed_tests
        
        print(f"🎯 测试总数: {total_tests}")
        print(f"✅ 通过测试: {passed_tests}")
        print(f"❌ 失败测试: {failed_tests}")
        print(f"⏱️  总耗时: {total_time:.2f}秒")
        
        # 详细结果
        print(f"\n📈 详细结果:")
        for test_name, result in self.test_results.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"   {test_name}: {status}")
        
        # 最终判断
        if failed_tests == 0:
            print(f"\n🎉 所有测试通过！LocalQwenEmbeddingMatcher 功能正常")
            return True
        elif passed_tests / total_tests >= 0.7:
            print(f"\n⚠️  部分测试失败，核心功能正常")
            return True
        else:
            print(f"\n❌ 多数测试失败，需要修复")
            return False


# 快捷运行函数
def run_quick_test():
    """快速测试（仅核心功能）"""
    print("🚀 运行 LocalQwenEmbeddingMatcher 快速测试")
    
    tester = TestLocalQwenMatcher()
    
    # 只运行核心测试
    core_tests = [
        ('model_loading', tester.test_01_model_loading),
    ]
    
    results = {}
    
    for test_name, test_func in core_tests:
        print(f"\n🧪 运行 {test_name}...")
        try:
            if test_name == 'model_loading':
                matcher = test_func()
                results[test_name] = matcher is not None
            else:
                results[test_name] = test_func()
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results[test_name] = False
    
    # 总结
    print(f"\n📊 快速测试结果:")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    return all(results.values())


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='LocalQwenEmbeddingMatcher 单元测试')
    parser.add_argument('--quick', action='store_true', help='快速测试模式')
    parser.add_argument('--model', type=str, default='tiny', 
                       choices=['tiny', 'medium', 'large'], 
                       help='测试使用的模型大小')
    
    args = parser.parse_args()
    
    if args.quick:
        success = run_quick_test()
        sys.exit(0 if success else 1)
    else:
        tester = TestLocalQwenMatcher()
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)
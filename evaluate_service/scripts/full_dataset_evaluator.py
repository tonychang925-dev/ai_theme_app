#!/usr/bin/env python3
"""
完整数据集评估器 - 在所有76个测试用例上评估
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
import statistics
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class FullDatasetEvaluator:
    """完整数据集评估器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {
            "semantic_threshold": 0.7,
            "eval_mode": "semantic",
            "batch_size": 5,  # 更小的批量大小，避免API限制
            "enable_progress_bar": True,
            "max_retries": 3,
            "retry_delay": 2
        }
        
        # 完整的同义词映射
        self.synonym_mapping = {
            # AI/AR眼镜相关
            "AI/AR眼镜": ["智能眼镜", "AR眼镜", "AI眼镜", "混合现实眼镜", "MR眼镜", "XR设备", 
                        "增强现实", "虚拟现实", "可穿戴设备", "人机交互设备"],
            "智能眼镜": ["AI/AR眼镜", "AI眼镜", "AR眼镜", "混合现实眼镜"],
            "AI眼镜": ["AI/AR眼镜", "智能眼镜", "AR眼镜"],
            "AR眼镜": ["AI/AR眼镜", "智能眼镜", "AI眼镜"],
            
            # SpaceX相关
            "SpaceX": ["太空探索", "商业航天", "航天技术", "火箭发射", "卫星互联网", 
                      "太空经济", "低轨卫星", "航天公司", "火箭技术"],
            "太空探索": ["SpaceX", "商业航天", "航天探索", "太空开发"],
            "商业航天": ["SpaceX", "太空探索", "民营航天", "航天商业化"],
            "卫星互联网": ["SpaceX", "低轨卫星", "卫星通信", "太空互联网"],
            
            # 可控核聚变
            "可控核聚变": ["核聚变", "人造太阳", "聚变能源", "终极能源", "清洁能源", 
                        "聚变反应", "核能技术"],
            "核聚变": ["可控核聚变", "人造太阳", "聚变能源"],
            
            # 海洋经济
            "海洋经济": ["海洋产业", "海洋开发", "海洋资源", "蓝色经济", "海洋科技", 
                       "海洋工程", "海洋经济"],
            "海洋产业": ["海洋经济", "海洋开发", "海洋经济产业"],
            
            # AI算力
            "AI算力": ["人工智能算力", "AI计算", "算力基础设施", "GPU算力", 
                      "计算能力", "AI基础设施"],
            "人工智能算力": ["AI算力", "AI计算", "算力基础设施"],
            
            # 低空经济
            "低空经济": ["低空飞行", "无人机", "空中交通", "eVTOL", "空中出行", 
                       "城市空中交通"],
            "无人机": ["低空经济", "低空飞行", "无人驾驶航空器"],
            
            # 数据要素
            "数据要素": ["数据资产", "数据资源", "数据流通", "数据交易", "数据价值化"],
            "数据资产": ["数据要素", "数据资源", "数据资本"],
            
            # MR混合现实
            "MR混合现实": ["混合现实", "MR", "扩展现实", "XR", "虚实融合"],
            "混合现实": ["MR混合现实", "MR", "扩展现实"],
            
            # 消费电子
            "消费电子创新": ["消费电子", "电子产品创新", "数码创新", "智能设备", 
                          "电子消费品"],
            "消费电子": ["消费电子创新", "电子产品", "数码产品"],
            
            # 人机交互
            "人机交互": ["交互技术", "人机界面", "用户体验", "交互设计", "界面设计"],
            
            # 其他技术主题
            "自动驾驶": ["无人驾驶", "智能驾驶", "自动驾驶技术", "智能交通"],
            "无人驾驶": ["自动驾驶", "智能驾驶", "自动驾驶汽车"],
            
            "区块链": ["分布式账本", "区块链技术", "数字货币技术", "加密技术"],
            "分布式账本": ["区块链", "区块链技术"],
            
            "元宇宙": ["虚拟世界", "数字世界", "虚拟空间", "数字宇宙"],
            "虚拟世界": ["元宇宙", "数字世界"],
            
            "碳中和": ["碳减排", "碳中和目标", "碳达峰", "气候变化", "绿色低碳"],
            "碳减排": ["碳中和", "减排技术", "低碳发展"],
            
            "量子计算": ["量子技术", "量子计算机", "量子信息", "量子科技"],
            "量子技术": ["量子计算", "量子信息"],
        }
        
        self.engine = None
        self.ai_client = None
    
    async def initialize(self) -> bool:
        """初始化引擎"""
        try:
            from theme_service.services.ai_client import AIThemeClient
            from theme_service.services.theme_discovery import ThemeDiscoveryEngine
            from theme_service.config import settings
            
            logger.info("初始化AI引擎...")
            self.ai_client = AIThemeClient(settings)
            self.engine = ThemeDiscoveryEngine(self.ai_client)
            logger.info("AI引擎初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False
    
    def calculate_similarity(self, theme1: str, theme2: str) -> float:
        """计算两个主题的语义相似度"""
        # 1. 完全相等
        if theme1.lower() == theme2.lower():
            return 1.0
        
        # 2. 同义词检查
        theme1_lower = theme1.lower()
        theme2_lower = theme2.lower()
        
        for main_theme, synonyms in self.synonym_mapping.items():
            main_lower = main_theme.lower()
            
            # 检查theme1是否是某个主题或其同义词
            theme1_is_synonym = False
            if theme1_lower == main_lower:
                theme1_is_synonym = True
            else:
                for synonym in synonyms:
                    if theme1_lower == synonym.lower():
                        theme1_is_synonym = True
                        break
            
            # 检查theme2是否是同一个主题或其同义词
            theme2_is_synonym = False
            if theme2_lower == main_lower:
                theme2_is_synonym = True
            else:
                for synonym in synonyms:
                    if theme2_lower == synonym.lower():
                        theme2_is_synonym = True
                        break
            
            # 如果是同一个主题的同义词，返回高相似度
            if theme1_is_synonym and theme2_is_synonym:
                return 0.9
        
        # 3. 字符串相似度（Jaccard相似度）
        words1 = set(theme1_lower.replace('/', ' ').replace('-', ' ').replace('_', ' ').split())
        words2 = set(theme2_lower.replace('/', ' ').replace('-', ' ').replace('_', ' ').split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        similarity = len(intersection) / len(union)
        
        # 4. 如果包含关系，提高相似度
        if words1.issubset(words2) or words2.issubset(words1):
            similarity = max(similarity, 0.7)
        
        return similarity
    
    def evaluate_match(self, discovered: List[str], ground_truth: List[str]) -> Dict:
        """评估匹配结果"""
        best_match = {
            "matched": False,
            "match_type": "none",
            "similarity": 0.0,
            "best_pair": ("", ""),
            "details": []
        }
        
        for truth in ground_truth:
            # 扩展同义词
            truth_expanded = [truth]
            if truth in self.synonym_mapping:
                truth_expanded.extend(self.synonym_mapping[truth])
            
            for truth_var in truth_expanded:
                for disc in discovered:
                    similarity = self.calculate_similarity(truth_var, disc)
                    
                    best_match["details"].append({
                        "truth": truth_var,
                        "discovered": disc,
                        "similarity": similarity
                    })
                    
                    if similarity > best_match["similarity"]:
                        best_match["similarity"] = similarity
                        best_match["best_pair"] = (truth, disc)
                        
                        # 根据阈值判断是否匹配
                        threshold = self.config["semantic_threshold"]
                        best_match["matched"] = similarity >= threshold
        
        # 按相似度排序详情
        if best_match["details"]:
            best_match["details"].sort(key=lambda x: x["similarity"], reverse=True)
        
        return best_match
    
    async def evaluate_single_case(self, test_case: Dict, case_index: int) -> Dict:
        """评估单个测试用例"""
        theme = test_case.get("theme", f"case_{case_index}")
        test_id = test_case.get("test_id", f"test_{case_index}")
        
        # 构建事件
        mock_event = {
            "id": test_id,
            "title": test_case.get("title", ""),
            "summary": test_case.get("content", "")[:200],
            "content": test_case.get("content", ""),
            "impact_industries": test_case.get("impact_industries", [])
        }
        
        start_time = time.time()
        
        for retry in range(self.config["max_retries"]):
            try:
                result = await self.engine.process_single_event(mock_event)
                
                discovered = result.get("themes_found", [])
                ground_truth = test_case.get("ground_truth_themes", [])
                
                match_result = self.evaluate_match(discovered, ground_truth)
                
                processing_time = time.time() - start_time
                
                return {
                    "test_id": test_id,
                    "theme": theme,
                    "success": True,
                    "ground_truth": ground_truth,
                    "discovered": discovered,
                    "confidence": result.get("confidence", 0.5),
                    "match_result": match_result,
                    "processing_time": round(processing_time, 3),
                    "retries": retry
                }
                
            except Exception as e:
                logger.warning(f"评估失败 {theme} (重试 {retry+1}/{self.config['max_retries']}): {e}")
                if retry < self.config["max_retries"] - 1:
                    await asyncio.sleep(self.config["retry_delay"])
                else:
                    return {
                        "test_id": test_id,
                        "theme": theme,
                        "success": False,
                        "error": str(e),
                        "processing_time": round(time.time() - start_time, 3),
                        "retries": retry + 1
                    }
        
        return {
            "test_id": test_id,
            "theme": theme,
            "success": False,
            "error": "超出最大重试次数",
            "processing_time": round(time.time() - start_time, 3),
            "retries": self.config["max_retries"]
        }
    
    async def evaluate_batch(self, test_cases: List[Dict]) -> List[Dict]:
        """批量评估测试用例"""
        results = []
        total_cases = len(test_cases)
        
        for i, test_case in enumerate(test_cases):
            # 显示进度
            progress = (i + 1) / total_cases * 100
            logger.info(f"进度: {i+1}/{total_cases} ({progress:.1f}%) - {test_case.get('theme', f'case_{i}')}")
            
            # 评估单个用例
            result = await self.evaluate_single_case(test_case, i)
            results.append(result)
            
            # 批量大小控制，避免API限制
            if (i + 1) % self.config["batch_size"] == 0:
                logger.info(f"已处理 {i+1} 个用例，等待2秒...")
                await asyncio.sleep(2)
        
        return results
    
    def analyze_results(self, results: List[Dict]) -> Dict:
        """分析评估结果"""
        stats = {
            "total": len(results),
            "successful": 0,
            "failed": 0,
            "matched": 0,
            "similarities": [],
            "processing_times": [],
            "retries_count": defaultdict(int),
            "theme_stats": defaultdict(lambda: {
                "total": 0,
                "successful": 0,
                "matched": 0,
                "similarities": [],
                "processing_times": []
            }),
            "confidence_scores": []
        }
        
        for result in results:
            theme = result["theme"]
            stats["theme_stats"][theme]["total"] += 1
            
            if result["success"]:
                stats["successful"] += 1
                stats["theme_stats"][theme]["successful"] += 1
                
                match_result = result["match_result"]
                similarity = match_result["similarity"]
                
                stats["similarities"].append(similarity)
                stats["theme_stats"][theme]["similarities"].append(similarity)
                
                if "confidence" in result:
                    stats["confidence_scores"].append(result["confidence"])
                
                if match_result["matched"]:
                    stats["matched"] += 1
                    stats["theme_stats"][theme]["matched"] += 1
                
                if "processing_time" in result:
                    stats["processing_times"].append(result["processing_time"])
                    stats["theme_stats"][theme]["processing_times"].append(result["processing_time"])
                
                if "retries" in result:
                    stats["retries_count"][result["retries"]] += 1
            else:
                stats["failed"] += 1
        
        # 计算整体指标
        if stats["successful"] > 0:
            stats["accuracy"] = stats["matched"] / stats["successful"]
            stats["success_rate"] = stats["successful"] / stats["total"]
            
            if stats["similarities"]:
                stats["avg_similarity"] = statistics.mean(stats["similarities"])
                stats["max_similarity"] = max(stats["similarities"])
                stats["min_similarity"] = min(stats["similarities"])
                if len(stats["similarities"]) > 1:
                    stats["similarity_std"] = statistics.stdev(stats["similarities"])
                else:
                    stats["similarity_std"] = 0
            else:
                stats["avg_similarity"] = 0
                stats["max_similarity"] = 0
                stats["min_similarity"] = 0
                stats["similarity_std"] = 0
            
            if stats["processing_times"]:
                stats["avg_processing_time"] = statistics.mean(stats["processing_times"])
                stats["max_processing_time"] = max(stats["processing_times"])
                stats["min_processing_time"] = min(stats["processing_times"])
                if len(stats["processing_times"]) > 1:
                    stats["processing_time_std"] = statistics.stdev(stats["processing_times"])
                else:
                    stats["processing_time_std"] = 0
            else:
                stats["avg_processing_time"] = 0
                stats["max_processing_time"] = 0
                stats["min_processing_time"] = 0
                stats["processing_time_std"] = 0
            
            if stats["confidence_scores"]:
                stats["avg_confidence"] = statistics.mean(stats["confidence_scores"])
                stats["max_confidence"] = max(stats["confidence_scores"])
                stats["min_confidence"] = min(stats["confidence_scores"])
            else:
                stats["avg_confidence"] = 0
                stats["max_confidence"] = 0
                stats["min_confidence"] = 0
        else:
            stats["accuracy"] = 0
            stats["success_rate"] = 0
            stats["avg_similarity"] = 0
            stats["avg_processing_time"] = 0
            stats["avg_confidence"] = 0
        
        # 计算各主题指标
        for theme, theme_stat in stats["theme_stats"].items():
            if theme_stat["successful"] > 0:
                theme_stat["accuracy"] = theme_stat["matched"] / theme_stat["successful"]
                if theme_stat["similarities"]:
                    theme_stat["avg_similarity"] = statistics.mean(theme_stat["similarities"])
                    theme_stat["min_similarity"] = min(theme_stat["similarities"])
                    theme_stat["max_similarity"] = max(theme_stat["similarities"])
                else:
                    theme_stat["avg_similarity"] = 0
                    theme_stat["min_similarity"] = 0
                    theme_stat["max_similarity"] = 0
                
                if theme_stat["processing_times"]:
                    theme_stat["avg_processing_time"] = statistics.mean(theme_stat["processing_times"])
                else:
                    theme_stat["avg_processing_time"] = 0
            else:
                theme_stat["accuracy"] = 0
                theme_stat["avg_similarity"] = 0
                theme_stat["avg_processing_time"] = 0
        
        return dict(stats)  # 转换为普通dict
    
    def identify_problem_areas(self, stats: Dict, results: List[Dict]) -> Dict:
        """识别问题区域"""
        problem_areas = {
            "low_accuracy_themes": [],
            "failed_cases": [],
            "low_similarity_cases": [],
            "slow_processing_cases": [],
            "recommendations": []
        }
        
        # 收集失败案例
        for result in results:
            if not result["success"]:
                problem_areas["failed_cases"].append({
                    "theme": result["theme"],
                    "error": result.get("error", "未知错误"),
                    "test_id": result["test_id"]
                })
        
        # 识别低准确率主题
        for theme, theme_stat in stats["theme_stats"].items():
            if theme_stat.get("accuracy", 0) < 0.6 and theme_stat["total"] >= 2:
                problem_areas["low_accuracy_themes"].append({
                    "theme": theme,
                    "accuracy": theme_stat["accuracy"],
                    "samples": theme_stat["total"],
                    "avg_similarity": theme_stat.get("avg_similarity", 0)
                })
        
        # 识别低相似度案例
        for result in results:
            if result["success"]:
                similarity = result["match_result"].get("similarity", 0)
                if similarity < 0.4:
                    problem_areas["low_similarity_cases"].append({
                        "theme": result["theme"],
                        "similarity": similarity,
                        "ground_truth": result["ground_truth"],
                        "discovered": result["discovered"],
                        "test_id": result["test_id"]
                    })
        
        # 识别处理缓慢的案例
        if "processing_times" in stats and stats["processing_times"]:
            avg_time = stats["avg_processing_time"]
            for result in results:
                if result["success"] and "processing_time" in result:
                    if result["processing_time"] > avg_time * 2:  # 超过平均时间2倍
                        problem_areas["slow_processing_cases"].append({
                            "theme": result["theme"],
                            "processing_time": result["processing_time"],
                            "test_id": result["test_id"]
                        })
        
        # 生成建议
        if problem_areas["low_accuracy_themes"]:
            themes = [t["theme"] for t in problem_areas["low_accuracy_themes"][:3]]
            problem_areas["recommendations"].append(
                f"重点优化主题: {', '.join(themes)}。检查同义词映射和AI提示词。"
            )
        
        if problem_areas["failed_cases"]:
            problem_areas["recommendations"].append(
                f"处理失败 {len(problem_areas['failed_cases'])} 个案例，检查API连接和错误处理。"
            )
        
        if stats.get("accuracy", 0) < 0.8:
            problem_areas["recommendations"].append(
                f"整体准确率({stats.get('accuracy', 0):.1%})有待提升，建议优化匹配算法。"
            )
        
        if stats.get("avg_similarity", 0) < 0.7:
            problem_areas["recommendations"].append(
                f"平均相似度({stats.get('avg_similarity', 0):.3f})较低，建议扩展同义词库。"
            )
        
        return problem_areas


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='完整数据集评估器')
    parser.add_argument('--data_path', default='data/processed/validation_dataset.json')
    parser.add_argument('--output_dir', default='data/results/full_dataset')
    parser.add_argument('--threshold', type=float, default=0.7)
    parser.add_argument('--sample_limit', type=int, default=0, 
                       help='限制测试用例数量，0表示全部')
    
    args = parser.parse_args()
    
    print("🎯 AI题材引擎 - 完整数据集语义评估")
    print("=" * 70)
    print(f"数据集: {args.data_path}")
    print(f"相似度阈值: {args.threshold}")
    print(f"样本限制: {'全部' if args.sample_limit == 0 else args.sample_limit}")
    print("=" * 70)
    
    # 初始化评估器
    config = {
        "semantic_threshold": args.threshold,
        "eval_mode": "semantic",
        "batch_size": 5,
        "max_retries": 3,
        "retry_delay": 2
    }
    
    evaluator = FullDatasetEvaluator(config)
    
    if not await evaluator.initialize():
        print("❌ 评估器初始化失败")
        return 1
    
    # 加载数据
    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"❌ 数据文件不存在: {data_path}")
        return 1
    
    with open(data_path, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
    
    # 应用样本限制
    if args.sample_limit > 0:
        test_cases = test_cases[:args.sample_limit]
        print(f"📊 使用前 {len(test_cases)} 个测试用例（样本限制）")
    else:
        print(f"📊 加载全部 {len(test_cases)} 个测试用例")
    
    # 统计主题分布
    print("\n📁 数据集主题分布:")
    theme_counts = defaultdict(int)
    for case in test_cases:
        theme = case.get("theme", "unknown")
        theme_counts[theme] += 1
    
    for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {theme}: {count}个案例")
    
    print(f"\n🔬 开始评估...")
    print("   注意: 完整评估可能需要一些时间")
    print("   每个案例都会调用AI API进行分析")
    print("   请耐心等待...")
    
    start_time = time.time()
    
    # 运行评估
    try:
        results = await evaluator.evaluate_batch(test_cases)
    except KeyboardInterrupt:
        print("\n⚠️  评估被用户中断")
        return 1
    except Exception as e:
        print(f"❌ 评估过程出错: {e}")
        return 1
    
    total_time = time.time() - start_time
    
    # 分析结果
    stats = evaluator.analyze_results(results)
    problem_areas = evaluator.identify_problem_areas(stats, results)
    
    # 输出结果
    print(f"\n📊 评估完成!")
    print(f"   总耗时: {total_time:.1f}秒")
    print(f"   平均每个案例: {total_time/len(test_cases):.1f}秒")
    print("")
    print("📈 整体性能指标:")
    print("-" * 70)
    print(f"测试用例总数: {stats['total']}")
    print(f"成功处理数: {stats['successful']} ({stats.get('success_rate', 0):.1%})")
    print(f"匹配成功数: {stats['matched']} ({stats.get('accuracy', 0):.1%})")
    print(f"语义准确率: {stats.get('accuracy', 0):.1%}")
    print(f"平均语义相似度: {stats.get('avg_similarity', 0):.3f}")
    print(f"相似度范围: {stats.get('min_similarity', 0):.3f} - {stats.get('max_similarity', 0):.3f}")
    print(f"平均处理时间: {stats.get('avg_processing_time', 0):.2f}秒")
    print(f"平均置信度: {stats.get('avg_confidence', 0):.2f}")
    
    # 主题表现分析
    print(f"\n🎯 各主题表现 (按准确率排名):")
    theme_performance = []
    for theme, theme_stat in stats["theme_stats"].items():
        if theme_stat["successful"] > 0:
            accuracy = theme_stat.get("accuracy", 0)
            avg_sim = theme_stat.get("avg_similarity", 0)
            samples = theme_stat["successful"]
            theme_performance.append((theme, accuracy, avg_sim, samples))
    
    # 按准确率排序
    theme_performance.sort(key=lambda x: x[1], reverse=True)
    
    # 显示表现分类
    excellent = [(t, acc, sim, s) for t, acc, sim, s in theme_performance if acc >= 0.8]
    good = [(t, acc, sim, s) for t, acc, sim, s in theme_performance if 0.6 <= acc < 0.8]
    fair = [(t, acc, sim, s) for t, acc, sim, s in theme_performance if 0.4 <= acc < 0.6]
    poor = [(t, acc, sim, s) for t, acc, sim, s in theme_performance if acc < 0.4]
    
    if excellent:
        print(f"✅ 优秀表现 (准确率 ≥ 80%): {len(excellent)}个主题")
        for theme, accuracy, avg_sim, samples in excellent[:5]:
            print(f"   • {theme}: {accuracy:.1%} (相似度{avg_sim:.3f}, {samples}样本)")
    
    if good:
        print(f"\n⚠️  良好表现 (60-79%): {len(good)}个主题")
        for theme, accuracy, avg_sim, samples in good[:3]:
            print(f"   • {theme}: {accuracy:.1%} (相似度{avg_sim:.3f}, {samples}样本)")
    
    if fair:
        print(f"\n📝 一般表现 (40-59%): {len(fair)}个主题")
        for theme, accuracy, avg_sim, samples in fair[:3]:
            print(f"   • {theme}: {accuracy:.1%} (相似度{avg_sim:.3f}, {samples}样本)")
    
    if poor:
        print(f"\n❌ 需要改进 (<40%): {len(poor)}个主题")
        for theme, accuracy, avg_sim, samples in poor:
            print(f"   • {theme}: {accuracy:.1%} (相似度{avg_sim:.3f}, {samples}样本)")
    
    # 问题区域
    if problem_areas["low_accuracy_themes"]:
        print(f"\n🔧 重点优化建议:")
        for problem in problem_areas["low_accuracy_themes"][:5]:
            print(f"   • {problem['theme']}: 准确率{problem['accuracy']:.1%}, "
                  f"相似度{problem['avg_similarity']:.3f}")
    
    if problem_areas["failed_cases"]:
        print(f"\n⚠️  处理失败案例: {len(problem_areas['failed_cases'])}个")
        for case in problem_areas["failed_cases"][:3]:
            print(f"   • {case['theme']}: {case['error']}")
    
    # 业务价值评估
    print(f"\n💼 业务价值评估:")
    overall_accuracy = stats.get('accuracy', 0)
    avg_similarity = stats.get('avg_similarity', 0)
    
    if overall_accuracy >= 0.8 and avg_similarity >= 0.75:
        print("   ✅ 优秀 - 可以直接投入生产环境使用")
        print("       建议: 立即部署，建立同义词映射表即可")
    elif overall_accuracy >= 0.7:
        print("   ⚠️  良好 - 可以部署但建议继续优化")
        print("       建议: 部署后重点关注低准确率主题")
    elif overall_accuracy >= 0.6:
        print("   📝 一般 - 需要较多人工复核")
        print("       建议: 优化后再全面部署")
    else:
        print("   ❌ 需改进 - 需要深入优化")
        print("       建议: 分析架构问题，重新设计")
    
    # 保存结果
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    output_file = output_dir / f"full_evaluation_{timestamp}.json"
    
    # 准备保存的数据
    save_data = {
        "config": config,
        "stats": stats,
        "problem_areas": problem_areas,
        "theme_counts": dict(theme_counts),
        "summary": {
            "total_cases": stats["total"],
            "accuracy": stats.get("accuracy", 0),
            "avg_similarity": stats.get("avg_similarity", 0),
            "success_rate": stats.get("success_rate", 0),
            "total_time": total_time,
            "business_value": "优秀" if overall_accuracy >= 0.8 else "良好" if overall_accuracy >= 0.7 else "一般" if overall_accuracy >= 0.6 else "需改进"
        },
        "sample_results": results[:20]  # 只保存部分详细结果
    }
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        print(f"\n📁 评估结果已保存: {output_file}")
    except Exception as e:
        print(f"❌ 保存结果失败: {e}")
    
    print(f"\n🎯 下一步:")
    print("   1. 使用结果文件生成HTML报告")
    print("   2. 分析需要优化的主题")
    print("   3. 制定具体的优化计划")
    
    return 0


if __name__ == "__main__":
    asyncio.run(main())

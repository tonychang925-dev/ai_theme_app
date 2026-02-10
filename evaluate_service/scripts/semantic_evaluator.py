#!/usr/bin/env python3
"""
语义相似度评估器 - 基于语义而非字符串精确匹配
位置: evaluate_service/scripts/semantic_evaluator.py
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class SemanticThemeEvaluator:
    """
    语义主题评估器
    
    评估标准:
    1. 语义相似度 > 阈值 (如0.7)
    2. 关键词重叠度 > 阈值
    3. 行业关联一致性
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {
            "semantic_threshold": 0.7,     # 语义相似度阈值
            "keyword_threshold": 0.5,      # 关键词重叠阈值
            "industry_match_weight": 0.3,  # 行业匹配权重
            "use_synonyms": True,          # 使用同义词库
            "eval_mode": "semantic"        # 评估模式: strict|semantic|loose
        }
        
        # 同义词/近义词映射（可以根据业务扩展）
        self.synonym_mapping = {
            # AI/AR眼镜相关
            "AI/AR眼镜": ["智能眼镜", "AR眼镜", "AI眼镜", "混合现实眼镜", "智能穿戴设备"],
            "AI眼镜": ["智能眼镜", "AI/AR眼镜", "增强现实眼镜"],
            "智能眼镜": ["AI眼镜", "AR眼镜", "AI/AR眼镜", "智能穿戴"],
            
            # SpaceX相关
            "SpaceX": ["太空探索", "航天技术", "商业航天", "火箭发射"],
            "太空探索": ["SpaceX", "航天工程", "星际探索"],
            
            # 新能源汽车相关
            "新能源汽车": ["电动车", "电动汽车", "新能源车", "电动出行"],
            "电动车": ["新能源汽车", "电动汽车", "电动出行"],
            
            # 消费电子
            "消费电子": ["电子产品", "数码产品", "电子消费品"],
            "消费电子创新": ["消费电子", "电子产品创新", "数码创新"],
            
            # 通用映射
            "人工智能": ["AI", "人工智慧", "智能技术"],
            "AR/VR": ["增强现实", "虚拟现实", "混合现实"],
            "人机交互": ["交互技术", "人机界面", "用户体验"],
        }
        
        self.engine = None
    
    async def initialize(self) -> bool:
        """初始化AI引擎"""
        try:
            from theme_service.services.ai_client import AIThemeClient
            from theme_service.services.theme_discovery import ThemeDiscoveryEngine
            from theme_service.config import settings
            
            self.ai_client = AIThemeClient(settings)
            self.engine = ThemeDiscoveryEngine(self.ai_client)
            logger.info("语义评估器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False
    
    def expand_synonyms(self, themes: List[str]) -> List[str]:
        """扩展同义词"""
        expanded = set(themes)
        
        if self.config["use_synonyms"]:
            for theme in themes:
                if theme in self.synonym_mapping:
                    expanded.update(self.synonym_mapping[theme])
        
        return list(expanded)
    
    def calculate_semantic_similarity(self, theme1: str, theme2: str) -> float:
        """
        计算两个主题的语义相似度
        
        方法:
        1. 字符串相似度
        2. 关键词重叠
        3. 同义词匹配
        """
        # 0. 完全相等
        if theme1.lower() == theme2.lower():
            return 1.0
        
        # 1. 同义词检查
        if self.config["use_synonyms"]:
            if (theme1 in self.synonym_mapping and theme2 in self.synonym_mapping[theme1]) or \
               (theme2 in self.synonym_mapping and theme1 in self.synonym_mapping[theme2]):
                return 0.9
        
        # 2. 字符串相似度（简单实现）
        def string_similarity(s1: str, s2: str) -> float:
            # 使用集合交集计算相似度
            s1_words = set(s1.lower().replace('/', ' ').replace('-', ' ').split())
            s2_words = set(s2.lower().replace('/', ' ').replace('-', ' ').split())
            
            if not s1_words or not s2_words:
                return 0.0
            
            intersection = s1_words & s2_words
            union = s1_words | s2_words
            
            return len(intersection) / len(union)
        
        # 3. 关键词分析
        def keyword_overlap(s1: str, s2: str) -> float:
            # 中文关键词映射（简化的）
            keyword_map = {
                "AI": ["人工智能", "智能", "AI"],
                "AR": ["增强现实", "AR", "混合现实"],
                "VR": ["虚拟现实", "VR"],
                "眼镜": ["眼镜", "头显", "穿戴"],
                "新能源": ["新能源", "清洁能源", "绿色能源"],
                "汽车": ["汽车", "车辆", "出行"],
                "太空": ["太空", "航天", "空间"],
                "探索": ["探索", "开发", "研究"],
            }
            
            # 检查是否有共同的关键词类别
            s1_keywords = []
            s2_keywords = []
            
            for word, variants in keyword_map.items():
                for variant in variants:
                    if variant in s1:
                        s1_keywords.append(word)
                    if variant in s2:
                        s2_keywords.append(word)
            
            common = set(s1_keywords) & set(s2_keywords)
            total = set(s1_keywords) | set(s2_keywords)
            
            return len(common) / len(total) if total else 0.0
        
        str_sim = string_similarity(theme1, theme2)
        kw_overlap = keyword_overlap(theme1, theme2)
        
        # 加权综合相似度
        semantic_sim = 0.6 * str_sim + 0.4 * kw_overlap
        
        return semantic_sim
    
    def evaluate_single_match(self, discovered: List[str], ground_truth: List[str]) -> Dict:
        """
        评估单个匹配结果
        
        Returns:
            Dict: 包含匹配详情和相似度评分
        """
        # 扩展同义词
        expanded_truth = self.expand_synonyms(ground_truth)
        expanded_discovered = self.expand_synonyms(discovered)
        
        best_match = {
            "matched": False,
            "match_type": "none",
            "similarity": 0.0,
            "best_pair": ("", ""),
            "details": []
        }
        
        # 检查所有组合
        for truth in expanded_truth:
            for disc in expanded_discovered:
                similarity = self.calculate_semantic_similarity(truth, disc)
                
                best_match["details"].append({
                    "truth": truth,
                    "discovered": disc,
                    "similarity": similarity
                })
                
                if similarity > best_match["similarity"]:
                    best_match["similarity"] = similarity
                    best_match["best_pair"] = (truth, disc)
                    
                    # 根据评估模式判断是否匹配
                    if self.config["eval_mode"] == "strict":
                        matched = similarity >= 0.9
                        match_type = "strict" if matched else "none"
                    elif self.config["eval_mode"] == "semantic":
                        matched = similarity >= self.config["semantic_threshold"]
                        match_type = "semantic" if matched else "none"
                    else:  # loose
                        matched = similarity >= 0.5
                        match_type = "loose" if matched else "none"
                    
                    best_match["matched"] = matched
                    best_match["match_type"] = match_type
        
        # 按相似度排序详情
        best_match["details"].sort(key=lambda x: x["similarity"], reverse=True)
        
        return best_match
    
    async def evaluate_test_case(self, test_case: Dict) -> Dict:
        """评估单个测试用例"""
        if self.engine is None:
            if not await self.initialize():
                return {
                    "theme": test_case.get("theme", "unknown"),
                    "success": False,
                    "error": "引擎初始化失败"
                }
        
        theme = test_case.get("theme", "unknown")
        
        # 构建事件
        mock_event = {
            "id": test_case.get("test_id", f"semantic_{hash(str(test_case))}"),
            "title": test_case.get("title", ""),
            "summary": test_case.get("content", "")[:200],
            "content": test_case.get("content", ""),
            "impact_industries": test_case.get("impact_industries", [])
        }
        
        try:
            # 获取引擎结果
            result = await self.engine.process_single_event(mock_event)
            
            discovered = result.get("themes_found", [])
            ground_truth = test_case.get("ground_truth_themes", [])
            
            # 语义匹配评估
            match_result = self.evaluate_single_match(discovered, ground_truth)
            
            return {
                "theme": theme,
                "success": True,
                "ground_truth": ground_truth,
                "discovered": discovered,
                "confidence": result.get("confidence", 0.5),
                "match_result": match_result,
                "ai_analysis": {
                    "event_type": result.get("event_type", ""),
                    "impact_industries": result.get("impact_industries", [])
                }
            }
            
        except Exception as e:
            logger.error(f"评估失败 {theme}: {e}")
            return {
                "theme": theme,
                "success": False,
                "error": str(e)
            }
    
    async def evaluate_batch(self, test_cases: List[Dict], sample_size: int = None) -> Dict:
        """批量评估"""
        if sample_size is None:
            sample_size = len(test_cases)
        
        sample_size = min(sample_size, len(test_cases))
        
        logger.info(f"开始语义评估 {sample_size} 个测试用例")
        logger.info(f"评估模式: {self.config['eval_mode']}, 阈值: {self.config['semantic_threshold']}")
        
        results = []
        for i in range(sample_size):
            result = await self.evaluate_test_case(test_cases[i])
            results.append(result)
            
            if (i + 1) % 5 == 0:
                logger.info(f"已处理 {i+1}/{sample_size} 个用例")
        
        # 计算语义评估指标
        metrics = self._calculate_semantic_metrics(results)
        
        return {
            "config": self.config,
            "total_cases": sample_size,
            "results": results,
            "metrics": metrics
        }
    
    def _calculate_semantic_metrics(self, results: List[Dict]) -> Dict:
        """计算语义评估指标"""
        stats = {
            "total": len(results),
            "successful": 0,
            "failed": 0,
            "matched_strict": 0,    # 相似度 >= 0.9
            "matched_semantic": 0,  # 相似度 >= semantic_threshold
            "matched_loose": 0,     # 相似度 >= 0.5
            "similarity_scores": [],
            "theme_performance": {}
        }
        
        for result in results:
            theme = result.get("theme", "unknown")
            
            if theme not in stats["theme_performance"]:
                stats["theme_performance"][theme] = {
                    "total": 0,
                    "matched": 0,
                    "similarities": []
                }
            
            stats["theme_performance"][theme]["total"] += 1
            
            if result.get("success", False):
                stats["successful"] += 1
                
                match_result = result.get("match_result", {})
                similarity = match_result.get("similarity", 0)
                
                stats["similarity_scores"].append(similarity)
                stats["theme_performance"][theme]["similarities"].append(similarity)
                
                # 统计不同严格程度的匹配
                if similarity >= 0.9:
                    stats["matched_strict"] += 1
                    stats["theme_performance"][theme]["matched"] += 1
                elif similarity >= self.config["semantic_threshold"]:
                    stats["matched_semantic"] += 1
                    stats["theme_performance"][theme]["matched"] += 1
                elif similarity >= 0.5:
                    stats["matched_loose"] += 1
            else:
                stats["failed"] += 1
        
        # 计算准确率
        if stats["successful"] > 0:
            stats["accuracy_strict"] = stats["matched_strict"] / stats["successful"]
            stats["accuracy_semantic"] = stats["matched_semantic"] / stats["successful"]
            stats["accuracy_loose"] = stats["matched_loose"] / stats["successful"]
            
            # 平均相似度
            if stats["similarity_scores"]:
                stats["avg_similarity"] = sum(stats["similarity_scores"]) / len(stats["similarity_scores"])
                stats["max_similarity"] = max(stats["similarity_scores"])
                stats["min_similarity"] = min(stats["similarity_scores"])
            else:
                stats["avg_similarity"] = 0.0
                stats["max_similarity"] = 0.0
                stats["min_similarity"] = 0.0
        else:
            stats["accuracy_strict"] = 0.0
            stats["accuracy_semantic"] = 0.0
            stats["accuracy_loose"] = 0.0
            stats["avg_similarity"] = 0.0
            stats["max_similarity"] = 0.0
            stats["min_similarity"] = 0.0
        
        return stats


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='语义相似度评估器')
    parser.add_argument('--data_path', default='data/processed/validation_dataset.json',
                       help='测试数据集路径')
    parser.add_argument('--output_dir', default='data/results/semantic',
                       help='输出目录')
    parser.add_argument('--sample_size', type=int, default=20,
                       help='采样数量')
    parser.add_argument('--eval_mode', default='semantic',
                       choices=['strict', 'semantic', 'loose'],
                       help='评估模式')
    parser.add_argument('--threshold', type=float, default=0.7,
                       help='语义相似度阈值')
    
    args = parser.parse_args()
    
    print("🎯 语义相似度评估器")
    print("=" * 60)
    print(f"评估模式: {args.eval_mode}")
    print(f"相似度阈值: {args.threshold}")
    print(f"目标: 评估语义一致性，而非字符串精确匹配")
    print("=" * 60)
    
    # 配置评估器
    config = {
        "semantic_threshold": args.threshold,
        "eval_mode": args.eval_mode,
        "use_synonyms": True
    }
    
    evaluator = SemanticThemeEvaluator(config)
    
    # 加载数据
    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"❌ 数据文件不存在: {data_path}")
        return 1
    
    with open(data_path, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
    
    print(f"📊 加载 {len(test_cases)} 个测试用例")
    print(f"🎯 评估样本: {min(args.sample_size, len(test_cases))}")
    
    # 运行评估
    results = await evaluator.evaluate_batch(test_cases, args.sample_size)
    
    # 输出结果
    metrics = results["metrics"]
    
    print(f"\\n📊 语义评估结果")
    print("-" * 40)
    print(f"测试用例总数: {metrics['total']}")
    print(f"成功处理数: {metrics['successful']}")
    print(f"失败处理数: {metrics['failed']}")
    print(f"平均语义相似度: {metrics.get('avg_similarity', 0):.3f}")
    print(f"语义相似度范围: {metrics.get('min_similarity', 0):.3f} - {metrics.get('max_similarity', 0):.3f}")
    print(f"严格准确率 (≥0.9): {metrics['accuracy_strict']:.1%}")
    print(f"语义准确率 (≥{args.threshold}): {metrics['accuracy_semantic']:.1%}")
    print(f"宽松准确率 (≥0.5): {metrics['accuracy_loose']:.1%}")
    
    # 显示主题表现
    if metrics['theme_performance']:
        print(f"\\n🎯 各主题语义匹配表现:")
        
        for theme, perf in metrics['theme_performance'].items():
            if perf['total'] > 0:
                avg_sim = sum(perf['similarities']) / len(perf['similarities']) if perf['similarities'] else 0
                match_rate = perf['matched'] / perf['total']
                
                if match_rate >= 0.8:
                    status = "✅ 优秀"
                elif match_rate >= 0.6:
                    status = "⚠️  良好"
                elif match_rate >= 0.4:
                    status = "📝 一般"
                else:
                    status = "❌ 需改进"
                
                print(f"  {status} {theme}: 匹配率{match_rate:.1%}, 平均相似度{avg_sim:.3f}")
    
    # 显示语义匹配示例
    print(f"\\n🔍 语义匹配示例 (前3个):")
    example_count = 0
    for result in results["results"]:
        if result.get("success", False) and example_count < 3:
            match_result = result.get("match_result", {})
            
            if match_result.get("similarity", 0) >= 0.7:
                best_pair = match_result.get("best_pair", ("", ""))
                print(f"  主题: {result['theme']}")
                print(f"    久赢恒丰: {best_pair[0]}")
                print(f"    我们的AI: {best_pair[1]}")
                print(f"    语义相似度: {match_result['similarity']:.3f}")
                print(f"    是否匹配: {'✅' if match_result['matched'] else '❌'}")
                print()
                example_count += 1
    
    # 保存结果
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = asyncio.get_event_loop().time()
    output_file = output_dir / f"semantic_eval_{int(timestamp)}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"📁 结果保存至: {output_file}")
    
    # 评估结论
    print(f"\\n📋 评估结论:")
    if metrics['accuracy_semantic'] >= 0.8:
        print("  ✅ 语义匹配表现优秀，AI能够理解并正确分类事件主题")
    elif metrics['accuracy_semantic'] >= 0.6:
        print("  ⚠️  语义匹配表现良好，但仍有优化空间")
    elif metrics['accuracy_semantic'] >= 0.4:
        print("  📝 语义匹配表现一般，需要优化主题库或AI提示词")
    else:
        print("  ❌ 语义匹配表现较差，需要深入分析问题")
    
    return 0


if __name__ == "__main__":
    asyncio.run(main())

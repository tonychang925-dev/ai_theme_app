#!/usr/bin/env python3
"""
语义相似度评估器 - 修复版
修复了matched判断逻辑问题
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


class SemanticThemeEvaluatorFixed:
    """修复版语义主题评估器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {
            "semantic_threshold": 0.7,
            "keyword_threshold": 0.5,
            "eval_mode": "semantic"
        }
        
        # 简化的同义词映射
        self.synonym_mapping = {
            "AI/AR眼镜": ["智能眼镜", "AR眼镜", "AI眼镜", "混合现实眼镜", "MR眼镜", "XR设备"],
            "智能眼镜": ["AI/AR眼镜", "AI眼镜", "AR眼镜"],
            "AI眼镜": ["AI/AR眼镜", "智能眼镜"],
            "AR眼镜": ["AI/AR眼镜", "智能眼镜"],
            
            "SpaceX": ["太空探索", "商业航天", "航天技术", "火箭发射"],
            "太空探索": ["SpaceX", "商业航天"],
            "商业航天": ["SpaceX", "太空探索"],
            
            "可控核聚变": ["核聚变", "人造太阳", "聚变能源", "终极能源"],
            "核聚变": ["可控核聚变", "人造太阳"],
            
            "人机交互": ["交互技术", "人机界面", "用户体验"],
            "消费电子创新": ["消费电子", "电子产品创新", "数码创新"],
        }
        
        self.engine = None
    
    async def initialize(self) -> bool:
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
    
    def calculate_similarity(self, theme1: str, theme2: str) -> float:
        """计算两个主题的相似度（修复版）"""
        # 0. 完全相等
        if theme1.lower() == theme2.lower():
            return 1.0
        
        # 1. 检查同义词
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
        
        # 2. 字符串相似度（简化的Jaccard相似度）
        words1 = set(theme1_lower.replace('/', ' ').replace('-', ' ').replace('_', ' ').split())
        words2 = set(theme2_lower.replace('/', ' ').replace('-', ' ').replace('_', ' ').split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        similarity = len(intersection) / len(union)
        
        # 3. 如果包含关系，提高相似度
        if words1.issubset(words2) or words2.issubset(words1):
            similarity = max(similarity, 0.7)
        
        return similarity
    
    def evaluate_match(self, discovered: List[str], ground_truth: List[str]) -> Dict:
        """评估匹配结果（修复版）"""
        best_match = {
            "matched": False,
            "match_type": "none",
            "similarity": 0.0,
            "best_pair": ("", ""),
            "details": []
        }
        
        # 处理ground_truth
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
                        
                        # 根据评估模式判断是否匹配（修复了这里的逻辑）
                        eval_mode = self.config.get("eval_mode", "semantic")
                        threshold = self.config.get("semantic_threshold", 0.7)
                        
                        if eval_mode == "strict":
                            best_match["matched"] = similarity >= 0.9
                            best_match["match_type"] = "strict" if best_match["matched"] else "none"
                        elif eval_mode == "semantic":
                            best_match["matched"] = similarity >= threshold
                            best_match["match_type"] = "semantic" if best_match["matched"] else "none"
                        else:  # loose
                            best_match["matched"] = similarity >= 0.5
                            best_match["match_type"] = "loose" if best_match["matched"] else "none"
        
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
            "id": test_case.get("test_id", f"eval_{hash(str(test_case))}"),
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
            match_result = self.evaluate_match(discovered, ground_truth)
            
            return {
                "theme": theme,
                "success": True,
                "ground_truth": ground_truth,
                "discovered": discovered,
                "confidence": result.get("confidence", 0.5),
                "match_result": match_result
            }
            
        except Exception as e:
            logger.error(f"评估失败 {theme}: {e}")
            return {
                "theme": theme,
                "success": False,
                "error": str(e)
            }


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='修复版语义相似度评估器')
    parser.add_argument('--data_path', default='data/processed/validation_dataset.json')
    parser.add_argument('--output_dir', default='data/results/semantic_fixed')
    parser.add_argument('--sample_size', type=int, default=10)
    parser.add_argument('--eval_mode', default='semantic', choices=['strict', 'semantic', 'loose'])
    parser.add_argument('--threshold', type=float, default=0.7)
    
    args = parser.parse_args()
    
    print("🎯 修复版语义相似度评估器")
    print("=" * 60)
    print(f"评估模式: {args.eval_mode}")
    print(f"相似度阈值: {args.threshold}")
    print("=" * 60)
    
    # 配置评估器
    config = {
        "semantic_threshold": args.threshold,
        "eval_mode": args.eval_mode
    }
    
    evaluator = SemanticThemeEvaluatorFixed(config)
    
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
    results = []
    sample_size = min(args.sample_size, len(test_cases))
    
    for i in range(sample_size):
        result = await evaluator.evaluate_test_case(test_cases[i])
        results.append(result)
        
        if (i + 1) % 5 == 0:
            print(f"  已处理 {i+1}/{sample_size}")
    
    # 计算指标
    stats = {
        "total": len(results),
        "successful": 0,
        "failed": 0,
        "matched": 0,
        "similarities": []
    }
    
    for result in results:
        if result.get("success", False):
            stats["successful"] += 1
            match_result = result.get("match_result", {})
            similarity = match_result.get("similarity", 0)
            
            stats["similarities"].append(similarity)
            
            if match_result.get("matched", False):
                stats["matched"] += 1
        else:
            stats["failed"] += 1
    
    # 计算准确率
    if stats["successful"] > 0:
        accuracy = stats["matched"] / stats["successful"]
        avg_similarity = sum(stats["similarities"]) / len(stats["similarities"])
        max_similarity = max(stats["similarities"])
        min_similarity = min(stats["similarities"])
    else:
        accuracy = 0.0
        avg_similarity = 0.0
        max_similarity = 0.0
        min_similarity = 0.0
    
    print(f"\\n📊 语义评估结果")
    print("-" * 40)
    print(f"测试用例总数: {stats['total']}")
    print(f"成功处理数: {stats['successful']}")
    print(f"匹配成功数: {stats['matched']}")
    print(f"准确率: {accuracy:.1%}")
    print(f"平均相似度: {avg_similarity:.3f}")
    print(f"相似度范围: {min_similarity:.3f} - {max_similarity:.3f}")
    
    # 显示匹配详情
    print(f"\\n🔍 匹配详情 (前3个):")
    for result in results[:3]:
        if result.get("success", False):
            theme = result["theme"]
            match_result = result["match_result"]
            matched = match_result["matched"]
            similarity = match_result["similarity"]
            best_pair = match_result.get("best_pair", ("", ""))
            
            status = "✅" if matched else "❌"
            print(f"  {status} {theme}: 相似度={similarity:.3f}, 匹配={matched}")
            print(f"     久赢恒丰: {best_pair[0]}")
            print(f"     我们的AI: {best_pair[1]}")
            
            # 显示相似度最高的详情
            if match_result["details"]:
                best_detail = match_result["details"][0]
                print(f"     最佳匹配: '{best_detail['truth']}' ≈ '{best_detail['discovered']}' ({best_detail['similarity']:.3f})")
            print()
    
    # 业务价值评估
    print(f"💼 业务价值评估:")
    if accuracy >= 0.8:
        print("  ✅ 优秀 - AI能够准确理解事件主题，分类结果可直接用于投资分析")
        print("      建议: 可以直接投入生产环境使用")
    elif accuracy >= 0.6:
        print("  ⚠️  良好 - AI基本理解事件主题，分类结果有较好参考价值")
        print("      建议: 可以应用，但建议增加人工复核")
    elif accuracy >= 0.4:
        print("  📝 一般 - AI对主题理解有限，分类结果需较多人工复核")
        print("      建议: 需要优化后再投入实际使用")
    else:
        print("  ❌ 需改进 - AI难以理解事件主题，分类结果业务价值有限")
        print("      建议: 需要深入分析和优化")
    
    # 保存结果
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = asyncio.get_event_loop().time()
    output_file = output_dir / f"semantic_fixed_{int(timestamp)}.json"
    
    result_data = {
        "config": config,
        "stats": stats,
        "accuracy": accuracy,
        "avg_similarity": avg_similarity,
        "results": results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    print(f"\\n📁 结果保存至: {output_file}")
    
    return 0


if __name__ == "__main__":
    asyncio.run(main())

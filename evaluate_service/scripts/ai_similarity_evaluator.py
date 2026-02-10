# ai_theme_app/evaluate_service/scripts/ai_similarity_evaluator.py
"""
AI相似性分析器评估脚本 - 使用真实AI大模型
针对主题名称生成问题的专项评估
"""
import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RealAIEvaluator:
    """使用真实AI大模型的评估器"""
    
    def __init__(self):
        self.parser = None
        self.analyzer = None
        self.test_results = []
        
    async def initialize_ai_service(self):
        """初始化真实的AI服务"""
        try:
            # 检查API密钥
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                logger.error("❌ DEEPSEEK_API_KEY 环境变量未设置")
                logger.info("请设置环境变量: export DEEPSEEK_API_KEY='your-api-key'")
                return False
            
            # 尝试导入DeepSeek解析器
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 🔥 修复：使用正确的构造函数参数
            # ReliableDeepSeekParser 只接受 model_name 参数
            self.parser = ReliableDeepSeekParser(model_name="deepseek-chat")
            
            logger.info("✅ 成功创建DeepSeek解析器实例")
            
            # 简单的健康检查
            try:
                health_status = await self.parser.health_check()
                logger.info(f"健康检查结果: {health_status.get('is_healthy', False)}")
                
                if health_status.get('is_healthy', False):
                    # 创建分析器
                    from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
                    self.analyzer = AIThemeSimilarityAnalyzer(self.parser)
                    logger.info("✅ AI主题相似性分析器初始化完成")
                    
                    # 测试一个简单调用
                    test_result = await self.test_simple_ai_call()
                    if test_result:
                        logger.info("✅ AI服务测试调用成功")
                        return True
                    else:
                        logger.error("❌ AI服务测试调用失败")
                        return False
                else:
                    logger.error(f"❌ AI服务健康检查失败: {health_status}")
                    return False
                    
            except Exception as health_e:
                logger.error(f"❌ 健康检查异常: {health_e}")
                import traceback
                logger.error(traceback.format_exc())
                return False
                
        except ImportError as e:
            logger.error(f"❌ 无法导入DeepSeek解析器: {e}")
            logger.info("请确保 model_service 模块正确安装")
            return False
        except Exception as e:
            logger.error(f"❌ 初始化AI服务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.info("可能需要配置API密钥或检查网络连接")
            return False
    
    async def test_simple_ai_call(self):
        """测试简单的AI调用"""
        try:
            # 非常简单的测试内容
            test_content = "请用JSON格式回复：{'test': 'success'}"
            logger.info("🔧 测试AI调用...")
            
            result = await self.parser.parse_content(test_content)
            
            if result:
                logger.info(f"✅ AI测试调用成功，返回: {type(result)}")
                return True
            else:
                logger.warning("⚠️ AI返回空结果")
                return False
                
        except Exception as e:
            logger.error(f"❌ AI测试调用失败: {e}")
            return False
    
    def get_test_cases(self) -> List[Dict[str, Any]]:
        """获取真实的测试用例"""
        return [
            # 🔥 关键测试案例1：SpaceX卫星采购（原始问题案例）
            {
                "id": "spacex_001",
                "name": "SpaceX卫星采购",
                "description": "国防卫星采购事件，应该创建航天军工主题，而不是消费电子",
                "event": {
                    "news_id": "spacex_001",
                    "original_news": {
                        "title": "美国太空军采购72颗导弹预警和跟踪卫星",
                        "content": """
美国太空军与SpaceX公司签署了价值25亿美元的合同，采购72颗先进的导弹预警和跟踪卫星。
这批卫星将用于增强美国的导弹防御能力，能够实时监测全球范围内的导弹发射活动。
合同包括卫星的设计、制造、发射和在轨维护，预计在2026年前完成部署。
这是美国国防部太空战略的重要组成部分，也是SpaceX获得的最大军事合同之一。
                        """
                    },
                    "event_info": {
                        "event_type": "国防采购",
                        "impact_industries": ["航天", "军工", "国防科技", "卫星技术"],
                        "direction": "正面",
                        "event_confidence": 0.95
                    },
                    "theme_discovery_directive": {
                        "action": "CLUSTER",
                        "decision_confidence": 0.8,
                        "reason": "国防航天领域重大采购事件"
                    }
                },
                "existing_themes": [
                    {
                        "id": 1,
                        "name": "消费电子",
                        "description": "消费电子产品和技术发展，包括智能手机、电脑、可穿戴设备等",
                        "keywords": ["消费电子", "智能手机", "智能家居", "电子产品", "数码产品"],
                        "event_count": 15,
                        "confidence": 0.85
                    },
                    {
                        "id": 2,
                        "name": "人工智能技术",
                        "description": "人工智能算法、模型和应用技术",
                        "keywords": ["AI", "人工智能", "机器学习", "深度学习", "算法"],
                        "event_count": 12,
                        "confidence": 0.9
                    }
                ],
                "expected_outcome": {
                    "should_not_match": ["消费电子"],  # 绝对不能匹配消费电子
                    "good_names": ["国防卫星", "航天军工", "卫星技术", "导弹预警"],
                    "bad_suffixes": ["相关", "新闻", "报道"],
                    "expected_action": "CREATE_NEW"
                }
            },
            
            # 🔥 关键测试案例2：Meta智能眼镜（正确匹配消费电子）
            {
                "id": "meta_001",
                "name": "Meta智能眼镜",
                "description": "消费电子产品发布，应该匹配消费电子主题",
                "event": {
                    "news_id": "meta_001",
                    "original_news": {
                        "title": "Meta与Oakley合作发布新一代智能眼镜",
                        "content": """
Meta公司近日与著名运动品牌Oakley合作，发布了新一代智能眼镜产品。
这款眼镜集成了AR增强现实技术和AI人工智能，具备实时翻译、导航、运动监测等功能。
产品采用轻量化设计，电池续航达到8小时，支持5G网络连接。
定价299美元，预计下个月在全球主要市场上市销售。
                        """
                    },
                    "event_info": {
                        "event_type": "产品发布",
                        "impact_industries": ["消费电子", "人工智能", "可穿戴设备", "AR技术"],
                        "direction": "正面",
                        "event_confidence": 0.85
                    }
                },
                "existing_themes": [
                    {
                        "id": 1,
                        "name": "消费电子",
                        "description": "消费电子产品和技术",
                        "keywords": ["消费电子", "智能硬件", "可穿戴设备", "电子产品"],
                        "event_count": 10,
                        "confidence": 0.8
                    }
                ],
                "expected_outcome": {
                    "can_match": ["消费电子"],  # 可以匹配消费电子
                    "good_names": ["智能穿戴", "AR眼镜", "可穿戴设备"],
                    "bad_suffixes": ["相关", "新闻"],
                    "expected_action": "MERGE_WITH_EXISTING"
                }
            },
            
            # 🔥 关键测试案例3：台积电芯片技术（半导体领域）
            {
                "id": "tsmc_001",
                "name": "台积电芯片技术",
                "description": "半导体技术突破，应该创建半导体主题",
                "event": {
                    "news_id": "tsmc_001",
                    "original_news": {
                        "title": "台积电宣布2nm芯片制造技术突破",
                        "content": """
台积电（TSMC）宣布在2nm芯片制造技术上取得重大突破。
新技术将使晶体管密度提高30%，功耗降低25%，性能提升15%。
台积电计划在2025年开始量产2nm芯片，已经获得苹果、英伟达、AMD等主要客户的订单。
这一技术突破将推动整个半导体产业的发展。
                        """
                    },
                    "event_info": {
                        "event_type": "技术突破",
                        "impact_industries": ["半导体", "芯片制造", "集成电路", "高科技"],
                        "direction": "正面",
                        "event_confidence": 0.9
                    }
                },
                "existing_themes": [
                    {
                        "id": 1,
                        "name": "消费电子",
                        "description": "消费电子产品",
                        "keywords": ["消费电子"],
                        "event_count": 5
                    }
                ],
                "expected_outcome": {
                    "should_not_match": ["消费电子"],  # 不能匹配消费电子
                    "good_names": ["半导体", "芯片技术", "集成电路", "先进制程"],
                    "bad_suffixes": ["相关", "新闻"],
                    "expected_action": "CREATE_NEW"
                }
            }
        ]
    
    async def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """运行单个测试用例"""
        case_id = test_case["id"]
        case_name = test_case["name"]
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📋 测试用例: {case_name} ({case_id})")
        logger.info(f"描述: {test_case['description']}")
        
        try:
            # 记录开始时间
            start_time = datetime.now()
            
            # 运行AI分析
            result = await self.analyzer.analyze_similarity(
                test_case["event"],
                test_case["existing_themes"]
            )
            
            # 记录耗时
            time_cost = (datetime.now() - start_time).total_seconds()
            
            # 提取关键信息
            theme_name = result.get('most_similar_theme', {}).get('theme_name', '')
            recommendation = result.get('recommendation', '')
            confidence = result.get('most_similar_theme', {}).get('confidence', 0)
            reason = result.get('recommendation_reason', '')[:200] if result.get('recommendation_reason') else ""
            
            # 评估结果
            evaluation = self.evaluate_test_result(result, test_case)
            
            # 构建测试结果
            test_result = {
                "case_id": case_id,
                "case_name": case_name,
                "time_cost": time_cost,
                "theme_name": theme_name,
                "recommendation": recommendation,
                "confidence": confidence,
                "reason": reason,
                "evaluation": evaluation,
                "success": evaluation["score"] >= 0.7
            }
            
            # 输出结果
            self.print_test_result(test_result)
            
            return test_result
            
        except Exception as e:
            logger.error(f"❌ 测试用例执行失败: {e}")
            import traceback
            traceback_text = traceback.format_exc()
            logger.error(f"堆栈跟踪: {traceback_text}")
            
            return {
                "case_id": case_id,
                "case_name": case_name,
                "error": str(e),
                "traceback": traceback_text,
                "success": False
            }
    
    def evaluate_test_result(self, result: Dict[str, Any], test_case: Dict[str, Any]) -> Dict[str, Any]:
        """评估测试结果"""
        evaluation = {
            "score": 0.0,
            "theme_name_quality": 0.0,
            "decision_correctness": 0.0,
            "naming_issues": [],
            "decision_issues": [],
            "warnings": []
        }
        
        theme_name = result.get('most_similar_theme', {}).get('theme_name', '')
        recommendation = result.get('recommendation', '')
        expected = test_case.get('expected_outcome', {})
        
        # 1. 评估主题名称质量
        name_score = 1.0
        
        # 检查是否包含禁止的后缀
        bad_suffixes = expected.get('bad_suffixes', ["相关", "新闻", "报道", "资讯"])
        for suffix in bad_suffixes:
            if suffix in theme_name:
                name_score -= 0.5
                evaluation["naming_issues"].append(f"包含禁止词汇: '{suffix}'")
                break
        
        # 检查是否包含禁止匹配的主题
        should_not_match = expected.get('should_not_match', [])
        for bad_theme in should_not_match:
            if bad_theme in theme_name:
                name_score -= 0.7  # 严重错误
                evaluation["naming_issues"].append(f"错误匹配到禁止主题: '{bad_theme}'")
        
        # 检查名称长度
        if len(theme_name) < 2:
            name_score -= 0.3
            evaluation["naming_issues"].append("主题名称太短")
        elif len(theme_name) > 12:
            name_score -= 0.1
            evaluation["warnings"].append("主题名称可能过长")
        
        # 检查是否包含好的名称关键词
        good_names = expected.get('good_names', [])
        if good_names:
            has_good_keyword = any(keyword in theme_name for keyword in good_names)
            if has_good_keyword:
                name_score += 0.2
                evaluation["warnings"].append("主题名称包含好的关键词")
            elif theme_name and theme_name not in ["未分类主题", "科技创新"]:
                evaluation["warnings"].append("主题名称可能不够准确")
        
        evaluation["theme_name_quality"] = max(0.0, min(1.0, name_score))
        
        # 2. 评估决策正确性
        expected_action = expected.get('expected_action', '')
        if expected_action:
            if recommendation == expected_action:
                evaluation["decision_correctness"] = 1.0
            else:
                evaluation["decision_correctness"] = 0.0
                evaluation["decision_issues"].append(
                    f"决策错误: 期望'{expected_action}', 实际'{recommendation}'"
                )
        
        # 3. 计算总分
        weights = {
            "theme_name_quality": 0.6,
            "decision_correctness": 0.4
        }
        
        evaluation["score"] = (
            evaluation["theme_name_quality"] * weights["theme_name_quality"] +
            evaluation["decision_correctness"] * weights["decision_correctness"]
        )
        
        # 如果有严重问题，降低分数
        if "错误匹配到禁止主题" in str(evaluation["naming_issues"]):
            evaluation["score"] = max(0.0, evaluation["score"] - 0.3)
        
        return evaluation
    
    def print_test_result(self, test_result: Dict[str, Any]):
        """打印测试结果"""
        logger.info(f"📊 测试结果:")
        logger.info(f"  主题名称: {test_result['theme_name']}")
        logger.info(f"  推荐动作: {test_result['recommendation']}")
        logger.info(f"  置信度: {test_result['confidence']:.2f}")
        logger.info(f"  耗时: {test_result['time_cost']:.2f}秒")
        
        eval_info = test_result['evaluation']
        logger.info(f"  评估分数: {eval_info['score']:.2f}")
        logger.info(f"  名称质量: {eval_info['theme_name_quality']:.2f}")
        logger.info(f"  决策正确: {eval_info['decision_correctness']:.2f}")
        
        if eval_info['naming_issues']:
            logger.warning(f"  ⚠️  命名问题:")
            for issue in eval_info['naming_issues']:
                logger.warning(f"    - {issue}")
        
        if eval_info['decision_issues']:
            logger.error(f"  ❌ 决策问题:")
            for issue in eval_info['decision_issues']:
                logger.error(f"    - {issue}")
        
        if eval_info['warnings']:
            logger.info(f"  📝 备注:")
            for warning in eval_info['warnings']:
                logger.info(f"    - {warning}")
        
        if test_result['success']:
            logger.info(f"  ✅ 测试通过")
        else:
            logger.error(f"  ❌ 测试失败")
    
    async def run_all_tests(self):
        """运行所有测试用例"""
        logger.info("🚀 开始运行所有测试用例...")
        
        # 获取测试用例
        test_cases = self.get_test_cases()
        logger.info(f"📋 共 {len(test_cases)} 个测试用例")
        
        # 运行测试
        all_results = []
        for test_case in test_cases:
            result = await self.run_single_test(test_case)
            all_results.append(result)
            
            # 添加延迟避免API限流
            if test_case != test_cases[-1]:
                logger.info(f"⏳ 等待2秒后继续下一个测试...")
                await asyncio.sleep(2)
        
        # 生成总结报告
        self.generate_summary_report(all_results)
        
        return all_results
    
    def generate_summary_report(self, results: List[Dict[str, Any]]):
        """生成总结报告"""
        logger.info("\n" + "="*80)
        logger.info("📈 测试总结报告")
        logger.info("="*80)
        
        # 统计信息
        total = len(results)
        passed = sum(1 for r in results if r.get('success', False))
        failed = total - passed
        
        # 计算平均分
        scores = [r.get('evaluation', {}).get('score', 0) for r in results if 'evaluation' in r]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # 计算平均耗时
        times = [r.get('time_cost', 0) for r in results if 'time_cost' in r]
        avg_time = sum(times) / len(times) if times else 0
        
        logger.info(f"📊 总体统计:")
        logger.info(f"  总用例数: {total}")
        logger.info(f"  通过数: {passed}")
        logger.info(f"  失败数: {failed}")
        logger.info(f"  通过率: {passed/total*100:.1f}%" if total > 0 else "N/A")
        logger.info(f"  平均分数: {avg_score:.2f}")
        logger.info(f"  平均耗时: {avg_time:.2f}秒")
        
        # 详细结果
        logger.info(f"\n📋 详细结果:")
        for i, result in enumerate(results):
            status = "✅" if result.get('success') else "❌"
            theme_name = result.get('theme_name', 'N/A')
            score = result.get('evaluation', {}).get('score', 0)
            time_cost = result.get('time_cost', 0)
            logger.info(f"  {i+1}. {status} {result.get('case_name')}")
            logger.info(f"     主题: {theme_name}")
            logger.info(f"     分数: {score:.2f} 耗时: {time_cost:.1f}秒")
        
        # 问题分析
        logger.info(f"\n🔍 问题分析:")
        
        # 收集所有问题
        all_issues = []
        for result in results:
            if not result.get('success'):
                issues = result.get('evaluation', {}).get('naming_issues', []) + \
                        result.get('evaluation', {}).get('decision_issues', [])
                all_issues.extend(issues)
                
                if 'error' in result:
                    all_issues.append(f"执行错误: {result['error']}")
        
        if all_issues:
            logger.info(f"  发现 {len(all_issues)} 个问题:")
            for issue in all_issues[:10]:  # 显示前10个问题
                logger.info(f"    - {issue}")
        else:
            logger.info(f"   🎉 未发现问题!")
        
        # 关键问题检查：SpaceX是否匹配到消费电子
        logger.info(f"\n🔑 关键问题检查:")
        for result in results:
            if "SpaceX" in result.get('case_name', '') or "spacex" in result.get('case_id', ''):
                theme_name = result.get('theme_name', '')
                if "消费电子" in theme_name:
                    logger.error(f"  ❌ CRITICAL: SpaceX卫星事件错误匹配到消费电子! 主题名: {theme_name}")
                elif "相关" in theme_name or "新闻" in theme_name:
                    logger.warning(f"  ⚠️  SpaceX主题名称包含不良后缀: {theme_name}")
                else:
                    logger.info(f"  ✅ SpaceX测试通过，主题名: {theme_name}")
        
        # 保存详细报告
        self.save_detailed_report(results)
    
    def save_detailed_report(self, results: List[Dict[str, Any]]):
        """保存详细报告"""
        report_dir = project_root / "evaluate_service" / "data" / "results"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成报告文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"ai_theme_fix_report_{timestamp}.json"
        
        # 构建报告数据
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_cases": len(results),
                "passed_cases": sum(1 for r in results if r.get('success', False)),
                "failed_cases": len(results) - sum(1 for r in results if r.get('success', False)),
                "average_score": sum(r.get('evaluation', {}).get('score', 0) for r in results) / len(results) if results else 0,
                "average_time": sum(r.get('time_cost', 0) for r in results) / len(results) if results else 0
            },
            "test_cases": results
        }
        
        # 保存报告
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"\n💾 详细报告已保存: {report_file}")
        except Exception as e:
            logger.error(f"保存报告失败: {e}")

async def main():
    """主函数"""
    print("\n" + "="*80)
    print("🚀 AI主题相似性分析器修复测试 - 使用真实AI大模型")
    print("="*80)
    
    # 检查环境变量
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY 环境变量未设置")
        print("\n💡 设置方法:")
        print("   1. 临时设置: export DEEPSEEK_API_KEY='your-api-key'")
        print("   2. 永久设置: 添加到 ~/.bashrc 或 ~/.zshrc")
        print("\n🔗 获取API密钥: https://platform.deepseek.com/api_keys")
        return
    
    print(f"✅ 找到DeepSeek API密钥: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")
    
    # 创建评估器
    evaluator = RealAIEvaluator()
    
    # 初始化AI服务
    print("\n🔧 正在初始化AI服务...")
    success = await evaluator.initialize_ai_service()
    
    if not success:
        print("❌ 无法初始化AI服务")
        print("\n💡 可能的解决方案:")
        print("   1. 检查网络连接")
        print("   2. 验证API密钥是否正确")
        print("   3. 检查是否有防火墙阻挡")
        print("   4. 查看上面的错误日志获取更多信息")
        return
    
    print("✅ AI服务初始化成功，开始测试...")
    
    # 运行测试
    try:
        results = await evaluator.run_all_tests()
        
        # 最终总结
        passed = sum(1 for r in results if r.get('success', False))
        total = len(results)
        
        print("\n" + "="*80)
        if passed == total:
            print(f"🎉 所有测试通过！ ({passed}/{total})")
        elif passed == 0:
            print(f"❌ 所有测试失败！ (0/{total})")
        else:
            print(f"📊 测试完成: {passed}通过, {total-passed}失败")
        
        # 显示关键测试结果
        print("\n🔑 关键测试结果:")
        for result in results:
            theme_name = result.get('theme_name', 'N/A')
            case_name = result.get('case_name', '')
            if "相关" in theme_name or "新闻" in theme_name:
                print(f"  ⚠️  {case_name}: 主题名包含不良后缀 -> '{theme_name}'")
            if "消费电子" in theme_name and "SpaceX" in case_name:
                print(f"  ❌ {case_name}: 严重错误! 航天军工匹配到消费电子 -> '{theme_name}'")
        
        print("="*80)
        
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())
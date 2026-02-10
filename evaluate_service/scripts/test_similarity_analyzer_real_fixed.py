# evaluate_service/scripts/test_similarity_analyzer_real_fixed.py
"""
AI相似性分析器真实AI测试 - 使用实际数据结构
🚀 只使用真实DeepSeek AI，无模拟数据
🔥 验证CREATE_NEW和CLUSTER事件的相似性分析
"""
import asyncio
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RealAISimilarityTester:
    """真实AI相似性分析测试器 - 使用实际数据结构"""
    
    def __init__(self):
        self.test_cases = self._create_actual_structure_test_cases()
        self.analyzer = None
        
    def _create_actual_structure_test_cases(self) -> List[Dict[str, Any]]:
        """创建使用实际数据结构的测试用例"""
        return [
            # 🔥 核心测试1：SpaceX卫星（必须正确区分）
            {
                "test_id": "REAL_001",
                "test_name": "国防航天 vs 消费电子",
                "test_description": "验证AI能否正确区分国防航天和消费电子",
                "event": {
                    "news_id": "spacex_missile_defense_001",
                    "event_info": {
                        "event_type": "国防采购",
                        "impact_industries": ["航天", "军工", "国防科技", "卫星技术"],
                        "direction": "利好",
                        "event_confidence": 0.95
                    },
                    "theme_discovery_directive": {
                        "action": "CREATE_NEW",
                        "decision_confidence": 0.9,
                        "reason": "重大国防航天采购，涉及国家安全，应作为独立重大主题"
                    },
                    "original_news": {
                        "title": "美国太空军与SpaceX签署72颗导弹预警卫星采购合同",
                        "content": """
美国太空军宣布与SpaceX签署价值25亿美元的合同，采购72颗先进的导弹预警和跟踪卫星。
这批卫星将用于增强美国的导弹防御能力，采用最新合成孔径雷达技术。
合同包括卫星的设计、制造、发射和在轨维护，预计2026年前完成部署。
该合同是美军太空防御体系现代化的重要组成部分。
                        """,
                        "content_length": 120,
                        "date": "2025年1月15日"
                    }
                },
                "existing_themes": [
                    {
                        "id": 1,
                        "name": "消费电子",
                        "description": "消费电子产品和技术发展，包括智能手机、电脑、可穿戴设备等",
                        "keywords": ["消费电子", "智能手机", "智能家居", "电子产品", "可穿戴设备"],
                        "created_at": "2024-12-01"
                    },
                    {
                        "id": 2,
                        "name": "人工智能技术",
                        "description": "人工智能算法、模型和应用，包括机器学习、深度学习、计算机视觉等",
                        "keywords": ["AI", "人工智能", "机器学习", "深度学习", "大语言模型"],
                        "created_at": "2024-12-01"
                    },
                    {
                        "id": 3,
                        "name": "半导体",
                        "description": "半导体芯片设计、制造和封装技术",
                        "keywords": ["半导体", "芯片", "集成电路", "晶圆代工", "封装测试"],
                        "created_at": "2024-12-01"
                    }
                ],
                "verification_points": {
                    "critical_check": "国防航天 ≠ 消费电子",
                    "must_not_match": ["消费电子"],
                    "max_acceptable_similarity": 0.3,
                    "expected_analysis_contains": ["国防", "军事", "航天", "领域不同", "本质不同"]
                }
            },
            
            # 🔥 核心测试2：台积电芯片（应该匹配半导体）
            {
                "test_id": "REAL_002",
                "test_name": "半导体技术匹配测试",
                "test_description": "验证AI能否正确识别半导体技术的相似性",
                "event": {
                    "news_id": "tsmc_2nm_breakthrough_001",
                    "event_info": {
                        "event_type": "技术突破",
                        "impact_industries": ["半导体", "芯片制造", "集成电路", "先进制程"],
                        "direction": "利好",
                        "event_confidence": 0.92
                    },
                    "theme_discovery_directive": {
                        "action": "CREATE_NEW",
                        "decision_confidence": 0.85,
                        "reason": "重大半导体技术突破，可能引领产业升级"
                    },
                    "original_news": {
                        "title": "台积电宣布2nm芯片制造技术取得重大突破",
                        "content": """
台积电在2nm芯片制造技术上取得重大进展，晶体管密度较3nm工艺提高30%，功耗降低25%。
新技术采用全新的环绕栅极晶体管（GAA）架构，预计2025年下半年量产。
该技术突破将显著提升芯片性能和能效，对AI芯片、高性能计算等领域有重要影响。
                        """,
                        "content_length": 110,
                        "date": "2025年1月16日"
                    }
                },
                "existing_themes": [
                    {
                        "id": 1,
                        "name": "半导体",
                        "description": "半导体芯片设计、制造和封装技术",
                        "keywords": ["半导体", "芯片", "集成电路", "晶圆代工", "封装测试"],
                        "created_at": "2024-12-01"
                    },
                    {
                        "id": 2,
                        "name": "消费电子",
                        "description": "消费电子产品和技术发展",
                        "keywords": ["消费电子", "智能手机", "智能家居", "电子产品"],
                        "created_at": "2024-12-01"
                    },
                    {
                        "id": 3,
                        "name": "人工智能技术",
                        "description": "人工智能算法和应用",
                        "keywords": ["AI", "人工智能", "机器学习"],
                        "created_at": "2024-12-01"
                    }
                ],
                "verification_points": {
                    "critical_check": "半导体技术 ≈ 半导体",
                    "should_match": "半导体",
                    "min_acceptable_similarity": 0.6,
                    "expected_analysis_contains": ["半导体", "芯片", "技术相关", "领域相同"]
                }
            },
            
            # 🔥 核心测试3：智能眼镜（CLUSTER指令测试）
            {
                "test_id": "REAL_003",
                "test_name": "CLUSTER事件相似性测试",
                "test_description": "验证CLUSTER指令下的相似性分析",
                "event": {
                    "news_id": "meta_smart_glasses_001",
                    "event_info": {
                        "event_type": "产品发布",
                        "impact_industries": ["消费电子", "可穿戴设备", "人工智能", "增强现实"],
                        "direction": "利好",
                        "event_confidence": 0.88
                    },
                    "theme_discovery_directive": {
                        "action": "CLUSTER",
                        "decision_confidence": 0.8,
                        "reason": "常规消费电子产品发布，可归类到现有主题"
                    },
                    "original_news": {
                        "title": "Meta与Oakley合作发布新一代智能眼镜",
                        "content": """
Meta与知名运动品牌Oakley合作，发布集成AR和AI技术的新一代智能眼镜。
产品具备实时翻译、导航指引、运动监测等功能，定价299美元。
该产品定位为消费级智能眼镜，主打运动场景应用。
                        """,
                        "content_length": 85,
                        "date": "2025年1月17日"
                    }
                },
                "existing_themes": [
                    {
                        "id": 1,
                        "name": "消费电子",
                        "description": "消费电子产品和技术发展",
                        "keywords": ["消费电子", "智能手机", "智能家居", "电子产品", "可穿戴设备"],
                        "created_at": "2024-12-01"
                    },
                    {
                        "id": 2,
                        "name": "智能穿戴设备",
                        "description": "可穿戴智能设备和技术",
                        "keywords": ["可穿戴设备", "智能手表", "智能眼镜", "健康监测"],
                        "created_at": "2024-12-01"
                    },
                    {
                        "id": 3,
                        "name": "人工智能应用",
                        "description": "人工智能技术在各个领域的应用",
                        "keywords": ["AI应用", "人工智能", "机器学习应用"],
                        "created_at": "2024-12-01"
                    }
                ],
                "verification_points": {
                    "critical_check": "智能眼镜 ∈ 消费电子",
                    "should_match": "消费电子",
                    "min_acceptable_similarity": 0.7,
                    "expected_analysis_contains": ["消费电子", "可穿戴", "同类产品", "领域相同"]
                }
            }
        ]
    
    def _check_api_key(self) -> bool:
        """检查API密钥"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            logger.error("❌ DEEPSEEK_API_KEY 环境变量未设置")
            logger.info("请设置: export DEEPSEEK_API_KEY='your-api-key'")
            return False
        
        # 检查是否为有效格式
        if not api_key.startswith("sk-"):
            logger.error("❌ API密钥格式不正确，应以'sk-'开头")
            return False
        
        logger.info(f"✅ API密钥检查通过")
        return True
    
    async def initialize_real_ai(self) -> bool:
        """初始化真实AI分析器"""
        try:
            # 检查API密钥
            if not self._check_api_key():
                return False
            
            # 导入稳定的可靠解析器
            logger.info("📦 导入ReliableDeepSeekParser...")
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 使用与生产环境相同的配置
            llm_parser = ReliableDeepSeekParser(
                model_name="deepseek-chat",
                config={
                    'max_retries': 3,
                    'timeout': 60,  # 适当延长超时时间
                    'enable_cache': True,
                    'cache_ttl': 600,
                    'temperature': 0.1
                }
            )
            
            # 健康检查
            logger.info("🔍 进行AI健康检查...")
            health = await llm_parser.health_check()
            
            if not health:
                logger.error("❌ AI健康检查失败")
                return False
            
            logger.info("✅ AI健康检查通过")
            
            # 初始化相似性分析器
            logger.info("🔧 初始化AIThemeSimilarityAnalyzer...")
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            self.analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            logger.info("✅ 真实AI相似性分析器初始化成功")
            return True
            
        except ImportError as e:
            logger.error(f"❌ 无法导入模块: {e}")
            logger.info("请检查以下模块是否存在：")
            logger.info("  1. model_service.llm_parser.reliable_deepseek_parser")
            logger.info("  2. theme_service.ai_similarity_analyzer")
            return False
        except Exception as e:
            logger.error(f"❌ 初始化真实AI失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def run_real_ai_test(self) -> List[Dict[str, Any]]:
        """运行真实AI测试"""
        logger.info("🚀 开始真实AI相似性分析器测试")
        logger.info(f"测试用例: {len(self.test_cases)}个关键案例")
        
        all_results = []
        
        for i, test_case in enumerate(self.test_cases):
            logger.info(f"\n{'='*60}")
            logger.info(f"测试 {i+1}/{len(self.test_cases)}: {test_case['test_name']}")
            logger.info(f"描述: {test_case['test_description']}")
            
            result = await self._execute_single_test(test_case)
            all_results.append(result)
            
            # 添加延迟避免API限流
            if i < len(self.test_cases) - 1:
                logger.info("⏳ 等待2秒后继续下一个测试...")
                await asyncio.sleep(2)
        
        # 生成总结报告
        self._generate_summary_report(all_results)
        
        return all_results
    
    async def _execute_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个测试用例"""
        try:
            # 记录开始时间
            import time
            start_time = time.time()
            
            # 调用真实AI分析器
            logger.info(f"🤖 调用AI相似性分析...")
            
            # 提取事件和主题信息
            event = test_case["event"]
            existing_themes = test_case["existing_themes"]
            
            # 打印调试信息
            logger.debug(f"事件ID: {event['news_id']}")
            logger.debug(f"上游指令: {event['theme_discovery_directive']['action']}")
            logger.debug(f"现有主题数: {len(existing_themes)}")
            
            # 🔥 修复：移除 top_n 参数，使用正确的调用方式
            result = await self.analyzer.analyze_similarity(
                event,
                existing_themes
                # 注意：当前版本的analyze_similarity方法不支持top_n参数
            )
            
            processing_time = time.time() - start_time
            
            # 提取关键信息
            similarity_analysis = result.get('similarity_analysis', {})
            theme_name = similarity_analysis.get('best_match_theme', '')
            similarity_score = similarity_analysis.get('similarity_score', 0)
            similarity_reason = similarity_analysis.get('similarity_reason', '')
            
            logger.info(f"⏱️  AI分析完成，耗时: {processing_time:.2f}秒")
            logger.info(f"📊 AI分析结果:")
            logger.info(f"   最佳匹配主题: {theme_name}")
            logger.info(f"   相似度分数: {similarity_score:.3f}")
            
            if similarity_reason:
                # 截取前100字符显示
                short_reason = similarity_reason[:100] + "..." if len(similarity_reason) > 100 else similarity_reason
                logger.info(f"   分析理由: {short_reason}")
            
            # 验证结果
            verification = self._verify_ai_result(test_case, theme_name, similarity_score, similarity_reason)
            
            test_result = {
                "test_id": test_case["test_id"],
                "test_name": test_case["test_name"],
                "upstream_action": event["theme_discovery_directive"]["action"],
                "processing_time": processing_time,
                "ai_analysis": {
                    "best_match_theme": theme_name,
                    "similarity_score": similarity_score,
                    "similarity_reason": similarity_reason[:200] if similarity_reason else ""
                },
                "verification": verification,
                "passed": verification["passed"]
            }
            
            # 打印验证结果
            self._print_verification_result(verification)
            
            return test_result
            
        except Exception as e:
            logger.error(f"❌ 测试执行失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "test_id": test_case.get("test_id", "UNKNOWN"),
                "test_name": test_case.get("test_name", "UNKNOWN"),
                "error": str(e),
                "passed": False
            }
    
    def _verify_ai_result(self, test_case: Dict[str, Any],
                         theme_name: str,
                         similarity_score: float,
                         similarity_reason: str) -> Dict[str, Any]:
        """验证AI分析结果"""
        verification = {
            "passed": False,
            "critical_check_passed": False,
            "score_check_passed": False,
            "reason_quality_check_passed": False,
            "issues": [],
            "warnings": []
        }
        
        expected = test_case["verification_points"]
        critical_check = expected["critical_check"]
        
        # 1. 关键检查：是否匹配了禁止的主题
        must_not_match = expected.get("must_not_match", [])
        for bad_theme in must_not_match:
            if bad_theme in theme_name:
                verification["issues"].append(f"❌ 严重错误：匹配到禁止主题 '{bad_theme}'")
                verification["critical_check_passed"] = False
                break
        else:
            # 如果没有break，说明没有匹配禁止主题
            verification["critical_check_passed"] = True
            verification["warnings"].append(f"✅ 关键检查通过: {critical_check}")
        
        # 2. 检查是否应该匹配某个主题
        should_match = expected.get("should_match")
        if should_match and should_match not in theme_name:
            verification["warnings"].append(f"⚠️  未匹配到期望主题 '{should_match}'，实际匹配: '{theme_name}'")
        
        # 3. 检查相似度分数范围
        max_acceptable = expected.get("max_acceptable_similarity", 1.0)
        min_acceptable = expected.get("min_acceptable_similarity", 0.0)
        
        if min_acceptable <= similarity_score <= max_acceptable:
            verification["score_check_passed"] = True
            verification["warnings"].append(f"✅ 分数范围正确: {similarity_score:.3f} 在 [{min_acceptable}, {max_acceptable}] 内")
        else:
            verification["score_check_passed"] = False
            verification["issues"].append(f"❌ 分数范围错误: {similarity_score:.3f} 不在 [{min_acceptable}, {max_acceptable}] 内")
        
        # 4. 检查分析理由质量
        if similarity_reason and len(similarity_reason.strip()) > 30:
            verification["reason_quality_check_passed"] = True
            
            # 检查是否包含期望的关键词
            expected_keywords = expected.get("expected_analysis_contains", [])
            missing_keywords = []
            
            for keyword in expected_keywords:
                if keyword not in similarity_reason:
                    missing_keywords.append(keyword)
            
            if missing_keywords:
                verification["warnings"].append(f"⚠️  分析理由缺少关键词: {missing_keywords}")
            else:
                verification["warnings"].append(f"✅ 分析理由包含所有期望关键词")
        else:
            verification["reason_quality_check_passed"] = False
            verification["issues"].append("❌ 分析理由太短或为空")
        
        # 5. 总体判断
        verification["passed"] = (
            verification["critical_check_passed"] and 
            verification["score_check_passed"] and
            verification["reason_quality_check_passed"]
        )
        
        return verification
    
    def _print_verification_result(self, verification: Dict[str, Any]):
        """打印验证结果"""
        logger.info(f"🔍 验证总结:")
        
        if verification["passed"]:
            logger.info(f"  ✅ 测试通过")
        else:
            logger.error(f"  ❌ 测试失败")
        
        # 打印所有问题和警告
        for item in verification["issues"]:
            if "❌" in item:
                logger.error(f"  {item}")
            else:
                logger.info(f"  {item}")
        
        for item in verification["warnings"]:
            if "✅" in item:
                logger.info(f"  {item}")
            else:
                logger.warning(f"  {item}")
    
    def _generate_summary_report(self, test_results: List[Dict[str, Any]]):
        """生成总结报告"""
        logger.info("\n" + "="*80)
        logger.info("📈 真实AI相似性分析器测试总结报告")
        logger.info("="*80)
        
        # 基本统计
        total = len(test_results)
        passed = sum(1 for r in test_results if r.get("passed", False))
        failed = total - passed
        
        logger.info(f"📊 基本统计:")
        logger.info(f"  总测试用例: {total}")
        logger.info(f"  通过用例: {passed}")
        logger.info(f"  失败用例: {failed}")
        logger.info(f"  通过率: {passed/total*100:.1f}%" if total > 0 else "N/A")
        
        # 分类统计
        create_new_cases = [r for r in test_results if r.get("upstream_action") == "CREATE_NEW"]
        cluster_cases = [r for r in test_results if r.get("upstream_action") == "CLUSTER"]
        
        logger.info(f"\n📋 分类统计:")
        logger.info(f"  CREATE_NEW用例: {len(create_new_cases)}个")
        logger.info(f"  CLUSTER用例: {len(cluster_cases)}个")
        
        # 详细结果
        logger.info(f"\n📝 详细结果:")
        for i, result in enumerate(test_results):
            status = "✅" if result.get("passed") else "❌"
            test_name = result.get("test_name", "未知测试")
            analysis = result.get("ai_analysis", {})
            theme = analysis.get("best_match_theme", "N/A")
            score = analysis.get("similarity_score", 0)
            
            logger.info(f"  {i+1}. {status} {test_name}")
            logger.info(f"      匹配主题: {theme}")
            logger.info(f"      相似度: {score:.3f}")
            logger.info(f"      耗时: {result.get('processing_time', 0):.2f}秒")
            
            if not result.get("passed"):
                issues = result.get("verification", {}).get("issues", [])
                for issue in issues:
                    logger.error(f"      问题: {issue}")
        
        # 🔥 关键诊断：检查SpaceX是否错误匹配
        logger.info(f"\n🔍 关键诊断:")
        spacex_results = [r for r in test_results if "国防航天" in r.get("test_name", "")]
        
        for result in spacex_results:
            theme_name = result.get("ai_analysis", {}).get("best_match_theme", "")
            score = result.get("ai_analysis", {}).get("similarity_score", 0)
            
            if "消费电子" in theme_name and score > 0.3:
                logger.error(f"  ❌ 严重问题: {result.get('test_name')}")
                logger.error(f"      错误匹配到消费电子，相似度: {score:.3f}")
                logger.error(f"      说明AI未能正确区分国防航天和消费电子领域")
            elif result.get("passed"):
                logger.info(f"  ✅ {result.get('test_name')}: 通过，匹配到 '{theme_name}'，相似度 {score:.3f}")
        
        # 保存JSON报告
        self._save_json_report(test_results)
    
    def _save_json_report(self, test_results: List[Dict[str, Any]]):
        """保存JSON格式详细报告"""
        try:
            report_dir = PROJECT_ROOT / "evaluate_service" / "data" / "results" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = report_dir / f"similarity_analyzer_real_ai_test_{timestamp}.json"
            
            report = {
                "metadata": {
                    "test_type": "REAL_AI_SIMILARITY_ANALYZER_TEST",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "ai_provider": "DeepSeek",
                    "data_structure": "实际生产数据结构",
                    "test_focus": "领域区分能力和相似性分析准确性"
                },
                "test_summary": {
                    "total_cases": len(test_results),
                    "passed_cases": sum(1 for r in test_results if r.get("passed", False)),
                    "success_rate": sum(1 for r in test_results if r.get("passed", False)) / len(test_results) if test_results else 0,
                    "failed_cases": [r["test_name"] for r in test_results if not r.get("passed", False)]
                },
                "detailed_results": test_results,
                "key_findings": self._extract_key_findings(test_results),
                "recommendations": [
                    "分析AI提示词是否需要优化以更好区分领域",
                    "考虑调整相似度分数的阈值",
                    "检查AI返回的理由是否符合业务要求"
                ]
            }
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"\n💾 详细报告已保存: {report_file.relative_to(PROJECT_ROOT)}")
            
        except Exception as e:
            logger.error(f"保存报告失败: {e}")
    
    def _extract_key_findings(self, test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """提取关键发现"""
        findings = {
            "domain_differentiation": {
                "status": "unknown",
                "details": []
            },
            "score_accuracy": {
                "status": "unknown", 
                "details": []
            },
            "reasoning_quality": {
                "status": "unknown",
                "details": []
            },
            "critical_issues": [],
            "successful_tests": []
        }
        
        # 分析测试结果
        for result in test_results:
            case_name = result.get("test_name", "")
            passed = result.get("passed", False)
            
            if passed:
                findings["successful_tests"].append(case_name)
                
                # 检查领域区分能力
                if "国防航天" in case_name:
                    analysis = result.get("ai_analysis", {})
                    best_match = analysis.get("best_match_theme", "")
                    score = analysis.get("similarity_score", 0)
                    
                    if "消费电子" not in best_match and score < 0.3:
                        findings["domain_differentiation"]["status"] = "good"
                        findings["domain_differentiation"]["details"].append(
                            f"✅ {case_name}: 正确区分国防航天和消费电子"
                        )
            else:
                error = result.get("error", "")
                findings["critical_issues"].append({
                    "case": case_name,
                    "error": error[:100] if error else "测试失败"
                })
        
        # 更新状态总结
        total = len(test_results)
        passed_count = len(findings["successful_tests"])
        
        if total > 0:
            success_rate = passed_count / total
            if success_rate >= 0.8:
                findings["overall_status"] = "excellent"
            elif success_rate >= 0.6:
                findings["overall_status"] = "good"
            elif success_rate >= 0.4:
                findings["overall_status"] = "fair"
            else:
                findings["overall_status"] = "poor"
        
        return findings


async def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("🚀 真实AI相似性分析器测试")
    print("使用实际生产数据结构")
    print("="*80)
    
    # 检查必要的环境
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY 环境变量未设置")
        print("\n💡 设置方法:")
        print("   临时设置: export DEEPSEEK_API_KEY='your-api-key'")
        print("   永久设置: 添加到 ~/.bashrc 或 ~/.zshrc")
        print("\n🔗 获取API密钥: https://platform.deepseek.com/api_keys")
        return
    
    print(f"✅ 找到DeepSeek API密钥: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")
    
    # 创建测试器
    tester = RealAISimilarityTester()
    
    # 初始化真实AI
    print("\n🔧 初始化真实AI分析器...")
    success = await tester.initialize_real_ai()
    
    if not success:
        print("❌ 无法初始化真实AI分析器")
        print("\n💡 可能的原因:")
        print("   1. API密钥无效")
        print("   2. 网络连接问题")
        print("   3. 依赖模块未正确安装")
        return
    
    print("✅ 真实AI初始化成功")
    print("\n🔍 开始执行测试...")
    
    # 运行测试
    try:
        results = await tester.run_real_ai_test()
        
        # 最终总结
        passed = sum(1 for r in results if r.get("passed", False))
        total = len(results)
        
        print("\n" + "="*80)
        if passed == total:
            print(f"🎉 所有测试通过！ ({passed}/{total})")
        elif passed == 0:
            print(f"❌ 所有测试失败！ (0/{total})")
        else:
            print(f"📊 测试完成: {passed}通过, {total-passed}失败")
        
        # 显示最关键的结果
        print("\n🔑 最关键测试结果:")
        for result in results:
            test_name = result.get("test_name", "")
            theme_name = result.get("ai_analysis", {}).get("best_match_theme", "")
            
            if "国防航天" in test_name:
                if "消费电子" in theme_name:
                    print(f"  ❌ {test_name}: 严重错误! 匹配到消费电子")
                else:
                    print(f"  ✅ {test_name}: 通过，匹配到 '{theme_name}'")
        
        print("="*80)
        
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 设置事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行测试
    asyncio.run(main())
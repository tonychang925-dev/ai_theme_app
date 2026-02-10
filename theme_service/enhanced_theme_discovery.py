# theme_service/enhanced_theme_discovery.py
"""
增强版主题发现模块 - 修复版
修复AIThemeSimilarityAnalyzerFactory调用问题
"""
import logging
from typing import Dict, List, Any, Optional
import asyncio

logger = logging.getLogger(__name__)


class EnhancedThemeDiscovery:
    """增强版主题发现模块"""
    
    def __init__(self, 
                 data_fetcher, 
                 similarity_analyzer,
                 new_theme_threshold: float = 0.3):
        """
        初始化
        
        Args:
            data_fetcher: 数据获取器
            similarity_analyzer: AI相似性分析器（增强版）
            new_theme_threshold: 新主题阈值，低于此值创建新主题
        """
        # 🔥 关键修复：正确初始化 related_theme_fetcher
        self.data_fetcher = data_fetcher
        self.similarity_analyzer = similarity_analyzer
        self.new_theme_threshold = new_theme_threshold
        
        # 初始化 related_theme_fetcher
        try:
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            self.related_theme_fetcher = RelatedThemeFetcher(data_fetcher)
            logger.info("✅ 相关主题获取器初始化成功")
        except ImportError as e:
            logger.error(f"❌ 无法导入 RelatedThemeFetcher: {e}")
            # 创建简单的替代实现
            self.related_theme_fetcher = self._create_fallback_fetcher()
        except Exception as e:
            logger.error(f"❌ 初始化相关主题获取器失败: {e}")
            self.related_theme_fetcher = self._create_fallback_fetcher()
        
        # 主题名称生成器（如果需要）
        self.theme_name_generator = None
        
        logger.info("✅ 增强版主题发现模块初始化完成")
    
    def _create_fallback_fetcher(self):
        """创建备用主题获取器"""
        class FallbackThemeFetcher:
            def __init__(self, data_fetcher):
                self.data_fetcher = data_fetcher
            
            async def fetch_relevant_themes(self, event, limit=5):
                """简单的主题获取实现"""
                try:
                    if hasattr(self.data_fetcher, 'get_all_active_themes'):
                        themes = await self.data_fetcher.get_all_active_themes(limit=limit)
                        return themes
                    return []
                except:
                    return []
            
            async def fetch_themes_by_industries(self, industries, limit=20):
                """按行业过滤主题"""
                try:
                    all_themes = await self.fetch_relevant_themes(None, limit=100)
                    # 简单过滤：主题名称包含行业关键词
                    relevant_themes = []
                    for theme in all_themes:
                        theme_name = theme.get('name', '').lower()
                        for industry in industries:
                            if industry.lower() in theme_name:
                                relevant_themes.append(theme)
                                break
                    return relevant_themes[:limit]
                except:
                    return []
        
        logger.warning("⚠️  使用备用主题获取器")
        return FallbackThemeFetcher(self.data_fetcher)
    
    async def process_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个事件 - 增强版
        
        Args:
            event_data: 事件数据
            
        Returns:
            处理结果，包含主题提取、相似性分析和决策
        """
        event_id = event_data.get('news_id', 'unknown')
        logger.info(f"🚀 开始处理事件 - 事件ID: {event_id}")
        
        try:
            # 🔥 修复：使用 related_theme_fetcher 获取相关主题
            # 步骤1: 获取现有主题
            existing_themes = await self._fetch_existing_themes(event_data)
            
            if not existing_themes:
                logger.warning(f"数据库中没有现有主题，事件: {event_id}")
                return await self._create_new_theme_for_no_existing(event_data)
            
            # 步骤2: 使用增强版分析器（一次调用完成所有）
            analysis_result = await self.similarity_analyzer.analyze_with_theme_extraction(
                event_data,
                existing_themes
            )
            
            # 步骤3: 根据分析结果处理
            if analysis_result['metadata']['should_create_new']:
                # 创建新主题
                return await self._handle_create_new(event_data, analysis_result)
            else:
                # 归并到现有主题
                return await self._handle_cluster(event_data, analysis_result)
                
        except Exception as e:
            logger.error(f"❌ 处理事件失败 {event_id}: {e}")
            import traceback
            traceback.print_exc()
            return self._create_error_response(event_id, str(e))
    
    async def _fetch_existing_themes(self, event_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取现有主题 - 强制使用完整内容接口"""
        event_id = event_data.get('news_id', 'unknown')
        logger.info(f"🔍 获取现有主题 - 事件: {event_id}")
        
        try:
            # 🔥 关键修复：统一使用 fetch_themes_with_complete_news_content 方法
            if hasattr(self.related_theme_fetcher, 'fetch_themes_with_complete_news_content'):
                logger.info("🎯 使用 fetch_themes_with_complete_news_content 方法获取完整内容")
                themes = await self.related_theme_fetcher.fetch_themes_with_complete_news_content(event_data, limit=10)
                
                # 🔥 验证数据完整性
                if themes:
                    self._validate_theme_data_integrity(themes)
                
                return themes
            
            # 🔥 如果上述方法不存在，说明组件版本不匹配，直接报错
            logger.error("❌🔥 严重错误：RelatedThemeFetcher 缺少 fetch_themes_with_complete_news_content 方法")
            logger.error("⚠️  AI将无法获得完整新闻内容，这会导致小题材分裂问题")
            
            # 降级到 fetch_relevant_themes，但必须警告
            if hasattr(self.related_theme_fetcher, 'fetch_relevant_themes'):
                logger.warning("⚠️  降级使用 fetch_relevant_themes（可能导致小题材分裂）")
                themes = await self.related_theme_fetcher.fetch_relevant_themes(event_data, limit=10)
                return themes
            
            # 完全失败
            raise ValueError("RelatedThemeFetcher 没有可用的主题获取方法")
            
        except Exception as e:
            logger.error(f"❌ 获取现有主题失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _handle_create_new(self, 
                               event_data: Dict[str, Any], 
                               analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建新主题"""
        event_id = event_data.get('news_id', 'unknown')
        extracted_name = analysis_result['theme_extraction']['extracted_name']
        
        logger.info(f"🎯 创建新主题 - 事件: {event_id}, 主题名: {extracted_name}")
        
        # 构建新主题信息
        new_theme = await self._build_new_theme(event_data, extracted_name, analysis_result)
        
        return {
            'event_id': event_id,
            'action': 'CREATE_NEW',
            'theme': new_theme,
            'analysis': analysis_result,
            'metadata': {
                'processing_time': '待添加',
                'reason': f"与现有主题相似度过低({analysis_result['similarity_analysis']['similarity_score']:.3f})"
            }
        }
    
    async def _handle_cluster(self, 
                            event_data: Dict[str, Any], 
                            analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """处理归并到现有主题"""
        event_id = event_data.get('news_id', 'unknown')
        matched_theme = analysis_result['similarity_analysis']['best_match_theme']
        theme_id = analysis_result['similarity_analysis']['theme_id']
        
        logger.info(f"🔗 归并到现有主题 - 事件: {event_id}, 主题: {matched_theme}")
        
        return {
            'event_id': event_id,
            'action': 'CLUSTER',
            'theme': {
                'id': theme_id,
                'name': matched_theme
            },
            'analysis': analysis_result,
            'metadata': {
                'processing_time': '待添加',
                'reason': f"与主题'{matched_theme}'高度相似({analysis_result['similarity_analysis']['similarity_score']:.3f})"
            }
        }
    
    async def _build_new_theme(self, 
                             event_data: Dict[str, Any], 
                             theme_name: str,
                             analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建新主题信息"""
        # 可以从分析结果中获取更多信息
        naming_reason = analysis_result['theme_extraction'].get('naming_reason', '')
        similarity_reason = analysis_result['similarity_analysis'].get('similarity_reason', '')
        
        # 生成主题描述
        description = await self._generate_theme_description(
            event_data, 
            theme_name, 
            naming_reason,
            similarity_reason
        )
        
        # 提取关键词
        keywords = await self._extract_keywords(event_data)
        
        # 计算置信度
        confidence = analysis_result['recommendation']['confidence']
        
        return {
            'name': theme_name,
            'description': description,
            'keywords': keywords,
            'confidence': confidence,
            'extraction_quality': analysis_result['theme_extraction']['confidence'],
            'naming_reason': naming_reason
        }
    
    async def _generate_theme_description(self, 
                                        event_data: Dict[str, Any],
                                        theme_name: str,
                                        naming_reason: str,
                                        similarity_reason: str) -> str:
        """生成主题描述"""
        # 简单实现：组合关键信息
        title = event_data.get('original_news', {}).get('title', '')
        event_type = event_data.get('event_info', {}).get('event_type', '')
        industries = event_data.get('event_info', {}).get('impact_industries', [])
        
        description = f"{theme_name}主题，基于新闻事件：{title}。"
        
        if event_type:
            description += f" 事件类型：{event_type}。"
        
        if industries:
            description += f" 影响行业：{', '.join(industries)}。"
        
        if naming_reason:
            description += f" 命名依据：{naming_reason}"
        
        return description[:500]  # 限制长度
    
    async def _extract_keywords(self, event_data: Dict[str, Any]) -> List[str]:
        """提取关键词"""
        # 简单实现：从标题和行业中提取
        title = event_data.get('original_news', {}).get('title', '')
        industries = event_data.get('event_info', {}).get('impact_industries', [])
        
        keywords = []
        keywords.extend(industries)
        
        # 从标题中提取关键词（简单实现）
        title_keywords = ['芯片', '半导体', '智能', 'AR', 'VR', '卫星', '导弹', '国防', '军事']
        for kw in title_keywords:
            if kw in title:
                keywords.append(kw)
        
        # 去重
        return list(set(keywords))[:10]  # 限制数量
    
    async def _create_new_theme_for_no_existing(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """没有现有主题时的处理"""
        event_id = event_data.get('news_id', 'unknown')
        
        # 直接使用AI提取主题名
        try:
            # 调用分析器（传入空主题列表）
            analysis_result = await self.similarity_analyzer.analyze_with_theme_extraction(
                event_data,
                []  # 空列表
            )
            
            extracted_name = analysis_result['theme_extraction']['extracted_name']
            
            return {
                'event_id': event_id,
                'action': 'CREATE_NEW',
                'theme': await self._build_new_theme(event_data, extracted_name, analysis_result),
                'analysis': analysis_result,
                'metadata': {
                    'reason': '数据库中无现有主题，必须创建新主题'
                }
            }
        except Exception as e:
            logger.error(f"❌ 无主题时创建失败: {e}")
            import traceback
            traceback.print_exc()
            return self._create_error_response(event_id, f"无主题时创建失败: {str(e)}")
    
    def _create_error_response(self, event_id: str, error_msg: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            'event_id': event_id,
            'action': 'ERROR',
            'error': error_msg,
            'metadata': {
                'processing_failed': True,
                'error_time': '待添加'
            }
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查相关组件
            components_ok = all([
                self.data_fetcher is not None,
                self.similarity_analyzer is not None,
                self.related_theme_fetcher is not None
            ])
            
            # 检查分析器
            if self.similarity_analyzer:
                if hasattr(self.similarity_analyzer, 'health_check'):
                    ai_ok = await self.similarity_analyzer.health_check()
                else:
                    ai_ok = True
            else:
                ai_ok = False
            
            return components_ok and ai_ok
            
        except Exception as e:
            logger.error(f"❌ 健康检查失败: {e}")
            return False
        
    def _validate_theme_data_integrity(self, themes: List[Dict[str, Any]]):
        """验证主题数据完整性"""
        if not themes:
            logger.warning("⚠️  主题列表为空")
            return
        
        complete_count = 0
        total_content_length = 0
        
        for i, theme in enumerate(themes):
            theme_name = theme.get('name', f'主题_{i}')
            
            # 检查关键字段
            has_complete_content = theme.get('has_complete_content', False)
            has_related_news = 'related_news_full_contents' in theme
            
            if has_complete_content and has_related_news:
                complete_count += 1
                
                # 检查关联新闻内容
                related_news = theme.get('related_news_full_contents', [])
                if related_news:
                    news_count = len(related_news)
                    total_length = sum(n.get('content_length', 0) for n in related_news)
                    total_content_length += total_length
                    
                    logger.debug(f"  主题 '{theme_name}': {news_count}篇新闻，总长度{total_length}字符")
                    
                    # 检查内容是否完整
                    if total_length < 100:
                        logger.warning(f"    ⚠️  主题 '{theme_name}' 新闻内容过短，可能不完整")
                else:
                    logger.warning(f"    ⚠️  主题 '{theme_name}' 标记为有完整内容但关联新闻为空")
            else:
                logger.warning(f"    ⚠️  主题 '{theme_name}' 缺少完整内容标记或关联新闻字段")
        
        logger.info(f"📊 主题数据完整性报告:")
        logger.info(f"  总主题数: {len(themes)}")
        logger.info(f"  有完整内容的主题: {complete_count}")
        logger.info(f"  缺失完整内容的主题: {len(themes) - complete_count}")
        logger.info(f"  总内容长度: {total_content_length}字符")
        
        # 🔥 关键检查：确保至少有一个主题有完整内容
        if complete_count == 0 and len(themes) > 0:
            logger.error("❌🔥 严重问题：所有主题都缺少完整内容！")
            logger.error("⚠️  AI将无法进行深度分析，必然导致小题材分裂！")
            
            # 显示第一个主题的字段供调试
            first_theme = themes[0]
            logger.error(f"  第一个主题字段: {list(first_theme.keys())}")


# 工厂类 - 修复版
class EnhancedThemeDiscoveryFactory:
    """增强版主题发现模块工厂 - 修复版"""
    
    @staticmethod
    async def create(data_fetcher, 
                    similarity_analyzer_config: Optional[Dict[str, Any]] = None) -> EnhancedThemeDiscovery:
        """
        创建增强版主题发现模块
        
        Args:
            data_fetcher: 数据获取器
            similarity_analyzer_config: AI分析器配置（现在会被忽略，但保留参数兼容性）
            
        Returns:
            EnhancedThemeDiscovery实例
        """
        try:
            logger.info("🔧 开始创建增强版主题发现模块...")
            
            # 方法1: 尝试使用工厂类（根据测试结果，它不接受参数）
            try:
                from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzerFactory
                
                # 🔥 修复点：根据测试，这个工厂类的create()方法不接受参数
                logger.info("尝试使用AIThemeSimilarityAnalyzerFactory创建分析器...")
                similarity_analyzer = await AIThemeSimilarityAnalyzerFactory.create()
                logger.info("✅ 使用AIThemeSimilarityAnalyzerFactory创建分析器成功")
                
            except (ImportError, AttributeError, TypeError) as factory_error:
                logger.warning(f"工厂类创建失败: {factory_error}")
                logger.info("🔄 尝试直接创建分析器组件...")
                
                # 方法2: 直接创建分析器（绕过工厂类）
                try:
                    from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
                    from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
                    
                    # 🔧 配置LLM解析器
                    llm_config = {}
                    
                    # 如果提供了配置参数，应用到LLM解析器
                    if similarity_analyzer_config:
                        # 只传递有效的配置参数
                        valid_config_keys = ['api_key', 'model_name', 'max_retries', 'timeout', 'temperature']
                        for key in valid_config_keys:
                            if key in similarity_analyzer_config:
                                llm_config[key] = similarity_analyzer_config[key]
                    
                    # 创建LLM解析器
                    llm_parser = ReliableDeepSeekParser(config=llm_config)
                    
                    # 创建AI分析器
                    similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
                    
                    # 健康检查
                    if await similarity_analyzer.health_check():
                        logger.info("✅ 直接创建分析器成功")
                    else:
                        raise RuntimeError("分析器健康检查失败")
                        
                except ImportError as parser_error:
                    logger.error(f"❌ 无法导入LLM解析器: {parser_error}")
                    raise RuntimeError("缺少必要的依赖组件")
            
            # 创建主题发现模块
            discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            logger.info("✅ 增强版主题发现模块创建成功")
            return discovery
            
        except Exception as e:
            logger.error(f"❌ 创建增强版主题发现模块失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    # 新增：简化的创建方法
    async def create_enhanced_theme_discovery(data_fetcher, api_key: Optional[str] = None) -> EnhancedThemeDiscovery:
        """
        简化的创建函数
        
        Args:
            data_fetcher: 数据获取器
            api_key: 可选的API密钥
            
        Returns:
            EnhancedThemeDiscovery实例
        """
        try:
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 配置LLM解析器
            llm_config = {}
            if api_key:
                llm_config['api_key'] = api_key
            
            # 创建LLM解析器
            llm_parser = ReliableDeepSeekParser(config=llm_config)
            
            # 创建AI分析器
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            # 创建主题发现模块
            discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            logger.info("✅ 简化版增强主题发现模块创建成功")
            return discovery
            
        except Exception as e:
            logger.error(f"❌ 简化创建失败: {e}")
            raise
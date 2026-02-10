"""
决策矩阵 - 根据两阶段AI结果决定处理路径
实现智能路由和阈值管理
"""
import logging
from typing import Dict, Any, Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DecisionPath(Enum):
    """决策路径枚举"""
    FAST_TRACK_CREATE = "fast_track_create"      # 快速创建新题材
    GUIDED_CREATE = "guided_create"              # 引导创建（需判重检查）
    GUIDED_MERGE = "guided_merge"                # 引导归并到现有题材
    REVIEW_POOL = "review_pool"                  # 进入审查队列
    AUTO_MERGE = "auto_merge"                    # 自动归并
    SKIP = "skip"                                # 跳过处理
    FALLBACK = "fallback"                        # 降级处理


class ConfidenceLevel(Enum):
    """置信度级别"""
    HIGH = "high"      # 高置信度
    MEDIUM = "medium"  # 中置信度
    LOW = "low"        # 低置信度
    VERY_LOW = "very_low"  # 极低置信度


class DecisionMatrix:
    """
    决策矩阵 - 根据指令和置信度决定处理路径
    实现智能路由逻辑
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化决策矩阵
        
        Args:
            config: 配置参数
        """
        self.config = config or self._get_default_config()
        
        # 置信度阈值
        self.thresholds = self.config.get('thresholds', {})
        
        # 决策规则表
        self.rules = self._build_decision_rules()
        
        logger.info("DecisionMatrix 初始化完成")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "name": "决策矩阵配置",
            "version": "1.0",
            "description": "两阶段归并框架的决策路由逻辑",
            
            "thresholds": {
                "confidence_levels": {
                    "high": 0.85,     # 高置信度
                    "medium": 0.65,   # 中置信度
                    "low": 0.40,      # 低置信度
                    "very_low": 0.20  # 极低置信度
                },
                "fast_track": 0.85,   # 快速通道阈值
                "auto_merge": 0.90,   # 自动合并阈值
                "ignore": 0.30        # 忽略事件阈值
            },
            
            "weights": {
                "first_round_action": 0.4,   # 第一轮指令权重
                "first_round_confidence": 0.3,  # 第一轮置信度权重
                "second_round_confidence": 0.3  # 第二轮置信度权重
            },
            
            "fallback_rules": {
                "enable_fallback": True,
                "max_fallback_attempts": 3,
                "fallback_timeout_seconds": 5
            }
        }
    
    def _build_decision_rules(self) -> Dict[Tuple, DecisionPath]:
        """
        构建决策规则表
        
        规则键: (第一轮action, 第一轮置信度级别, 第二轮decision, 第二轮置信度级别)
        规则值: 处理路径
        """
        return {
            # CREATE_NEW 相关规则
            ('CREATE_NEW', ConfidenceLevel.HIGH, 'CREATE_NEW', ConfidenceLevel.HIGH): 
                DecisionPath.FAST_TRACK_CREATE,
            ('CREATE_NEW', ConfidenceLevel.HIGH, 'CREATE_NEW', ConfidenceLevel.MEDIUM): 
                DecisionPath.GUIDED_CREATE,
            ('CREATE_NEW', ConfidenceLevel.HIGH, 'CREATE_NEW', ConfidenceLevel.LOW): 
                DecisionPath.REVIEW_POOL,
            
            ('CREATE_NEW', ConfidenceLevel.MEDIUM, 'CREATE_NEW', ConfidenceLevel.HIGH): 
                DecisionPath.GUIDED_CREATE,
            ('CREATE_NEW', ConfidenceLevel.MEDIUM, 'CREATE_NEW', ConfidenceLevel.MEDIUM): 
                DecisionPath.GUIDED_CREATE,
            ('CREATE_NEW', ConfidenceLevel.MEDIUM, 'CREATE_NEW', ConfidenceLevel.LOW): 
                DecisionPath.REVIEW_POOL,
            
            # CLUSTER 相关规则
            ('CLUSTER', ConfidenceLevel.HIGH, 'MERGE_INTO', ConfidenceLevel.HIGH): 
                DecisionPath.GUIDED_MERGE,
            ('CLUSTER', ConfidenceLevel.HIGH, 'MERGE_INTO', ConfidenceLevel.MEDIUM): 
                DecisionPath.GUIDED_MERGE,
            ('CLUSTER', ConfidenceLevel.HIGH, 'MERGE_INTO', ConfidenceLevel.LOW): 
                DecisionPath.REVIEW_POOL,
            
            ('CLUSTER', ConfidenceLevel.MEDIUM, 'MERGE_INTO', ConfidenceLevel.HIGH): 
                DecisionPath.GUIDED_MERGE,
            ('CLUSTER', ConfidenceLevel.MEDIUM, 'MERGE_INTO', ConfidenceLevel.MEDIUM): 
                DecisionPath.REVIEW_POOL,
            ('CLUSTER', ConfidenceLevel.MEDIUM, 'MERGE_INTO', ConfidenceLevel.LOW): 
                DecisionPath.REVIEW_POOL,
            
            # 跨类别规则（第一轮和第二轮判断不一致）
            ('CREATE_NEW', ConfidenceLevel.HIGH, 'MERGE_INTO', ConfidenceLevel.HIGH): 
                DecisionPath.AUTO_MERGE,
            ('CREATE_NEW', ConfidenceLevel.HIGH, 'MERGE_INTO', ConfidenceLevel.MEDIUM): 
                DecisionPath.GUIDED_MERGE,
            
            ('CLUSTER', ConfidenceLevel.HIGH, 'CREATE_NEW', ConfidenceLevel.HIGH): 
                DecisionPath.GUIDED_CREATE,
            ('CLUSTER', ConfidenceLevel.HIGH, 'CREATE_NEW', ConfidenceLevel.MEDIUM): 
                DecisionPath.REVIEW_POOL,
            
            # IGNORE 相关规则
            (None, None, 'IGNORE', ConfidenceLevel.HIGH): 
                DecisionPath.SKIP,
            (None, None, 'IGNORE', ConfidenceLevel.MEDIUM): 
                DecisionPath.REVIEW_POOL,
            
            # NONE 相关规则
            ('NONE', ConfidenceLevel.HIGH, None, None): 
                DecisionPath.SKIP,
            ('NONE', ConfidenceLevel.MEDIUM, None, None): 
                DecisionPath.REVIEW_POOL,
            
            # 默认规则（未匹配时的降级处理）
            (None, None, None, None): 
                DecisionPath.FALLBACK
        }
    
    def get_decision_path(self,
                         first_round_action: Optional[str],
                         first_round_confidence: float,
                         second_round_decision: Optional[str],
                         second_round_confidence: float) -> Tuple[DecisionPath, Dict[str, Any]]:
        """
        获取决策路径
        
        Args:
            first_round_action: 第一轮指令action
            first_round_confidence: 第一轮置信度
            second_round_decision: 第二轮决策
            second_round_confidence: 第二轮置信度
            
        Returns:
            (决策路径, 决策详情)
        """
        # 确定置信度级别
        first_level = self._get_confidence_level(first_round_confidence)
        second_level = self._get_confidence_level(second_round_confidence)
        
        # 构建规则键
        rule_key = (
            first_round_action,
            first_level,
            second_round_decision,
            second_level
        )
        
        # 查找匹配的规则
        decision_path = self.rules.get(rule_key)
        
        # 如果未找到精确匹配，尝试模糊匹配
        if decision_path is None:
            decision_path = self._find_fuzzy_match(
                first_round_action, first_level,
                second_round_decision, second_level
            )
        
        # 构建决策详情
        decision_details = {
            "first_round": {
                "action": first_round_action,
                "confidence": first_round_confidence,
                "confidence_level": first_level.value
            },
            "second_round": {
                "decision": second_round_decision,
                "confidence": second_round_confidence,
                "confidence_level": second_level.value
            },
            "rule_key": str(rule_key),
            "matched_exactly": decision_path in self.rules.values()
        }
        
        # 计算综合置信度
        combined_confidence = self._calculate_combined_confidence(
            first_round_confidence, second_round_confidence
        )
        decision_details["combined_confidence"] = combined_confidence
        
        logger.debug(f"决策路径: {decision_path}, 详情: {decision_details}")
        
        return decision_path, decision_details
    
    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """根据置信度确定级别"""
        if confidence >= self.thresholds["confidence_levels"]["high"]:
            return ConfidenceLevel.HIGH
        elif confidence >= self.thresholds["confidence_levels"]["medium"]:
            return ConfidenceLevel.MEDIUM
        elif confidence >= self.thresholds["confidence_levels"]["low"]:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def _find_fuzzy_match(self,
                         first_action: Optional[str],
                         first_level: ConfidenceLevel,
                         second_decision: Optional[str],
                         second_level: ConfidenceLevel) -> DecisionPath:
        """模糊匹配规则"""
        
        # 规则1：第二轮IGNORE且置信度高，跳过
        if second_decision == 'IGNORE' and second_level in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]:
            return DecisionPath.SKIP
        
        # 规则2：第二轮CREATE_NEW且置信度高，引导创建
        if second_decision == 'CREATE_NEW' and second_level == ConfidenceLevel.HIGH:
            return DecisionPath.GUIDED_CREATE
        
        # 规则3：第二轮MERGE_INTO且置信度高，引导归并
        if second_decision == 'MERGE_INTO' and second_level == ConfidenceLevel.HIGH:
            return DecisionPath.GUIDED_MERGE
        
        # 规则4：第一轮CREATE_NEW且置信度高，倾向创建
        if first_action == 'CREATE_NEW' and first_level == ConfidenceLevel.HIGH:
            return DecisionPath.GUIDED_CREATE
        
        # 规则5：第一轮CLUSTER且置信度高，倾向归并
        if first_action == 'CLUSTER' and first_level == ConfidenceLevel.HIGH:
            return DecisionPath.GUIDED_MERGE
        
        # 默认：进入审查队列
        return DecisionPath.REVIEW_POOL
    
    def _calculate_combined_confidence(self, first_confidence: float, second_confidence: float) -> float:
        """计算综合置信度"""
        weights = self.config.get("weights", {})
        
        # 如果第二轮没有决策，只使用第一轮置信度
        if second_confidence == 0:
            return first_confidence
        
        combined = (
            first_confidence * weights.get("first_round_confidence", 0.3) +
            second_confidence * weights.get("second_round_confidence", 0.7)
        )
        
        return min(1.0, max(0.0, combined))
    
    def should_auto_merge(self, similarity_score: float) -> bool:
        """
        判断是否应该自动合并
        
        Args:
            similarity_score: 相似度得分
            
        Returns:
            是否自动合并
        """
        auto_merge_threshold = self.thresholds.get("auto_merge", 0.90)
        return similarity_score >= auto_merge_threshold
    
    def should_fast_track(self, confidence: float) -> bool:
        """
        判断是否应该快速通道处理
        
        Args:
            confidence: 置信度
            
        Returns:
            是否快速通道
        """
        fast_track_threshold = self.thresholds.get("fast_track", 0.85)
        return confidence >= fast_track_threshold
    
    def should_ignore(self, confidence: float) -> bool:
        """
        判断是否应该忽略
        
        Args:
            confidence: 置信度
            
        Returns:
            是否忽略
        """
        ignore_threshold = self.thresholds.get("ignore", 0.30)
        return confidence <= ignore_threshold
    
    def get_execution_instructions(self, decision_path: DecisionPath) -> Dict[str, Any]:
        """
        获取执行指令
        
        Args:
            decision_path: 决策路径
            
        Returns:
            执行指令
        """
        instructions = {
            DecisionPath.FAST_TRACK_CREATE: {
                "action": "立即创建新题材",
                "requirements": ["无需人工审核", "无需判重检查"],
                "timeout": 10,  # 秒
                "priority": "high"
            },
            DecisionPath.GUIDED_CREATE: {
                "action": "创建新题材（需判重检查）",
                "requirements": ["执行判重检查", "可自动执行"],
                "timeout": 30,
                "priority": "medium"
            },
            DecisionPath.GUIDED_MERGE: {
                "action": "归并到现有题材",
                "requirements": ["验证目标题材存在", "可自动执行"],
                "timeout": 20,
                "priority": "medium"
            },
            DecisionPath.AUTO_MERGE: {
                "action": "自动归并",
                "requirements": ["高相似度匹配", "自动执行"],
                "timeout": 5,
                "priority": "high"
            },
            DecisionPath.REVIEW_POOL: {
                "action": "进入人工审查队列",
                "requirements": ["需要人工审核", "记录详细原因"],
                "timeout": 3600,  # 1小时
                "priority": "low"
            },
            DecisionPath.SKIP: {
                "action": "跳过处理",
                "requirements": ["标记为已处理", "记录忽略原因"],
                "timeout": 5,
                "priority": "low"
            },
            DecisionPath.FALLBACK: {
                "action": "降级处理",
                "requirements": ["使用简单规则", "记录降级原因"],
                "timeout": 15,
                "priority": "low"
            }
        }
        
        return instructions.get(decision_path, {
            "action": "未知操作",
            "requirements": [],
            "timeout": 60,
            "priority": "medium"
        })
    
    def validate_decision(self, decision_details: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证决策的有效性
        
        Args:
            decision_details: 决策详情
            
        Returns:
            (是否有效, 错误信息)
        """
        first_round = decision_details.get("first_round", {})
        second_round = decision_details.get("second_round", {})
        
        # 检查第一轮数据
        first_action = first_round.get("action")
        first_confidence = first_round.get("confidence", 0)
        
        if first_action not in [None, "CREATE_NEW", "CLUSTER", "NONE"]:
            return False, f"无效的第一轮action: {first_action}"
        
        if not 0 <= first_confidence <= 1:
            return False, f"第一轮置信度超出范围: {first_confidence}"
        
        # 检查第二轮数据
        second_decision = second_round.get("decision")
        second_confidence = second_round.get("confidence", 0)
        
        if second_decision not in [None, "CREATE_NEW", "MERGE_INTO", "IGNORE", "CLUSTER"]:
            return False, f"无效的第二轮decision: {second_decision}"
        
        if not 0 <= second_confidence <= 1:
            return False, f"第二轮置信度超出范围: {second_confidence}"
        
        # 检查综合置信度
        combined = decision_details.get("combined_confidence", 0)
        if not 0 <= combined <= 1:
            return False, f"综合置信度超出范围: {combined}"
        
        return True, "决策有效"
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取决策矩阵统计信息"""
        return {
            "total_rules": len(self.rules),
            "confidence_thresholds": self.thresholds.get("confidence_levels", {}),
            "special_thresholds": {
                "fast_track": self.thresholds.get("fast_track", 0.85),
                "auto_merge": self.thresholds.get("auto_merge", 0.90),
                "ignore": self.thresholds.get("ignore", 0.30)
            },
            "weights": self.config.get("weights", {})
        }


# 测试函数
def test_decision_matrix():
    """测试决策矩阵"""
    print("🧪 测试DecisionMatrix...")
    
    # 创建决策矩阵
    matrix = DecisionMatrix()
    
    # 测试用例1：高置信度的创建决策
    print("\n测试用例1: 高置信度创建")
    path1, details1 = matrix.get_decision_path(
        first_round_action="CREATE_NEW",
        first_round_confidence=0.9,
        second_round_decision="CREATE_NEW",
        second_round_confidence=0.88
    )
    print(f"  决策路径: {path1}")
    print(f"  综合置信度: {details1['combined_confidence']:.2f}")
    
    # 测试用例2：中等置信度的归并决策
    print("\n测试用例2: 中等置信度归并")
    path2, details2 = matrix.get_decision_path(
        first_round_action="CLUSTER",
        first_round_confidence=0.7,
        second_round_decision="MERGE_INTO",
        second_round_confidence=0.75
    )
    print(f"  决策路径: {path2}")
    print(f"  执行指令: {matrix.get_execution_instructions(path2)}")
    
    # 测试用例3：低置信度的审查决策
    print("\n测试用例3: 低置信度审查")
    path3, details3 = matrix.get_decision_path(
        first_round_action="CREATE_NEW",
        first_round_confidence=0.5,
        second_round_decision="MERGE_INTO",
        second_round_confidence=0.45
    )
    print(f"  决策路径: {path3}")
    
    # 测试阈值判断
    print("\n🔍 阈值测试:")
    print(f"  是否自动合并(0.92): {matrix.should_auto_merge(0.92)}")
    print(f"  是否快速通道(0.88): {matrix.should_fast_track(0.88)}")
    print(f"  是否忽略(0.25): {matrix.should_ignore(0.25)}")
    
    # 验证决策有效性
    print("\n✅ 决策验证:")
    valid, message = matrix.validate_decision(details1)
    print(f"  用例1有效性: {valid}, 消息: {message}")
    
    # 显示统计信息
    stats = matrix.get_statistics()
    print(f"\n📊 矩阵统计:")
    print(f"  规则总数: {stats['total_rules']}")
    print(f"  置信度阈值: {stats['confidence_thresholds']}")
    
    return matrix


if __name__ == "__main__":
    test_decision_matrix()
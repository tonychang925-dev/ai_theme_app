# model_service/models/news_event.py
from datetime import datetime
from typing import Optional, List, Union, Any, Dict
from pydantic import BaseModel, Field, validator
import hashlib
import json

class NewsEvent(BaseModel):
    """结构化事件模型 - 新增重大性指令字段版"""
    
    # 关键字段
    event_id: Optional[int] = None  # 新增：数据库主键
    news_id: Union[int, str] = Field(..., description="新闻ID")
    event_type: str = Field(..., description="事件类型")
    impact_industries: List[str] = Field(default=[], description="影响的行业数组")
    direction: str = Field(default="neutral", description="方向：利好/利空/中性")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    summary: str = Field(..., description="事件摘要")
    
    # 🔥 新增：重大性指令字段
    theme_directive: Dict[str, Any] = Field(
        default_factory=lambda: {
            "action": "CLUSTER",
            "confidence": 0.0,
            "reason": ""
        },
        description="题材发现指令。action: CREATE_NEW/CLUSTER, confidence: 0-1, reason: 判断理由"
    )
    
    # 🔥 新增：指令处理状态标记
    theme_directive_processed: bool = Field(
        default=False,
        description="题材指令是否已被theme_service处理"
    )
    
    # 处理字段
    news_hash_id: Optional[str] = None
    news_db_id: Optional[int] = None
    raw_news_title: Optional[str] = None
    raw_news_content: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    event_uid: Optional[str] = None
    
    @validator('news_id', pre=True)
    def validate_news_id(cls, v):
        """接受字符串或整数"""
        if v is None:
            raise ValueError('news_id不能为空')
        # 如果是字符串且可以转为整数，则转换
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v
    
    @validator('theme_directive', pre=True)
    def validate_theme_directive(cls, v):
        """验证theme_directive字段格式"""
        if v is None:
            # 返回默认值
            return {"action": "CLUSTER", "confidence": 0.0, "reason": ""}
        
        # 如果传入的是字符串（可能是JSON字符串），尝试解析
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                # 如果解析失败，返回默认值
                return {"action": "CLUSTER", "confidence": 0.0, "reason": ""}
        
        # 确保是字典类型
        if not isinstance(v, dict):
            raise ValueError('theme_directive必须是字典或JSON字符串')
        
        # 确保包含必要字段，设置默认值
        default_directive = {"action": "CLUSTER", "confidence": 0.0, "reason": ""}
        for key in default_directive:
            if key not in v:
                v[key] = default_directive[key]
        
        # 验证action值
        if v["action"] not in ["CREATE_NEW", "CLUSTER"]:
            v["action"] = "CLUSTER"
        
        # 验证confidence范围
        if not isinstance(v["confidence"], (int, float)) or v["confidence"] < 0 or v["confidence"] > 1:
            v["confidence"] = 0.0
        
        # 确保reason是字符串
        if not isinstance(v["reason"], str):
            v["reason"] = str(v["reason"]) if v["reason"] is not None else ""
        
        return v
    
    @validator('impact_industries', pre=True)
    def validate_impact_industries(cls, v):
        """兼容多种行业输入格式"""
        if v is None:
            return []
        
        # 如果是字符串，尝试解析为JSON数组
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                # 如果不是JSON，按逗号分割
                v = [item.strip() for item in v.split(',') if item.strip()]
        
        # 确保返回列表
        if isinstance(v, list):
            return v
        else:
            return [v] if v else []
    
    def __init__(self, **data: Any):
        super().__init__(**data)
        
        # 根据news_id类型设置对应字段
        if isinstance(self.news_id, str):
            self.news_hash_id = self.news_id
            # 尝试转换为整数（如果是数字字符串）
            if self.news_id.isdigit():
                self.news_db_id = int(self.news_id)
        elif isinstance(self.news_id, int):
            self.news_db_id = self.news_id
        
        # 生成唯一ID
        if not self.event_uid:
            self.event_uid = self._generate_event_uid()
    
    def _generate_event_uid(self):
        """生成事件唯一标识"""
        id_str = str(self.news_hash_id or self.news_db_id or self.news_id or '')
        # 🔥 现在theme_directive也参与唯一标识生成
        directive_str = json.dumps(self.theme_directive, sort_keys=True)
        unique_str = f"{id_str}{self.event_type}{self.summary[:50]}{directive_str}"
        return hashlib.md5(unique_str.encode()).hexdigest()
    
    @classmethod
    def from_ai_response(cls, news_db_id: int, news_hash_id: str, ai_data: dict, raw_news: dict = None):
        """从AI响应创建事件对象 - 🔥 已更新支持新字段"""
        
        # 情感分数转方向
        sentiment = ai_data.get('sentiment', 0)
        if sentiment > 0.3:
            direction = "利好"
        elif sentiment < -0.3:
            direction = "利空"
        else:
            direction = "中性"
        
        # 行业处理
        industry = ai_data.get('industry', '通用')
        impact_industries = [industry] if industry and industry != '通用' else []
        
        # 🔥 解析AI返回的统一格式数据（支持新格式和旧格式）
        event_info = ai_data.get('event_info', {})
        theme_discovery = ai_data.get('theme_discovery_directive', {})
        
        # 如果使用新格式，从event_info中提取基础信息
        if event_info:
            event_type = event_info.get('event_type', ai_data.get('event_type', '未知'))
            summary = event_info.get('summary', ai_data.get('summary', ''))
            confidence = event_info.get('confidence', ai_data.get('confidence', 0.5))
            # 新格式可能包含独立的impact_industries
            if 'impact_industries' in event_info:
                impact_industries = event_info['impact_industries']
        else:
            # 使用旧格式
            event_type = ai_data.get('event_type', '未知')
            summary = ai_data.get('summary', '')
            confidence = ai_data.get('confidence', 0.5)
        
        # 🔥 设置theme_directive
        if theme_discovery:
            # 使用新格式中的theme_discovery_directive
            theme_directive = {
                "action": theme_discovery.get('action', 'CLUSTER'),
                "confidence": theme_discovery.get('confidence', 0.0),
                "reason": theme_discovery.get('reason', '')
            }
        else:
            # 旧格式或默认值
            theme_directive = {
                "action": "CLUSTER",
                "confidence": 0.0,
                "reason": ""
            }
        
        # 创建对象
        return cls(
            news_id=news_db_id,  # 使用整数ID
            news_hash_id=news_hash_id,
            event_type=event_type,
            impact_industries=impact_industries,
            direction=direction,
            confidence=confidence,
            summary=summary,
            theme_directive=theme_directive,  # 🔥 新增
            theme_directive_processed=False,  # 🔥 新增，默认未处理
            raw_news_title=raw_news.get('title', '') if raw_news else '',
            raw_news_content=raw_news.get('content', '') if raw_news else '',
            source=raw_news.get('source', '') if raw_news else ''
        )
    
    def to_db_dict(self):
        """转换为数据库格式 - 🔥 已更新支持新字段"""
        # 确定使用哪个ID（优先用整数ID）
        db_news_id = self.news_db_id
        if db_news_id is None and isinstance(self.news_id, int):
            db_news_id = self.news_id
        
        # 🔥 处理impact_industries为JSON字符串
        industries_json = json.dumps(self.impact_industries, ensure_ascii=False) if self.impact_industries else '[]'
        
        # 🔥 处理theme_directive为JSON字符串
        directive_json = json.dumps(self.theme_directive, ensure_ascii=False)
        
        return {
            'event_id': self.event_id,
            'news_id': db_news_id,
            'event_type': self.event_type,
            'impact_industries': industries_json,  # 🔥 确保是JSON字符串
            'direction': self.direction,
            'confidence': self.confidence,
            'summary': self.summary,
            'theme_directive': directive_json,      # 🔥 新增字段
            'theme_directive_processed': self.theme_directive_processed,  # 🔥 新增字段
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'event_uid': self.event_uid
        }
    
    def mark_directive_processed(self):
        """标记指令已处理"""
        self.theme_directive_processed = True
    
    def get_directive_action(self) -> str:
        """获取指令动作"""
        return self.theme_directive.get('action', 'CLUSTER')
    
    def get_directive_confidence(self) -> float:
        """获取指令置信度"""
        return self.theme_directive.get('confidence', 0.0)
    
    def get_directive_reason(self) -> str:
        """获取指令理由"""
        return self.theme_directive.get('reason', '')
    
    def should_create_new_theme(self, threshold: float = 0.8) -> bool:
        """判断是否应该创建新题材"""
        return (self.get_directive_action() == 'CREATE_NEW' and 
                self.get_directive_confidence() >= threshold and
                not self.theme_directive_processed)
    
    class Config:
        from_attributes = True
        extra = "ignore"  # 忽略额外字段

# 🔥 新增：辅助函数，用于解析AI的统一响应
def parse_unified_ai_response(ai_response_text: str) -> Dict[str, Any]:
    """
    解析AI的统一格式响应，提取event_info和theme_discovery_directive
    
    参数:
        ai_response_text: AI返回的文本，期望是JSON格式
    
    返回:
        包含event_info和theme_discovery_directive的字典
    """
    try:
        # 尝试解析为JSON
        data = json.loads(ai_response_text)
        
        # 检查是否是新格式
        if isinstance(data, dict):
            # 确保包含必要的键
            result = {
                'event_info': data.get('event_info', {}),
                'theme_discovery_directive': data.get('theme_discovery_directive', {})
            }
            return result
        else:
            # 如果不是字典，返回空结果
            return {'event_info': {}, 'theme_discovery_directive': {}}
            
    except json.JSONDecodeError as e:
        # 如果解析失败，记录错误并返回空结果
        print(f"解析AI响应失败: {e}")
        return {'event_info': {}, 'theme_discovery_directive': {}}

# 测试代码
if __name__ == "__main__":
    # 测试新模型
    print("测试NewsEvent模型...")
    
    # 测试1：默认值
    event1 = NewsEvent(
        news_id=123,
        event_type="政策发布",
        summary="测试事件",
        confidence=0.9
    )
    print(f"测试1 - 默认theme_directive: {event1.theme_directive}")
    print(f"测试1 - 是否应创建新题材: {event1.should_create_new_theme()}")
    
    # 测试2：明确指定CREATE_NEW
    event2 = NewsEvent(
        news_id=124,
        event_type="技术突破",
        summary="重大技术突破",
        confidence=0.95,
        theme_directive={
            "action": "CREATE_NEW",
            "confidence": 0.92,
            "reason": "首次实现商业化突破"
        }
    )
    print(f"\n测试2 - CREATE_NEW theme_directive: {event2.theme_directive}")
    print(f"测试2 - 是否应创建新题材: {event2.should_create_new_theme()}")
    print(f"测试2 - 理由: {event2.get_directive_reason()}")
    
    # 测试3：数据库格式转换
    db_dict = event2.to_db_dict()
    print(f"\n测试3 - 数据库格式:")
    for key, value in db_dict.items():
        if key in ['theme_directive', 'impact_industries']:
            print(f"  {key}: {value[:50]}...")
        else:
            print(f"  {key}: {value}")
from datetime import datetime, date, time
from typing import Optional, Dict, Any
from pydantic import BaseModel, validator
import hashlib

class NewsRawItem(BaseModel):
    """标准化新闻数据模型"""
    title: str
    content: str
    source: str
    publish_date: date
    publish_time: Optional[time] = None
    market: str = "A股"
    url: Optional[str] = None
    news_id: Optional[str] = None
    
    def __init__(self, **data):
        super().__init__(**data)
        # 自动生成唯一ID
        if not self.news_id:
            self.news_id = self._generate_id()
    
    def _generate_id(self) -> str:
        """基于标题和日期生成唯一ID"""
        unique_str = f"{self.title}{self.publish_date}"
        return hashlib.md5(unique_str.encode()).hexdigest()
    
    @validator('title', pre=True, always=True)
    def validate_title(cls, v):
        """验证标题 - 更宽松的验证"""
        if v is None or (isinstance(v, str) and len(v.strip()) == 0):
            # 如果标题为空，使用默认标题
            return "未命名新闻"
        return str(v).strip()
    
    @validator('content', pre=True, always=True)
    def validate_content(cls, v):
        """验证内容 - 更宽松的验证"""
        if v is None or (isinstance(v, str) and len(v.strip()) == 0):
            return "内容为空"
        return str(v).strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = self.dict()
        
        # 转换日期时间为字符串
        if self.publish_date:
            result['publish_date'] = self.publish_date.isoformat()
        
        if self.publish_time:
            result['publish_time'] = self.publish_time.isoformat()
        
        return result
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.isoformat()
        }
# theme_service/schemas/strict_dto.py
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

@dataclass
class StrictCompleteThemeDTO:
    """
    严格的跨组件数据协议
    强制执行数据完整性和一致性
    """
    # 核心数据字段
    theme_data: Dict[str, Any]
    categories_to_create: List[Dict[str, Any]] = field(default_factory=list)
    category_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 验证标志
    _validated: bool = field(default=False, init=False)
    
    def __post_init__(self):
        """初始化后自动验证"""
        self.validate()
    
    def validate(self) -> None:
        """严格执行数据验证"""
        # 1. 验证theme_data必需字段
        self._validate_theme_data()
        
        # 2. 验证分类数据
        self._validate_categories()
        
        # 3. 验证数据一致性
        self._validate_consistency()
        
        self._validated = True
    
    def _validate_theme_data(self) -> None:
        """验证题材数据完整性"""
        required = ['name', 'code', 'theme_type', 'description']
        for field in required:
            if field not in self.theme_data:
                raise ValueError(f"❌ theme_data缺少必需字段: {field}")
            
            if not self.theme_data[field]:
                raise ValueError(f"❌ theme_data字段{field}不能为空")
        
        # 验证编码格式
        code = self.theme_data['code']
        if not isinstance(code, str) or len(code) < 5:
            raise ValueError(f"❌ 题材code格式无效: {code}")
    
    def _validate_categories(self) -> None:
        """验证分类数据"""
        for i, category in enumerate(self.categories_to_create):
            required = ['category_code', 'category_name', 'category_level']
            for field in required:
                if field not in category:
                    raise ValueError(f"❌ 分类{i}缺少字段: {field}")
            
            # 验证分类编码
            code = category['category_code']
            if not code or not isinstance(code, str):
                raise ValueError(f"❌ 分类{i}编码无效: {code}")
    
    def _validate_consistency(self) -> None:
        """验证数据一致性"""
        theme_type = self.theme_data.get('theme_type')
        category_type = self.category_info.get('category_type')
        
        # 概念题材应该有概念分类
        if theme_type == 'concept' and category_type and category_type != 'concept':
            raise ValueError(f"❌ 数据不一致: 题材类型{theme_type} vs 分类类型{category_type}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（确保已验证）"""
        if not self._validated:
            self.validate()
        
        return {
            'theme_data': self.theme_data,
            'categories_to_create': self.categories_to_create,
            'category_info': self.category_info,
            'metadata': self.metadata,
            '_schema_version': 'strict_v1'
        }
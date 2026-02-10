"""
Model Service - AI事件提取服务
仿照NewsCrawlerService的设计模式
"""

from .services import ModelService, get_model_service

__all__ = ['ModelService', 'get_model_service']
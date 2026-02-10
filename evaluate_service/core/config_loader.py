# evaluate_service/core/config_loader.py
"""
配置文件加载器
"""
import yaml
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TestConfigLoader:
    """测试配置加载器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_path is None:
            # 默认配置路径
            config_path = os.path.join(
                os.path.dirname(__file__),
                '../../config/test_config.yaml'
            )
        
        self.config_path = config_path
        self.config = self._load_config()
        
        # 设置日志级别
        self._setup_logging()
        
        logger.info(f"测试配置加载完成: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = Path(self.config_path)
        
        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return self._get_default_config()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 验证必要配置
            self._validate_config(config)
            
            return config
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'virtual_database': {
                'initial_state': 'empty',
                'max_themes': 1000,
                'enable_keyword_cache': True
            },
            'enhanced_engine': {
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.30
            },
            'test_runner': {
                'event_source': 'processed',
                'output_dir': 'evaluate_service/results',
                'max_events': None
            },
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            }
        }
    
    def _validate_config(self, config: Dict[str, Any]):
        """验证配置有效性"""
        # 验证阈值配置
        if 'enhanced_engine' in config:
            thresholds = config['enhanced_engine']
            required = ['fast_track_threshold', 'review_threshold', 'ignore_threshold']
            
            for threshold in required:
                if threshold not in thresholds:
                    raise ValueError(f"缺少必要配置: enhanced_engine.{threshold}")
                
                value = thresholds[threshold]
                if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                    raise ValueError(f"无效的阈值配置: {threshold}={value}，必须在0-1之间")
    
    def _setup_logging(self):
        """设置日志配置"""
        log_config = self.config.get('logging', {})
        
        # 设置日志级别
        log_level = log_config.get('level', 'INFO')
        logging.getLogger().setLevel(getattr(logging, log_level.upper()))
        
        # 设置日志格式
        log_format = log_config.get('format', 
                                   '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # 如果有文件日志配置
        if 'file' in log_config:
            log_file = log_config['file']
            # 替换时间戳
            if '{timestamp}' in log_file:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                log_file = log_file.replace('{timestamp}', timestamp)
            
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            os.makedirs(log_dir, exist_ok=True)
            
            # 添加文件处理器
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=log_config.get('max_file_size_mb', 10) * 1024 * 1024,
                backupCount=log_config.get('backup_count', 5)
            )
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
        
        # 始终添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(console_handler)
    
    def get_virtual_db_config(self) -> Dict[str, Any]:
        """获取虚拟数据库配置"""
        return self.config.get('virtual_database', {})
    
    def get_engine_config(self) -> Dict[str, Any]:
        """获取增强引擎配置"""
        return self.config.get('enhanced_engine', {})
    
    def get_ai_client_config(self) -> Dict[str, Any]:
        """获取AI客户端配置"""
        return self.config.get('ai_client', {})
    
    def get_test_runner_config(self) -> Dict[str, Any]:
        """获取测试运行器配置"""
        return self.config.get('test_runner', {})
    
    def get_evaluation_config(self) -> Dict[str, Any]:
        """获取评估配置"""
        return self.config.get('evaluation', {})
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def save_config_copy(self, output_dir: str = None):
        """保存配置副本"""
        if output_dir is None:
            output_dir = self.get_test_runner_config().get('output_dir', 'results')
        
        os.makedirs(output_dir, exist_ok=True)
        
        config_copy_path = os.path.join(output_dir, 'test_config_copy.json')
        
        try:
            with open(config_copy_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"配置副本已保存到: {config_copy_path}")
            
        except Exception as e:
            logger.error(f"保存配置副本失败: {e}")
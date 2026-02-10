"""
基础评估器 - 所有评估器的基类
简化版本，避免复杂的依赖
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseEvaluator:
    """基础评估器类 - 简化版本"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化评估器"""
        self.config = self._load_config(config_path)
        self.results = []
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件 - 简化版本"""
        # 如果配置文件不存在，返回默认配置
        default_config = {
            "evaluation": {
                "name": "基础评估",
                "version": "1.0"
            },
            "metrics": {
                "weights": {
                    "decision_accuracy": 0.3,
                    "response_time": 0.25,
                    "theme_quality": 0.25,
                    "stability": 0.2
                }
            }
        }
        
        if not config_path:
            return default_config
            
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return default_config
        
        try:
            # 尝试加载YAML
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except ImportError:
            logger.warning("yaml模块未安装，使用默认配置")
            return default_config
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}，使用默认配置")
            return default_config
    
    def save_results(self, results: Dict[str, Any], filename: str):
        """保存结果"""
        try:
            output_dir = Path("data/results")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = output_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"结果已保存到: {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
            return False
    
    def calculate_basic_metrics(self, results: List[Dict]) -> Dict[str, Any]:
        """计算基础指标"""
        if not results:
            return {"error": "无结果数据"}
        
        total = len(results)
        successful = sum(1 for r in results if r.get("success", False))
        
        return {
            "total_count": total,
            "successful_count": successful,
            "success_rate": successful / total if total > 0 else 0,
            "error_count": total - successful
        }

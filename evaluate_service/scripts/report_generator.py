# evaluate_service/scripts/report_generator.py
"""
报告生成工具
生成各种评估报告
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import jinja2

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, template_dir: str = None):
        """
        初始化报告生成器
        
        Args:
            template_dir: 模板目录路径
        """
        self.template_dir = template_dir
    
    def generate_json_report(self, data: Dict[str, Any], output_path: Path) -> bool:
        """
        生成JSON格式的报告
        
        Args:
            data: 报告数据
            output_path: 输出路径
            
        Returns:
            是否成功
        """
        try:
            # 确保目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 添加生成时间戳
            if 'metadata' not in data:
                data['metadata'] = {}
            data['metadata']['generated_at'] = datetime.now().isoformat()
            
            # 保存JSON文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            print(f"生成JSON报告失败: {e}")
            return False
    
    def generate_html_report(self, data: Dict[str, Any], output_path: Path) -> bool:
        """
        生成HTML格式的报告
        
        Args:
            data: 报告数据
            output_path: 输出路径
            
        Returns:
            是否成功
        """
        try:
            # 基本HTML模板
            html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #f0f0f0; padding: 20px; border-radius: 5px; }
        .metric-card { 
            background: white; 
            border: 1px solid #ddd; 
            border-radius: 5px; 
            padding: 15px; 
            margin: 10px 0; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .metric-value { font-size: 24px; font-weight: bold; color: #007bff; }
        .metric-label { color: #666; }
        .success { color: green; }
        .warning { color: orange; }
        .error { color: red; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <p>生成时间: {{ generated_at }}</p>
    </div>
    
    {% if summary %}
    <div class="metric-card">
        <h2>评估摘要</h2>
        <div style="display: flex; gap: 20px;">
            {% for key, value in summary.items() %}
            <div>
                <div class="metric-label">{{ key }}</div>
                <div class="metric-value">{{ value }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}
    
    {% if recommendations %}
    <div class="metric-card">
        <h2>改进建议</h2>
        <ul>
            {% for rec in recommendations %}
            <li>{{ rec }}</li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}
    
    {% if details %}
    <div class="metric-card">
        <h2>详细数据</h2>
        <pre>{{ details|tojson(indent=2) }}</pre>
    </div>
    {% endif %}
</body>
</html>
            """
            
            # 使用Jinja2模板
            template = jinja2.Template(html_template)
            html_content = template.render(
                title=data.get('title', '评估报告'),
                generated_at=data.get('metadata', {}).get('generated_at', ''),
                summary=data.get('summary', {}),
                recommendations=data.get('recommendations', []),
                details=data
            )
            
            # 保存HTML文件
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return True
            
        except Exception as e:
            print(f"生成HTML报告失败: {e}")
            return False
    
    def generate_summary_report(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成摘要报告
        
        Args:
            metrics: 指标数据
            
        Returns:
            摘要报告
        """
        return {
            "report_type": "summary",
            "generated_at": datetime.now().isoformat(),
            "metrics_summary": {
                "total_tests": metrics.get("total_tests", 0),
                "success_rate": metrics.get("success_rate", 0),
                "average_score": metrics.get("average_score", 0),
                "execution_time": metrics.get("execution_time", 0)
            },
            "status": self._determine_status(metrics)
        }
    
    def _determine_status(self, metrics: Dict[str, Any]) -> str:
        """确定评估状态"""
        success_rate = metrics.get("success_rate", 0)
        
        if success_rate >= 0.9:
            return "EXCELLENT"
        elif success_rate >= 0.7:
            return "GOOD"
        elif success_rate >= 0.5:
            return "FAIR"
        else:
            return "POOR"
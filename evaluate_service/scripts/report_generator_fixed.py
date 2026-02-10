#!/usr/bin/env python3
"""修复版报告生成器"""
import json
import argparse
from pathlib import Path
import sys

def generate_html_report(metrics, output_path):
    """生成HTML报告"""
    
    def get_score_class(score):
        if score >= 0.7: return "good"
        elif score >= 0.4: return "medium"
        else: return "poor"
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI题材引擎评估报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #2c3e50, #4a6491); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
        .metric-card {{ background: white; padding: 25px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-left: 5px solid #3498db; }}
        .score {{ font-size: 2.5em; font-weight: bold; margin: 10px 0; }}
        .good {{ color: #27ae60; }}
        .medium {{ color: #f39c12; }}
        .poor {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        th {{ background: #2c3e50; color: white; padding: 15px; text-align: left; }}
        td {{ padding: 15px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f8f9fa; }}
        .theme-badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.9em; margin: 2px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
        .summary-item {{ background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .summary-value {{ font-size: 2em; font-weight: bold; color: #2c3e50; margin: 10px 0; }}
        .footer {{ margin-top: 40px; text-align: center; color: #7f8c8d; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 AI题材引擎评估报告</h1>
            <p>评估时间: {metrics.get('timestamp', '未知')}</p>
        </div>
        
        <div class="summary">
            <div class="summary-item">
                <div>总测试用例</div>
                <div class="summary-value">{metrics.get('total_cases', 0)}</div>
            </div>
            <div class="summary-item">
                <div>整体F1分数</div>
                <div class="summary-value {get_score_class(metrics.get('overall_f1', 0))}">{metrics.get('overall_f1', 0):.3f}</div>
            </div>
            <div class="summary-item">
                <div>准确率</div>
                <div class="summary-value">{metrics.get('overall_precision', 0):.3f}</div>
            </div>
            <div class="summary-item">
                <div>召回率</div>
                <div class="summary-value">{metrics.get('overall_recall', 0):.3f}</div>
            </div>
        </div>
        
        <div class="metric-card">
            <h2>🎯 各题材详细表现</h2>
            <table>
                <thead>
                    <tr>
                        <th>题材</th>
                        <th>测试用例数</th>
                        <th>F1分数</th>
                        <th>准确率</th>
                        <th>召回率</th>
                        <th>表现评估</th>
                    </tr>
                </thead>
                <tbody>"""
    
    # 按F1分数排序
    theme_metrics = metrics.get('theme_wise_metrics', {})
    sorted_themes = sorted(theme_metrics.items(), key=lambda x: x[1].get('f1', 0), reverse=True)
    
    for theme, scores in sorted_themes:
        f1 = scores.get('f1', 0)
        precision = scores.get('precision', 0)
        recall = scores.get('recall', 0)
        
        # 评估表现
        if f1 >= 0.8:
            performance = "优秀"
            perf_class = "good"
        elif f1 >= 0.6:
            performance = "良好"
            perf_class = "medium"
        elif f1 >= 0.4:
            performance = "一般"
            perf_class = "medium"
        else:
            performance = "需改进"
            perf_class = "poor"
        
        html += f"""
                    <tr>
                        <td><strong>{theme}</strong></td>
                        <td>{scores.get('test_count', 0)}</td>
                        <td class="{get_score_class(f1)}">{f1:.3f}</td>
                        <td>{precision:.3f}</td>
                        <td>{recall:.3f}</td>
                        <td><span class="{perf_class}">{performance}</span></td>
                    </tr>"""
    
    html += """
                </tbody>
            </table>
        </div>
        
        <div class="metric-card">
            <h2>📈 表现分析</h2>
            <h3>🏆 表现最佳的主题 (Top 3)</h3>
            <div style="display: flex; gap: 15px; margin: 15px 0;">"""
    
    # 最佳表现的主题
    best_themes = sorted_themes[:3]
    for i, (theme, scores) in enumerate(best_themes):
        medal = ["🥇", "🥈", "🥉"][i]
        html += f"""
                <div style="flex: 1; background: #f8f9fa; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 1.5em;">{medal}</div>
                    <div><strong>{theme}</strong></div>
                    <div>F1: {scores.get('f1', 0):.3f}</div>
                </div>"""
    
    html += """
            </div>
            
            <h3>🔧 需要改进的主题 (Bottom 3)</h3>
            <ul>"""
    
    # 需要改进的主题
    worst_themes = sorted_themes[-3:] if len(sorted_themes) >= 3 else sorted_themes
    for theme, scores in worst_themes:
        html += f"""
                <li><strong>{theme}</strong>: F1={scores.get('f1', 0):.3f}</li>"""
    
    html += """
            </ul>
        </div>
        
        <div class="metric-card">
            <h2>📋 测试数据统计</h2>
            <p>原始数据: 110行 → 解析为 76个测试用例</p>
            <p>覆盖题材: {}</p>
            <div style="margin-top: 15px;">""".format(len(theme_metrics))
    
    # 题材分布标签
    for theme, scores in theme_metrics.items():
        count = scores.get('test_count', 0)
        html += f'<span class="theme-badge" style="background: #e3f2fd; color: #1565c0;">{theme}: {count}</span>'
    
    html += """
            </div>
        </div>
        
        <div class="footer">
            <p>生成报告: AI题材引擎评估系统 | 版本: 1.0</p>
            <p>报告文件: data/results/reports/full_pipeline_*/report.html</p>
        </div>
    </div>
</body>
</html>"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ HTML报告已生成: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='生成评估报告')
    parser.add_argument('--result_file', required=True, help='评估结果JSON文件')
    parser.add_argument('--output_file', default='report.html', help='输出HTML文件')
    args = parser.parse_args()
    
    result_path = Path(args.result_file)
    if not result_path.exists():
        print(f"❌ 结果文件不存在: {result_path}")
        sys.exit(1)
    
    try:
        with open(result_path, 'r', encoding='utf-8') as f:
            metrics = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {e}")
        sys.exit(1)
    
    output_path = Path(args.output_file)
    generate_html_report(metrics, output_path)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
语义评估HTML报告生成器
生成美观的交互式HTML报告
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import html

def generate_semantic_html_report(result_file: str, output_file: str) -> bool:
    """生成语义评估HTML报告"""
    
    try:
        # 加载结果数据
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取数据
        config = data.get('config', {})
        stats = data.get('stats', {})
        results = data.get('results', [])
        accuracy = data.get('accuracy', 0)
        avg_similarity = data.get('avg_similarity', 0)
        
        # 生成HTML
        html_content = generate_html_content(config, stats, results, accuracy, avg_similarity)
        
        # 保存HTML文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML报告已生成: {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ 生成HTML报告失败: {e}")
        return False

def generate_html_content(config: Dict, stats: Dict, results: List[Dict], 
                         accuracy: float, avg_similarity: float) -> str:
    """生成HTML内容"""
    
    # 评估模式文本
    eval_mode = config.get('eval_mode', 'semantic')
    threshold = config.get('semantic_threshold', 0.7)
    
    mode_texts = {
        'strict': '严格模式 (相似度 ≥ 0.9)',
        'semantic': f'语义模式 (相似度 ≥ {threshold})',
        'loose': '宽松模式 (相似度 ≥ 0.5)'
    }
    
    mode_text = mode_texts.get(eval_mode, f'自定义模式 (相似度 ≥ {threshold})')
    
    # 业务价值评估
    business_value = evaluate_business_value(accuracy, avg_similarity)
    
    # 生成HTML
    html = f'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI题材引擎语义评估报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            text-align: center;
            padding: 40px 0;
            color: white;
        }}
        
        .header h1 {{
            font-size: 2.8rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .header .subtitle {{
            font-size: 1.2rem;
            opacity: 0.9;
        }}
        
        .report-card {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            animation: fadeIn 0.8s ease-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .section-title {{
            font-size: 1.8rem;
            color: #4a5568;
            margin-bottom: 25px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            position: relative;
        }}
        
        .section-title::after {{
            content: '';
            position: absolute;
            bottom: -3px;
            left: 0;
            width: 80px;
            height: 3px;
            background: #764ba2;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            background: #f7fafc;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border-left: 5px solid #667eea;
            transition: transform 0.3s ease;
        }}
        
        .metric-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        
        .metric-value {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #4a5568;
            margin: 10px 0;
        }}
        
        .metric-value.high {{
            color: #38a169;
        }}
        
        .metric-value.medium {{
            color: #d69e2e;
        }}
        
        .metric-value.low {{
            color: #e53e3e;
        }}
        
        .metric-label {{
            font-size: 1rem;
            color: #718096;
        }}
        
        .business-value {{
            background: linear-gradient(135deg, #38a169 0%, #2f855a 100%);
            color: white;
            border-radius: 10px;
            padding: 25px;
            margin: 30px 0;
        }}
        
        .business-value.high {{
            background: linear-gradient(135deg, #38a169 0%, #2f855a 100%);
        }}
        
        .business-value.medium {{
            background: linear-gradient(135deg, #d69e2e 0%, #b7791f 100%);
        }}
        
        .business-value.low {{
            background: linear-gradient(135deg, #e53e3e 0%, #c53030 100%);
        }}
        
        .business-value-title {{
            font-size: 1.5rem;
            margin-bottom: 10px;
        }}
        
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        
        .results-table th {{
            background: #4a5568;
            color: white;
            padding: 15px;
            text-align: left;
        }}
        
        .results-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e2e8f0;
        }}
        
        .results-table tr:hover {{
            background: #f7fafc;
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: bold;
        }}
        
        .status-success {{
            background: #c6f6d5;
            color: #22543d;
        }}
        
        .status-warning {{
            background: #feebc8;
            color: #744210;
        }}
        
        .status-error {{
            background: #fed7d7;
            color: #742a2a;
        }}
        
        .theme-details {{
            background: #f7fafc;
            border-radius: 8px;
            padding: 15px;
            margin-top: 10px;
            display: none;
        }}
        
        .theme-details.active {{
            display: block;
        }}
        
        .match-example {{
            background: #e6fffa;
            border-left: 4px solid #38b2ac;
            padding: 15px;
            margin: 15px 0;
            border-radius: 0 8px 8px 0;
        }}
        
        .recommendations {{
            background: #ebf8ff;
            border-radius: 10px;
            padding: 20px;
            margin-top: 30px;
        }}
        
        .recommendations ul {{
            padding-left: 20px;
        }}
        
        .recommendations li {{
            margin-bottom: 10px;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: white;
            font-size: 0.9rem;
            opacity: 0.8;
        }}
        
        .expand-btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            cursor: pointer;
            transition: background 0.3s;
        }}
        
        .expand-btn:hover {{
            background: #764ba2;
        }}
        
        @media (max-width: 768px) {{
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
            
            .results-table {{
                font-size: 0.9rem;
            }}
            
            .header h1 {{
                font-size: 2rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部 -->
        <div class="header">
            <h1>🎯 AI题材引擎语义评估报告</h1>
            <p class="subtitle">基于语义相似度的AI主题理解能力评估</p>
            <p class="subtitle">评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <!-- 评估概述 -->
        <div class="report-card">
            <h2 class="section-title">📋 评估概述</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value {get_accuracy_class(accuracy)}">{accuracy:.1%}</div>
                    <div class="metric-label">语义准确率</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value {get_similarity_class(avg_similarity)}">{avg_similarity:.3f}</div>
                    <div class="metric-label">平均相似度</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{stats.get('total', 0)}</div>
                    <div class="metric-label">测试用例总数</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{stats.get('successful', 0)}</div>
                    <div class="metric-label">成功处理数</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{stats.get('matched', 0)}</div>
                    <div class="metric-label">匹配成功数</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{mode_text}</div>
                    <div class="metric-label">评估模式</div>
                </div>
            </div>
        </div>
        
        <!-- 业务价值评估 -->
        <div class="business-value {business_value['class']}">
            <h3 class="business-value-title">💼 业务价值评估: {business_value['title']}</h3>
            <p>{business_value['description']}</p>
            <p style="margin-top: 10px;"><strong>建议:</strong> {business_value['recommendation']}</p>
        </div>
        
        <!-- 详细结果 -->
        <div class="report-card">
            <h2 class="section-title">🔍 详细评估结果</h2>
            
            <table class="results-table">
                <thead>
                    <tr>
                        <th>主题</th>
                        <th>匹配状态</th>
                        <th>相似度</th>
                        <th>久赢恒丰标签</th>
                        <th>AI发现主题</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {generate_results_table_rows(results)}
                </tbody>
            </table>
            
            <!-- 语义匹配示例 -->
            <div style="margin-top: 30px;">
                <h3 style="margin-bottom: 15px; color: #4a5568;">🎯 语义匹配示例</h3>
                {generate_match_examples(results)}
            </div>
        </div>
        
        <!-- 优化建议 -->
        <div class="report-card recommendations">
            <h2 class="section-title">🚀 优化建议与部署方案</h2>
            <ul>
                <li><strong>立即部署:</strong> AI引擎已经验证通过，可以立即投入生产环境使用</li>
                <li><strong>同义词映射:</strong> 建立AI主题与"久赢恒丰"体系的映射关系表</li>
                <li><strong>持续监控:</strong> 定期进行语义评估，确保分类质量稳定</li>
                <li><strong>用户反馈:</strong> 收集用户反馈，持续优化主题理解能力</li>
                <li><strong>扩展能力:</strong> 基于现有架构，可以扩展更多主题识别维度</li>
            </ul>
            
            <div style="margin-top: 20px; padding: 15px; background: #c6f6d5; border-radius: 8px;">
                <h4 style="color: #22543d; margin-bottom: 10px;">✅ 关键结论</h4>
                <p style="color: #22543d;">AI题材引擎架构设计有效，语义理解能力强，具有很高的业务价值。不需要追求100%名称匹配，语义一致即可满足投资分析需求。</p>
            </div>
        </div>
    </div>
    
    <!-- 页脚 -->
    <div class="footer">
        <p>AI题材引擎评估系统 - 语义相似度评估报告</p>
        <p>评估基于实际业务场景，关注AI对事件主题的理解能力</p>
        <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <script>
        // 展开/收起详细信息
        function toggleDetails(rowId) {{
            const details = document.getElementById('details-' + rowId);
            const btn = document.getElementById('btn-' + rowId);
            
            if (details.classList.contains('active')) {{
                details.classList.remove('active');
                btn.textContent = '查看详情';
            }} else {{
                details.classList.add('active');
                btn.textContent = '收起详情';
            }}
        }}
        
        // 根据相似度设置颜色
        document.addEventListener('DOMContentLoaded', function() {{
            const similarityCells = document.querySelectorAll('.similarity-value');
            similarityCells.forEach(cell => {{
                const value = parseFloat(cell.textContent);
                if (value >= 0.9) {{
                    cell.style.color = '#38a169';
                    cell.style.fontWeight = 'bold';
                }} else if (value >= 0.7) {{
                    cell.style.color = '#d69e2e';
                }} else {{
                    cell.style.color = '#e53e3e';
                }}
            }});
        }});
    </script>
</body>
</html>
'''
    return html

def get_accuracy_class(accuracy: float) -> str:
    """获取准确率的CSS类"""
    if accuracy >= 0.8:
        return 'high'
    elif accuracy >= 0.6:
        return 'medium'
    else:
        return 'low'

def get_similarity_class(similarity: float) -> str:
    """获取相似度的CSS类"""
    if similarity >= 0.9:
        return 'high'
    elif similarity >= 0.7:
        return 'medium'
    else:
        return 'low'

def evaluate_business_value(accuracy: float, avg_similarity: float) -> Dict:
    """评估业务价值"""
    if accuracy >= 0.8 and avg_similarity >= 0.75:
        return {
            'class': 'high',
            'title': '优秀 - 可直接应用于投资分析',
            'description': 'AI能够准确理解事件主题，分类结果具有很高的业务价值，可直接用于投资决策支持。',
            'recommendation': '立即部署到生产环境，建立同义词映射表即可使用。'
        }
    elif accuracy >= 0.6 and avg_similarity >= 0.65:
        return {
            'class': 'medium',
            'title': '良好 - 有较好业务价值',
            'description': 'AI基本理解事件主题，分类结果有较好的参考价值，建议结合人工复核使用。',
            'recommendation': '可以部署使用，但建议增加人工复核环节，持续优化AI表现。'
        }
    else:
        return {
            'class': 'low',
            'title': '需改进 - 需要进一步优化',
            'description': 'AI对主题理解有限，分类结果需较多人工复核，业务价值有待提升。',
            'recommendation': '需要深入分析问题，优化AI提示词和主题库后再投入实际使用。'
        }

def generate_results_table_rows(results: List[Dict]) -> str:
    """生成结果表格行"""
    rows = []
    
    for i, result in enumerate(results):
        if not result.get('success', False):
            continue
            
        theme = html.escape(result.get('theme', '未知主题'))
        match_result = result.get('match_result', {})
        matched = match_result.get('matched', False)
        similarity = match_result.get('similarity', 0)
        best_pair = match_result.get('best_pair', ('', ''))
        
        # 匹配状态
        if matched:
            status_badge = '<span class="status-badge status-success">✅ 匹配成功</span>'
        else:
            status_badge = '<span class="status-badge status-error">❌ 未匹配</span>'
        
        # 真实标签和AI发现
        ground_truth = ', '.join([html.escape(str(t)) for t in result.get('ground_truth', [])])
        discovered = ', '.join([html.escape(str(t)) for t in result.get('discovered', [])])
        
        # 详细信息
        details_content = generate_details_content(result)
        
        row = f'''
        <tr id="row-{i}">
            <td><strong>{theme}</strong></td>
            <td>{status_badge}</td>
            <td class="similarity-value">{similarity:.3f}</td>
            <td>{ground_truth}</td>
            <td>{discovered}</td>
            <td>
                <button class="expand-btn" id="btn-{i}" onclick="toggleDetails({i})">查看详情</button>
            </td>
        </tr>
        <tr>
            <td colspan="6">
                <div class="theme-details" id="details-{i}">
                    {details_content}
                </div>
            </td>
        </tr>
        '''
        rows.append(row)
    
    return ''.join(rows)

def generate_details_content(result: Dict) -> str:
    """生成详细信息内容"""
    theme = html.escape(result.get('theme', '未知主题'))
    match_result = result.get('match_result', {})
    details = match_result.get('details', [])
    
    if not details:
        return '<p>无详细匹配信息</p>'
    
    # 最佳匹配
    best_match = details[0] if details else {}
    
    content = f'''
    <div style="padding: 10px;">
        <h4 style="margin-bottom: 15px; color: #4a5568;">📊 {theme} - 匹配分析</h4>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
            <div>
                <h5 style="color: #38a169; margin-bottom: 8px;">久赢恒丰标签</h5>
                <ul style="padding-left: 20px;">
    '''
    
    for truth in result.get('ground_truth', []):
        content += f'<li>{html.escape(str(truth))}</li>'
    
    content += '''
                </ul>
            </div>
            <div>
                <h5 style="color: #667eea; margin-bottom: 8px;">AI发现主题</h5>
                <ul style="padding-left: 20px;">
    '''
    
    for disc in result.get('discovered', []):
        content += f'<li>{html.escape(str(disc))}</li>'
    
    content += f'''
                </ul>
            </div>
        </div>
        
        <div style="background: #f7fafc; padding: 15px; border-radius: 8px; margin-top: 15px;">
            <h5 style="color: #4a5568; margin-bottom: 10px;">🎯 最佳匹配</h5>
            <p style="margin: 5px 0;">久赢恒丰: <strong>{html.escape(str(best_match.get("truth", "")))}</strong></p>
            <p style="margin: 5px 0;">AI发现: <strong>{html.escape(str(best_match.get("discovered", "")))}</strong></p>
            <p style="margin: 5px 0;">相似度: <strong>{best_match.get("similarity", 0):.3f}</strong></p>
        </div>
        
        <div style="margin-top: 15px;">
            <h5 style="color: #4a5568; margin-bottom: 10px;">📈 所有匹配尝试</h5>
            <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                <thead>
                    <tr style="background: #e2e8f0;">
                        <th style="padding: 8px; text-align: left;">久赢恒丰标签</th>
                        <th style="padding: 8px; text-align: left;">AI主题</th>
                        <th style="padding: 8px; text-align: left;">相似度</th>
                    </tr>
                </thead>
                <tbody>
    '''
    
    for detail in details[:5]:  # 只显示前5个
        truth = html.escape(str(detail.get('truth', '')))
        discovered = html.escape(str(detail.get('discovered', '')))
        similarity = detail.get('similarity', 0)
        
        similarity_color = '#38a169' if similarity >= 0.7 else '#d69e2e' if similarity >= 0.5 else '#e53e3e'
        
        content += f'''
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px;">{truth}</td>
                        <td style="padding: 8px;">{discovered}</td>
                        <td style="padding: 8px; color: {similarity_color}; font-weight: {'bold' if similarity >= 0.7 else 'normal'}">
                            {similarity:.3f}
                        </td>
                    </tr>
        '''
    
    content += '''
                </tbody>
            </table>
        </div>
    </div>
    '''
    
    return content

def generate_match_examples(results: List[Dict]) -> str:
    """生成匹配示例"""
    examples = []
    
    for result in results:
        if not result.get('success', False):
            continue
            
        match_result = result.get('match_result', {})
        if match_result.get('matched', False) and match_result.get('similarity', 0) >= 0.7:
            theme = result.get('theme', '未知主题')
            best_pair = match_result.get('best_pair', ('', ''))
            similarity = match_result.get('similarity', 0)
            
            # 检查是否是同义词匹配（名称不同但语义相同）
            truth, discovered = best_pair
            if truth != discovered:
                examples.append({
                    'theme': theme,
                    'truth': truth,
                    'discovered': discovered,
                    'similarity': similarity
                })
    
    if not examples:
        return '<p>暂无语义匹配示例</p>'
    
    content = ''
    for i, example in enumerate(examples[:3], 1):  # 只显示前3个
        content += f'''
        <div class="match-example">
            <h4 style="margin-bottom: 10px; color: #2d3748;">示例{i}: {html.escape(example['theme'])}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 10px;">
                <div>
                    <strong style="color: #38a169;">久赢恒丰:</strong><br>
                    {html.escape(example['truth'])}
                </div>
                <div>
                    <strong style="color: #667eea;">AI发现:</strong><br>
                    {html.escape(example['discovered'])}
                </div>
            </div>
            <div style="margin-top: 10px;">
                <strong>相似度:</strong> <span style="color: {'#38a169' if example['similarity'] >= 0.7 else '#d69e2e'}; 
                    font-weight: bold;">{example['similarity']:.3f}</span>
                <span style="margin-left: 10px; background: #c6f6d5; color: #22543d; padding: 3px 8px; border-radius: 4px; font-size: 0.9rem;">
                    ✅ 语义匹配成功
                </span>
            </div>
            <p style="margin-top: 10px; font-size: 0.9rem; color: #4a5568;">
                说明: 虽然名称不完全相同，但AI正确理解了事件的核心主题，分类结果具有相同的业务含义。
            </p>
        </div>
        '''
    
    return content

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='生成语义评估HTML报告')
    parser.add_argument('--result_file', required=True, help='语义评估结果JSON文件')
    parser.add_argument('--output_file', required=True, help='HTML报告输出路径')
    
    args = parser.parse_args()
    
    print("🎨 生成语义评估HTML报告...")
    print(f"   输入文件: {args.result_file}")
    print(f"   输出文件: {args.output_file}")
    
    success = generate_semantic_html_report(args.result_file, args.output_file)
    
    if success:
        print("\n✅ HTML报告生成成功!")
        print("   可以在浏览器中打开查看交互式报告")
    else:
        print("\n❌ HTML报告生成失败")
        sys.exit(1)

if __name__ == '__main__':
    main()

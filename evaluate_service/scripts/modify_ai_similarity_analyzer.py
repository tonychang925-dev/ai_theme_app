#!/usr/bin/env python3
"""
修改ai_similarity_analyzer.py以使用完整内容
位置: evaluate_service/scripts/modify_ai_similarity_analyzer.py
"""
import sys
import re
from pathlib import Path

# 设置项目路径
EVALUATE_DIR = Path(__file__).parent.parent.absolute()
PROJECT_ROOT = EVALUATE_DIR.parent.absolute()

print("="*60)
print("🔧 修改 ai_similarity_analyzer.py 完整内容分析")
print("="*60)

# 定位文件
analyzer_file = PROJECT_ROOT / "theme_service" / "ai_similarity_analyzer.py"

if not analyzer_file.exists():
    print(f"❌ 文件不存在: {analyzer_file}")
    sys.exit(1)

print(f"修改文件: {analyzer_file}")

# 备份原文件
import shutil
backup_file = analyzer_file.with_suffix('.py.bak')
shutil.copy2(analyzer_file, backup_file)
print(f"✅ 已备份到: {backup_file}")

# 读取文件内容
with open(analyzer_file, 'r', encoding='utf-8') as f:
    content = f.read()

print("🔍 分析当前文件结构...")

# 查找关键方法
methods_to_check = [
    '_format_event_for_ai',
    '_build_enhanced_prompt',
    'analyze_similarity'
]

found_methods = []
for method in methods_to_check:
    pattern = rf'def {method}\s*\([^)]*\)\s*:'
    if re.search(pattern, content):
        found_methods.append(method)
        print(f"✅ 找到 {method} 方法")

if not found_methods:
    print("❌ 未找到关键方法，可能需要手动修改")
    sys.exit(1)

# 修改 _format_event_for_ai 方法（如果存在）
if '_format_event_for_ai' in found_methods:
    print("\n🔧 修改 _format_event_for_ai 方法...")
    
    method_pattern = r'def _format_event_for_ai\s*\([^)]*\)\s*:.*?(?=\n\s*def|\n\s*async|\Z)'
    match = re.search(method_pattern, content, re.DOTALL)
    
    if match:
        old_method = match.group(0)
        
        # 创建新的方法实现
        new_method = '''def _format_event_for_ai(self, event_data: Dict[str, Any]) -> str:
    """格式化事件信息供AI分析（优先使用完整内容）"""
    lines = []
    
    lines.append(f"事件ID: {event_data.get('id', 'unknown')}")
    lines.append(f"标题: {event_data.get('title', '无标题')}")
    
    # 🚀 关键修复：优先使用完整内容
    # 1. 首先尝试从original_data获取完整内容
    full_content = None
    
    if 'original_data' in event_data:
        original_data = event_data['original_data']
        if 'content' in original_data and original_data['content']:
            full_content = original_data['content']
            lines.append(f"完整内容: {full_content}")
        elif 'content_preview' in original_data and original_data['content_preview']:
            full_content = original_data['content_preview']
            lines.append(f"内容预览: {full_content}")
    
    # 2. 如果没有完整内容，使用AI摘要
    if not full_content:
        summary = event_data.get('summary', '无摘要')
        lines.append(f"摘要: {summary}")
        self.logger.warning(f"事件 {event_data.get('id', 'unknown')} 缺少完整内容，只有摘要")
    else:
        # 3. 如果有完整内容，也显示AI摘要作为参考
        summary = event_data.get('summary', '')
        if summary:
            lines.append(f"AI判断摘要（参考）: {summary}")
    
    # 其他信息...
    lines.append(f"事件类型: {event_data.get('event_type', '未知')}")
    
    impact_industries = event_data.get('impact_industries', [])
    if impact_industries:
        lines.append(f"影响行业: {', '.join(impact_industries)}")
    
    lines.append(f"方向: {event_data.get('direction', '中性')}")
    lines.append(f"置信度: {event_data.get('confidence', 0.5)}")
    
    theme_directive = event_data.get('theme_directive', {})
    if theme_directive:
        lines.append(f"主题指令: {theme_directive.get('action', '未知')}")
        reason = theme_directive.get('reason', '')
        if reason:
            lines.append(f"指令理由: {reason}")
    
    return "\\n".join(lines)'''
        
        # 替换方法
        content = content.replace(old_method, new_method)
        print("✅ _format_event_for_ai 方法已修改为优先使用完整内容")
    else:
        print("❌ 无法找到 _format_event_for_ai 方法的具体实现")

# 修改提示词中的说明
print("\n🔧 修改提示词说明...")
if "请基于事件的完整内容进行分析" not in content:
    # 在提示词中添加强调
    prompt_pattern = r'(def _build_enhanced_prompt\s*\([^)]*\)\s*:.*?return.*?f""".*?""")'
    match = re.search(prompt_pattern, content, re.DOTALL)
    
    if match:
        old_prompt = match.group(0)
        # 在提示词开头添加强调
        new_prompt = old_prompt.replace('f"""', 'f"""\n# 🎯 重要：请基于事件的完整内容进行分析，不要只看摘要\n\n')
        content = content.replace(old_prompt, new_prompt)
        print("✅ 已在提示词中添加完整内容分析要求")
    else:
        print("⚠️  未找到提示词部分，可能需要手动添加")

# 写回文件
with open(analyzer_file, 'w', encoding='utf-8') as f:
    f.write(new_content if 'new_content' in locals() else content)

print("\n✅ ai_similarity_analyzer.py 已修改为优先使用完整内容")
print("\n🔍 修改要点:")
print("  1. 🚀 _format_event_for_ai 方法优先使用 original_data.content")
print("  2. 📊 提示词强调基于完整内容分析")
print("  3. 🔍 保持AI判断摘要作为参考")

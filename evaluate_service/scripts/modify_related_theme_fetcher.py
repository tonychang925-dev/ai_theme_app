#!/usr/bin/env python3
"""
修改related_theme_fetcher.py的数据增强逻辑
位置: evaluate_service/scripts/modify_related_theme_fetcher.py
"""
import sys
import re
from pathlib import Path

# 设置项目路径
EVALUATE_DIR = Path(__file__).parent.parent.absolute()
PROJECT_ROOT = EVALUATE_DIR.parent.absolute()

print("="*60)
print("🔧 修改 related_theme_fetcher.py 数据增强逻辑")
print("="*60)

# 定位文件
fetcher_file = PROJECT_ROOT / "theme_service" / "related_theme_fetcher.py"

if not fetcher_file.exists():
    print(f"❌ 文件不存在: {fetcher_file}")
    sys.exit(1)

print(f"修改文件: {fetcher_file}")

# 备份原文件
import shutil
backup_file = fetcher_file.with_suffix('.py.bak')
shutil.copy2(fetcher_file, backup_file)
print(f"✅ 已备份到: {backup_file}")

# 读取文件内容
with open(fetcher_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 查找 _enhance_event_data 方法
import re
method_pattern = r'def _enhance_event_data\s*\([^)]*\)\s*:.*?(?=\n\s*def|\n\s*async|\Z)'
match = re.search(method_pattern, content, re.DOTALL)

if not match:
    print("❌ 未找到 _enhance_event_data 方法")
    print("建议手动添加数据增强逻辑")
    sys.exit(1)

old_method = match.group(0)
print(f"找到 _enhance_event_data 方法，长度: {len(old_method)} 字符")

# 创建新的方法实现
new_method = '''def _enhance_event_data(self, event_data: Dict) -> Dict:
    """
    增强事件数据
    🚀 修复：优先使用最完整的内容进行主题分析
    """
    enhanced = event_data.copy()
    
    # 获取当前摘要（可能是AI生成的判断摘要）
    current_summary = event_data.get('summary', '')
    best_content = current_summary
    
    # 🚀 关键修复：建立内容获取优先级
    content_sources = []
    
    # 优先级1：original_data.content（最完整）
    if 'original_data' in event_data:
        od = event_data['original_data']
        if 'content' in od and od['content']:
            content_sources.append(('original_data.content', od['content']))
    
    # 优先级2：original_data.content_preview
    if 'original_data' in event_data:
        od = event_data['original_data']
        if 'content_preview' in od and od['content_preview']:
            content_sources.append(('original_data.content_preview', od['content_preview']))
    
    # 优先级3：full_summary字段
    if 'full_summary' in event_data and event_data['full_summary']:
        content_sources.append(('full_summary', event_data['full_summary']))
    
    # 🚀 选择最长的内容（用于主题分析）
    for source_name, content in content_sources:
        if content and len(content) > len(best_content):
            best_content = content
            self.logger.info(f"🚀 使用{source_name}增强事件 {event_data.get('id', 'unknown')}: "
                           f"{len(current_summary)} -> {len(content)}字符")
    
    # 更新summary字段（用于主题分析）
    if best_content != current_summary:
        enhanced['summary'] = best_content
        enhanced['full_summary'] = best_content  # 明确标记完整内容
        enhanced['data_enhanced'] = True
        enhanced['original_summary'] = current_summary  # 保存原始判断摘要
    else:
        enhanced['data_enhanced'] = False
    
    # 添加数据完整性信息
    enhanced['data_integrity'] = {
        'has_original_data': 'original_data' in event_data,
        'has_full_content': enhanced.get('data_enhanced', False),
        'summary_length': len(enhanced.get('summary', '')),
        'original_summary_length': len(current_summary)
    }
    
    return enhanced'''

# 替换方法
new_content = content.replace(old_method, new_method)

# 写回文件
with open(fetcher_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ related_theme_fetcher.py 数据增强逻辑已修复")
print("\n🔍 修改要点:")
print("  1. 🚀 建立内容获取优先级: original_data.content > original_data.content_preview > full_summary")
print("  2. 📊 选择最长的内容用于主题分析")
print("  3. 🔍 添加数据完整性标记")
print("  4. 💾 保存原始判断摘要供参考")

# 验证修改
print("\n🔍 验证修改:")
with open(fetcher_file, 'r', encoding='utf-8') as f:
    modified = f.read()

if "original_data.content" in modified and "content_sources" in modified:
    print("✅ 成功添加内容优先级逻辑")
else:
    print("❌ 修改可能未生效")

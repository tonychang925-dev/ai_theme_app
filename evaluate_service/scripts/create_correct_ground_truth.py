# evaluate_service/scripts/create_correct_ground_truth.py
#!/usr/bin/env python3
"""
创建正确的地面真值映射
"""
import json
from pathlib import Path

# 项目根目录
project_root = Path(__file__).parent.parent.parent

def create_ground_truth():
    """创建地面真值映射"""
    print("🔧 创建正确的地面真值映射...")
    
    # 1. 加载测试数据
    data_path = project_root / 'evaluate_service' / 'data' / 'processed' / 'validation_events_enhanced.json'
    
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    events = data['events']
    
    # 2. 从original_data中提取theme信息
    ground_truth = {}
    
    for i, event in enumerate(events):
        news_id = event.get('news_id', f'news_{i:03d}')
        
        # 从original_data中提取theme
        original_data = event.get('original_data', {})
        theme = original_data.get('theme', '未知主题')
        
        ground_truth[news_id] = theme
    
    # 3. 保存映射
    output_path = project_root / 'evaluate_service' / 'config' / 'ground_truth_correct.json'
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ground_truth, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 地面真值映射已创建!")
    print(f"   映射数量: {len(ground_truth)}")
    print(f"   保存路径: {output_path}")
    
    # 4. 显示样本
    print("\n📋 映射样本:")
    for i, (news_id, theme) in enumerate(list(ground_truth.items())[:10]):
        print(f"  {i+1:2d}. {news_id:15s} → {theme}")
    
    return ground_truth


def update_ground_truth_evaluator():
    """更新地面真值评估器"""
    print("\n🔧 更新地面真值评估器...")
    
    evaluator_path = project_root / 'evaluate_service' / 'core' / 'ground_truth_evaluator.py'
    
    with open(evaluator_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 更新默认路径
    old_path = "'ground_truth_mapping.json'"
    new_path = "'ground_truth_correct.json'"
    
    if old_path in content:
        content = content.replace(old_path, new_path)
        
        with open(evaluator_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 地面真值评估器已更新!")
    else:
        print("⚠️  未找到路径配置，可能需要手动更新")


def main():
    """主函数"""
    print("🎯 创建正确的地面真值系统")
    print("=" * 60)
    
    # 创建正确的映射
    ground_truth = create_ground_truth()
    
    # 更新评估器
    update_ground_truth_evaluator()
    
    print("\n" + "=" * 60)
    print("🎉 地面真值系统更新完成!")
    
    # 统计数据
    theme_counts = {}
    for theme in ground_truth.values():
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
    
    print("\n📊 主题分布:")
    for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {theme:15s}: {count:2d} 个事件")


if __name__ == "__main__":
    main()
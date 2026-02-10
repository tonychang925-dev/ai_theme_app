"""
最终修复 tags 参数问题 - 使用 json.dumps()
"""
import os

def fix_postgres_manager():
    filepath = "managers/postgres_manager.py"
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # 备份原文件
    backup = filepath + ".backup_original"
    with open(backup, 'w') as f:
        f.write(content)
    print(f"✅ 已备份原文件: {backup}")
    
    # 修复 create_theme 方法
    old_create = '''            # 处理tags字段
            tags_data = kwargs.get('tags', {})
            if isinstance(tags_data, ThemeTags):
                tags_data = tags_data.to_dict()
            
            # 插入新主题'''
    
    new_create = '''            # 处理tags字段
            tags_data = kwargs.get('tags', {})
            if isinstance(tags_data, ThemeTags):
                tags_data = tags_data.to_dict()
            
            # 关键修复：将字典转换为JSON字符串（解决asyncpg jsonb参数问题）
            if isinstance(tags_data, dict):
                import json
                tags_data = json.dumps(tags_data, ensure_ascii=False)
            
            # 插入新主题'''
    
    # 修复 batch_create_themes 方法
    old_batch = '''                        # 处理tags字段
                        tags_data = data.get('tags', {})
                        if isinstance(tags_data, ThemeTags):
                            tags_data = tags_data.to_dict()
                        
                        row = await conn.fetchrow('''
    
    new_batch = '''                        # 处理tags字段
                        tags_data = data.get('tags', {})
                        if isinstance(tags_data, ThemeTags):
                            tags_data = tags_data.to_dict()
                        
                        # 关键修复：将字典转换为JSON字符串（解决asyncpg jsonb参数问题）
                        if isinstance(tags_data, dict):
                            import json
                            tags_data = json.dumps(tags_data, ensure_ascii=False)
                        
                        row = await conn.fetchrow('''
    
    # 修复 update_theme 方法
    old_update = '''                for key, value in updates.items():
                    if key == 'tags' and isinstance(value, ThemeTags):
                        value = value.to_dict()
                    
                    set_clauses.append(f"{key} = ${index}")
                    values.append(value)
                    index += 1'''
    
    new_update = '''                for key, value in updates.items():
                    if key == 'tags' and isinstance(value, ThemeTags):
                        value = value.to_dict()
                    
                    # 关键修复：如果更新tags字段，将字典转换为JSON字符串
                    if key == 'tags' and isinstance(value, dict):
                        import json
                        value = json.dumps(value, ensure_ascii=False)
                    
                    set_clauses.append(f"{key} = ${index}")
                    values.append(value)
                    index += 1'''
    
    # 应用所有修复
    if old_create in content:
        content = content.replace(old_create, new_create)
        print("✅ 已修复 create_theme 方法")
    else:
        print("⚠️  未找到 create_theme 方法的待修复代码")
    
    if old_batch in content:
        content = content.replace(old_batch, new_batch)
        print("✅ 已修复 batch_create_themes 方法")
    else:
        print("⚠️  未找到 batch_create_themes 方法的待修复代码")
    
    if old_update in content:
        content = content.replace(old_update, new_update)
        print("✅ 已修复 update_theme 方法")
    else:
        print("⚠️  未找到 update_theme 方法的待修复代码")
    
    # 写回文件
    with open(filepath, 'w') as f:
        f.write(content)
    
    print("🎉 所有修复已完成！")
    return True

if __name__ == "__main__":
    print("🔧 开始修复 postgres_manager.py 中的 tags 参数问题")
    print("=" * 60)
    fix_postgres_manager()

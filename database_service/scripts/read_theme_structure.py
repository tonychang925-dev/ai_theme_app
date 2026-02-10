# scripts/read_theme_structure.py
#!/usr/bin/env python3
"""
读取当前theme_master表结构
"""
import asyncpg
import asyncio
import json
from typing import Dict, Any
from datetime import datetime


async def get_theme_master_structure():
    """获取theme_master表结构"""
    # 你的数据库连接信息
    connection_info = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    
    conn = None
    try:
        # 连接数据库
        print("🔍 连接数据库...")
        conn = await asyncpg.connect(**connection_info)
        
        # 1. 获取表结构
        print("\n📊 表结构信息:")
        print("=" * 60)
        
        columns = await conn.fetch("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'theme_master'
            ORDER BY ordinal_position
        """)
        
        print(f"theme_master表共有 {len(columns)} 列:")
        for col in columns:
            print(f"  {col['column_name']:30} {col['data_type']:20} "
                  f"{'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")
            
            if col['column_default']:
                print(f"    默认值: {col['column_default']}")
        
        # 2. 获取示例数据（了解实际数据类型）
        print("\n📋 示例数据（前3行）:")
        print("=" * 60)
        
        rows = await conn.fetch("SELECT * FROM theme_master LIMIT 3")
        
        for i, row in enumerate(rows, 1):
            print(f"\n第 {i} 行:")
            for key in row.keys():
                value = row[key]
                if value is None:
                    value_str = "NULL"
                elif isinstance(value, (dict, list)):
                    value_str = json.dumps(value, ensure_ascii=False)[:50] + "..."
                else:
                    value_str = str(value)[:50]
                
                print(f"  {key:30}: {value_str}")
        
        # 3. 获取索引信息
        print("\n🔍 索引信息:")
        print("=" * 60)
        
        indexes = await conn.fetch("""
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = 'theme_master'
            ORDER BY indexname
        """)
        
        if indexes:
            for idx in indexes:
                print(f"  {idx['indexname']}")
                print(f"    {idx['indexdef']}")
        else:
            print("  无索引")
        
        # 4. 获取约束信息
        print("\n🔒 约束信息:")
        print("=" * 60)
        
        constraints = await conn.fetch("""
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                ccu.column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.table_schema = 'public'
            AND tc.table_name = 'theme_master'
            ORDER BY tc.constraint_type, tc.constraint_name
        """)
        
        if constraints:
            for cons in constraints:
                print(f"  {cons['constraint_name']}: {cons['constraint_type']} "
                      f"({cons['column_name']})")
        else:
            print("  无约束")
        
        # 5. 统计信息
        print("\n📈 统计信息:")
        print("=" * 60)
        
        count = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
        print(f"  总记录数: {count}")
        
        # 获取不同状态的数量
        status_counts = await conn.fetch("""
            SELECT lifecycle_stage, COUNT(*) as count
            FROM theme_master
            GROUP BY lifecycle_stage
            ORDER BY count DESC
        """)
        
        if status_counts:
            print("  生命周期分布:")
            for stat in status_counts:
                print(f"    {stat['lifecycle_stage']}: {stat['count']}")
        
        # 6. 获取JSON字段结构
        print("\n📄 JSON字段结构分析:")
        print("=" * 60)
        
        # 检查是否有JSON/JSONB字段
        json_columns = [col for col in columns 
                       if col['data_type'] in ('json', 'jsonb')]
        
        if json_columns:
            for col in json_columns:
                print(f"\n  分析字段: {col['column_name']}")
                
                # 获取非NULL的JSON示例
                json_samples = await conn.fetch(f"""
                    SELECT {col['column_name']}
                    FROM theme_master
                    WHERE {col['column_name']} IS NOT NULL
                    LIMIT 3
                """)
                
                for j, sample in enumerate(json_samples, 1):
                    json_data = sample[col['column_name']]
                    if json_data:
                        print(f"    示例{j}:")
                        if isinstance(json_data, dict):
                            for key, value in list(json_data.items())[:5]:
                                value_type = type(value).__name__
                                value_preview = str(value)[:30] + "..." if len(str(value)) > 30 else str(value)
                                print(f"      {key}: {value_preview} ({value_type})")
                        else:
                            print(f"      {json_data}")
        
        # 7. 生成建议的Python数据模型
        print("\n💡 建议的Python数据模型:")
        print("=" * 60)
        
        generate_python_model(columns, rows)
        
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False
    
    finally:
        if conn:
            await conn.close()


def generate_python_model(columns, rows):
    """生成Python数据模型建议"""
    
    print("""
# database_service/interface.py
\"\"\"
数据库接口定义 - 基于实际theme_master表结构
\"\"\"
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
""")
    
    # 分析字段类型
    field_definitions = []
    
    for col in columns:
        field_name = col['column_name']
        data_type = col['data_type']
        nullable = col['is_nullable'] == 'YES'
        
        # 映射PostgreSQL类型到Python类型
        type_mapping = {
            'integer': 'int',
            'bigint': 'int',
            'text': 'str',
            'character varying': 'str',
            'boolean': 'bool',
            'timestamp without time zone': 'datetime',
            'timestamp with time zone': 'datetime',
            'numeric': 'float',
            'real': 'float',
            'double precision': 'float',
            'jsonb': 'Dict[str, Any]',
            'json': 'Dict[str, Any]',
            'ARRAY': 'List[str]'
        }
        
        python_type = type_mapping.get(data_type, 'Any')
        
        # 处理数组类型
        if '[]' in data_type:
            if 'text' in data_type or 'character varying' in data_type:
                python_type = 'List[str]'
            elif 'integer' in data_type:
                python_type = 'List[int]'
            else:
                python_type = 'List[Any]'
        
        # 添加Optional如果可为空
        if nullable and python_type != 'Any':
            python_type = f'Optional[{python_type}]'
        
        # 获取示例值用于设置默认值
        default_value = None
        if rows and len(rows) > 0:
            example_value = rows[0].get(field_name)
            if example_value is not None:
                if python_type == 'str':
                    default_value = f'"{example_value}"' if len(str(example_value)) < 20 else '""'
                elif python_type == 'int':
                    default_value = str(example_value)
                elif python_type == 'bool':
                    default_value = str(example_value).lower()
        
        # 构建字段定义
        if default_value:
            field_def = f'    {field_name}: {python_type} = {default_value}'
        elif nullable:
            field_def = f'    {field_name}: {python_type} = None'
        else:
            field_def = f'    {field_name}: {python_type}'
        
        field_definitions.append(field_def)
    
    print("@dataclass")
    print("class ThemeRecord:")
    print('    """主题记录 - 基于实际数据库表结构"""')
    print()
    
    for field_def in field_definitions:
        print(field_def)
    
    print()
    print("    def to_dict(self) -> Dict[str, Any]:")
    print('        """转换为字典"""')
    print("        return {")
    
    for col in columns:
        field_name = col['column_name']
        print(f"            '{field_name}': self.{field_name},")
    
    print("        }")
    
    print()
    print("# 其他必要的类...")
    print("@dataclass")
    print("class EventThemeRelation:")
    print('    """事件-主题关联记录"""')
    print("    id: int")
    print("    event_id: int")
    print("    theme_id: int")
    print("    confidence: float = 0.0")
    print("    confidence_level: str = 'medium'")
    print("    confidence_weight: int = 50")
    print("    evidence: Optional[str] = None")
    print("    created_at: Optional[datetime] = None")


async def main():
    """主函数"""
    print("🎯 读取theme_master表结构")
    print("=" * 60)
    
    success = await get_theme_master_structure()
    
    if success:
        print("\n✅ 表结构读取完成")
        print("\n📋 下一步:")
        print("  1. 查看上面的表结构信息")
        print("  2. 根据实际结构编写interface.py")
        print("  3. 调整其他manager的实现")
    else:
        print("\n❌ 表结构读取失败")


if __name__ == "__main__":
    asyncio.run(main())
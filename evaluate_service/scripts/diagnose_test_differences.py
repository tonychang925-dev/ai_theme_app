# evaluate_service/scripts/diagnose_test_differences.py
"""
诊断手动测试与自动测试的差异
"""
#!/usr/bin/env python3
import ast
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def analyze_file_differences():
    """分析两个测试文件的差异"""
    
    files = {
        'manual': project_root / "evaluate_service" / "runners" / "test_data_integrity.py",
        'auto': project_root / "evaluate_service" / "runners" / "run_76_dataset_real_ai.py"
    }
    
    differences = []
    
    for name, filepath in files.items():
        print(f"\n📁 分析 {name} 测试文件: {filepath}")
        
        if not filepath.exists():
            print(f"   ❌ 文件不存在")
            continue
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取关键代码段
        imports = []
        db_initializations = []
        theme_fetcher_usage = []
        
        try:
            tree = ast.parse(content)
            
            # 提取导入语句
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.extend([f"{module}.{alias.name}" for alias in node.names])
                
                # 查找数据库初始化
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['MemoryDatabaseManager', 'PureDataFetcher']:
                            db_initializations.append(ast.unparse(node))
                
                # 查找主题获取器使用
                if isinstance(node, ast.Await):
                    if isinstance(node.value, ast.Call):
                        call_expr = ast.unparse(node.value)
                        if 'fetch_relevant_themes' in call_expr:
                            theme_fetcher_usage.append(call_expr)
        
        except Exception as e:
            print(f"   ⚠️  解析失败: {e}")
            continue
        
        print(f"   导入的模块: {imports[:5]}{'...' if len(imports) > 5 else ''}")
        print(f"   数据库初始化: {db_initializations[:3]}")
        print(f"   主题获取器调用: {theme_fetcher_usage[:3]}")
    
    # 分析核心差异
    print("\n🔍 核心差异分析:")
    
    manual_file = files['manual']
    auto_file = files['auto']
    
    if manual_file.exists() and auto_file.exists():
        with open(manual_file, 'r', encoding='utf-8') as f:
            manual_content = f.read()
        
        with open(auto_file, 'r', encoding='utf-8') as f:
            auto_content = f.read()
        
        # 检查关键差异
        checks = [
            ("数据库管理器类型", "MemoryDatabaseManager" in manual_content, "MemoryDatabaseManager" in auto_content),
            ("数据获取器使用", "PureDataFetcher" in manual_content, "PureDataFetcher" in auto_content),
            ("主题获取器初始化", "RelatedThemeFetcher(" in manual_content, "RelatedThemeFetcher(" in auto_content),
            ("fetch_relevant_themes调用", "fetch_relevant_themes" in manual_content, "fetch_relevant_themes" in auto_content),
            ("EnhancedThemeDiscovery使用", "EnhancedThemeDiscovery" in manual_content, "EnhancedThemeDiscovery" in auto_content),
        ]
        
        for check_name, in_manual, in_auto in checks:
            status = "✅ 一致" if in_manual == in_auto else "⚠️  不一致"
            print(f"   {check_name:20} 手动: {in_manual} | 自动: {in_auto} | {status}")

if __name__ == "__main__":
    print("🔍 诊断测试文件差异")
    print("="*60)
    analyze_file_differences()
import sys
import os

print("📁 当前工作目录:", os.getcwd())
print("🐍 Python路径:")
for p in sys.path[:10]:
    print(f"  {p}")

print("\n🔍 查找deepseek_parser模块...")

# 尝试不同方式导入
try:
    # 方式1：直接导入
    from model_service.llm_parser.deepseek_parser_0203 import DeepSeekParser
    print("✅ 方式1成功: 直接导入")
except ImportError as e:
    print(f"❌ 方式1失败: {e}")

try:
    # 方式2：添加路径后导入
    sys.path.insert(0, os.path.join(os.getcwd(), 'model_service/llm_parser'))
    from deepseek_parser import DeepSeekParser
    print("✅ 方式2成功: 添加路径后导入")
except ImportError as e:
    print(f"❌ 方式2失败: {e}")

try:
    # 方式3：检查文件是否存在
    parser_path = "model_service/llm_parser/deepseek_parser.py"
    if os.path.exists(parser_path):
        print(f"✅ 文件存在: {parser_path}")
        print(f"   文件大小: {os.path.getsize(parser_path)} 字节")
    else:
        print(f"❌ 文件不存在: {parser_path}")
except Exception as e:
    print(f"❌ 检查文件失败: {e}")

# 检查目录结构
print("\n📂 model_service/llm_parser 目录内容:")
llm_dir = "model_service/llm_parser"
if os.path.exists(llm_dir):
    for item in os.listdir(llm_dir):
        full_path = os.path.join(llm_dir, item)
        if os.path.isfile(full_path):
            print(f"  📄 {item}")
        else:
            print(f"  📁 {item}")
else:
    print(f"❌ 目录不存在: {llm_dir}")

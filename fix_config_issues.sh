#!/bin/bash
# fix_config_issues.sh - 修复配置和导入问题
echo "🔧 修复 theme_service 配置问题"
echo "=============================="

# 备份原文件
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "1. 备份原文件..."
cp theme_service/config.py "$BACKUP_DIR/config.py.backup" 2>/dev/null || true
cp theme_service/database.py "$BACKUP_DIR/database.py.backup" 2>/dev/null || true

echo "✅ 备份完成到: $BACKUP_DIR"

# 修复 config.py
echo ""
echo "2. 修复 config.py..."
cat > theme_service/config.py << 'FILEEOF'
"""
theme_service 配置
修复导入问题 - 确保 DATABASE_URL 可访问
"""
from pydantic_settings import BaseSettings
from functools import lru_cache

class ThemeServiceSettings(BaseSettings):
    """主题服务配置"""
    
    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    # 集成模式
    INTEGRATION_MODE: str = "direct"
    
    # 题材发现配置
    THEME_DISCOVERY_ENABLED: bool = True
    MIN_EVENTS_FOR_THEME: int = 2
    THEME_CONFIDENCE_THRESHOLD: float = 0.6
    
    # AI配置
    DEEPSEEK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    
    class Config:
        env_file = ".env.theme"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> ThemeServiceSettings:
    """获取配置实例（缓存）"""
    return ThemeServiceSettings()

# 创建全局settings实例
settings = get_settings()

# 导出 DATABASE_URL 以兼容旧代码
DATABASE_URL = settings.DATABASE_URL
FILEEOF

echo "✅ config.py 修复完成"

# 修复 database.py 导入
echo ""
echo "3. 修复 database.py 导入..."
if [ -f "theme_service/database.py" ]; then
    # 替换导入语句
    sed -i '' 's/from theme_service.config import DATABASE_URL/from theme_service.config import settings/g' theme_service/database.py 2>/dev/null || \
    sed -i 's/from theme_service.config import DATABASE_URL/from theme_service.config import settings/g' theme_service/database.py
    
    # 替换 DATABASE_URL 使用
    sed -i '' 's/DATABASE_URL/settings.DATABASE_URL/g' theme_service/database.py 2>/dev/null || \
    sed -i 's/DATABASE_URL/settings.DATABASE_URL/g' theme_service/database.py
    
    echo "✅ database.py 导入修复完成"
else
    echo "⚠️  database.py 不存在，跳过修复"
fi

# 修复其他模块的导入
echo ""
echo "4. 修复其他模块导入..."
for file in theme_service/services/theme_mapper.py theme_service/app.py; do
    if [ -f "$file" ]; then
        echo "   修复 $file..."
        sed -i '' 's/from theme_service.config import DATABASE_URL/from theme_service.config import settings/g' "$file" 2>/dev/null || \
        sed -i 's/from theme_service.config import DATABASE_URL/from theme_service.config import settings/g' "$file"
        
        sed -i '' 's/DATABASE_URL/settings.DATABASE_URL/g' "$file" 2>/dev/null || \
        sed -i 's/DATABASE_URL/settings.DATABASE_URL/g' "$file"
    fi
done

echo "✅ 其他模块导入修复完成"

# 修复 AI 客户端导入问题
echo ""
echo "5. 修复 AI 客户端 deepseek_parser 导入..."
echo "   查看当前 llm_parser 结构:"
ls -la model_service/llm_parser/ | grep -E "\.py$"

# 检查 deepseek_parser 是否存在
if [ -f "model_service/llm_parser/deepseek_parser.py" ]; then
    echo "✅ deepseek_parser.py 存在"
    
    # 检查导入语句
    IMPORT_CHECK=$(grep -n "from deepseek_parser import" model_service/llm_parser/theme_analyzer.py 2>/dev/null || true)
    if [ -n "$IMPORT_CHECK" ]; then
        echo "⚠️  发现错误的导入语句，修复..."
        sed -i '' 's/from deepseek_parser import/from .deepseek_parser import/g' model_service/llm_parser/theme_analyzer.py 2>/dev/null || \
        sed -i 's/from deepseek_parser import/from .deepseek_parser import/g' model_service/llm_parser/theme_analyzer.py
        echo "✅ 导入路径修复完成"
    fi
else
    echo "❌ deepseek_parser.py 不存在"
    echo "   创建简化版本..."
    cat > model_service/llm_parser/deepseek_parser.py << 'PYEOF'
"""
简化版 DeepSeek 解析器 - 用于修复导入
"""
import os
from typing import Dict, Any, Optional
from .base_parser import BaseLLMParser

class DeepSeekParser(BaseLLMParser):
    """DeepSeek API解析器（简化版）"""
    
    def __init__(self, model_name: str = "deepseek-chat"):
        super().__init__(model_name)
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
    
    async def parse_content(self, content: str) -> Optional[Dict[str, Any]]:
        """解析内容"""
        return {"mock": "deepseek_parser", "content": content[:100]}
    
    async def parse_news(self, title: str, content: str) -> Optional[Dict[str, Any]]:
        """解析新闻"""
        return {
            "event_type": "mock",
            "summary": f"Mock: {title[:50]}"
        }
    
    async def close(self):
        """关闭"""
        pass
PYEOF
    echo "✅ 创建简化版 deepseek_parser.py"
fi

# 创建环境变量文件
echo ""
echo "6. 创建环境变量文件..."
cat > .env.theme << 'ENVEOF'
# theme_service 环境变量
# 数据库配置
DATABASE_URL=postgresql://postgres:zxbzj~925@localhost/stock_data

# AI配置
DEEPSEEK_API_KEY=your_deepseek_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# 服务配置
INTEGRATION_MODE=direct
PORT=8002
ENVEOF

echo "✅ 创建 .env.theme 文件"
echo "   请编辑此文件设置真实的API密钥"

# 测试修复结果
echo ""
echo "7. 测试修复结果..."
python -c "
import sys
sys.path.insert(0, '.')

print('🧪 测试修复后的导入...')

# 测试1: 配置导入
try:
    from theme_service.config import settings, DATABASE_URL
    print('✅ 1. config.py 导入成功')
    print(f'   数据库URL: {settings.DATABASE_URL}')
    print(f'   直接变量: {DATABASE_URL}')
except Exception as e:
    print(f'❌ 1. config.py 导入失败: {e}')

# 测试2: 数据库导入
try:
    from theme_service.database import ThemeDatabase
    print('✅ 2. database.py 导入成功')
except Exception as e:
    print(f'❌ 2. database.py 导入失败: {e}')

# 测试3: AI客户端
try:
    from theme_service.services.ai_client import AIThemeClient
    
    class MockConfig:
        INTEGRATION_MODE = 'direct'
    
    client = AIThemeClient(MockConfig())
    print('✅ 3. AI客户端导入成功')
except Exception as e:
    print(f'❌ 3. AI客户端导入失败: {e}')

print('\\n📊 修复测试完成')
"

echo ""
echo "🎉 修复完成！"
echo ""
echo "📋 下一步:"
echo "1. 编辑 .env.theme 文件设置API密钥（如果需要真实AI）"
echo "2. 运行测试: python test_full_integration.py"
echo "3. 启动服务: ./start_theme_service.sh"
echo ""
echo "🔧 如果还有问题，查看备份文件: $BACKUP_DIR"

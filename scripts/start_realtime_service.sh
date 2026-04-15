#!/bin/bash

# Redis Stream 实时推送服务启动脚本
# 启动Frontend BFF服务（包含实时推送功能）

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Redis Stream 实时推送服务启动脚本${NC}"
echo "=========================================="

# 检查Python环境
echo -e "\n${YELLOW}1. 检查Python环境${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}❌ 未找到Python，请安装Python 3.8+${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
echo "✅ Python版本: $PYTHON_VERSION"

# 检查虚拟环境
if [ -d ".venv" ]; then
    echo "📁 检测到虚拟环境 .venv"
    if [ -f ".venv/bin/activate" ]; then
        echo "🔄 激活虚拟环境"
        source .venv/bin/activate
    fi
fi

# 检查依赖
echo -e "\n${YELLOW}2. 检查依赖包${NC}"
REQUIRED_PACKAGES=("fastapi" "uvicorn" "redis" "websockets")
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if $PYTHON_CMD -c "import $pkg" 2>/dev/null; then
        echo "✅ $pkg 已安装"
    else
        echo -e "${RED}❌ $pkg 未安装${NC}"
        echo "   安装命令: pip install $pkg"
        read -p "   是否现在安装？ (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            pip install $pkg
        else
            echo -e "${RED}依赖缺失，服务可能无法启动${NC}"
        fi
    fi
done

# 检查Redis
echo -e "\n${YELLOW}3. 检查Redis服务${NC}"
REDIS_HOST="localhost"
REDIS_PORT="6379"

if command -v redis-cli &> /dev/null; then
    echo "✅ redis-cli 可用"

    # 测试Redis连接
    if redis-cli -h $REDIS_HOST -p $REDIS_PORT ping 2>/dev/null | grep -q "PONG"; then
        echo "✅ Redis连接成功 ($REDIS_HOST:$REDIS_PORT)"
    else
        echo -e "${YELLOW}⚠️  Redis连接失败 ($REDIS_HOST:$REDIS_PORT)${NC}"
        echo "   请确保Redis服务正在运行:"
        echo "   - macOS: brew services start redis"
        echo "   - Linux: sudo systemctl start redis"
        echo "   - Docker: docker run -d -p 6379:6379 redis:latest"
        read -p "   是否继续？ (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}⚠️  redis-cli 不可用${NC}"
    echo "   请确保Redis已安装"
    read -p "   是否继续？ (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查环境变量
echo -e "\n${YELLOW}4. 检查环境变量${NC}"
if [ -f ".env" ]; then
    echo "✅ 找到 .env 文件"
    # 检查REDIS_URL
    if grep -q "REDIS_URL" .env; then
        echo "✅ REDIS_URL 已配置"
    else
        echo -e "${YELLOW}⚠️  REDIS_URL 未配置，将使用默认值${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  未找到 .env 文件${NC}"
    echo "   创建示例 .env 文件..."
    cat > .env << EOF
ENABLED_SOURCES=["akshare_cls", "akshare_cctv"]
TUSHARE_TOKEN='your_tushare_token'

# Redis Stream 实时推送服务配置
REDIS_URL="redis://localhost:6379/0"
REALTIME_SERVICE_ENABLED=true
REALTIME_SERVICE_LOG_LEVEL="INFO"
EOF
    echo "✅ 已创建 .env 文件"
fi

# 检查frontend_bff目录
echo -e "\n${YELLOW}5. 检查服务代码${NC}"
if [ -d "frontend_bff" ]; then
    echo "✅ frontend_bff 目录存在"

    if [ -f "frontend_bff/app.py" ]; then
        echo "✅ app.py 文件存在"

        # 检查实时推送服务集成
        if grep -q "realtime_service" frontend_bff/app.py; then
            echo "✅ 实时推送服务已集成"
        else
            echo -e "${RED}❌ 实时推送服务未集成到app.py${NC}"
            echo "   请确保已完成实时推送服务的集成"
            exit 1
        fi
    else
        echo -e "${RED}❌ app.py 文件不存在${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ frontend_bff 目录不存在${NC}"
    exit 1
fi

# 启动服务
echo -e "\n${YELLOW}6. 启动服务${NC}"
echo "🚀 启动Frontend BFF服务（包含实时推送）"
echo "   服务地址: http://localhost:8000"
echo "   WebSocket: ws://localhost:8000/ws/realtime"
echo "   按 Ctrl+C 停止服务"
echo "------------------------------------------"

# 切换到frontend_bff目录
cd frontend_bff

# 设置环境变量
export PYTHONPATH="../:$PYTHONPATH"

# 启动uvicorn服务
echo -e "\n${GREEN}启动命令:${NC}"
echo "uvicorn app:app --host 0.0.0.0 --port 8000 --reload"
echo ""

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# 服务停止后的清理
echo -e "\n${YELLOW}服务已停止${NC}"
cd ..
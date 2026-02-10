#!/bin/bash
# 终极版一键启动脚本

echo "🚀 AI题材引擎 - 终极版启动"
echo "="*70

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数定义
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}➜ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }

# 1. 检查Python
print_info "检查Python环境..."
if ! python3 --version > /dev/null 2>&1; then
    print_error "Python3 未安装"
    exit 1
fi
print_success "Python版本: $(python3 --version | cut -d' ' -f2)"

# 2. 检查依赖
print_info "检查Python依赖..."
if ! python3 -c "import asyncpg" > /dev/null 2>&1; then
    print_warning "正在安装 asyncpg..."
    pip3 install asyncpg > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        print_error "asyncpg 安装失败"
        exit 1
    fi
    print_success "asyncpg 安装成功"
else
    print_success "asyncpg 已安装"
fi

# 3. 检查数据库
print_info "检查数据库连接..."
cd theme_service
python3 -c "
import asyncio
import asyncpg
try:
    from config import settings
    async def test_db():
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            print('${GREEN}✓ 数据库连接成功${NC}')
            events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
            themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
            print(f'   新闻事件: {events}')
            print(f'   投资主题: {themes}')
            await conn.close()
        except Exception as e:
            print(f'\${RED}✗ 数据库连接失败: {e}\${NC}')
    asyncio.run(test_db())
except ImportError as e:
    print(f'\${RED}✗ 配置导入失败: {e}\${NC}')
    print('请确保在项目根目录运行')
" 2>&1
cd ..

# 4. 启动主题服务
print_info "启动主题服务 (端口 8002)..."
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    print_warning "主题服务已在运行"
else
    cd theme_service
    nohup python3 -c "
import uvicorn
from app import app
uvicorn.run(app, host='0.0.0.0', port=8002, log_level='warning')
" > ../theme_service.log 2>&1 &
    THEME_PID=$!
    cd ..
    
    # 等待启动
    sleep 5
    
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        print_success "主题服务启动成功 (PID: $THEME_PID)"
        print_info "API地址: http://localhost:8002"
    else
        print_error "主题服务启动失败"
        echo "查看日志: tail -f theme_service.log"
        exit 1
    fi
fi

# 5. 启动数据处理器
print_info "启动数据处理器..."
if pgrep -f "fixed_processor.py" > /dev/null; then
    print_warning "数据处理器已在运行"
else
    cd theme_service
    nohup python3 fixed_processor.py > ../processor.log 2>&1 &
    PROCESSOR_PID=$!
    cd ..
    
    sleep 2
    
    if ps -p $PROCESSOR_PID > /dev/null 2>&1; then
        print_success "数据处理器启动成功 (PID: $PROCESSOR_PID)"
        print_info "处理日志: processor.log"
    else
        print_error "数据处理器启动失败"
        echo "查看日志: tail -f processor.log"
        exit 1
    fi
fi

# 6. 显示启动完成信息
echo ""
echo "="*70
echo -e "${GREEN}🎉 AI题材引擎系统启动完成！${NC}"
echo "="*70
echo ""
echo "📋 服务状态:"
echo -e "   ${GREEN}✓ 主题服务${NC}: http://localhost:8002"
echo -e "   ${GREEN}✓ 数据处理器${NC}: 运行中"
echo ""
echo "🔧 管理命令:"
echo "   查看监控:      ./simple_monitor.sh"
echo "   检查状态:      ./check_system.sh"
echo "   停止所有服务:  pkill -f 'python.*(uvicorn|fixed_processor)'"
echo ""
echo "📊 数据流已建立:"
echo "   model_service → 新闻事件 → 主题发现 → 主题映射 → API服务"
echo ""
echo -e "${YELLOW}⚠ 重要: 在新终端窗口运行监控命令查看实时处理${NC}"

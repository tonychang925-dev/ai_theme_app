#!/bin/bash

# AI主题分析应用 - 生产环境部署脚本
# 版本: 1.0
# 日期: 2026-04-17

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "命令 $1 未安装，请先安装"
        exit 1
    fi
}

# 显示部署标题
show_title() {
    echo "=========================================="
    echo "  AI主题分析应用 - 生产环境部署"
    echo "=========================================="
    echo ""
}

# 环境检查
check_environment() {
    log_info "开始环境检查..."

    # 检查Python
    check_command python3
    python_version=$(python3 --version | awk '{print $2}')
    log_info "Python版本: $python_version"

    # 检查pip
    check_command pip3
    pip_version=$(pip3 --version | awk '{print $2}')
    log_info "pip版本: $pip_version"

    # 检查Node.js (前端)
    if [ "$DEPLOY_FRONTEND" = "true" ]; then
        check_command node
        node_version=$(node --version)
        log_info "Node.js版本: $node_version"

        check_command npm
        npm_version=$(npm --version)
        log_info "npm版本: $npm_version"
    fi

    # 检查Docker (如果使用容器部署)
    if [ "$USE_DOCKER" = "true" ]; then
        check_command docker
        docker_version=$(docker --version | awk '{print $3}' | tr -d ',')
        log_info "Docker版本: $docker_version"

        check_command docker-compose
        docker_compose_version=$(docker-compose --version | awk '{print $3}' | tr -d ',')
        log_info "Docker Compose版本: $docker_compose_version"
    fi

    # 检查系统资源
    log_info "检查系统资源..."
    total_memory=$(free -h | awk '/^Mem:/ {print $2}')
    available_memory=$(free -h | awk '/^Mem:/ {print $7}')
    total_disk=$(df -h / | awk 'NR==2 {print $2}')
    available_disk=$(df -h / | awk 'NR==2 {print $4}')

    log_info "总内存: $total_memory, 可用内存: $available_memory"
    log_info "总磁盘: $total_disk, 可用磁盘: $available_disk"

    log_success "环境检查完成"
}

# 安装Python依赖
install_python_dependencies() {
    log_info "安装Python依赖..."

    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        log_info "创建Python虚拟环境..."
        python3 -m venv venv
    fi

    # 激活虚拟环境
    source venv/bin/activate

    # 升级pip
    pip3 install --upgrade pip

    # 安装基础依赖
    log_info "安装基础依赖..."
    pip3 install -r requirements.txt

    # 安装服务特定依赖
    if [ -f "database_service/requirements.txt" ]; then
        log_info "安装数据库服务依赖..."
        pip3 install -r database_service/requirements.txt
    fi

    if [ -f "model_service/requirements.txt" ]; then
        log_info "安装模型服务依赖..."
        pip3 install -r model_service/requirements.txt
    fi

    if [ -f "frontend_bff/requirements.txt" ]; then
        log_info "安装前端BFF依赖..."
        pip3 install -r frontend_bff/requirements.txt
    fi

    log_success "Python依赖安装完成"
}

# 安装Node.js依赖
install_node_dependencies() {
    if [ "$DEPLOY_FRONTEND" != "true" ]; then
        return
    fi

    log_info "安装Node.js依赖..."

    cd frontend

    # 检查package.json
    if [ ! -f "package.json" ]; then
        log_error "frontend/package.json 不存在"
        exit 1
    fi

    # 安装依赖
    npm install

    # 生产环境构建
    log_info "执行生产环境构建..."
    npm run build

    cd ..

    log_success "Node.js依赖安装完成"
}

# 配置环境变量
setup_environment() {
    log_info "配置环境变量..."

    # 检查.env文件
    if [ ! -f ".env" ]; then
        log_warning ".env 文件不存在，创建示例配置..."
        cat > .env.example << EOF
# 数据库配置
DATABASE_URL=postgresql://username:password@localhost:5432/ai_theme_app
REDIS_URL=redis://localhost:6379/0

# AI服务配置
OPENAI_API_KEY=your_openai_api_key_here
AI_MODEL_NAME=gpt-4
AI_MAX_TOKENS=2000

# 应用配置
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=your_secret_key_here

# 监控配置
SENTRY_DSN=your_sentry_dsn_here
LOG_LEVEL=INFO

# 邮件配置
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Slack配置
SLACK_WEBHOOK_URL=your_slack_webhook_url
EOF
        log_warning "请复制 .env.example 为 .env 并填写实际配置"
        exit 1
    fi

    # 加载环境变量
    set -a
    source .env
    set +a

    log_success "环境变量配置完成"
}

# 数据库初始化
initialize_database() {
    log_info "初始化数据库..."

    # 检查数据库连接
    if ! python3 -c "
import asyncpg
import asyncio
import os

async def test_db():
    try:
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        print('数据库连接成功')
        await conn.close()
    except Exception as e:
        print(f'数据库连接失败: {e}')
        exit(1)

asyncio.run(test_db())
"; then
        log_error "数据库连接测试失败"
        exit 1
    fi

    # 运行数据库迁移
    if [ -f "database_service/migrations/init.sql" ]; then
        log_info "执行数据库迁移..."
        psql $DATABASE_URL -f database_service/migrations/init.sql
    fi

    log_success "数据库初始化完成"
}

# Redis初始化
initialize_redis() {
    log_info "初始化Redis..."

    # 检查Redis连接
    if ! python3 -c "
import redis
import os

try:
    r = redis.from_url(os.getenv('REDIS_URL'))
    r.ping()
    print('Redis连接成功')
except Exception as e:
    print(f'Redis连接失败: {e}')
    exit(1)
"; then
        log_error "Redis连接测试失败"
        exit 1
    fi

    log_success "Redis初始化完成"
}

# 启动服务
start_services() {
    log_info "启动服务..."

    # 创建服务管理目录
    mkdir -p logs

    # 启动后端服务
    log_info "启动后端服务..."
    nohup python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4 > logs/backend.log 2>&1 &
    echo $! > logs/backend.pid

    # 启动前端BFF服务
    if [ -f "frontend_bff/app.py" ]; then
        log_info "启动前端BFF服务..."
        nohup python3 -m uvicorn frontend_bff.app:app --host 0.0.0.0 --port 8001 --workers 2 > logs/frontend_bff.log 2>&1 &
        echo $! > logs/frontend_bff.pid
    fi

    # 启动模型服务
    if [ -f "model_service/app.py" ]; then
        log_info "启动模型服务..."
        nohup python3 -m uvicorn model_service.app:app --host 0.0.0.0 --port 8002 --workers 2 > logs/model_service.log 2>&1 &
        echo $! > logs/model_service.pid
    fi

    # 启动前端服务 (如果部署了前端)
    if [ "$DEPLOY_FRONTEND" = "true" ] && [ -d "frontend/dist" ]; then
        log_info "启动前端服务..."
        nohup python3 -m http.server 8080 --directory frontend/dist > logs/frontend.log 2>&1 &
        echo $! > logs/frontend.pid
    fi

    log_success "服务启动完成"
}

# 健康检查
health_check() {
    log_info "执行健康检查..."

    # 等待服务启动
    sleep 5

    # 检查后端服务
    if curl -s http://localhost:8000/health > /dev/null; then
        log_success "后端服务健康检查通过"
    else
        log_error "后端服务健康检查失败"
        exit 1
    fi

    # 检查前端BFF服务
    if [ -f "logs/frontend_bff.pid" ]; then
        if curl -s http://localhost:8001/health > /dev/null; then
            log_success "前端BFF服务健康检查通过"
        else
            log_error "前端BFF服务健康检查失败"
            exit 1
        fi
    fi

    # 检查模型服务
    if [ -f "logs/model_service.pid" ]; then
        if curl -s http://localhost:8002/health > /dev/null; then
            log_success "模型服务健康检查通过"
        else
            log_error "模型服务健康检查失败"
            exit 1
        fi
    fi

    log_success "所有服务健康检查通过"
}

# 显示部署信息
show_deployment_info() {
    echo ""
    echo "=========================================="
    echo "  部署完成！服务访问信息："
    echo "=========================================="
    echo ""

    echo "后端API服务: http://localhost:8000"
    echo "前端BFF服务: http://localhost:8001"
    echo "模型服务: http://localhost:8002"

    if [ "$DEPLOY_FRONTEND" = "true" ]; then
        echo "前端界面: http://localhost:8080"
    fi

    echo ""
    echo "日志文件位置:"
    echo "  - 后端服务: logs/backend.log"
    echo "  - 前端BFF: logs/frontend_bff.log"
    echo "  - 模型服务: logs/model_service.log"

    if [ "$DEPLOY_FRONTEND" = "true" ]; then
        echo "  - 前端服务: logs/frontend.log"
    fi

    echo ""
    echo "进程ID文件: logs/*.pid"
    echo ""
    echo "停止所有服务: ./deployment/stop_services.sh"
    echo "重启所有服务: ./deployment/restart_services.sh"
    echo ""
    echo "=========================================="
}

# 主部署函数
main_deploy() {
    show_title

    # 解析命令行参数
    DEPLOY_FRONTEND="true"
    USE_DOCKER="false"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-frontend)
                DEPLOY_FRONTEND="false"
                shift
                ;;
            --docker)
                USE_DOCKER="true"
                shift
                ;;
            --help)
                echo "使用方法: $0 [选项]"
                echo "选项:"
                echo "  --no-frontend    不部署前端"
                echo "  --docker         使用Docker部署"
                echo "  --help           显示帮助信息"
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                exit 1
                ;;
        esac
    done

    # 执行部署步骤
    check_environment
    setup_environment
    install_python_dependencies

    if [ "$USE_DOCKER" = "true" ]; then
        deploy_with_docker
    else
        install_node_dependencies
        initialize_database
        initialize_redis
        start_services
        health_check
        show_deployment_info
    fi
}

# Docker部署
deploy_with_docker() {
    log_info "使用Docker部署..."

    # 检查Docker Compose文件
    if [ ! -f "docker-compose.yml" ]; then
        log_error "docker-compose.yml 文件不存在"
        exit 1
    fi

    # 启动Docker服务
    docker-compose up -d

    # 等待服务启动
    sleep 10

    # 健康检查
    if docker-compose ps | grep -q "Up"; then
        log_success "Docker服务启动成功"
    else
        log_error "Docker服务启动失败"
        docker-compose logs
        exit 1
    fi

    log_success "Docker部署完成"
}

# 执行主函数
main_deploy "$@"
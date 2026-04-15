#!/bin/bash
# 团队集成管理脚本

set -euo pipefail

PROJECT_ROOT="/Users/admin/desktop/ai_theme_app"
CONFIG_DIR="$PROJECT_ROOT/.tmux-team-config"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_menu() {
    clear
    echo -e "${BLUE}=== tmux团队协作管理 ===${NC}"
    echo ""
    echo -e "${GREEN}1. 安装优化套件${NC}"
    echo -e "${GREEN}2. 激活团队环境${NC}"
    echo -e "${GREEN}3. 启动队友${NC}"
    echo -e "${GREEN}4. 监控团队${NC}"
    echo -e "${GREEN}5. 检查状态${NC}"
    echo -e "${GREEN}6. 管理资源${NC}"
    echo -e "${GREEN}7. 查看日志${NC}"
    echo -e "${GREEN}8. 生成报告${NC}"
    echo -e "${GREEN}9. 清理系统${NC}"
    echo -e "${GREEN}0. 退出${NC}"
    echo ""
    echo -n "请选择 (0-9): "
}

install_optimization() {
    echo -e "${BLUE}安装优化套件...${NC}"

    # 运行优化脚本
    "$PROJECT_ROOT/tmux-team-optimization.sh"

    echo -e "${GREEN}优化套件安装完成${NC}"
    echo "配置目录: $CONFIG_DIR"
    echo "日志目录: $PROJECT_ROOT/logs/tmux-teams"
}

activate_environment() {
    echo -e "${BLUE}激活团队环境...${NC}"

    if [[ -f "$CONFIG_DIR/activate-team.sh" ]]; then
        source "$CONFIG_DIR/activate-team.sh"
    else
        echo -e "${RED}错误: 环境激活脚本不存在${NC}"
        echo "请先运行安装优化套件"
    fi
}

start_teammates() {
    echo -e "${BLUE}启动队友...${NC}"

    if [[ -f "$CONFIG_DIR/start-teammates.sh" ]]; then
        "$CONFIG_DIR/start-teammates.sh" "$@"
    else
        echo -e "${RED}错误: 队友启动脚本不存在${NC}"
    fi
}

monitor_team() {
    echo -e "${BLUE}监控团队...${NC}"

    if [[ -f "$CONFIG_DIR/monitor-team.sh" ]]; then
        "$CONFIG_DIR/monitor-team.sh" "$@"
    else
        echo -e "${RED}错误: 监控脚本不存在${NC}"
    fi
}

check_status() {
    echo -e "${BLUE}检查状态...${NC}"

    if [[ -f "$CONFIG_DIR/check-teammates.sh" ]]; then
        "$CONFIG_DIR/check-teammates.sh"
    else
        echo -e "${RED}错误: 状态检查脚本不存在${NC}"
    fi
}

manage_resources() {
    echo -e "${BLUE}管理资源...${NC}"

    if [[ -f "$CONFIG_DIR/resource-monitor.sh" ]]; then
        "$CONFIG_DIR/resource-monitor.sh" "$@"
    else
        echo -e "${RED}错误: 资源监控脚本不存在${NC}"
    fi
}

view_logs() {
    echo -e "${BLUE}查看日志...${NC}"

    LOG_DIR="$PROJECT_ROOT/logs/tmux-teams"

    if [[ -d "$LOG_DIR" ]]; then
        echo "日志目录: $LOG_DIR"
        echo ""
        ls -la "$LOG_DIR" | head -20

        echo ""
        echo -n "查看哪个日志文件? (输入名称或按Enter返回): "
        read -r logfile

        if [[ -n "$logfile" && -f "$LOG_DIR/$logfile" ]]; then
            less "$LOG_DIR/$logfile"
        fi
    else
        echo -e "${YELLOW}日志目录不存在${NC}"
    fi
}

generate_report() {
    echo -e "${BLUE}生成报告...${NC}"

    if [[ -f "$CONFIG_DIR/monitor-team.sh" ]]; then
        "$CONFIG_DIR/monitor-team.sh" report
    else
        echo -e "${RED}错误: 无法生成报告${NC}"
    fi
}

cleanup_system() {
    echo -e "${BLUE}清理系统...${NC}"

    # 清理旧日志
    if [[ -f "$CONFIG_DIR/resource-monitor.sh" ]]; then
        "$CONFIG_DIR/resource-monitor.sh" cleanup
    fi

    # 清理tmux会话
    echo "清理不活动的tmux会话..."
    tmux list-sessions | grep -E "(claude-swarm|attached)" || true

    echo -e "${GREEN}清理完成${NC}"
}

main() {
    cd "$PROJECT_ROOT"

    while true; do
        print_menu
        read -r choice

        case "$choice" in
            1)
                install_optimization
                ;;
            2)
                activate_environment
                ;;
            3)
                echo -n "输入队友名称或编号 (用空格分隔多个): "
                read -r teammates
                start_teammates $teammates
                ;;
            4)
                echo -n "监控模式 (直接回车=实时, daemon=后台, report=日报): "
                read -r mode
                monitor_team "$mode"
                ;;
            5)
                check_status
                ;;
            6)
                echo -n "资源操作 (直接回车=检查, cleanup=清理): "
                read -r action
                manage_resources "$action"
                ;;
            7)
                view_logs
                ;;
            8)
                generate_report
                ;;
            9)
                cleanup_system
                ;;
            0)
                echo -e "${BLUE}退出管理脚本${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}无效选择${NC}"
                ;;
        esac

        echo ""
        echo -n "按Enter继续..."
        read -r
    done
}

main "$@"

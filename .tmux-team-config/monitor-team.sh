#!/bin/bash
# 实时监控所有队友pane输出

set -euo pipefail

PROJECT_ROOT="/Users/admin/desktop/ai_theme_app"
LOG_DIR="$PROJECT_ROOT/logs/tmux-teams"
mkdir -p "$LOG_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查是否在tmux中
if [[ -z "$TMUX" ]]; then
    echo -e "${YELLOW}警告: 不在tmux会话中，只能监控外部会话${NC}"
    TMUX_CMD="tmux -L claude-swarm"
else
    TMUX_CMD="tmux"
fi

monitor_panes() {
    echo -e "${BLUE}=== 开始监控团队输出 ===${NC}"
    echo -e "${BLUE}时间: $(date)${NC}"
    echo ""

    while true; do
        clear

        # 获取所有pane信息
        PANES=$($TMUX_CMD list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_title} #{pane_current_command}" 2>/dev/null || true)

        if [[ -z "$PANES" ]]; then
            echo -e "${YELLOW}未找到活动的tmux pane${NC}"
            sleep 5
            continue
        fi

        echo -e "${GREEN}活动中的队友 ($(date '+%H:%M:%S')):${NC}"
        echo "----------------------------------------"

        IFS=$'\n'
        for pane_info in $PANES; do
            pane_id=$(echo "$pane_info" | awk '{print $1}')
            pane_title=$(echo "$pane_info" | cut -d' ' -f2- | awk '{$NF=""; print $0}' | sed 's/ $//')
            pane_cmd=$(echo "$pane_info" | awk '{print $NF}')

            # 跳过非队友pane（根据标题判断）
            if [[ ! "$pane_title" =~ (专家|开发|分析|测试|经理|负责人) ]]; then
                continue
            fi

            echo -e "${YELLOW}▶ $pane_title${NC} (命令: $pane_cmd)"

            # 获取最后5行输出
            output=$($TMUX_CMD capture-pane -p -t "$pane_id" -S -5 2>/dev/null || echo "无法获取输出")

            if [[ -n "$output" ]]; then
                echo "$output" | sed 's/^/    /'
            fi

            echo ""
        done

        echo -e "${BLUE}----------------------------------------${NC}"
        echo -e "按 Ctrl+C 退出监控 | 自动刷新: 10秒"
        echo ""

        sleep 10
    done
}

# 生成日报
generate_daily_report() {
    REPORT_FILE="$LOG_DIR/daily-report-$(date '+%Y%m%d').md"

    cat > "$REPORT_FILE" << REPORT_EOF
# 团队日报 - $(date '+%Y年%m月%d日')

## 监控概览
- 监控开始时间: $(date)
- 活动队友数量: $(echo "$PANES" | grep -c "专家\|开发\|分析\|测试")

## 队友状态

REPORT_EOF

    IFS=$'\n'
    for pane_info in $PANES; do
        pane_title=$(echo "$pane_info" | cut -d' ' -f2- | awk '{$NF=""; print $0}' | sed 's/ $//')

        if [[ ! "$pane_title" =~ (专家|开发|分析|测试|经理|负责人) ]]; then
            continue
        fi

        echo "### $pane_title" >> "$REPORT_FILE"
        echo "- 状态: 运行中" >> "$REPORT_FILE"
        echo "- 最后活动: $(date '+%H:%M:%S')" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
    done

    echo -e "${GREEN}日报已生成: $REPORT_FILE${NC}"
}

# 主函数
main() {
    case "${1:-}" in
        "report")
            generate_daily_report
            ;;
        "daemon")
            # 后台运行监控
            monitor_panes > "$LOG_DIR/monitor-$(date '+%Y%m%d-%H%M%S').log" 2>&1 &
            echo "监控已在后台运行，PID: $!"
            ;;
        *)
            monitor_panes
            ;;
    esac
}

main "$@"

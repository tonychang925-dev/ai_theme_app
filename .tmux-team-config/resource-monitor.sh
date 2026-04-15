#!/bin/bash
# 团队资源监控

set -euo pipefail

check_resources() {
    echo "=== 系统资源监控 ==="
    echo ""

    # CPU使用率
    CPU_USAGE=$(top -l 1 | grep "CPU usage" | sed 's/.*://')
    echo "CPU使用率: $CPU_USAGE"

    # 内存使用
    MEMORY_USAGE=$(memory_pressure | grep "System-wide memory free percentage:" | awk '{print $5}')
    echo "内存空闲百分比: $MEMORY_USAGE%"

    # tmux进程
    TMUX_PROCESSES=$(ps aux | grep -c "[t]mux")
    echo "tmux进程数: $TMUX_PROCESSES"

    # Claude Code进程
    CLAUDE_PROCESSES=$(ps aux | grep -c "[c]laude")
    echo "Claude Code进程数: $CLAUDE_PROCESSES"

    # 日志文件大小
    LOG_SIZE=$(du -sh logs/tmux-teams 2>/dev/null | awk '{print $1}' || echo "0")
    echo "日志目录大小: $LOG_SIZE"

    echo ""

    # 警告检查
    if [[ $TMUX_PROCESSES -gt 10 ]]; then
        echo "⚠ 警告: tmux进程过多，可能需清理"
    fi

    if [[ $CLAUDE_PROCESSES -gt 5 ]]; then
        echo "⚠ 警告: Claude Code进程过多"
    fi
}

# 清理旧日志
cleanup_logs() {
    echo "=== 清理旧日志 ==="

    # 保留最近7天的日志
    find "$LOG_DIR" -name "*.log" -mtime +7 -delete 2>/dev/null || true
    find "$LOG_DIR" -name "daily-report-*.md" -mtime +30 -delete 2>/dev/null || true

    echo "日志清理完成"
}

main() {
    case "${1:-}" in
        "cleanup")
            cleanup_logs
            ;;
        *)
            check_resources
            ;;
    esac
}

main "$@"

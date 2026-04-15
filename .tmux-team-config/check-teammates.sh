#!/bin/bash
# 检查队友状态

set -euo pipefail

check_teammate_status() {
    echo "=== 队友状态检查 ==="
    echo "检查时间: $(date)"
    echo ""

    # 检查tmux中的队友pane
    if command -v tmux &> /dev/null; then
        echo "tmux会话中的队友:"
        echo "----------------"

        # 检查内部会话
        if [[ -n "$TMUX" ]]; then
            tmux list-panes -F "#{pane_title} #{pane_current_command} #{pane_pid}" | while read line; do
                if [[ "$line" =~ (专家|开发|分析|测试|经理|负责人) ]]; then
                    echo "  - $line"
                fi
            done
        fi

        # 检查外部会话
        tmux -L claude-swarm list-panes -a 2>/dev/null | grep -E "(专家|开发|分析|测试|经理|负责人)" || true

        echo ""
    fi

    # 检查进程
    echo "相关进程:"
    echo "----------------"
    ps aux | grep -E "(claude|python|node|bun)" | grep -v grep || true

    echo ""

    # 检查任务列表
    if [[ -f "docs/teams/进度跟踪看板_*.md" ]]; then
        latest_progress=$(ls -t docs/teams/进度跟踪看板_*.md | head -1)
        echo "最新进度文件: $latest_progress"

        # 提取任务状态
        echo "任务状态统计:"
        grep -E "(✅|⏳|❌)" "$latest_progress" | sort | uniq -c || true
    fi
}

check_system_health() {
    echo ""
    echo "=== 系统健康检查 ==="

    # 磁盘空间
    DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}')
    echo "磁盘使用率: $DISK_USAGE"

    # 内存使用
    FREE_MEM=$(memory_pressure | grep "System-wide memory free percentage:" | awk '{print $5}' || echo "N/A")
    echo "空闲内存: $FREE_MEM%"

    # 网络连接
    NETWORK=$(ping -c 1 -t 2 8.8.8.8 &> /dev/null && echo "正常" || echo "异常")
    echo "网络连接: $NETWORK"
}

main() {
    check_teammate_status
    check_system_health

    echo ""
    echo "=== 建议 ==="

    # 给出建议
    if [[ $(ps aux | grep -c "[t]mux") -gt 8 ]]; then
        echo "⚠ 建议: tmux会话较多，考虑清理不用的会话"
    fi

    if [[ -f "docs/teams/进度跟踪看板_*.md" ]]; then
        pending_tasks=$(grep -c "⏳" "$(ls -t docs/teams/进度跟踪看板_*.md | head -1)" 2>/dev/null || echo 0)
        if [[ $pending_tasks -gt 5 ]]; then
            echo "⚠ 建议: 有 $pending_tasks 个任务进行中，请关注进度"
        fi
    fi
}

main

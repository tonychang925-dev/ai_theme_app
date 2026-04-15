#!/bin/bash
# 快速启动团队队友

set -euo pipefail

TEAMMATES=(
    "前端开发专家:负责UI/前端实现"
    "后端开发专家:负责API/服务端"
    "数据分析专家:负责数据分析和算法"
    "测试专家:负责质量保证"
    "产品经理:负责需求管理"
)

print_teammate_info() {
    echo "可用队友列表:"
    echo ""

    for i in "${!TEAMMATES[@]}"; do
        name=$(echo "${TEAMMATES[$i]}" | cut -d: -f1)
        desc=$(echo "${TEAMMATES[$i]}" | cut -d: -f2)
        echo "  $((i+1)). $name - $desc"
    done

    echo ""
}

start_teammate() {
    local teammate_name="$1"
    local teammate_desc="$2"

    echo "启动队友: $teammate_name ($teammate_desc)"

    # 这里应该调用Claude Code的API启动队友
    # 暂时用模拟命令
    echo "执行: ./claude \"请为当前团队添加一个队友，名为'$teammate_name'，描述:'$teammate_desc'\""

    # 记录启动日志
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 启动队友: $teammate_name" >> "$LOG_DIR/teammate-start.log"
}

main() {
    print_teammate_info

    if [[ $# -eq 0 ]]; then
        echo "使用方法: $0 <队友编号或名称>"
        echo "示例: $0 1  # 启动前端开发专家"
        echo "示例: $0 前端开发专家"
        exit 1
    fi

    for arg in "$@"; do
        # 检查是否是数字
        if [[ "$arg" =~ ^[0-9]+$ ]]; then
            index=$((arg-1))
            if [[ $index -ge 0 && $index -lt ${#TEAMMATES[@]} ]]; then
                teammate="${TEAMMATES[$index]}"
                name=$(echo "$teammate" | cut -d: -f1)
                desc=$(echo "$teammate" | cut -d: -f2)
                start_teammate "$name" "$desc"
            else
                echo "错误: 无效的队友编号 $arg"
            fi
        else
            # 按名称查找
            found=0
            for teammate in "${TEAMMATES[@]}"; do
                name=$(echo "$teammate" | cut -d: -f1)
                if [[ "$name" == "$arg" ]]; then
                    desc=$(echo "$teammate" | cut -d: -f2)
                    start_teammate "$name" "$desc"
                    found=1
                    break
                fi
            done

            if [[ $found -eq 0 ]]; then
                echo "错误: 未找到队友 '$arg'"
            fi
        fi
    done
}

main "$@"

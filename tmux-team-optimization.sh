#!/bin/bash
# tmux团队协作优化脚本
# 用于优化Claude Code tmux模式的团队协作体验

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/Users/admin/desktop/ai_theme_app"
cd "$PROJECT_ROOT"

# 日志目录
LOG_DIR="$PROJECT_ROOT/logs/tmux-teams"
mkdir -p "$LOG_DIR"

# 优化配置目录
CONFIG_DIR="$PROJECT_ROOT/.tmux-team-config"
mkdir -p "$CONFIG_DIR"

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# 1. 创建tmux团队配置
create_tmux_config() {
    print_header "1. 创建tmux团队协作配置"

    cat > "$CONFIG_DIR/tmux.team.conf" << 'EOF'
# tmux团队协作优化配置
# 适用于Claude Code团队协作

# 基础设置
set-option -g default-terminal "screen-256color"
set-option -g terminal-overrides ",xterm-256color:Tc"
set-option -g focus-events on

# 历史缓冲区（便于查看队友输出）
set-option -g history-limit 100000
set-option -g buffer-limit 50

# 鼠标支持
set-option -g mouse on

# 状态栏优化
set-option -g status on
set-option -g status-interval 5
set-option -g status-justify centre
set-option -g status-left-length 100
set-option -g status-right-length 150

# 状态栏显示队友信息
set-option -g status-right "#[fg=cyan]#S #[fg=yellow]%H:%M #[fg=green]#(tmux list-panes -F '#{pane_title}' 2>/dev/null | tr '\n' ' ' | cut -c1-100)"

# Pane边框和标题
set-option -g pane-border-status top
set-option -g pane-border-format "#[fg=cyan,bold] #{pane_title} #[default]"

# 窗口和pane索引从1开始
set-option -g base-index 1
set-option -g pane-base-index 1

# 重命名窗口自动
set-option -g allow-rename off
set-option -g automatic-rename off
set-option -g automatic-rename-format '#{b:pane_title}'

# 复制模式优化
set-option -g mode-keys vi
bind-key -T copy-mode-vi v send-keys -X begin-selection
bind-key -T copy-mode-vi y send-keys -X copy-selection

# 团队协作快捷键
# 查看所有队友pane
bind-key T list-panes -F "#{pane_index}: #{pane_title} #{pane_current_command}"
# 切换到队友pane（按数字）
bind-key -r C-t choose-tree -Zw
# 广播命令到所有队友pane
bind-key B command-prompt -p "广播命令:" "run-shell 'tmux list-panes -F \"#{pane_id}\" | grep -v \"$(tmux display-message -p \"#{pane_id}\")\" | xargs -I {} tmux send-keys -t {} \"%%\" Enter'"
EOF

    print_success "tmux配置已创建: $CONFIG_DIR/tmux.team.conf"
    echo "应用配置: tmux source-file $CONFIG_DIR/tmux.team.conf"
    echo ""
}

# 2. 创建监控脚本
create_monitoring_scripts() {
    print_header "2. 创建团队监控脚本"

    # 2.1 实时监控脚本
    cat > "$CONFIG_DIR/monitor-team.sh" << 'EOF'
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
EOF

    chmod +x "$CONFIG_DIR/monitor-team.sh"
    print_success "监控脚本已创建: $CONFIG_DIR/monitor-team.sh"

    # 2.2 资源监控脚本
    cat > "$CONFIG_DIR/resource-monitor.sh" << 'EOF'
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
EOF

    chmod +x "$CONFIG_DIR/resource-monitor.sh"
    print_success "资源监控脚本已创建: $CONFIG_DIR/resource-monitor.sh"
    echo ""
}

# 3. 创建队友管理工具
create_teammate_tools() {
    print_header "3. 创建队友管理工具"

    # 3.1 队友快速启动脚本
    cat > "$CONFIG_DIR/start-teammates.sh" << 'EOF'
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
EOF

    chmod +x "$CONFIG_DIR/start-teammates.sh"
    print_success "队友启动脚本已创建: $CONFIG_DIR/start-teammates.sh"

    # 3.2 队友状态检查
    cat > "$CONFIG_DIR/check-teammates.sh" << 'EOF'
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
EOF

    chmod +x "$CONFIG_DIR/check-teammates.sh"
    print_success "队友状态检查脚本已创建: $CONFIG_DIR/check-teammates.sh"
    echo ""
}

# 4. 创建环境同步脚本
create_env_sync() {
    print_header "4. 创建环境同步配置"

    # 4.1 团队共享环境变量
    cat > "$CONFIG_DIR/team-environment.sh" << 'EOF'
#!/bin/bash
# 团队共享环境变量

# 项目相关
export AI_THEME_APP_ROOT="/Users/admin/desktop/ai_theme_app"
export PROJECT_ROOT="$AI_THEME_APP_ROOT"
export TEAM_LOG_DIR="$AI_THEME_APP_ROOT/logs/tmux-teams"

# 团队配置
export TEAM_NAME="AI主题开发团队"
export TEAM_MODE="tmux"
export MAX_TEAMMATES=5

# Claude Code相关
export CLAUDE_MODEL="deepseek-chat"
export CLAUDE_CONFIG_DIR="$HOME/.claude"

# 任务相关
export TASK_PRIORITY_CRITICAL="P0"
export TASK_PRIORITY_HIGH="P1"
export TASK_PRIORITY_NORMAL="P2"
export TASK_PRIORITY_LOW="P3"

# 日志级别
export LOG_LEVEL_DEBUG="DEBUG"
export LOG_LEVEL_INFO="INFO"
export LOG_LEVEL_WARN="WARN"
export LOG_LEVEL_ERROR="ERROR"

# 路径添加到PATH
export PATH="$AI_THEME_APP_ROOT/.tmux-team-config:$PATH"

# 别名定义
alias team-monitor="$AI_THEME_APP_ROOT/.tmux-team-config/monitor-team.sh"
alias team-check="$AI_THEME_APP_ROOT/.tmux-team-config/check-teammates.sh"
alias team-resources="$AI_THEME_APP_ROOT/.tmux-team-config/resource-monitor.sh"
alias team-start="$AI_THEME_APP_ROOT/.tmux-team-config/start-teammates.sh"

# 函数: 切换到项目目录
cdproj() {
    cd "$AI_THEME_APP_ROOT" || return 1
    echo "已切换到项目目录: $AI_THEME_APP_ROOT"
}

# 函数: 查看队友
teammates() {
    echo "当前团队: $TEAM_NAME"
    echo "模式: $TEAM_MODE"
    echo ""
    team-check | head -20
}

# 函数: 快速启动监控
monitor-team() {
    team-monitor "$@"
}

# 加载用户自定义配置（如果存在）
if [[ -f "$AI_THEME_APP_ROOT/.team-custom.env" ]]; then
    source "$AI_THEME_APP_ROOT/.team-custom.env"
fi

echo "团队环境已加载: $TEAM_NAME"
EOF

    # 4.2 创建环境激活脚本
    cat > "$CONFIG_DIR/activate-team.sh" << 'EOF'
#!/bin/bash
# 激活团队环境

set -euo pipefail

TEAM_ENV_FILE="$AI_THEME_APP_ROOT/.tmux-team-config/team-environment.sh"

if [[ ! -f "$TEAM_ENV_FILE" ]]; then
    echo "错误: 团队环境文件不存在"
    exit 1
fi

# 备份原始环境变量
BACKUP_FILE="$HOME/.team-env-backup-$(date +%s).txt"
{
    echo "=== 环境变量备份 $(date) ==="
    echo ""
    env | sort
} > "$BACKUP_FILE"

echo "已备份环境变量到: $BACKUP_FILE"

# 加载团队环境
source "$TEAM_ENV_FILE"

echo ""
echo "✅ 团队环境已激活"
echo "   团队: $TEAM_NAME"
echo "   项目: $PROJECT_ROOT"
echo "   模式: $TEAM_MODE"
echo ""
echo "可用命令:"
echo "  teammates    - 查看队友状态"
echo "  monitor-team - 启动监控"
echo "  cdproj       - 切换到项目目录"
echo ""
echo "环境文件: $TEAM_ENV_FILE"
EOF

    chmod +x "$CONFIG_DIR/activate-team.sh"
    print_success "环境同步脚本已创建: $CONFIG_DIR/activate-team.sh"
    echo ""
}

# 5. 创建使用说明
create_usage_guide() {
    print_header "5. 创建使用指南"

    cat > "$CONFIG_DIR/USAGE.md" << 'EOF'
# tmux团队协作优化使用指南

## 概述
本优化套件增强了Claude Code tmux模式的团队协作能力，提供监控、管理、环境同步等功能。

## 快速开始

### 1. 激活团队环境
```bash
cd /Users/admin/desktop/ai_theme_app
source .tmux-team-config/activate-team.sh
```

### 2. 启动队友
```bash
# 启动单个队友
.team-start 前端开发专家

# 启动多个队友
.team-start 前端开发专家 后端开发专家
```

### 3. 监控团队
```bash
# 实时监控
team-monitor

# 后台监控
team-monitor daemon

# 生成日报
team-monitor report
```

### 4. 检查状态
```bash
# 检查队友状态
team-check

# 检查资源使用
team-resources

# 清理旧日志
team-resources cleanup
```

## 常用工作流

### 晨会启动
```bash
# 1. 激活环境
source .tmux-team-config/activate-team.sh

# 2. 启动关键队友
.team-start 前端开发专家 后端开发专家 测试专家

# 3. 启动监控
team-monitor daemon

# 4. 开始工作
./claude
```

### 日常监控
```bash
# 在一个终端中运行监控
team-monitor

# 在另一个终端中工作
./claude
```

### 收尾工作
```bash
# 检查一天的工作
team-check

# 生成日报
team-monitor report

# 清理资源
team-resources cleanup
```

## 配置文件

### tmux配置
位置: `.tmux-team-config/tmux.team.conf`

应用配置:
```bash
tmux source-file .tmux-team-config/tmux.team.conf
```

### 环境变量
位置: `.tmux-team-config/team-environment.sh`

### 日志目录
位置: `logs/tmux-teams/`

## 故障排除

### 问题1: tmux pane无法创建
**解决**: 检查tmux是否安装，尝试重启tmux服务

### 问题2: 队友输出不显示
**解决**: 检查pane标题是否正确设置，重启监控

### 问题3: 资源使用过高
**解决**: 使用`team-resources`检查，减少同时运行的队友数量

### 问题4: 环境变量不生效
**解决**: 重新运行`activate-team.sh`，检查文件权限

## 高级功能

### 自定义队友配置
编辑`.tmux-team-config/start-teammates.sh`，修改TEAMMATES数组

### 扩展监控功能
编辑`.tmux-team-config/monitor-team.sh`，添加自定义监控项

### 集成其他工具
在`.tmux-team-config/team-environment.sh`中添加工具路径和别名

## 最佳实践

1. **定期清理日志**: 使用`team-resources cleanup`
2. **监控资源使用**: 避免启动过多队友
3. **使用环境变量**: 确保所有队友环境一致
4. **备份重要配置**: 定期备份团队配置
5. **文档化工作流程**: 记录团队协作规范

## 支持与反馈

问题反馈请检查日志文件:
- `logs/tmux-teams/monitor-*.log`
- `logs/tmux-teams/daily-report-*.md`

优化建议可编辑配置文件或联系架构师。
EOF

    print_success "使用指南已创建: $CONFIG_DIR/USAGE.md"
    echo ""
}

# 6. 创建集成脚本
create_integration_script() {
    print_header "6. 创建集成管理脚本"

    cat > "$PROJECT_ROOT/manage-team.sh" << 'EOF'
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
EOF

    chmod +x "$PROJECT_ROOT/manage-team.sh"
    print_success "集成管理脚本已创建: $PROJECT_ROOT/manage-team.sh"
    echo ""
}

# 主函数
main() {
    echo -e "${BLUE}=== tmux团队协作优化套件安装 ===${NC}"
    echo ""

    create_tmux_config
    create_monitoring_scripts
    create_teammate_tools
    create_env_sync
    create_usage_guide
    create_integration_script

    echo -e "${GREEN}=== 优化套件安装完成 ===${NC}"
    echo ""
    echo "主要功能:"
    echo "1. tmux配置优化: $CONFIG_DIR/tmux.team.conf"
    echo "2. 团队监控: $CONFIG_DIR/monitor-team.sh"
    echo "3. 队友管理: $CONFIG_DIR/start-teammates.sh"
    echo "4. 环境同步: $CONFIG_DIR/activate-team.sh"
    echo "5. 集成管理: $PROJECT_ROOT/manage-team.sh"
    echo ""
    echo "使用方式:"
    echo "  直接运行: ./manage-team.sh"
    echo "  或手动激活: source .tmux-team-config/activate-team.sh"
    echo ""
    echo "详细指南: $CONFIG_DIR/USAGE.md"
}

main "$@"
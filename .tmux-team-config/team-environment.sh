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

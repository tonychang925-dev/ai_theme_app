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

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

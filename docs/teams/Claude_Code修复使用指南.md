# Claude Code修复使用指南

## 问题已解决
**"Error writing file"错误已彻底修复**

### 修复内容
1. 修改了Claude Code核心的`expandPath()`函数，优先使用`AI_THEME_APP_ROOT`环境变量
2. 将修复集成到`./claude`启动脚本，自动设置环境变量

## 使用方法

### 1. 启动Claude Code
```bash
cd /Users/admin/desktop/ai_theme_app
./claude  # 使用修复版
```

启动时会显示：
```
🔧 Claude Code修复版已启动
   项目目录: /Users/admin/desktop/ai_theme_app
   环境变量: AI_THEME_APP_ROOT=/Users/admin/desktop/ai_theme_app
```

### 2. 创建文件

#### 方法A: 相对路径 (推荐)
在Claude Code会话中：
```
请在 docs/teams/文件名.md 创建文件
```

**示例**:
```
请在 docs/teams/项目计划.md 创建项目计划文档
```

#### 方法B: 绝对路径 (确保成功)
```
请在 /Users/admin/desktop/ai_theme_app/docs/teams/文件名.md 创建文件
```

### 3. 团队功能使用

#### 创建团队
```
请创建一个名为'AI主题分析团队'的团队
```

#### 添加队友
```
请为'AI主题分析团队'添加一个队友，名为'数据分析专家'
```

#### 分配任务
队友会自动检查任务列表并认领任务。您也可以手动分配：
```
请将'数据分析任务'分配给'数据分析专家'
```

#### 创建团队报告
```
请在 docs/teams/AI主题分析团队报告.md 创建团队报告
```

### 4. 架构师监督工作流

#### 启动监督控制台
```bash
cd /Users/admin/desktop/ai_theme_app
./architect-supervision.sh dashboard
```

#### 实时监控队友输出
```bash
./architect-supervision.sh monitor
```

#### 查看团队日志
```bash
./architect-supervision.sh logs
```

## 验证修复

### 测试命令
1. **启动测试**:
   ```bash
   ./claude --version
   ```

2. **创建测试文件** (在Claude Code中):
   ```
   请在 docs/teams/测试文件-$(date +%s).md 创建测试文件
   ```

3. **验证环境变量** (在Claude Code中):
   ```
   请检查AI_THEME_APP_ROOT环境变量
   ```

## 常见问题

### Q1: 仍然出现"Error writing file"怎么办？
A: 使用绝对路径确保成功：
```
请在 /Users/admin/desktop/ai_theme_app/docs/teams/文件名.md 创建文件
```

### Q2: 如何检查环境变量是否正确设置？
A: 在Claude Code中：
```
请运行'echo $AI_THEME_APP_ROOT'命令
```

### Q3: 团队功能不起作用？
A: 确保使用最新修复版：
1. 退出当前Claude Code会话
2. 重新运行`./claude`
3. 再次尝试创建团队

### Q4: 需要手动设置环境变量吗？
A: 不需要。`./claude`脚本已自动设置。如需手动覆盖：
```bash
export AI_THEME_APP_ROOT="/custom/path"
./claude
```

## 文件结构建议
```
docs/teams/
├── 团队报告/          # 团队协作报告
├── 项目文档/          # 项目相关文档
├── 会议记录/          # 团队会议记录
└── 技术分析/          # 技术分析文档
```

## 高级功能

### 多团队协作
可以创建多个团队并行工作：
1. `AI主题分析团队` - 负责主题分析
2. `前端开发团队` - 负责前端实现
3. `后端开发团队` - 负责后端服务

### 跨团队协调
使用架构师监督控制台监控所有团队输出，进行决策协调。

## 技术支持
如遇问题，请检查：
1. 是否在正确目录运行 (`/Users/admin/desktop/ai_theme_app`)
2. 是否使用修复版`./claude`脚本
3. `docs/teams/`目录是否存在且可写

---
*本指南基于Claude Code修复版创建 - 2026-04-11*
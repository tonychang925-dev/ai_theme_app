# AI Theme App - 个人投资助理

## 项目概述

AI Theme App 是一个智能投资辅助系统，专注于题材投资分析和决策支持。系统通过人工智能技术分析新闻事件、市场动态和股票数据，自动识别投资题材，为投资者提供实时情报和决策建议。

## 当前状态

**最新进展 (2026-04-10)**: 已完成实时情报全链路阶段1（AkShare→Stream→SSE→Intel页面）并完成前端架构优化阶段2

### 项目阶段进展

| 阶段 | 状态 | 完成日期 | 主要成果 |
|------|------|----------|----------|
| P1.phase0-2 | 已完成 | 2026-02-19 | 基础数据模型与API |
| P2.phase0-1 | 已完成 | 2026-03-31 | 数据库标准化与只读API |
| P3.phaseA | 已完成 | 2026-03-31 | 前端BFF服务边界 |
| P4.phaseA | 已完成 | 2026-03-31 | 前端初始实现与情报页面 |
| **前端架构优化阶段2** | **已完成** | **2026-04-10** | **组件重构与架构优化** |
| **实时情报全链路阶段1** | **已完成** | **2026-04-10** | **AkShare定期采集→结构化→匹配→SSE推送→Intel展示** |

## 前端架构优化阶段2成果

### 主要改进
1. **组件化重构**: 将377行的ThemeWorkspacePage拆分为9个独立可复用组件
2. **关注点分离**: 创建`useThemeWorkspace`钩子，分离数据逻辑与UI逻辑
3. **代码统一**: 集中管理格式化函数，提高代码一致性
4. **类型安全**: 完整TypeScript支持，编译检查通过

### 新组件体系
- `WorkspaceHeader` - 工作台头部
- `OverviewCard` - 题材概览
- `PrimaryCycleCard` - 主线周期分析
- `TrendCard` - 近5日走势
- `LeaderInflowCard` - 资金流入前排
- `LeaderTechCard` - 前排股票技术
- `HistoryCard` - 历史驱动
- `ChildThemesCard` - 子题材
- `StockPoolCard` - 股票池

## 实时情报全链路阶段1成果

### 主要改进
1. **链路打通**: 建立 AkShare 定期采集到 `stream:news:raw` 的实时入口，并接入既有结构化与匹配链路
2. **约束落地**: 实时链路默认禁止自动创建新题材，未匹配事件进入人工复核队列
3. **前端可见**: Intel 页面新增“待复核事件”筛选，支持实时复核项展示
4. **诊断增强**: 增加 `source_channel` 口径与 `diagnostics.source_channel_counts` 统计，便于运营观察双源状态

### 新增/更新关键文档
- `docs/project_control/reports/realtime-intel-pipeline-phase1-2026-04-10.md`
- `docs/project_control/REALTIME_DUAL_SOURCE_ROLLOUT.md`

## 系统架构

### 核心服务
```
frontend/                    # React前端应用 (Vite + TypeScript)
frontend_bff/               # 前端BFF聚合服务
theme_service/              # 题材领域服务
database_service/           # 数据ETL与标准化
model_service/              # AI模型服务
evaluate_service/          # 评估与测试服务
```

### 技术栈
- **前端**: React 18, TypeScript, Vite, Tailwind CSS, Zustand
- **后端**: Python FastAPI, PostgreSQL, Redis
- **AI/ML**: Transformers, Sentence-BERT, 文本向量化
- **数据**: 久赢恒丰数据源，实时行情集成
- **部署**: Docker, Kubernetes (规划中)

## 核心功能

### 1. 情报流分析
- 实时新闻事件监测与分类
- 题材异动识别与关联分析
- 新题材候选发现与评估

### 2. 题材工作台
- 多维题材分析（热度、周期、资金、技术）
- 题材历史驱动追溯
- 子题材关系图谱
- 关联股票池分析

### 3. 个股工作台
- 个股题材归属分析
- 资金流向与技术指标
- 龙头地位识别
- 跨题材关联分析

## 数据流程

```
久赢恒丰数据源 → 数据标准化层 → 主题模型分析 → 题材匹配
     ↓
PostgreSQL数据库 → 只读API服务 → 前端BFF聚合 → React前端
     ↓
实时更新与监控 ← 评估与测试 ← 用户交互反馈
```

## 项目结构

```
ai_theme_app/
├── frontend/                    # React前端应用
│   ├── src/
│   │   ├── components/         # 可复用组件
│   │   ├── hooks/             # 自定义React钩子
│   │   ├── routes/            # 页面路由
│   │   ├── lib/               # 工具库
│   │   └── App.tsx            # 应用入口
│   └── package.json
├── frontend_bff/              # 前端BFF服务
├── theme_service/             # 题材领域服务
├── database_service/          # 数据ETL与存储
├── model_service/            # AI模型服务
├── evaluate_service/         # 评估与测试
├── docs/                     # 项目文档
│   ├── project_control/      # 项目管理文档
│   ├── architecture/         # 架构设计文档
│   └── reports/             # 阶段报告
└── README.md                 # 本文档
```

## 开发指南

### 环境要求
- Node.js 18+ (前端开发)
- Python 3.10+ (后端开发)
- PostgreSQL 14+ (数据库)
- Bun 1.3.10+ (可选，用于Claude Code开发)

### 快速开始
```bash
# 一键启动实时链路（推荐）
cd /Users/admin/Desktop/ai_theme_app
./scripts/run_realtime_stack.sh --with-frontend

# 一键停止实时链路
./scripts/stop_realtime_stack.sh --with-frontend

# 一键查看实时链路状态
./scripts/status_realtime_stack.sh

# 前端开发
cd frontend
npm install
npm run dev

# 后端开发
cd theme_service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

### 测试执行
```bash
# 前端测试
cd frontend
npm run test

# 后端测试
cd theme_service
python -m pytest
```

## 文档资源

- **阶段报告**: `docs/project_control/reports/` - 各阶段执行报告
- **架构设计**: `docs/architecture/` - 系统架构与技术设计
- **项目管理**: `docs/project_control/` - 需求、合同、测试规范
- **团队管理**: `docs/teams/` - 团队组织结构与职责分工
- **最新进展**: `docs/project_control/reports/frontend-architecture-optimization-phase2-2026-04-10.md`
- **实时链路进展**: `docs/project_control/reports/realtime-intel-pipeline-phase1-2026-04-10.md`
- **上线指引**: `docs/project_control/REALTIME_DUAL_SOURCE_ROLLOUT.md`
- **运行手册（SOP）**: `docs/project_control/REALTIME_OPERATIONS_RUNBOOK.md`

## 后续规划

### 短期目标 (Q2 2026)
1. 前端性能优化与用户体验改进
2. 实时推送与通知系统
3. 移动端适配与响应式设计

### 中期目标 (Q3 2026)
1. 高级分析功能（预测模型、风险评估）
2. 多用户协作与分享功能
3. API开放平台建设

### 长期愿景
构建行业领先的智能投资决策支持平台，赋能个人投资者与专业机构。

## 贡献指南

欢迎提交Issue和Pull Request。请先阅读`CONTRIBUTING.md`（待创建）了解开发规范。

## 许可证

本项目为私有项目，版权所有。

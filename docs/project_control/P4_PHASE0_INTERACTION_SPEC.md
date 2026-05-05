# P4.phase0 交互设计产物（R02A）

## Meta
- 对应任务：`P4.phase0-R02A`
- 目的：先完成动态交互逻辑线框设计，通过评审后再进入前端架构开发。

## 1. 线框状态集
- 主态：三栏完整展示（ThemeRadar / IntelStream / MarketValidation）
- 空态：无题材、无情报、无验证数据
- Loading态：三栏独立 loading，不互相阻塞
- Error态：面板级错误提示，不阻塞全页
- Fallback态：stream 异常自动切 feed，顶部显示 `stream_state=fallback`

## 2. 动态交互时序
1. 左栏点击主题
- 更新 `selectedTheme`
- 中栏按 `subject_key` 过滤
- 右栏刷新主题级验证

2. 中栏点击事件
- 更新 `activeIntelItemId`
- 若事件含 `stockId`，更新 `selectedStock`
- 右栏切换个股验证视图

3. 日期切换
- 更新 `recapDate`
- 三栏并行刷新
- stream 进入回放/静态模式

4. stream 异常
- `stream_state=error`
- 自动切 `feed` 拉取
- 恢复后 `stream_state=connected`

## 3. 布局规范
- 桌面端：`280 / auto / 320`
- 平板端：左中两栏，右栏抽屉化
- 移动端：单栏堆叠（左→中→右）
- 右栏最小宽度：`300px`
- 中栏最小宽度：`640px`

## 4. 开发前置验收清单（Gate）
- [ ] 线框图与状态稿评审通过
- [ ] 交互时序图评审通过
- [ ] 布局规范评审通过
- [ ] 联动冒烟清单通过（左驱中/中驱右/日期切换/fallback）

> Gate 规则：以上 4 项未全通过，不进入前端架构开发任务。

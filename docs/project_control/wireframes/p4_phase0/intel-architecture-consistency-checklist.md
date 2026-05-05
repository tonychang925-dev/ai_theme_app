# Intel 交互一致性清单（旧链复刻评估）

评估对象：`intel-architecture-demo.html`
基线来源：`frontend/src/routes/intel/IntelPage.tsx`、`useIntelFeed.ts`、`IntelFilters.tsx`、`IntelListItem.tsx`

## A. 导航与页面入口
- [x] 顶部 6 个功能按钮存在并可跳转
- [x] 盘后复盘按钮携带 `date` 参数
- [x] 盘前必读按钮携带 `date` 参数
- [x] 中栏双击可跳转题材详情 `/themes/:subjectKey`
- [x] 右栏增加个股详情快捷跳转 `/stocks/:stockId`

评分：5/5

## B. 三栏联动逻辑
- [x] 左栏点击主题 -> 中栏按 `subject_key` 过滤
- [x] 中栏点击事件 -> 更新 `activeIntelItemId`
- [x] 中栏点击事件 -> 更新 `selectedStock` 并驱动右栏
- [x] 日期/session/type 切换 -> 三栏同步刷新

评分：4/4

## C. URL 状态同步
- [x] `date` 同步
- [x] `session` 同步
- [x] `type` 同步
- [x] `subject_key` 同步
- [x] `stock_id` 同步
- [x] `item` 同步

评分：6/6

## D. 实时通信与兜底
- [x] SSE 状态显示（connecting/connected/error）
- [x] 手工触发 SSE 异常
- [x] 异常后切换 feed 轮询兜底
- [x] 轮询状态可见（idle/running）

评分：4/4

## E. 右栏验证可解释性
- [x] 候选级别/支撑类型/分数可见
- [x] 增加“查看验证细节”弹层
- [x] 弹层可关闭并显示结构化 payload

评分：3/3

## 总分
- 22 / 22（100%）

## 仍与生产代码存在的差异（说明）
1. 当前为演示页面，数据为 mock，不直接请求真实后端。
2. 右栏细节弹层字段为示例结构，正式值需来自 `/api/v2/workspace/market-validation`。
3. SSE 为前端模拟时钟推送，非真实 EventSource 连接。

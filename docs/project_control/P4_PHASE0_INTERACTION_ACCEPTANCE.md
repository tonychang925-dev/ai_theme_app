# P4.phase0 交互设计与动态联动验收清单（R02A）

## 1. 验收范围
- 页面：`/intel`
- 三栏：`ThemeRadarPanel / IntelStreamPanel / MarketValidationPanel`
- 数据口径：仅 `/api/v2/*`

## 2. 线框态清单
1. 主态（有数据）
2. 空态（当日无数据）
3. loading 态（接口请求中）
4. error 态（接口失败）
5. fallback 态（stream 异常后回退 feed）

## 3. 动态交互时序
1. 左驱中
- 点击左栏主题 -> 中栏按主题过滤 -> 右栏刷新主题验证

2. 中驱右
- 点击中栏事件 -> 若含 `stock_id`，右栏切到个股验证
- 若不含 `stock_id`，右栏保持主题验证

3. 日期切换
- 修改日期 -> 三栏同时刷新
- stream 断连时自动切 feed，并显示 fallback 状态

4. SSE -> Feed fallback
- stream 报错/断开 -> 自动请求 `/api/v2/intel/feed`
- 页面展示 fallback 原因与恢复时间（若有）

## 4. 布局规范
1. 桌面端三栏固定：左 24% / 中 46% / 右 30%
2. 最小宽度：左>=260，中>=420，右>=320
3. 中栏独立滚动，左右栏吸顶
4. 移动端降级为纵向堆叠（左->中->右）

## 5. 验收命令
```bash
curl -i "http://127.0.0.1:5173/api/v2/intel/feed?date=2026-04-29&type=all&session=all&limit=20"
curl -i "http://127.0.0.1:5173/api/v2/workspace/intel-context?date=2026-04-29&session=all&limit=20"
curl -i "http://127.0.0.1:5173/api/v2/workspace/market-validation?trade_date=2026-04-29"
```

## 6. 通过标准
1. 三栏联动链路全部可复现，且无 `request failed: 503`
2. stream 异常时可自动回退 feed
3. 页面不出现非 `/api/v2/*` 请求
4. 交互状态（主态/空态/loading/error/fallback）可稳定触发

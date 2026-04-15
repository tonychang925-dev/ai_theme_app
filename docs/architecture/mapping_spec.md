# 弱转强 P0 协议：主键映射规范（mapping_spec）

版本：`mapping_spec.v1`

## 1. 目标

统一弱转强链路中的实体主键，确保盘后候选池、盘前确认、回放与提示使用同一标识体系。

## 2. 标准主键

1. 个股主键：`stock_id`  
   格式：`000001.SZ` / `600000.SH` / `430001.BJ`
2. 题材主键：`subject_key`  
   来源：`theme_master.subject_key`
3. 题材展示名：`theme_name`  
   来源：`theme_master.theme_name`
4. 交易日：`trade_date`  
   格式：`YYYY-MM-DD`

## 3. 映射优先级

### 3.1 stock_id 规范化

1. 若已为标准格式（含后缀），直接使用
2. 若为6位纯数字，按规则补后缀  
   `60/68 -> SH`，`00/30 -> SZ`，`43/83/87 -> BJ`
3. 若无法判定后缀，标记映射失败并进入 `mapping_error`

### 3.2 题材映射

1. 先按 `subject_key` 直接关联 `theme_master`
2. 若缺失，按候选来源中的规范化题材名回查（仅用于补全展示，不改变主键）
3. 若仍缺失，`subject_key = "__UNKNOWN__"`，并写入 evidence 的 `mapping_warnings`

## 4. 一致性约束

1. 同一 `trade_date + stock_id` 在候选池中只能有一条正式记录
2. 盘前信号必须带 `candidate_id`，且可反查候选池
3. `theme_name` 可变，`subject_key` 不可漂移

## 5. 错误处理

1. `stock_id` 无法规范化：拒绝进入正式信号流
2. `subject_key` 缺失：可进入观察流，但必须标记 `mapping_warnings`
3. 映射冲突：以 `theme_master` 真源为准，冲突写入审计日志

## 6. 验收清单（P0 Gate）

1. 样本校验中 `stock_id` 标准化成功率 >= 99%
2. 候选池与盘前确认可通过 `candidate_id` 全量回溯
3. 映射失败记录可追踪，不允许静默吞掉

---

# 主线周期判定 P0 协议：主题映射规范

版本：`theme_cycle_mapping_spec.v1`

## 1. 目标

统一主线周期判定中的主题标识映射，确保证据表、判定表、候选池使用同一主题体系。

## 2. 标准主键

1. **主题主键**：`subject_key`  
   来源：`theme_master.subject_key`
2. **主题展示名**：`theme_name`  
   来源：`theme_master.theme_name`
3. **交易日**：`trade_date`  
   格式：`YYYY-MM-DD`
4. **龙头个股**：`leader_stock_id`  
   格式：`000001.SZ`，可为空

## 3. 映射优先级

### 3.1 subject_key 规范化

1. 优先使用 `theme_master.subject_key` 作为唯一标识
2. 若 `theme_master` 中不存在，使用 `subject_stock_daily_snapshot.subject_key` 作为候选
3. 若仍缺失，`subject_key = "__UNKNOWN__"`，并在 `evidence_json` 中记录映射警告

### 3.2 theme_name 补全策略

1. 优先使用 `theme_master.theme_name`
2. 若缺失，使用 `subject_stock_daily_snapshot.subject_key` 作为展示名
3. 若 `subject_key` 为 `"__UNKNOWN__"`，`theme_name = "未知主题"`

### 3.3 龙头个股映射

1. 龙头个股必须为标准 `stock_id` 格式
2. 若龙头个股不存在或已退市，`leader_stock_id = NULL`，`leader_alive_score = 0`

## 4. 一致性约束

1. 同一 `trade_date + subject_key` 在证据表和判定表中只能有一条记录
2. 候选池中的 `cycle_state`、`fade_watch`、`fade_confirmed` 必须与判定表保持一致
3. `theme_name` 可变，`subject_key` 不可漂移

## 5. 错误处理

1. `subject_key` 缺失：可进入观察流，但必须标记映射警告
2. 主题映射冲突：以 `theme_master` 真源为准，冲突写入审计日志
3. 龙头个股映射失败：`leader_alive_score` 降为0，不影响其他证据层评分

## 6. 验收清单

1. 样本校验中 `subject_key` 映射成功率 >= 99%
2. 证据表与判定表可通过 `(trade_date, subject_key)` 全量关联
3. 映射失败记录可追踪，不允许静默吞掉


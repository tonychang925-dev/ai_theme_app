# 菲娱恒丰增量同步 SOP

适用范围：`P2.phase1`

目标：将久赢恒丰新增数据按固定链路同步到本地文件、数据库真源、staging、serving 与只读 API。

## 1. 总体链路
```text
久赢恒丰 API
-> theme_data_complete/*
-> manifest / cursor / changed_subjects
-> nodes / history(type=3 全局事件流) / detail / stock 四条增量导库链
-> staging / serving 刷新
-> phase1 只读 API
```

## 2. 同步原则
- 日常同步默认先跑 `lists_only`，不允许默认全量拉全部题材。
- 只有显式 `--full` 时，才允许全量采集。
- 所有导库链都必须支持 `--batch-id` 与 `--subjects-file`。
- 所有导库链必须按 `subject_key` 幂等重放。
- 日常同步不允许以 `DELETE + 全量重建` 作为主路径。
- `history` 日常增量不再按单题材逐个轮询 `subjectId`，而是统一抓取 `subject/top-history?type=3` 全局事件流。
- `history` 增量游标以事件真实时间为准：`createTime -> updateTime -> rankDate`。
- 日常执行默认遵循“两步式”：
  1. 先检查本地数据并生成增量清单
  2. 再按清单只下载缺失增量并统一入库

## 3. 元数据与状态
数据库状态表：
- `jyhf_sync_batch`
- `jyhf_sync_file_manifest`
- `jyhf_sync_subject_state`

本地状态文件：
- `theme_data_complete/_manifests/<batch_id>.json`
- `theme_data_complete/_state/sync_cursor.json`

## 4. 脚本职责
采集与判定：
- [sync_jyhf_to_local.py](/Users/admin/Desktop/ai_theme_app/sync_jyhf_to_local.py)
- [register_jyhf_sync_manifest.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/register_jyhf_sync_manifest.py)
- [detect_jyhf_changed_subjects.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/detect_jyhf_changed_subjects.py)

四条增量导库链：
- [import_jyhf_to_financial_and_theme.py](/Users/admin/Desktop/ai_theme_app/import_jyhf_to_financial_and_theme.py)
- [import_jyhf_history_incremental.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/import_jyhf_history_incremental.py)
- [import_jyhf_detail_incremental.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/import_jyhf_detail_incremental.py)
- [import_jyhf_stock_incremental.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/import_jyhf_stock_incremental.py)

画像链：
- [build_subject_gate_final.py](/Users/admin/Desktop/ai_theme_app/build_subject_gate_final.py)
- [import_jyhf_gate_profile.py](/Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py)
- [build_theme_profile_ext.py](/Users/admin/Desktop/ai_theme_app/build_theme_profile_ext.py)
- [build_theme_profile_ext_embedding.py](/Users/admin/Desktop/ai_theme_app/build_theme_profile_ext_embedding.py)

## 5. 日常同步执行顺序
### 日常推荐入口
如果你的要求是：
- 有新题材时自动补采并按增量链导库
- 没有新题材时也要把当天新增的情报事件导入数据库

优先直接运行：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python daily_jyhf_sync.py
```

该脚本会固定执行：
1. 先检查本地数据并生成增量清单
2. `lists_only` 拉取最新题材列表并识别新增题材
3. 对新增题材执行 `details/history/children/daily/stock_details` 采集与增量导库
4. 通过 `subject/top-history?type=3` 全局事件流刷新 `history`
5. 对指定 `trade-date` 只补缺失的股票快照题材
6. 执行导库，确保 `subject_history_staging / news_event / event_theme_map` 保持每日新增
7. 最后回写 `sync_cursor.json` 到本次 `lists` 批次

### 日常最短命令
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python daily_jyhf_sync.py --trade-date $(date +%F)
```

如果只想先生成清单，不立刻采集和导库：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python daily_jyhf_sync.py --trade-date $(date +%F) --plan-only
```

如果只想单独刷新情报事件：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python sync_jyhf_to_local.py \
  --batch-id jyhf_history_$(date +%Y%m%d%H%M%S) \
  --use-latest-list-subjects \
  --types history \
  --history-mode incremental \
  --history-max-pages 20
```

然后导库：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python database_service/scripts/import_jyhf_history_incremental.py \
  --batch-id <history_batch_id> \
  --mode append
```

如果要回补某一天缺失的情报事件，例如 `2026-04-01`：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python daily_jyhf_sync.py \
  --trade-date 2026-04-01 \
  --backfill-history-date 2026-04-01
```

说明：
- `--backfill-history-date` 会忽略“最新时间水位跳过更早事件”的限制
- 只回补指定日期的 `type=3` 全局情报事件
- 适合补齐某一天的缺失数据

### Step 1. 拉取 lists
```bash
cd /Users/admin/Desktop/ai_theme_app
AUTHORIZATION="..." .venv/bin/python sync_jyhf_to_local.py --batch-id jyhf_lists_$(date +%Y%m%d%H%M%S) --write-cursor
```

### Step 2. 注册 manifest
```bash
cd /Users/admin/Desktop/ai_theme_app
POSTGRES_DATABASE=stock_data_test .venv/bin/python database_service/scripts/register_jyhf_sync_manifest.py \
  --manifest theme_data_complete/_manifests/<batch_id>.json
```

### Step 3. 计算 changed_subjects
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python database_service/scripts/detect_jyhf_changed_subjects.py \
  --manifest theme_data_complete/_manifests/<batch_id>.json \
  --cursor theme_data_complete/_state/sync_cursor.json \
  --output tmp/jyhf_changed_subjects_<batch_id>.json
```

判定规则：
- `global_changed = true`：先执行 `nodes`
- `changed_subjects > 0`：再执行 `detail / stock`
- 都没有变化：本轮结束

### Step 4. nodes 增量导库
```bash
cd /Users/admin/Desktop/ai_theme_app
POSTGRES_DATABASE=stock_data_test .venv/bin/python import_jyhf_to_financial_and_theme.py
```

### Step 5. history 增量导库
`history` 已经改成独立于 `changed_subjects` 的全局情报事件流。

采集：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python sync_jyhf_to_local.py \
  --batch-id jyhf_history_$(date +%Y%m%d%H%M%S) \
  --use-latest-list-subjects \
  --types history \
  --history-mode incremental \
  --history-max-pages 20
```

如果要按指定日期回补：
```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python sync_jyhf_to_local.py \
  --batch-id jyhf_history_backfill_$(date +%Y%m%d%H%M%S) \
  --use-latest-list-subjects \
  --types history \
  --history-mode incremental \
  --history-max-pages 20 \
  --history-backfill-date 2026-04-01
```

导库：
```bash
cd /Users/admin/Desktop/ai_theme_app
POSTGRES_DATABASE=stock_data_test .venv/bin/python database_service/scripts/import_jyhf_history_incremental.py \
  --batch-id <history_batch_id> \
  --mode append
```

说明：
- 采集源是 `GET /api/app/subject/top-history?type=3&pageNum=...&pageSize=...`
- 返回结构使用 `rows`
- 支持 `--history-backfill-date YYYY-MM-DD` 指定日期回补
- 导库会把事件写入 `subject_history_staging / subject_rank_daily`
- 同时补写 synthetic `news_event / event_theme_map`

### Step 6. detail/profile 增量导库
```bash
cd /Users/admin/Desktop/ai_theme_app
POSTGRES_DATABASE=stock_data_test .venv/bin/python database_service/scripts/import_jyhf_detail_incremental.py \
  --subjects-file tmp/jyhf_changed_subject_keys.txt \
  --batch-id <batch_id>
```

### Step 7. stock 增量导库
```bash
cd /Users/admin/Desktop/ai_theme_app
POSTGRES_DATABASE=stock_data_test .venv/bin/python database_service/scripts/import_jyhf_stock_incremental.py \
  --subjects-file tmp/jyhf_changed_subject_keys.txt \
  --batch-id <batch_id>
```

## 6. 股票底表补齐
- [unified_data_manager.py](/Users/admin/Desktop/ai_theme_app/unified_data_manager.py) 已改为优先从 `*_stocks.jsonl` 扫描股票集合。
- 审计脚本：
  - [audit_stock_coverage.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/audit_stock_coverage.py)

## 7. Gate / Profile 全量重建
顺序固定：
1. [build_subject_gate_final.py](/Users/admin/Desktop/ai_theme_app/build_subject_gate_final.py)
2. [import_jyhf_gate_profile.py](/Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py)
3. [build_theme_profile_ext.py](/Users/admin/Desktop/ai_theme_app/build_theme_profile_ext.py)
4. [build_theme_profile_ext_embedding.py](/Users/admin/Desktop/ai_theme_app/build_theme_profile_ext_embedding.py)

## 8. 当前状态
已完成：
- `lists_only + manifest + cursor + changed_subjects`
- `nodes` 增量链
- `history(type=3 全局事件流)` 增量链
- `detail/profile/snapshot` 增量链
- `stock` 增量链
- 股票缺失扫描逻辑修正

待人工运行验收：
- 正式 token 下的日常增量批次
- 全量 gate/profile 重建
- 性能压测

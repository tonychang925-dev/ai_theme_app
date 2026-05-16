# 盘前必读 E2E 多题材回放评测

本目录用于把 `evaluate_service/data/raw/test_cases.txt` 回放到 `stream:news:raw`，验证从原始新闻到盘前必读快照与 SPS API 的新链路。

核心约束：

- 默认数据库是 `stock_data`。
- 脚本默认拒绝连接 `stock_data_test`，避免污染当前项目实际生产角色库。
- 如需让现有 SPS/前端直接查看 E2E 结果，可显式传 `--copy-snapshot-to-db stock_data_test`；这只复制最终 `pre_market_brief_snapshot`，不复制 raw/event/map 中间数据。
- `test_cases.txt` 的题材名称只写入 `gold_labels.jsonl`，不会进入 Redis Stream、`news_raw`、`news_event` 或题材匹配链路。
- 盘前必读 E2E 不经过已废弃的 `frontend_bff`，默认只请求 `stock_processing_service` 的 `/api/v1/pre_market_brief`。

常用命令：

```bash
export $(grep -v '^#' .env.e2e | xargs)

python evaluate_service/e2e/pre_market_brief/check_e2e_db_ready.py \
  --db-name stock_data \
  --trade-date 2026-05-16

python evaluate_service/e2e/pre_market_brief/run_pre_market_e2e.py \
  --test-cases evaluate_service/data/raw/test_cases.txt \
  --db-name stock_data \
  --trade-date 2026-05-16 \
  --run-id pm_e2e_smoke_20260516_001 \
  --limit 5 \
  --force-clean \
  --inject \
  --wait \
  --rebuild \
  --force-rebuild \
  --evaluate \
  --copy-snapshot-to-db stock_data_test \
  --sps-base-url http://127.0.0.1:8090
```

如果需要清掉同一 `trade_date` 上一次 E2E 生成的 final 快照，可额外传：

```bash
python evaluate_service/e2e/pre_market_brief/cleanup_e2e_run.py \
  --db-name stock_data \
  --source akshare_replay \
  --trade-date 2026-05-16 \
  --run-id pm_e2e_smoke_20260516_001 \
  --delete-final-snapshot
```

输出目录：

```text
evaluate_service/output/pre_market_e2e/<run_id>/
├── input_news.jsonl
├── gold_labels.jsonl
├── injection_result.json
├── db_trace_report.json
├── brief_snapshot.json
├── sps_payload.json
├── snapshot_copy_result.json
├── accuracy_report.json
├── stock_candidate_report.json
├── confusion_matrix.csv
└── summary.md
```

多题材映射增强不在这些脚本中实现；这些脚本只负责回放、追踪、评估。

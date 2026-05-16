# 盘前必读 E2E 多题材回放评测

本目录用于把 `evaluate_service/data/raw/test_cases.txt` 回放到 `stream:news:raw`，验证从原始新闻到盘前必读快照、SPS API、BFF 代理的全链路。

核心约束：

- 默认数据库是 `stock_data`。
- 脚本默认拒绝连接 `stock_data_test`，避免污染当前项目实际生产角色库。
- `test_cases.txt` 的题材名称只写入 `gold_labels.jsonl`，不会进入 Redis Stream、`news_raw`、`news_event` 或题材匹配链路。

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
  --evaluate
```

输出目录：

```text
evaluate_service/output/pre_market_e2e/<run_id>/
├── input_news.jsonl
├── gold_labels.jsonl
├── injection_result.json
├── db_trace_report.json
├── brief_snapshot.json
├── bff_payload.json
├── accuracy_report.json
├── stock_candidate_report.json
├── confusion_matrix.csv
└── summary.md
```

多题材映射增强不在这些脚本中实现；这些脚本只负责回放、追踪、评估。


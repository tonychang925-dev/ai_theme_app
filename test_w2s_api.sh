#!/bin/bash

# 测试弱转强API端点

echo "测试弱转强策略执行API..."
echo ""

# 发送POST请求
curl -X POST \
  http://localhost:8003/api/stock-screener/execute \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "weak_to_strong",
    "trade_date": "2026-04-07",
    "limit": 20,
    "auto_tune_min_score": true,
    "target_min_count": 30,
    "target_max_count": 120,
    "enable_llm_review": false,
    "llm_top_k": 20,
    "run_stage1": false,
    "run_stage2": true
  }' | python -m json.tool | head -100
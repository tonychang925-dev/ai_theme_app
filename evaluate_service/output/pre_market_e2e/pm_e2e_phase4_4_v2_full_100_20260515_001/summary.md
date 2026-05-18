# 盘前必读 E2E Summary

- 测试库: stock_data
- 注入/期望数量: 100
- news_raw_count: 100
- news_event_count: 100
- event_subject_map_count: 133
- review_queue_count: 15
- primary_hit_rate: 0.57
- related_hit_rate: 0.27
- theme_set_recall@5: 0.64
- wrong_related_count: 23
- generic_only_related_count: 0
- llm_anchor_guard_count: 3
- avg_match_ms: 4895.897
- p50_match_ms: 3430.547
- p95_match_ms: 13085.127
- llm_judge_count: 33
- event_profile_llm_count: 0
- profile_load_count: 4
- profile_cache_hit_count: 0
- profile_cache_miss_count: 4
- profile_map_cache_hit_count: 96
- profile_map_cache_miss_count: 4
- query_vector_cache_hit_count: 99
- query_vector_cache_miss_count: 0
- rerank_doc_vector_cache_hit_count: 2093
- rerank_doc_vector_cache_miss_count: 520
- brief_theme_count: 39
- brief_opportunity_count: 38
- 是否通过基础门禁: True

## Runtime

- sps_base_url: http://127.0.0.1:8090
- copied_snapshot_to_db: stock_data_test

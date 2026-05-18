# 盘前必读 E2E Summary

- 测试库: stock_data
- 注入/期望数量: 20
- news_raw_count: 20
- news_event_count: 16
- event_subject_map_count: 4
- review_queue_count: 1
- primary_hit_rate: 0.1
- related_hit_rate: 0.1
- theme_set_recall@5: 0.1
- wrong_related_count: 0
- generic_only_related_count: 0
- llm_anchor_guard_count: 0
- avg_match_ms: 42854.909
- p50_match_ms: 48472.237
- p95_match_ms: 61837.642
- llm_judge_count: 0
- event_profile_llm_count: 0
- profile_load_count: 1
- profile_cache_hit_count: 0
- profile_cache_miss_count: 1
- profile_map_cache_hit_count: 2
- profile_map_cache_miss_count: 1
- query_vector_cache_hit_count: 3
- query_vector_cache_miss_count: 0
- rerank_doc_vector_cache_hit_count: 27
- rerank_doc_vector_cache_miss_count: 64
- brief_theme_count: 7
- brief_opportunity_count: 7
- 是否通过基础门禁: False

## Runtime

- sps_base_url: http://127.0.0.1:8090
- copied_snapshot_to_db: stock_data_test

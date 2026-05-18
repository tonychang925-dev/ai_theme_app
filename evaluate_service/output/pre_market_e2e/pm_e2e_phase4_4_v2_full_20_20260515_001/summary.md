# 盘前必读 E2E Summary

- 测试库: stock_data
- 注入/期望数量: 20
- news_raw_count: 20
- news_event_count: 20
- event_subject_map_count: 26
- review_queue_count: 4
- primary_hit_rate: 0.65
- related_hit_rate: 0.45
- theme_set_recall@5: 0.65
- wrong_related_count: 2
- generic_only_related_count: 0
- llm_anchor_guard_count: 0
- avg_match_ms: 13553.137
- p50_match_ms: 12165.516
- p95_match_ms: 21136.892
- llm_judge_count: 3
- event_profile_llm_count: 0
- profile_load_count: 1
- profile_cache_hit_count: 0
- profile_cache_miss_count: 1
- profile_map_cache_hit_count: 18
- profile_map_cache_miss_count: 1
- rerank_doc_vector_cache_hit_count: 390
- rerank_doc_vector_cache_miss_count: 159
- brief_theme_count: 6
- brief_opportunity_count: 6
- 是否通过基础门禁: True

## Runtime

- sps_base_url: http://127.0.0.1:8090
- copied_snapshot_to_db: stock_data_test

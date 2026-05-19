# 盘前必读 E2E Summary

- 测试库: stock_data
- 注入/期望数量: 100
- news_raw_count: 100
- news_event_count: 100
- decision_entry_count: 100
- decision_distinct_event_count: 100
- duplicate_decision_event_count: 0
- terminal_distinct_event_count: 100
- non_terminal_event_count: 0
- decision_seen_but_no_output_count: 0
- event_subject_map_count: 86
- mapped_distinct_event_count: 86
- review_queue_count: 11
- review_distinct_event_count: 11
- pending_distinct_event_count: 3
- primary_hit_rate: 0.72
- related_hit_rate: 0.0
- theme_set_recall@5: 0.72
- wrong_related_count: 0
- neighbor_related_count: 0
- over_expanded_related_count: 0
- generic_only_related_count: 0
- llm_anchor_guard_count: 4
- avg_match_ms: 7117.809
- p50_match_ms: 4924.722
- p95_match_ms: 14950.615
- llm_judge_count: 99
- event_profile_llm_count: 0
- profile_load_count: 3
- profile_cache_hit_count: 0
- profile_cache_miss_count: 3
- profile_map_cache_hit_count: 97
- profile_map_cache_miss_count: 3
- query_vector_cache_hit_count: 99
- query_vector_cache_miss_count: 0
- rerank_doc_vector_cache_hit_count: 2130
- rerank_doc_vector_cache_miss_count: 478
- brief_theme_count: 25
- brief_opportunity_count: 24
- numeric_theme_name_count: 0
- unnamed_theme_count: 2
- subject_key_chip_count: 0
- 是否通过基础门禁: True

## Runtime

- sps_base_url: http://127.0.0.1:8090
- copied_snapshot_to_db: stock_data_test

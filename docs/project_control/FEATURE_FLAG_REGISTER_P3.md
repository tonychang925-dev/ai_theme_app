# P3 Feature Flag Register

| Flag | Scope | Default | Rollback Strategy | Owner | Notes |
| --- | --- | --- | --- | --- | --- |
| `SPS_READ_FROM_NEW_SNAPSHOTS` | `frontend_bff` / `recap_service` | `false` | switch to legacy `stock_service` read path | Backend | P3.phase2 before gray rollout |
| `SPS_WRITE_OBJECTS_ENABLED` | `stock_processing_service` writer | `false` | stop new writes, keep read-only | Backend | P3.phase1 gate close before enable |
| `SPS_STREAM_PUBLISH_ENABLED` | stream event publish | `false` | disable publish, keep DB objects | Data | P3.phase1-T12 close-loop gate |


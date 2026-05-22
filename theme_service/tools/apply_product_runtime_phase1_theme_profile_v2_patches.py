from __future__ import annotations

# Backward-compatible entry point. Phase 2 owns the current product runtime
# profile patch set, including the original Phase 1 high-noise repairs.
from theme_service.tools.apply_product_runtime_phase2_theme_profile_v2_patches import main


if __name__ == "__main__":
    main()

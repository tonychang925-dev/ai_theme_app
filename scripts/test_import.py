#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
    print("✅ EnhancedCandidateBuilder 导入成功")

    from stock_service.services.enhanced_mainline_judgement_service import EnhancedMainlineJudgementService
    print("✅ EnhancedMainlineJudgementService 导入成功")

    from stock_service.services.enhanced_cycle_judgement_service import EnhancedCycleJudgementService
    print("✅ EnhancedCycleJudgementService 导入成功")

except ImportError as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
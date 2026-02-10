#!/bin/bash
# evaluate_service/runners/run_regenerate_events.sh
#!/bin/bash

echo "🚀 开始重新生成事件数据..."

# 设置Python路径
export PYTHONPATH=$(pwd):$PYTHONPATH

# 运行重新生成脚本
python evaluate_service/scripts/regenerate_events.py

# 运行数据完整性验证
python evaluate_service/scripts/verify_data_integrity.py

echo "✅ 数据处理完成!"
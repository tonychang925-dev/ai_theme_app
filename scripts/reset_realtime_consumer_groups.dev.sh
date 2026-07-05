#!/usr/bin/env bash
# 紧急重置 realtime consumer groups（仅测试环境使用）
# 用途：当 consumer 卡死、lag 堆积、pending 无法清理时使用
#
# 警告：DESTROY 会丢失 consumer group 的 last-delivered-id，
#       重启后 consumer 会从最新消息开始读，中间的消息可能被跳过。

set -euo pipefail

echo "=============================================="
echo " DANGER: DEV / TEST ONLY"
echo " DESTROY consumer groups = lose read position"
echo " Do NOT run in production"
echo "=============================================="
echo ""

STREAM="stream:news:raw"

echo "=== 重置 realtime consumer groups ==="

# 1. Destroy old groups
redis-cli XGROUP DESTROY "$STREAM" news_processor_realtime 2>/dev/null && echo "  destroyed news_processor_realtime" || echo "  news_processor_realtime not found (OK)"
redis-cli XGROUP DESTROY "$STREAM" news_storage_realtime 2>/dev/null && echo "  destroyed news_storage_realtime" || echo "  news_storage_realtime not found (OK)"

# 2. Recreate groups from latest ($)
redis-cli XGROUP CREATE "$STREAM" news_processor_realtime '$' MKSTREAM 2>/dev/null && echo "  created news_processor_realtime" || echo "  news_processor_realtime already exists (OK)"
redis-cli XGROUP CREATE "$STREAM" news_storage_realtime '$' MKSTREAM 2>/dev/null && echo "  created news_storage_realtime" || echo "  news_storage_realtime already exists (OK)"

# 3. Clean all runtime pidfiles
rm -f logs/realtime/runtime/*.pid logs/realtime/runtime/realtime_stack.json 2>/dev/null && echo "  cleaned runtime pidfiles" || true

echo ""
echo "Done. Now run: ./scripts/start_new_chain_stack.sh --restart --with-frontend --start-realtime"

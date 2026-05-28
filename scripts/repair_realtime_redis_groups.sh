#!/usr/bin/env bash
# scripts/repair_realtime_redis_groups.sh
# Phase 6A: Redis Consumer Group 诊断/修复脚本
#
# 用法:
#   诊断所有实时 group:
#     ./scripts/repair_realtime_redis_groups.sh --dry-run
#
#   修复指定 group 到最新位置:
#     ./scripts/repair_realtime_redis_groups.sh \
#       --stream stream:events:normal \
#       --group news_processor_realtime \
#       --reset-to-latest
#
#   修复所有实时 group 到最新:
#     ./scripts/repair_realtime_redis_groups.sh --reset-all-to-latest
set -euo pipefail

REDIS_CLI="${REDIS_CLI:-redis-cli}"
DRY_RUN=false
RESET_TO_LATEST=false
RESET_ALL=false
TARGET_STREAM=""
TARGET_GROUP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --reset-to-latest) RESET_TO_LATEST=true; shift ;;
    --reset-all-to-latest) RESET_ALL=true; RESET_TO_LATEST=true; shift ;;
    --stream) TARGET_STREAM="$2"; shift 2 ;;
    --group) TARGET_GROUP="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--dry-run] [--stream S] [--group G] [--reset-to-latest] [--reset-all-to-latest]"; exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

declare -A RT_GROUPS
RT_GROUPS["stream:news:raw"]="news_storage_realtime"
RT_GROUPS["stream:events:normal"]="news_processor_realtime"
RT_GROUPS["stream:events:structured"]="theme_processor_realtime"
RT_GROUPS["stream:events:decision"]="decision_executor_realtime"

get_stream_len() { $REDIS_CLI xlen "$1" 2>/dev/null || echo "0"; }

diagnose_group() {
  local stream="$1" group="$2"
  local stream_len lag consumers pending
  stream_len=$(get_stream_len "$stream")
  lag=-1; consumers=-1; pending=-1

  local last_key="" in_target=false
  local group_info
  group_info=$($REDIS_CLI xinfo groups "$stream" 2>/dev/null || true)
  while IFS= read -r line; do
    line=$(echo "$line" | xargs)
    [[ -z "$line" ]] && continue
    if [[ "$line" == "$group" ]]; then in_target=true; last_key=""; continue; fi
    if $in_target; then
      if [[ -z "$last_key" ]]; then
        case "$line" in consumers|pending|lag|last-delivered-id|entries-read) last_key="$line" ;; name) in_target=false ;; esac
      else
        case "$last_key" in consumers) consumers="$line" ;; pending) pending="$line" ;; lag) lag="$line" ;; esac
        last_key=""
      fi
    fi
  done <<< "$group_info"

  local zombie=0 last_ckey=""
  local consumer_info
  consumer_info=$($REDIS_CLI xinfo consumers "$stream" "$group" 2>/dev/null || true)
  while IFS= read -r line; do
    line=$(echo "$line" | xargs)
    [[ -z "$line" ]] && continue
    if [[ -z "$last_ckey" ]]; then
      case "$line" in name|idle|inactive|pending) last_ckey="$line" ;; *) last_ckey="" ;; esac
    else
      case "$last_ckey" in idle|inactive) [[ "$line" =~ ^[0-9]+$ ]] && [[ "$line" -gt 60000 ]] && zombie=$((zombie + 1)) ;; esac
      last_ckey=""
    fi
  done <<< "$consumer_info"

  local stuck=false suggested=""
  [[ "$lag" =~ ^[0-9]+$ && "$lag" -gt 1000 ]] && stuck=true
  [[ "$pending" =~ ^[0-9]+$ && "$pending" -gt 1000 ]] && stuck=true
  [[ "$consumers" =~ ^[0-9]+$ && "$consumers" -gt 10 ]] && stuck=true
  $stuck && suggested="建议: $0 --stream $stream --group $group --reset-to-latest"

  printf "%-6s %-28s %-24s %-6s %-6s %-7s %-6s %-6s %s\n" \
    "$($stuck && echo "❌STUCK" || echo "✅OK")" "$stream" "$group" \
    "$stream_len" "$lag" "$pending" "$consumers" "$zombie" \
    "${suggested:+⚠️ $suggested}"
}

repair_group_to_latest() {
  local stream="$1" group="$2"
  echo ""; echo "🔧 修复: $stream / $group → reset to \$"
  echo "📋 BEFORE: stream_len=$($REDIS_CLI xlen "$stream" 2>/dev/null)"
  if $DRY_RUN; then
    echo "🔍 [DRY-RUN] 将执行: XGROUP DESTROY $stream $group; XGROUP CREATE $stream $group '\$' MKSTREAM"
    return
  fi
  echo "⚡ 执行修复..."
  $REDIS_CLI xgroup destroy "$stream" "$group" 2>/dev/null || true
  $REDIS_CLI xgroup create "$stream" "$group" '$' mkstream 2>/dev/null
  echo "✅ 完成"
  echo "📋 AFTER: stream_len=$($REDIS_CLI xlen "$stream" 2>/dev/null)"
}

echo "🔍 Redis Consumer Group 诊断 / 修复  $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

if $RESET_ALL; then
  for stream in "${!RT_GROUPS[@]}"; do repair_group_to_latest "$stream" "${RT_GROUPS[$stream]}"; done
  exit 0
fi

if $RESET_TO_LATEST && [[ -n "$TARGET_STREAM" && -n "$TARGET_GROUP" ]]; then
  repair_group_to_latest "$TARGET_STREAM" "$TARGET_GROUP"
  exit 0
fi

printf "%-8s %-28s %-24s %-6s %-6s %-7s %-9s %-6s %s\n" "STATUS" "STREAM" "GROUP" "XLEN" "LAG" "PENDING" "CONSUMERS" "ZOMBIE" "NOTE"
printf "%s\n" "$(printf '=%.0s' {1..140})"
for stream in "${!RT_GROUPS[@]}"; do diagnose_group "$stream" "${RT_GROUPS[$stream]}"; done
echo ""; echo "💡 --reset-to-latest --stream <S> --group <G>  修复卡死的 group"
echo "💡 --reset-all-to-latest  修复所有实时 group"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] python not found or not executable: $PYTHON_BIN"
  exit 1
fi

required_vars=(
  REPLAY_SHENJIAN_OLD_JSON
  REPLAY_SHENJIAN_NEW_JSON
  REPLAY_LIANDE_OLD_JSON
  REPLAY_LIANDE_NEW_JSON
)

missing=0
for var in "${required_vars[@]}"; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    echo "[MISSING] env $var is not set"
    missing=1
    continue
  fi
  if [[ ! -f "$val" ]]; then
    echo "[MISSING] file for $var not found: $val"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "[ERROR] replay input env/files are incomplete."
  echo "Example:"
  echo "  export REPLAY_SHENJIAN_OLD_JSON=/abs/path/shenjian_old.json"
  echo "  export REPLAY_SHENJIAN_NEW_JSON=/abs/path/shenjian_new.json"
  echo "  export REPLAY_LIANDE_OLD_JSON=/abs/path/liande_old.json"
  echo "  export REPLAY_LIANDE_NEW_JSON=/abs/path/liande_new.json"
  exit 2
fi

export REPLAY_ENABLE_REAL=1

echo "[RUN] replay samples: SHENJIAN + LIANDE"
"$PYTHON_BIN" -m pytest -q \
  stock_processing_service/tests/replay/test_replay_shenjian_2026_04_07.py \
  stock_processing_service/tests/replay/test_replay_liande_2026_04_15.py

echo "[SUMMARY] replay outputs"
for sample in SHENJIAN LIANDE; do
  out_dir="tmp/replay/${sample}"
  summary_path="${out_dir}/summary"
  diff_path="${out_dir}/diff_samples.jsonl"
  exp_path="${out_dir}/diff_explanation.md"
  echo "- ${sample}:"
  if [[ -f "$summary_path" ]]; then
    echo "  summary: ${summary_path}"
    cat "$summary_path"
  else
    echo "  summary: missing"
  fi
  if [[ -f "$diff_path" ]]; then
    echo "  diff_samples: ${diff_path}"
  else
    echo "  diff_samples: missing"
  fi
  if [[ -f "$exp_path" ]]; then
    echo "  diff_explanation: ${exp_path}"
  else
    echo "  diff_explanation: missing"
  fi
done


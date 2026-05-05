#!/usr/bin/env bash

set -euo pipefail

AGENT_ID="com.ai_theme.new_chain_stack"
PLIST_PATH="$HOME/Library/LaunchAgents/${AGENT_ID}.plist"

launchctl disable "gui/$(id -u)/${AGENT_ID}" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)/${AGENT_ID}" >/dev/null 2>&1 || true

if [[ -f "$PLIST_PATH" ]]; then
  rm -f "$PLIST_PATH"
  echo "Removed: $PLIST_PATH"
else
  echo "Plist not found: $PLIST_PATH"
fi

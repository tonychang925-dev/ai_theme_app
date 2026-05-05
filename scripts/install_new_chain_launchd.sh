#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
AGENT_ID="com.ai_theme.new_chain_stack"
PLIST_PATH="$HOME/Library/LaunchAgents/${AGENT_ID}.plist"
LOG_DIR="/tmp/ai_theme_realtime"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$LOG_DIR"

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${AGENT_ID}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${ROOT_DIR}/scripts/start_new_chain_stack.sh</string>
    <string>--restart</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd_new_chain.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd_new_chain.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${AGENT_ID}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/${AGENT_ID}"
launchctl kickstart -k "gui/$(id -u)/${AGENT_ID}"

echo "Installed launchd agent: $AGENT_ID"
echo "plist: $PLIST_PATH"
echo "Check: launchctl print gui/$(id -u)/${AGENT_ID}"

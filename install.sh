#!/usr/bin/env bash
# Sci-Hub MCP Server installer
# Usage: curl -fsSL https://raw.githubusercontent.com/riichard/Sci-Hub-MCP-Server/main/install.sh | bash
set -euo pipefail

REPO="riichard/Sci-Hub-MCP-Server"
PACKAGE="sci-hub-mcp-server @ git+https://github.com/${REPO}"
LABEL="com.riichard.sci-hub-mcp"
PORT=8000

# ── helpers ──────────────────────────────────────────────────────────────────
info()  { printf '\033[1;34m➜\033[0m  %s\n' "$*"; }
ok()    { printf '\033[1;32m✓\033[0m  %s\n' "$*"; }
die()   { printf '\033[1;31m✗\033[0m  %s\n' "$*" >&2; exit 1; }

# ── 1. ensure uv is available ────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# ── 2. install the tool ──────────────────────────────────────────────────────
info "Installing sci-hub-mcp..."
uv tool install "${PACKAGE}" --force --quiet
BIN="$(uv tool dir --bin)/sci-hub-mcp"
ok "Installed: $BIN"

# ── 3. Claude Desktop config (stdio) ────────────────────────────────────────
CLAUDE_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [[ -f "$CLAUDE_CFG" ]]; then
  # Check if already configured
  if ! grep -q "sci-hub-mcp" "$CLAUDE_CFG" 2>/dev/null; then
    # Use python/jq to merge the entry if either is available
    if command -v python3 &>/dev/null; then
      python3 - "$CLAUDE_CFG" "$BIN" <<'PYEOF'
import sys, json
cfg_path, bin_path = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    cfg = json.load(f)
cfg.setdefault("mcpServers", {})["scihub"] = {
    "command": bin_path,
    "args": ["--transport", "stdio"]
}
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
      ok "Added to Claude Desktop config (stdio)"
    else
      info "Add this to $CLAUDE_CFG manually:"
      printf '  "scihub": { "command": "%s", "args": ["--transport", "stdio"] }\n' "$BIN"
    fi
  else
    ok "Claude Desktop already configured"
  fi
fi

# ── 4. optional: macOS LaunchAgent (HTTP service, auto-starts on login) ──────
if [[ "$(uname)" == "Darwin" ]] && [[ "${1:-}" == "--service" ]]; then
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST="$PLIST_DIR/$LABEL.plist"
  LOG_DIR="$HOME/Library/Logs"

  mkdir -p "$PLIST_DIR" "$LOG_DIR"

  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>         <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${BIN}</string>
    <string>--transport</string>   <string>streamable-http</string>
    <string>--host</string>        <string>127.0.0.1</string>
    <string>--port</string>        <string>${PORT}</string>
  </array>
  <key>RunAtLoad</key>     <true/>
  <key>KeepAlive</key>     <true/>
  <key>StandardOutPath</key>  <string>${LOG_DIR}/sci-hub-mcp.log</string>
  <key>StandardErrorPath</key> <string>${LOG_DIR}/sci-hub-mcp.err</string>
</dict>
</plist>
PLIST

  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  ok "Service installed — starts on login, running at http://127.0.0.1:${PORT}/mcp"
  info "Logs: $LOG_DIR/sci-hub-mcp.log"
  info "Stop:  launchctl unload $PLIST"
fi

# ── done ─────────────────────────────────────────────────────────────────────
echo ""
ok "Done! Run 'sci-hub-mcp --help' to see options."
if [[ "${1:-}" != "--service" ]]; then
  echo ""
  echo "  Claude Desktop (stdio — recommended):"
  echo "    sci-hub-mcp --transport stdio    ← Claude Desktop starts this automatically"
  echo ""
  echo "  Persistent HTTP service (starts on login):"
  printf '    bash install.sh --service\n'
fi

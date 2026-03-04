#!/usr/bin/env bash
# install.sh — Set up the Telegram idle notifier hook for Claude Code
#
# Run once from the repo root:
#   bash claude/telegram-idle-hook/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
PYTHON="/usr/bin/python3"

echo "=== Telegram Idle Hook Installer ==="
echo ""

# ── 1. Create hooks directory ─────────────────────────────────────────────────
if [[ ! -d "$HOOKS_DIR" ]]; then
  echo "Creating $HOOKS_DIR …"
  mkdir -p "$HOOKS_DIR"
fi

# ── 2. Symlink hook scripts ───────────────────────────────────────────────────
SHELL_HOOK="$HOOKS_DIR/telegram-idle-notify.sh"
DAEMON="$HOOKS_DIR/telegram_idle_daemon.py"

echo "Symlinking hook scripts into $HOOKS_DIR …"

ln -sf "$REPO_DIR/telegram-idle-notify.sh" "$SHELL_HOOK"
chmod +x "$REPO_DIR/telegram-idle-notify.sh"
echo "  [ok] $SHELL_HOOK"

ln -sf "$REPO_DIR/telegram_idle_daemon.py" "$DAEMON"
chmod +x "$REPO_DIR/telegram_idle_daemon.py"
echo "  [ok] $DAEMON"

# ── 3. Patch ~/.claude/settings.json ─────────────────────────────────────────
echo ""
echo "Patching $SETTINGS …"

$PYTHON - "$SETTINGS" "$SHELL_HOOK" <<'EOF'
import json, sys, pathlib

settings_path = pathlib.Path(sys.argv[1])
hook_cmd = sys.argv[2]

# Load or create settings
if settings_path.exists():
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

# Build the new Stop hook entry
new_stop_hook = {
    "hooks": [
        {
            "type": "command",
            "command": hook_cmd,
            "timeout": 15,
        }
    ]
}

stop_hooks = hooks.setdefault("Stop", [])

# Check if already installed (avoid duplicates)
hook_cmd_tilde = hook_cmd.replace(str(pathlib.Path.home()), "~")
already_installed = any(
    any(
        h.get("command") in (hook_cmd, hook_cmd_tilde)
        for h in entry.get("hooks", [])
    )
    for entry in stop_hooks
)

if already_installed:
    print("  [skip] Stop hook already present.")
else:
    # Use tilde path for portability
    new_stop_hook["hooks"][0]["command"] = hook_cmd_tilde
    stop_hooks.append(new_stop_hook)
    settings_path.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  [ok] Added Stop hook to {settings_path}")
EOF

# ── 4. Ask where the .env file should live and create/verify it ───────────────
DEFAULT_ENV="$HOME/.claude/.env"

echo ""
echo "Where should the Telegram .env file be stored?"
read -r -p "  [${DEFAULT_ENV}]: " ENV_FILE
ENV_FILE="${ENV_FILE:-$DEFAULT_ENV}"
# Expand ~ if present
ENV_FILE="${ENV_FILE/#\~/$HOME}"

if [[ -f "$ENV_FILE" ]]; then
  if grep -q "TELEGRAM_BOT_TOKEN" "$ENV_FILE" && grep -q "TELEGRAM_CHAT_ID" "$ENV_FILE"; then
    echo "  [ok] .env found with required keys."
  else
    echo "  WARNING: .env exists but is missing required keys."
    echo "  Add to $ENV_FILE:"
    echo "    TELEGRAM_BOT_TOKEN=your_token_here"
    echo "    TELEGRAM_CHAT_ID=your_chat_id_here"
  fi
else
  echo "  File not found — creating $ENV_FILE ..."
  mkdir -p "$(dirname "$ENV_FILE")"
  while [[ -z "$BOT_TOKEN" ]]; do
    read -r -s -p "  TELEGRAM_BOT_TOKEN: " BOT_TOKEN; echo
    [[ -z "$BOT_TOKEN" ]] && echo "  ERROR: Token cannot be empty."
  done
  while [[ -z "$CHAT_ID" ]]; do
    read -r -s -p "  TELEGRAM_CHAT_ID:   " CHAT_ID; echo
    [[ -z "$CHAT_ID" ]] && echo "  ERROR: Chat ID cannot be empty."
  done
  printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\n' "$BOT_TOKEN" "$CHAT_ID" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "  [ok] Created $ENV_FILE"
fi

# Patch ENV_PATH in the daemon source file
echo ""
echo "Setting ENV_PATH in daemon..."
$PYTHON - "$REPO_DIR/telegram_idle_daemon.py" "$ENV_FILE" <<'EOF'
import sys, pathlib, re
daemon = pathlib.Path(sys.argv[1])
env_path = sys.argv[2]
text = daemon.read_text(encoding="utf-8")
text = re.sub(
    r'^ENV_PATH\s*=\s*Path\(.*?\)',
    f'ENV_PATH = Path("{env_path}")',
    text,
    flags=re.MULTILINE,
)
daemon.write_text(text, encoding="utf-8")
print(f"  [ok] ENV_PATH set to {env_path}")
EOF

# ── 5. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "=== Installation complete ==="
echo ""
echo "The Stop hook will fire after every Claude response."
echo "If you don't reply within 5 minutes, Claude's last message"
echo "will be sent to Telegram. Reply there to inject it back."
echo ""
echo "Logs:  tail -f /tmp/claude_idle_daemon.log"
echo "Token: cat /tmp/claude_idle_*.json"

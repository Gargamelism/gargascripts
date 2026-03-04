#!/usr/bin/env bash
# Claude Code Stop hook — Telegram idle notifier
#
# Fires when Claude finishes responding. Immediately writes a token file and
# spawns the background daemon, then exits 0 so the Claude UI stays responsive.
#
# Exit codes:
#   0 → hook ran cleanly (always used here; all long work is in the daemon)

set -euo pipefail

DAEMON="$HOME/.claude/hooks/telegram_idle_daemon.py"
PYTHON="/opt/homebrew/bin/python3.12"

# ── Read stdin JSON from Claude ───────────────────────────────────────────────
INPUT=$(cat)

SESSION_ID=$(printf '%s' "$INPUT" | $PYTHON -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','unknown'))" \
  2>/dev/null || echo "unknown")

TRANSCRIPT_PATH=$(printf '%s' "$INPUT" | $PYTHON -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('transcript_path',''))" \
  2>/dev/null || echo "")

# ── Extract last assistant message from transcript ───────────────────────────
LAST_MSG=""
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  LAST_MSG=$($PYTHON - "$TRANSCRIPT_PATH" <<'EOF'
import sys, json
path = sys.argv[1]
last = ""
try:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Transcript entries wrap the message under a "message" key
            entry = msg.get("message", msg)
            if entry.get("role") == "assistant":
                c = entry.get("content", "")
                if isinstance(c, str):
                    last = c
                elif isinstance(c, list):
                    last = " ".join(
                        b.get("text", "") for b in c
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
except Exception:
    pass
print(last[:3000])
EOF
  2>/dev/null || echo "")
fi

if [[ -z "$LAST_MSG" ]]; then
  LAST_MSG="(Claude finished responding — no transcript available)"
fi

# ── Write token file ──────────────────────────────────────────────────────────
TOKEN_FILE="/tmp/claude_idle_${SESSION_ID}.json"
TIMESTAMP=$(date +%s)
TERM_PROG="${TERM_PROGRAM:-Terminal}"

$PYTHON -c "
import json, sys
data = {
    'session_id': sys.argv[1],
    'timestamp': int(sys.argv[2]),
    'last_message': sys.argv[3],
    'term_program': sys.argv[4],
    'token_file': sys.argv[5],
}
with open(sys.argv[5], 'w') as f:
    json.dump(data, f)
" "$SESSION_ID" "$TIMESTAMP" "$LAST_MSG" "$TERM_PROG" "$TOKEN_FILE" 2>/dev/null || true

# ── Spawn daemon detached ─────────────────────────────────────────────────────
# Kill any existing daemon instances to prevent duplicate getUpdates polling (→ 409)
pkill -f "telegram_idle_daemon.py" 2>/dev/null || true

if [[ -f "$DAEMON" ]]; then
  nohup "$PYTHON" "$DAEMON" "$TOKEN_FILE" \
    >> /tmp/claude_idle_daemon.log 2>&1 &
  disown $! 2>/dev/null || true
fi

exit 0

#!/usr/bin/env python3
"""
Telegram idle notifier daemon for Claude Code.

Spawned by telegram-idle-notify.sh after each Claude response.
Waits 5 minutes; if no new Claude activity, sends the last response
to Telegram and waits for a reply, then injects it back into Claude
Code via osascript (macOS).

Pure stdlib — no external dependencies required.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

ENV_PATH = Path("/Volumes/data_2/dev/gargascripts/python/telegram_bots/.env")

IDLE_WAIT_SECONDS = 5 * 60       # Wait this long before notifying
POLL_CHECK_INTERVAL = 30          # Seconds between activity checks during idle wait
TELEGRAM_REPLY_TIMEOUT = 15 * 60  # Give up waiting for Telegram reply after this
TELEGRAM_LONG_POLL_SECS = 30      # Telegram getUpdates long-poll timeout per call


# ── .env parser ───────────────────────────────────────────────────────────────

def load_env(path: Path) -> dict:
    config = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as e:
        log(f"Failed to read .env: {e}")
    return config


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── HTTP helpers (stdlib only) ────────────────────────────────────────────────

def _http_get(url: str, params: dict | None = None, timeout: int = 35) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _http_post(url: str, body: dict, timeout: int = 30) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ── Telegram helpers ──────────────────────────────────────────────────────────

def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    _http_post(url, {"chat_id": chat_id, "text": text})


def get_updates(token: str, offset: int | None, timeout: int) -> list:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    try:
        data = _http_get(url, params=params, timeout=timeout + 5)
        return data.get("result", [])
    except Exception as e:
        log(f"getUpdates error: {e}")
        return []


def get_update_id_baseline(token: str) -> int | None:
    """Snapshot current highest update_id to ignore pre-existing messages."""
    updates = get_updates(token, offset=None, timeout=1)
    if updates:
        return updates[-1]["update_id"] + 1
    return None


def poll_for_reply(
    token: str, chat_id: str, offset: int | None, deadline: float
) -> tuple[str | None, int | None]:
    """Long-poll until a text message from chat_id arrives or deadline passes."""
    while time.time() < deadline:
        updates = get_updates(token, offset=offset, timeout=TELEGRAM_LONG_POLL_SECS)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) == str(chat_id):
                text = msg.get("text", "").strip()
                if text:
                    return text, offset
        if not updates:
            # Empty result: either no messages (long-poll returned cleanly) or a
            # network error in get_updates. Sleep briefly to avoid spinning on errors.
            time.sleep(5)
    return None, offset


# ── macOS injection via osascript ─────────────────────────────────────────────

def inject_reply(text: str, term_program: str) -> None:
    """Paste text into the active Claude Code / Terminal window."""
    # Put text on clipboard
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)

    # Decide which app to target
    app = "Code" if "vscode" in term_program.lower() else "Terminal"

    script = f"""
        tell application "{app}" to activate
        delay 0.8
        tell application "System Events"
            tell process "{app}"
                keystroke "v" using command down
                delay 0.2
                key code 36
            end tell
        end tell
    """
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log(f"osascript error: {result.stderr.strip()}")
        raise RuntimeError("osascript injection failed")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        log("Usage: telegram_idle_daemon.py <token_file>")
        sys.exit(1)

    token_file = Path(sys.argv[1])
    log(f"Daemon started — token file: {token_file}")

    # ── Read token ────────────────────────────────────────────────────────────
    try:
        token_data = json.loads(token_file.read_text())
    except Exception as e:
        log(f"Cannot read token file: {e}")
        sys.exit(0)

    my_timestamp: int = token_data["timestamp"]
    last_message: str = token_data.get("last_message", "")
    term_program: str = token_data.get("term_program", "Terminal")
    session_id: str = token_data.get("session_id", "unknown")

    log(f"Session: {session_id}, app: {term_program}")

    # ── Wait up to IDLE_WAIT_SECONDS, checking for new activity ──────────────
    checks = IDLE_WAIT_SECONDS // POLL_CHECK_INTERVAL
    for i in range(checks):
        time.sleep(POLL_CHECK_INTERVAL)
        try:
            current = json.loads(token_file.read_text())
            if current.get("timestamp", 0) != my_timestamp:
                log("New activity detected — exiting silently.")
                sys.exit(0)
        except FileNotFoundError:
            log("Token file removed — exiting silently.")
            sys.exit(0)
        except Exception:
            pass
        log(f"Still idle ({(i + 1) * POLL_CHECK_INTERVAL}s / {IDLE_WAIT_SECONDS}s)")

    log("Idle timeout reached — sending Telegram notification.")

    # ── Load credentials ──────────────────────────────────────────────────────
    env = load_env(ENV_PATH)
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        log("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env — aborting.")
        sys.exit(1)

    # ── Baseline update_id (ignore old messages) ──────────────────────────────
    offset = get_update_id_baseline(bot_token)
    log(f"Telegram update_id baseline: {offset}")

    # ── Send notification ─────────────────────────────────────────────────────
    notification = (
        f"Claude is waiting for your response:\n\n"
        f"{last_message}\n\n"
        f"Reply to continue..."
    )
    try:
        send_message(bot_token, chat_id, notification)
        log("Telegram notification sent.")
    except Exception as e:
        log(f"Failed to send Telegram message: {e}")
        sys.exit(1)

    # ── Poll for Telegram reply ───────────────────────────────────────────────
    deadline = time.time() + TELEGRAM_REPLY_TIMEOUT
    log(f"Waiting up to {TELEGRAM_REPLY_TIMEOUT // 60} min for Telegram reply...")

    reply, _ = poll_for_reply(bot_token, chat_id, offset, deadline)

    if reply is None:
        log("No Telegram reply received within timeout.")
        try:
            send_message(
                bot_token,
                chat_id,
                "No reply received -- Claude Code is still waiting.",
            )
        except Exception:
            pass
        sys.exit(0)

    log(f"Got Telegram reply: {reply!r}")

    # ── Acknowledge on Telegram ───────────────────────────────────────────────
    try:
        send_message(bot_token, chat_id, "Got it -- sending to Claude...")
    except Exception as e:
        log(f"Failed to send ack: {e}")

    # ── Inject reply into Claude Code ─────────────────────────────────────────
    try:
        inject_reply(reply, term_program)
        log("Reply injected via osascript.")
    except Exception as e:
        log(f"osascript injection failed: {e}")
        try:
            send_message(
                bot_token,
                chat_id,
                f"Could not inject reply automatically.\n"
                f"Please type in Claude Code manually:\n\n{reply}",
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

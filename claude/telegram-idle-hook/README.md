# Telegram Idle Notifier — Claude Code Hook

Sends Claude's last response to a Telegram bot if you don't reply within 5 minutes.
Reply on Telegram and the message is automatically injected back into Claude Code.

## How it works

1. Every time Claude finishes responding, the `Stop` hook fires.
2. A background daemon starts and waits 5 minutes.
3. If you type something before the 5 minutes are up, the daemon exits silently.
4. After 5 minutes of silence, the daemon sends Claude's last message to your Telegram bot.
5. You reply on Telegram (from your phone, etc.).
6. The daemon uses `osascript` to paste the reply into Claude Code and press Enter.
7. Claude continues as if you typed it yourself.

## Prerequisites

- macOS (uses `osascript` for injection)
- Claude Code installed (`~/.claude/`)
- A Telegram bot with a token and your chat ID stored in `.env`:

```
# python/telegram_bots/.env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=987654321
```

If you don't have a bot yet:
1. Message `@BotFather` on Telegram → `/newbot`
2. Copy the token it gives you
3. Start a chat with your new bot, then visit:
   `https://api.telegram.org/botTOKEN/getUpdates`
   to find your `chat.id`

## Installation

```bash
cd /Volumes/data_2/dev/gargascripts
bash claude/telegram-idle-hook/install.sh
```

The installer:
- Symlinks hook scripts into `~/.claude/hooks/`
- Adds the `Stop` hook to `~/.claude/settings.json`
- Asks where to store the `.env` file (default: `~/.claude/.env`), creates it if missing,
  and writes the path into the daemon

## Files

| File | Purpose |
|------|---------|
| `telegram-idle-notify.sh` | Stop hook — runs after each Claude response, spawns daemon |
| `telegram_idle_daemon.py` | Background daemon — timer, Telegram, injection |
| `install.sh` | One-shot installer |

After installation, the hooks live as symlinks in `~/.claude/hooks/`.

## Configuration

Edit constants at the top of `telegram_idle_daemon.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `IDLE_WAIT_SECONDS` | `300` (5 min) | How long to wait before notifying |
| `TELEGRAM_REPLY_TIMEOUT` | `900` (15 min) | Give up waiting for a Telegram reply |
| `TELEGRAM_LONG_POLL_SECS` | `30` | Telegram getUpdates poll window |

The `.env` path is also at the top of the daemon (`ENV_PATH`).

## Troubleshooting

**Check daemon logs:**
```bash
tail -f /tmp/claude_idle_daemon.log
```

**Inspect the token file (while idle):**
```bash
cat /tmp/claude_idle_*.json | python3 -m json.tool
```

**Test the osascript injection manually:**
```bash
echo "hello from telegram" | pbcopy
osascript -e 'tell application "Code" to activate' \
  -e 'tell application "System Events" to tell process "Code" to keystroke "v" using command down'
```

**Nothing sent to Telegram?**
- Confirm the daemon is running: `pgrep -fl telegram_idle_daemon`
- Check for `.env` errors in the log

**Reply not injected?**
- macOS may require Accessibility permissions for `osascript` to control other apps.
- Go to System Settings → Privacy & Security → Accessibility → add Terminal (or Code).
- If injection fails, the daemon sends the reply text back to Telegram so you can copy-paste it.

## Uninstall

```bash
rm ~/.claude/hooks/telegram-idle-notify.sh
rm ~/.claude/hooks/telegram_idle_daemon.py
```

Then remove the `Stop` entry from `~/.claude/settings.json`.

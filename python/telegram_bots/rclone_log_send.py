#!/usr/bin/env python3
"""
Read pending HTML message file and send to Telegram, then delete it.
Triggered by launchd StartCalendarInterval at 9:00 AM.
"""

import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Optional, TypedDict

import requests
from dotenv import load_dotenv


# ─── Constants ────────────────────────────────────────────────────────────────

LOG_DIR = Path("/Users/gargamel/Library/Logs/rclone-onedrive")
PENDING_FILE = LOG_DIR / "pending-message.html"
SCRIPT_DIR = Path(__file__).parent


# ─── Configuration ────────────────────────────────────────────────────────────

class Config(TypedDict):
    telegram_bot_token: str
    telegram_chat_id: str


def load_config() -> Config:
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    config = {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
    }
    missing = [k.upper() for k, v in config.items() if not v]
    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")
    return config


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("send")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


# ─── Telegram ─────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    """Escape HTML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram_message(message: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")


def send_error_notification(bot_token: str, chat_id: str, error: str) -> None:
    try:
        msg = f"\U0001f534 <b>send.py failed</b>\n\n<pre>{_esc(error[:800])}</pre>"
        send_telegram_message(msg, bot_token, chat_id)
    except Exception:
        pass


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    logger = setup_logging()
    config: Optional[Config] = None

    try:
        config = load_config()

        if not PENDING_FILE.exists():
            logger.info("No pending message file found. Nothing to send.")
            return 0

        message = PENDING_FILE.read_text(encoding="utf-8")
        logger.info(f"Sending message ({len(message)} chars) to Telegram...")

        send_telegram_message(message, config["telegram_bot_token"], config["telegram_chat_id"])
        PENDING_FILE.unlink()
        logger.info("Message sent and pending file deleted.")
        return 0

    except Exception:
        tb = traceback.format_exc()
        logger.error(f"Fatal error:\n{tb}")
        if config and config.get("telegram_bot_token") and config.get("telegram_chat_id"):
            send_error_notification(
                config["telegram_bot_token"], config["telegram_chat_id"], tb
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())

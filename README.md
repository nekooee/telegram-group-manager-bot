# Telegram Group Manager Bot

A Telegram bot for group management: scheduled message deletion, image conversion, translation, and ephemeral (private-to-you) command UI in groups.

Built with **python-telegram-bot 22.8** and Telegram Bot API **10.2** ephemeral messages.

---

## Features

### Scheduled message deletion (`/del`)

Reply to a message in a group and send `/del`. An interactive ephemeral UI appears **only for you**:

1. Choose **minutes** or **hours**
2. Pick a preset value or enter a **custom number**
3. Use **Cancel** to abort at any step

The bot stores the schedule in SQLite and deletes the target message when the time is reached.

Scheduling the same message again **replaces** the previous time. If a schedule already exists, use **Cancel scheduled deletion** in the `/del` UI to remove it entirely.

**Telegram limit:** a message can only be deleted within **48 hours** of when it was posted. If you request a longer delay, the bot caps the schedule and warns you.

**Ephemeral UI cleanup:** private bot replies are auto-removed after `EPHEMERAL_MESSAGE_TTL_SECONDS` in `config.py` (default **10**). Set to **0** to disable auto-deletion. The user's ephemeral `/del` command itself is left for Telegram's client-side ephemeral lifecycle.

---

### Image conversion (`/tojpg`)

Reply to an image message:

```
/tojpg          → upload converted file as document
/tojpg photo    → upload as photo
```

Supports formats listed in `config.py` (PNG, WEBP, HEIC, AVIF, etc.) via Pillow and `pillow-heif`.

---

### Translation (`/translate`)

Reply to a text message:

```
/translate      → default target language from config / `.env`
/translate fa   → translate to Persian
/translate en   → translate to English
```

---

### Admin commands (private chat, `ADMIN_USER_ID` only)

| Command | Description |
|---------|-------------|
| `/report` | Deletion status report |
| `/test_msg chat_id message_id` | Test deleting a specific message |
| `/cleanup` | Clear pending deletion records |
| `/groupid` | Show current chat ID and allow-list status |

---

## Configuration

### Environment (`.env`)

Copy `.env.example` to `.env`:

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Token from BotFather |
| `DB_PATH` | SQLite path (default `messages.db`) |
| `ADMIN_USER_ID` | Your Telegram user ID |
| `ALLOWED_GROUPS` | Comma-separated group chat IDs |
| `LANGUAGE` | UI language: `en` or `fa` |
| `DEFAULT_TRANSLATE_TO` | Default translation target |
| `TRANSLATE_FROM` | Source language (`auto` = detect) |

### `config.py`

| Setting | Description |
|---------|-------------|
| `RESTRICT_TO_ALLOWED_GROUPS` | If `True`, bot only works in `ALLOWED_GROUPS` |
| `DELETE_AFTER_HOURS` | Legacy default (24h); `/del` uses the interactive UI |
| `MAX_MESSAGE_AGE_HOURS` | Telegram delete limit (48) |
| `EPHEMERAL_MESSAGE_TTL_SECONDS` | Auto-delete ephemeral UI for you and bot; **0** = disabled |
| `SUPPORTED_IMAGE_FORMATS` | Extensions accepted by `/tojpg` |

Translations: `translations/en.json`, `translations/fa.json`.

---

## Project structure

```
group_manager_bot.py      # Entry point
config.py
handlers/                 # Command handlers
database/db_manager.py    # SQLite persistence
utils/ephemeral.py        # Ephemeral message helpers (Bot API 10.2)
translations/
requirements.txt
```

---

## Deployment (Ubuntu / AlmaLinux)

### 1. Files to copy

Copy source code (`handlers/`, `database/`, `utils/`, `translations/`, `*.py`, `requirements.txt`, `.env.example`). Do **not** copy `.venv`, `__pycache__`, or `.env` (create on server).

### 2. Setup

```bash
cd /opt/groupbot   # or your path
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python group_manager_bot.py
```

Requires **Python 3.10+** (3.12 recommended).

### 3. Supervisor (example)

`/etc/supervisord.d/groupbot.ini`:

```ini
[program:groupbot]
command=/opt/groupbot/.venv/bin/python -u /opt/groupbot/group_manager_bot.py
directory=/opt/groupbot
autostart=true
autorestart=true
startsecs=5
startretries=3
stopasgroup=true
killasgroup=true
stopsignal=TERM
stopwaitsecs=30
stdout_logfile=/opt/groupbot/bot.log
stdout_logfile_maxbytes=2MB
stdout_logfile_backups=0
stderr_logfile=/opt/groupbot/bot_error.log
stderr_logfile_maxbytes=2MB
stderr_logfile_backups=0
environment=PATH="/opt/groupbot/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin",PYTHONUNBUFFERED="1"
```

```bash
supervisorctl reread
supervisorctl update
supervisorctl start groupbot
supervisorctl status groupbot
```

### Alternative: `screen` or `nohup`

See older workflow: activate venv, run `python group_manager_bot.py`, or use `nohup` / `screen` for background execution.

---

## Getting started in a group

1. Add the bot to your group.
2. Grant **Delete messages** (and media permissions for `/tojpg`).
3. Add the group ID to `ALLOWED_GROUPS` in `.env` if `RESTRICT_TO_ALLOWED_GROUPS` is enabled.
4. Reply to a message → `/del` → follow the ephemeral UI.

---

## License

Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)

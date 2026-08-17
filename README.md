# Telegram Auto Text Repost Bot

Monitors one or more source channels for new **text-only** posts and automatically
reposts them (with optional personal-data removal, keyword filtering, duplicate
protection, text editing, and delay) into a destination channel.

## How it works

Two Telegram identities are used:

1. **A bot account** (`BOT_TOKEN` from @BotFather) — runs the admin panel and posts
   messages into the destination channel(s). Must be added as **admin** in every
   destination channel.
2. **A regular user account** (logged in via `API_ID`/`API_HASH` from
   https://my.telegram.org) — this is what actually "sees" new posts in the source
   channels, since a bot can't receive updates from a channel unless it's a member.
   This account must **join** each source channel (or already have access to it).

⚠️ Only add source channels you have the right to repost content from.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS

python main.py
```

On first run, Telethon will ask you to log in (phone number + code) in the terminal.
This creates a `.session` file so future restarts don't require logging in again.

## Admin commands

See `/help` inside the bot for the full list. Highlights:

| Command | Purpose |
|---|---|
| `/addsource <url>` | Add a source channel |
| `/setdestination <source_id> <dest_url>` | Set where its posts go |
| `/filter <source_id> <whitelist|blacklist|none> <kw1,kw2>` | Keyword filter |
| `/pdfilter <source_id> <on|off>` | Personal data filter toggle |
| `/wordremove` / `/wordreplace` / `/lineremove` | Text editing |
| `/footer` / `/hashtags` | Append text to every post |
| `/delay <source_id> <seconds>` | Delay before posting |
| `/pause` / `/resume` | Pause/resume (globally or per source) |
| `/stats` / `/logs` | Monitoring |

## Deploying on a VPS (24/7, auto-restart)

**Option A — Docker (recommended)**

```bash
docker compose up -d --build
docker compose logs -f      # first run: docker attach to log in with Telethon
```

`restart: always` in `docker-compose.yml` means it comes back up automatically
after a server reboot or crash. The `./data` folder persists the SQLite database
and the login session across restarts.

**Option B — systemd**

```ini
# /etc/systemd/system/repost-bot.service
[Unit]
Description=Telegram Auto Repost Bot
After=network.target

[Service]
WorkingDirectory=/opt/telegram_repost_bot
ExecStart=/opt/telegram_repost_bot/venv/bin/python main.py
Restart=always
EnvironmentFile=/opt/telegram_repost_bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now repost-bot
```

## What's implemented vs. spec

Implemented: multi-source monitoring, per-source destination, text-only filter,
personal data filter, keyword whitelist/blacklist, duplicate protection (content
hash), word remove/replace, line remove, footer/hashtags, delay, admin commands +
inline panel, statistics, activity log, error handling with admin notification,
auto-recovery on restart, `.env`-based secrets, Docker/systemd deployment.

Not implemented (spec marks these "Advanced"/"Optional" — architecture supports
adding them later): calendar-style scheduling (daily/weekend/timezone rules),
and the AI features (caption rewrite, translation, smart spam detection). These
would plug into `filters.process_text()` and a new `scheduler.py` without
changing the rest of the system.

## Project structure

```
config.py     - env/config loading
database.py   - SQLite schema + all queries
filters.py    - text processing pipeline (personal data, editing, dedup hash)
monitor.py    - Telethon listener: detect -> process -> post
bot.py        - admin commands + inline buttons (python-telegram-bot)
main.py       - wires everything together, entry point
```

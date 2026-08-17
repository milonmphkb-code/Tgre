# Telegram Auto Post + AI Group Bot

এই project-টি Telegram-এর জন্য একটি production-oriented foundation:

- Source Channel → Destination Channel auto-post
- Text-only processing
- Source → Destination mapping
- Whitelist / blacklist
- Personal-data filtering
- Text cleaning
- Word replacement
- Templates
- Delay / schedule
- Queue
- Duplicate protection
- Retry
- Logs / history / statistics
- AI group assistant
- Per-group AI settings
- Auto language instruction
- Context
- Welcome message
- Admin authorization
- Backup / restore
- Health status
- Test mode

## Important Telegram note

Source channel-এর পোস্ট পড়তে Bot/Client-এর প্রয়োজনীয় access থাকতে হবে। অন্য channel-এর content republish করার rights/permission আগে নিশ্চিত করুন।

## Architecture

- `aiogram` = Bot API admin/group interactions
- `Telethon` = source-channel event monitoring
- `SQLAlchemy` = database
- `APScheduler` = scheduled jobs
- `httpx` = AI-compatible HTTP API

## Quick start

1. Python 3.11+ install করুন.
2. `pip install -r requirements.txt`
3. `.env.example` → `.env`
4. `python -m app`
5. `/start` দিয়ে admin bot-এ কাজ শুরু করুন.

### Environment

`BOT_TOKEN` = Telegram BotFather token  
`ADMIN_IDS` = comma-separated numeric Telegram user IDs  
`API_ID`, `API_HASH` = Telegram API credentials for Telethon  
`DATABASE_URL` = default SQLite  
`AI_API_KEY` = AI provider key  
`AI_API_URL` = OpenAI-compatible chat endpoint

### Source monitoring

Telethon client bot token দিয়ে source channels monitor করতে পারে, যদি সেই bot account-এর access থাকে। যদি আপনার deployment-এ bot account দিয়ে source channel events পাওয়া না যায়, project-এ user-session monitoring যোগ করতে হবে; সেই ক্ষেত্রে Telegram terms এবং account security মেনে চলুন।

## First configuration

Admin commands:

- `/start`
- `/help`
- `/status`
- `/setmychannel <chat_id>`
- `/addsource <chat_id> [name]`
- `/removesource <chat_id>`
- `/sources`
- `/addmapping <source_id> <destination_chat_id>`
- `/mappings`
- `/deletemapping <mapping_id>`
- `/setdelay <source_id> <seconds>`
- `/setfilter <source_id> username|phone|email|telegram_link on|off`
- `/addblacklist <source_id> <keyword>`
- `/addwhitelist <source_id> <keyword>`
- `/addreplace <source_id> <old> => <new>`
- `/settemplate <source_id> <template>`
- `/addgroup <chat_id>`
- `/groupoff <chat_id>`
- `/groupon <chat_id>`
- `/setprompt <chat_id> <prompt>`
- `/stats`
- `/logs`
- `/backup`

## Destination

For simple deployment, each source mapping can point directly to a Telegram destination chat ID. The `My Channel` setting is also stored and used as the default destination when a mapping has no explicit destination.

## Test mode

Set `TEST_MODE=true`. Published posts are redirected to `TEST_CHANNEL_ID`.

## Scheduling

A mapping can be given `schedule_start` and `schedule_end` in `HH:MM`, using `TIMEZONE`. Posts arriving outside that window remain queued until the scheduler can publish them.

## Security

Never commit `.env`, Telegram sessions, database backups, or API keys to Git.

## Telegram In-Bot Admin Panel

`/panel` চালালে inline-button control center পাওয়া যাবে। Channel, AI Groups, filters, post settings, queue, statistics, logs, backup, health এবং bot control-এর বিভাগগুলো Bot-এর মধ্যেই থাকবে। যেসব action-এর জন্য ID/text input দরকার, সেগুলোর command fallback রাখা হয়েছে।

## Gemini AI

This build uses Google's official `google-genai` Python SDK when `AI_PROVIDER=gemini`.
Set these Railway variables:

`AI_PROVIDER=gemini`
`GEMINI_API_KEY` is accepted by Google's SDK, but this project also reads `AI_API_KEY` for compatibility.
`AI_API_KEY=<your Gemini key>`
`AI_MODEL=gemini-3.6-flash`

Never put the real API key in GitHub.

import hashlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from app.db import (
    SourceChannel, Mapping, FilterSetting, Keyword, Replacement,
    ProcessedPost, PostHistory, AppLog, BotConfig, GroupSetting, GroupMessage,
    QueueItem
)

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
TG_LINK = re.compile(r"(?:https?://)?t\.me/[A-Za-z0-9_+/.-]+", re.I)
TG_USER = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,32}\b")
TG_ID = re.compile(r"(?i)(?:telegram\s*(?:user\s*)?id|user\s*id)\s*[:=]?\s*\d+")

def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

async def process_text(session, source_id: int, text: str) -> tuple[str | None, str | None]:
    fs = (await session.execute(select(FilterSetting).where(FilterSetting.source_id == source_id))).scalar_one_or_none()
    if fs:
        if fs.username:
            text = TG_USER.sub("", text)
        if fs.phone:
            text = PHONE.sub("", text)
        if fs.email:
            text = EMAIL.sub("", text)
        if fs.telegram_link:
            text = TG_LINK.sub("", text)
        if fs.user_id:
            text = TG_ID.sub("", text)

    text = clean_text(text)

    kws = (await session.execute(select(Keyword).where(Keyword.source_id == source_id, Keyword.enabled == True))).scalars().all()
    white = [k.word.lower() for k in kws if k.kind == "white"]
    black = [k.word.lower() for k in kws if k.kind == "black"]
    lower = text.lower()
    if white and not any(k in lower for k in white):
        return None, "whitelist_miss"
    if any(k in lower for k in black):
        return None, "blacklist_match"

    reps = (await session.execute(select(Replacement).where(Replacement.source_id == source_id, Replacement.enabled == True))).scalars().all()
    for r in reps:
        text = text.replace(r.old_text, r.new_text)

    return text.strip(), None

def in_schedule(mapping: Mapping, tz_name: str) -> bool:
    if not mapping.schedule_start or not mapping.schedule_end:
        return True
    now = datetime.now(ZoneInfo(tz_name)).time()
    start = datetime.strptime(mapping.schedule_start, "%H:%M").time()
    end = datetime.strptime(mapping.schedule_end, "%H:%M").time()
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end

def render_template(template: str | None, text: str) -> str:
    if not template:
        return text
    return template.replace("{POST_TEXT}", text)

async def is_duplicate(session, source_chat_id: int, source_message_id: int, text: str) -> bool:
    stmt = select(ProcessedPost).where(
        (ProcessedPost.source_chat_id == source_chat_id) &
        (ProcessedPost.source_message_id == source_message_id)
    )
    if (await session.execute(stmt)).scalar_one_or_none():
        return True
    h = content_hash(text)
    stmt = select(ProcessedPost).where(ProcessedPost.content_hash == h)
    return (await session.execute(stmt)).scalar_one_or_none() is not None

async def mark_processed(session, source_chat_id: int, source_message_id: int, text: str):
    session.add(ProcessedPost(
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        content_hash=content_hash(text)
    ))

async def log_event(session, event: str, details: str = "", level: str = "INFO"):
    session.add(AppLog(level=level, event=event, details=details))

async def history(session, source_chat_id, source_message_id, destination_chat_id, status, reason=None, destination_message_id=None):
    session.add(PostHistory(
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        destination_chat_id=destination_chat_id,
        destination_message_id=destination_message_id,
        status=status,
        reason=reason
    ))

async def get_stats(session) -> dict:
    def count(model):
        return select(func.count()).select_from(model)
    return {
        "sources": await session.scalar(count(SourceChannel)),
        "mappings": await session.scalar(count(Mapping)),
        "detected_history": await session.scalar(count(PostHistory)),
        "published": await session.scalar(select(func.count()).select_from(PostHistory).where(PostHistory.status == "published")),
        "skipped": await session.scalar(select(func.count()).select_from(PostHistory).where(PostHistory.status == "skipped")),
        "errors": await session.scalar(select(func.count()).select_from(PostHistory).where(PostHistory.status == "error")),
        "ai_questions": await session.scalar(count(GroupMessage)),
    }

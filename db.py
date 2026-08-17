from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Boolean, Text, DateTime, BigInteger,
    ForeignKey, UniqueConstraint, select, func, delete
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

def utcnow():
    return datetime.now(timezone.utc)

class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="admin")

class BotConfig(Base):
    __tablename__ = "bot_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    my_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SourceChannel(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)

class Mapping(Base):
    __tablename__ = "mappings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    destination_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0)
    schedule_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    schedule_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    template: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=3)
    retry_delay: Mapped[int] = mapped_column(Integer, default=10)

class FilterSetting(Base):
    __tablename__ = "filter_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), unique=True)
    username: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[bool] = mapped_column(Boolean, default=True)
    email: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_link: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[bool] = mapped_column(Boolean, default=True)

class Keyword(Base):
    __tablename__ = "keywords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    word: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(10))  # white / black
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Replacement(Base):
    __tablename__ = "replacements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    old_text: Mapped[str] = mapped_column(Text)
    new_text: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class ProcessedPost(Base):
    __tablename__ = "processed_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("source_chat_id", "source_message_id", name="uq_source_post"),
    )

class PostHistory(Base):
    __tablename__ = "post_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    destination_chat_id: Mapped[int] = mapped_column(BigInteger)
    destination_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AppLog(Base):
    __tablename__ = "app_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(20))
    event: Mapped[str] = mapped_column(String(100))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class GroupSetting(Base):
    __tablename__ = "group_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reply_mode: Mapped[str] = mapped_column(String(30), default="question_only")
    prompt: Mapped[str] = mapped_column(Text, default="Answer politely and clearly.")
    style: Mapped[str] = mapped_column(String(30), default="friendly")
    length: Mapped[str] = mapped_column(String(30), default="medium")
    context_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    context_limit: Mapped[int] = mapped_column(Integer, default=8)
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_text: Mapped[str] = mapped_column(Text, default="Welcome!")

class GroupMessage(Base):
    __tablename__ = "group_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class QueueItem(Base):
    __tablename__ = "queue_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    destination_chat_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending")

class Database:
    def __init__(self, url: str):
        if url.startswith("sqlite") and "///" in url:
            Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(url, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.session_factory() as s:
            if not (await s.execute(select(BotConfig).where(BotConfig.id == 1))).scalar_one_or_none():
                s.add(BotConfig(id=1))
            await s.commit()

    def session(self) -> AsyncSession:
        return self.session_factory()

async def scalar(session, stmt):
    return (await session.execute(stmt)).scalar_one_or_none()

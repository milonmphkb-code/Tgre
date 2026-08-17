FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Database and Telethon session persist on a mounted volume
VOLUME ["/app/data"]
ENV DATABASE_PATH=/app/data/bot_database.db
ENV SESSION_NAME=/app/data/repost_userbot

CMD ["python", "main.py"]

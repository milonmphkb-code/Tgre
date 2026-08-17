import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from app.config import load_settings
from app.db import Database

async def main():
    settings = load_settings()
    if not settings.database_url.startswith("sqlite"):
        print("Automatic file backup in this script is for SQLite.")
        return
    db_path = Path(settings.database_url.split("///", 1)[1])
    if not db_path.exists():
        print("Database file not found.")
        return
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, target)
    print(f"Backup: {target}")

if __name__ == "__main__":
    asyncio.run(main())

import logging
from pathlib import Path

def setup_logging(level: str = "INFO"):
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/bot.log", encoding="utf-8"),
        ],
    )

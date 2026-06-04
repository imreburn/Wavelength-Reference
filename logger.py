import logging
from datetime import datetime
from pathlib import Path


def setup_logging(level=logging.INFO):
    """Configure logging once. Writes to logs/<date>.log and the console."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)

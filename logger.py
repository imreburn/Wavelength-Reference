import logging
from datetime import datetime
from pathlib import Path


def setup_logging(app_name, level=logging.INFO):
    """Configure logging once. Writes to logs/<app_name>/<date>_<time>.log and
    the console. `app_name` keeps each program's logs in their own folder and
    tags every line via the %(name)s field."""
    log_dir = Path("logs") / app_name
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # Werkzeug's dev server logs one INFO line per HTTP request (static assets,
    # callbacks, etc.). Quiet it to WARNING so only real problems (4xx/5xx) show.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    return logging.getLogger(app_name)

import logging
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "light_show_tool.log"


def configure_logging() -> None:
    """Set up file logging. Truncates the log on every run so it never
    grows unbounded — only the latest run's activity is kept for debugging."""
    logging.basicConfig(
        filename=LOG_PATH,
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(__name__).info("LightShowTool starting, log: %s", LOG_PATH)

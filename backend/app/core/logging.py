"""Applies LOG_LEVEL to the application's loggers (everything under `app.`).

Without this, `app.*` loggers have no handler: Python's fallback prints only WARNING and above,
so INFO lines such as the AI call records (docs/AI.md §15) never appear. Uvicorn configures only
its own loggers.
"""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level.upper())
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        app_logger.addHandler(handler)

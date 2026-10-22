from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    # Request bodies, uploaded files and question text are never logged.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

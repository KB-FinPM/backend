# EN: Shared logger factory for backend modules.
# KO: 백엔드 모듈에서 공통으로 사용하는 Logger 생성기입니다.

import logging
import os
import sys
from app.core.config import settings


os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _configure_stdout_encoding() -> None:
    if not hasattr(sys.stdout, "reconfigure"):
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        return


def get_logger(name: str) -> logging.Logger:
    _configure_stdout_encoding()
    logger = logging.getLogger(name)
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    logger.setLevel(level)

    handler_exists = False
    for handler in logger.handlers:
        handler.setLevel(level)
        if isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) is sys.stdout:
            handler_exists = True

    if not handler_exists:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False

    return logger

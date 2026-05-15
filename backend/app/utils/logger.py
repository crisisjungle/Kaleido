import logging
import os
from logging.handlers import RotatingFileHandler


_CONFIGURED = set()


def setup_logger(name="envfish", level=None):
    logger = logging.getLogger(name)
    if name in _CONFIGURED:
        return logger

    log_level = level or (logging.DEBUG if os.environ.get("FLASK_DEBUG", "True").lower() == "true" else logging.INFO)
    logger.setLevel(log_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)
    logger.addHandler(stream_handler)

    logs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
    os.makedirs(logs_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "backend.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)

    _CONFIGURED.add(name)
    return logger


def get_logger(name="envfish"):
    root_name = name.split(".", 1)[0]
    if root_name not in _CONFIGURED:
        setup_logger(root_name)
    logger = logging.getLogger(name)
    logger.setLevel(logging.getLogger(root_name).level)
    return logger

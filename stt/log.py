import logging
import sys


def setup(level: int = logging.INFO, log_file: str | None = None) -> None:
    logger = logging.getLogger("stt")
    if logger.handlers:
        return
    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)


def get() -> logging.Logger:
    return logging.getLogger("stt")

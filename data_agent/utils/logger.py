import os
import logging
import logging.handlers

from common.constants import ROOT_DIR


class LogConfig:
    LEVEL = logging.INFO
    LOG_DIR = os.path.join(ROOT_DIR, "logs")
    MAX_BYTES = 10 * 1024 * 1024
    BACKUP_COUNT = 20
    ENCODING = "UTF-8"
    FORMAT = "%(asctime)s %(levelname)-8s %(process)-5s --- [%(threadName)s] [%(filename)s:%(lineno)d] : %(message)s"


def initialize_logger(filename, logger=None):
    if not os.path.exists(LogConfig.LOG_DIR):
        os.makedirs(LogConfig.LOG_DIR, exist_ok=True)

    if not logger:
        logger = logging.getLogger()

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(LogConfig.LEVEL)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(LogConfig.LOG_DIR, filename),
        maxBytes=LogConfig.MAX_BYTES,
        backupCount=LogConfig.BACKUP_COUNT,
        encoding=LogConfig.ENCODING
    )
    formatter = logging.Formatter(LogConfig.FORMAT)
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.setLevel(LogConfig.LEVEL)

    return logger

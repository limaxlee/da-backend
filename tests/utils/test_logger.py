import logging
import logging.handlers
import os

from data_agent.utils.logger import LogConfig, initialize_logger


def test_initialize_logger(mocker, tmp_path):
    log_dir = tmp_path / "logs"
    mocker.patch.object(LogConfig, "LOG_DIR", str(log_dir))
    target = logging.getLogger("test_initialize_logger")
    target.handlers.clear()

    try:
        logger = initialize_logger("test.log", logger=target)

        assert logger is target
        assert logger.level == LogConfig.LEVEL
        assert len(logger.handlers) == 2
        stream_handler, file_handler = logger.handlers
        assert isinstance(stream_handler, logging.StreamHandler)
        assert isinstance(file_handler, logging.handlers.RotatingFileHandler)
        assert os.path.exists(os.path.join(str(log_dir), "test.log"))
    finally:
        for handler in target.handlers:
            handler.close()
        target.handlers.clear()

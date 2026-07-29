import os
import logging

import pytest

from common.constants import ROOT_DIR
from data_agent.utils.logger import LogConfig, initialize_logger


@pytest.fixture
def mock_makedirs(mocker):
    return mocker.patch("data_agent.utils.logger.os.makedirs")


@pytest.fixture
def mock_file_handler(mocker):
    handler = mocker.MagicMock(spec=logging.Handler)
    handler.level = LogConfig.LEVEL
    return mocker.patch(
        "data_agent.utils.logger.logging.handlers.RotatingFileHandler",
        return_value=handler,
    )


@pytest.fixture
def target_logger():
    logger = logging.getLogger("test_logger")
    logger.handlers.clear()
    yield logger
    logger.handlers.clear()


class TestLogConfig:

    def test_default_values(self):
        assert LogConfig.LEVEL == logging.INFO
        assert LogConfig.LOG_DIR == os.path.join(ROOT_DIR, "logs")
        assert LogConfig.MAX_BYTES == 10 * 1024 * 1024
        assert LogConfig.BACKUP_COUNT == 20
        assert LogConfig.ENCODING == "UTF-8"

    def test_format_is_usable_by_logging(self):
        formatter = logging.Formatter(LogConfig.FORMAT)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="module.py",
            lineno=42,
            msg="hello",
            args=(),
            exc_info=None,
        )

        assert "hello" in formatter.format(record)


class TestInitializeLogger:

    def test_creates_log_dir_when_missing(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=False)

        initialize_logger("app.log", target_logger)

        mock_makedirs.assert_called_once_with(LogConfig.LOG_DIR, exist_ok=True)

    def test_does_not_create_log_dir_when_present(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)

        initialize_logger("app.log", target_logger)

        mock_makedirs.assert_not_called()

    def test_returns_provided_logger(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)

        result = initialize_logger("app.log", target_logger)

        assert result is target_logger

    def test_falls_back_to_root_logger(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)
        mock_get_logger = mocker.patch(
            "data_agent.utils.logger.logging.getLogger", return_value=target_logger
        )

        result = initialize_logger("app.log")

        mock_get_logger.assert_called_once_with()
        assert result is target_logger

    def test_does_not_look_up_root_logger_when_one_is_given(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)
        mock_get_logger = mocker.patch("data_agent.utils.logger.logging.getLogger")

        initialize_logger("app.log", target_logger)

        mock_get_logger.assert_not_called()

    def test_file_handler_is_configured_from_log_config(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)

        initialize_logger("app.log", target_logger)

        mock_file_handler.assert_called_once_with(
            filename=os.path.join(LogConfig.LOG_DIR, "app.log"),
            maxBytes=LogConfig.MAX_BYTES,
            backupCount=LogConfig.BACKUP_COUNT,
            encoding=LogConfig.ENCODING,
        )

    def test_adds_stream_and_file_handlers(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)

        initialize_logger("app.log", target_logger)

        assert len(target_logger.handlers) == 2
        assert mock_file_handler.return_value in target_logger.handlers
        assert any(
            isinstance(handler, logging.StreamHandler)
            for handler in target_logger.handlers
        )

    def test_sets_logger_level(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)
        target_logger.setLevel(logging.DEBUG)

        initialize_logger("app.log", target_logger)

        assert target_logger.level == LogConfig.LEVEL

    def test_stream_handler_uses_configured_level_and_format(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)

        initialize_logger("app.log", target_logger)

        stream_handler = next(
            handler
            for handler in target_logger.handlers
            if isinstance(handler, logging.StreamHandler)
        )
        assert stream_handler.level == LogConfig.LEVEL
        assert stream_handler.formatter._fmt == LogConfig.FORMAT

    def test_file_handler_receives_formatter(
        self, mocker, mock_makedirs, mock_file_handler, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)

        initialize_logger("app.log", target_logger)

        formatter = mock_file_handler.return_value.setFormatter.call_args[0][0]
        assert formatter._fmt == LogConfig.FORMAT

    def test_repeated_initialization_appends_handlers(
        self, mocker, mock_makedirs, target_logger
    ):
        mocker.patch("data_agent.utils.logger.os.path.exists", return_value=True)
        mocker.patch(
            "data_agent.utils.logger.logging.handlers.RotatingFileHandler",
            side_effect=lambda **kwargs: mocker.MagicMock(
                spec=logging.Handler, level=LogConfig.LEVEL
            ),
        )

        initialize_logger("app.log", target_logger)
        initialize_logger("app.log", target_logger)

        assert len(target_logger.handlers) == 4

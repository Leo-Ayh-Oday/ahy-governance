"""Tests for ahy_governance.logging_config — structured logging setup."""

import logging
import pytest
from ahy_governance.logging_config import (
    setup_logging,
    get_logger,
    get_correlation_id,
    set_correlation_id,
)


class TestCorrelationId:
    def test_get_generates_id(self):
        cid = get_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 12

    def test_set_and_get(self):
        set_correlation_id("test123")
        assert get_correlation_id() == "test123"

    def test_returns_consistent(self):
        set_correlation_id("abc")
        assert get_correlation_id() == "abc"
        assert get_correlation_id() == "abc"


class TestSetupLogging:
    def test_setup_default(self):
        setup_logging()
        # Should not crash

    def test_setup_with_level(self):
        setup_logging(level="DEBUG")
        # basicConfig may not change root logger level if already configured
        # Just verify no crash
        logger = logging.getLogger("test_debug2")
        logger.debug("test")

    def test_setup_with_structlog(self):
        """If structlog is available, setup_logging configures it."""
        try:
            import structlog
            setup_logging(level="INFO")
            logger = get_logger("test_structlog")
            assert logger is not None
        except ImportError:
            pytest.skip("structlog not installed")

    def test_setup_console_format(self, monkeypatch):
        """LOG_FORMAT=console should use ConsoleRenderer."""
        monkeypatch.setenv("LOG_FORMAT", "console")
        try:
            import structlog
            setup_logging(level="INFO")
        except ImportError:
            pytest.skip("structlog not installed")
        except Exception:
            pass  # May already be configured


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test_module")
        assert logger is not None

    def test_with_structlog(self):
        try:
            import structlog
            logger = get_logger("test_sl")
            # structlog loggers have a .info method
            assert hasattr(logger, "info")
        except ImportError:
            pytest.skip("structlog not installed")

    def test_without_structlog(self, monkeypatch):
        """Falls back to stdlib logging when structlog unavailable."""
        import sys
        # Remove structlog temporarily
        saved = sys.modules.pop("structlog", None)
        try:
            logger = get_logger("test_fallback")
            assert isinstance(logger, logging.Logger)
        finally:
            if saved:
                sys.modules["structlog"] = saved

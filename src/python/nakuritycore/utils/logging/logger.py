import logging
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from typing import Optional
from ...data.config import LoggingConfig


class Logger:
    """Application logger based on LoggingConfig."""

    def __init__(self, name: Optional[str] = None, config: Optional[LoggingConfig] = None):
        self.config = config or LoggingConfig()
        self.config.ensure_log_path()
        self.logger = logging.getLogger(name or "AppLogger")
        self.logger.setLevel(getattr(logging, self.config.level))
        self._setup_handlers()

    def _setup_handlers(self):
        """Configure handlers based on config."""
        # Avoid duplicate handlers if re-instantiated
        if self.logger.handlers:
            self.logger.handlers.clear()

        fmt = logging.Formatter(self.config.format, self.config.date_format)

        # Console logging
        if self.config.log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(fmt)
            self.logger.addHandler(console_handler)

        # File logging
        if self.config.log_to_file:
            log_path = self.config.get_log_path()

            if self.config.rotation == "daily":
                handler = TimedRotatingFileHandler(
                    log_path, when="midnight", backupCount=self.config.backup_count, encoding="utf-8"
                )
            elif self.config.rotation == "size":
                handler = RotatingFileHandler(
                    log_path,
                    maxBytes=self.config.max_size_mb * 1024 * 1024,
                    backupCount=self.config.backup_count,
                    encoding="utf-8",
                )
            else:
                handler = logging.FileHandler(log_path, encoding="utf-8")

            handler.setFormatter(fmt)
            self.logger.addHandler(handler)

        self.logger.debug(f"Logger initialized with config: {self.config.to_dict()}")

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def get_logger(self) -> logging.Logger:
        """Return the underlying logger instance."""
        return self.logger

# ------------------------------------------------------------------
# Example usage
# ------------------------------------------------------------------
# if __name__ == "__main__":
#     cfg = LoggingConfig(
#         level="DEBUG",
#         rotation="size",
#         max_size_mb=5,
#         backup_count=3,
#     )
#
#     app_logger = Logger("nakurity.app", config=cfg)
#     log = app_logger.get_logger()
#
#     log.info("Application started.")
#     log.debug("Debugging details here.")
#     log.warning("This is a warning.")

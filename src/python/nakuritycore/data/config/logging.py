from dataclasses import dataclass, field
from typing import Literal
import os
from datetime import datetime

from ..defaults.configuration import DefaultConfig

@dataclass
class LoggingConfig(DefaultConfig):
    """Configuration for application logging."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_to_file: bool = True
    log_to_console: bool = True
    log_dir: str = "logs"
    log_file: str = field(default_factory=lambda: f"app_{datetime.now().strftime('%Y%m%d')}.log")
    rotation: Literal["daily", "size", "none"] = "daily"
    max_size_mb: int = 10
    backup_count: int = 5
    format: str = "[%(asctime)s] [%(levelname)s] %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"

    def ensure_log_path(self):
        """Ensure the log directory exists if file logging is enabled."""
        if self.log_to_file:
            os.makedirs(self.log_dir, exist_ok=True)

    def get_log_path(self) -> str:
        """Return full log file path."""
        return os.path.join(self.log_dir, self.log_file)

    def setup_logging(self):
        """Apply the logging config to Python's logging system."""
        import logging
        handlers = []

        if self.log_to_console:
            handlers.append(logging.StreamHandler())

        if self.log_to_file:
            self.ensure_log_path()
            file_handler = logging.FileHandler(self.get_log_path(), encoding="utf-8")
            handlers.append(file_handler)

        logging.basicConfig(
            level=getattr(logging, self.level),
            format=self.format,
            datefmt=self.date_format,
            handlers=handlers,
        )

        logging.debug(f"Logging initialized with config: {self.to_dict()}")

# ------------------------------
# Example usage
# ------------------------------
#
# if __name__ == "__main__":
#     cfg = LoggingConfig(level="DEBUG", debug=True, name="AppLogger")
#     cfg.setup_logging()
#
#     import logging
#     logging.info("Logger is up and running.")
#     logging.debug("Debug info here.")

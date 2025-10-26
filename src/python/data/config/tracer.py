from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set
from datetime import datetime

from ..defaults.configuration import DefaultConfig

@dataclass
class TracerConfig(DefaultConfig):
    """Configuration options for the Tracer system."""
    use_color: bool = True
    show_file_path: bool = False
    show_timestamp: bool = True

    max_value_len: int = 60
    max_locals: int = 4
    max_stack_depth: int = 12

    include_paths: List[str] = field(default_factory=lambda: ["src/dev"])
    exclude_functions: Set[str] = field(default_factory=lambda: {"write_log", "trace"})
    events: Set[str] = field(default_factory=lambda: {"call", "return", "exception"})

    # Logging
    log_dir: Path = Path("logs")
    log_file_base: str = "neuro_os_trace.log"

    def resolve_log_path(self) -> Path:
        """Generate a timestamped log path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(self.log_dir) / self.log_file_base
        resolved = base.parent / f"{base.stem}_{timestamp}{base.suffix}"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

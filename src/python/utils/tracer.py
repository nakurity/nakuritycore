import time # Used by sub-function in class: Tracer().trace().now()
import inspect # Used by class: Tracer().trace()

import sys # Used by class: Tracer().__enter__() and Tracer().__exit__()
import linecache # Used by class: Tracer().trace()
import re # Used by class: Tracer()._plain()

# Used by class: Tracer()
from pathlib import Path

# Used by class: Tracer().__init__()
from ..data.config.tracer import TracerConfig

class Tracer:
    def __init__(self, config: TracerConfig):
        self.config = config
        self.project_root = config.project_root
        self.log_path = config.resolve_log_path()
        self.start_time = time.perf_counter()

    # Used by class: Tracer().trace()
    # For applying ANSI color codes
    def _color(self, txt, fg=None, style=None):
        """Apply ANSI color codes to a string."""
        if not self.config.use_color:
            return txt
        codes = {
            "reset": "\033[0m", "bold": "\033[1m",
            "gray": "\033[90m", "red": "\033[91m",
            "green": "\033[92m", "yellow": "\033[93m",
            "blue": "\033[94m", "magenta": "\033[95m",
            "cyan": "\033[96m",
        }
        return f"{codes.get(style, '')}{codes.get(fg, '')}{txt}{codes['reset']}"

    # Used by class: Tracer().trace()
    # For writing logs to a log file
    def _write(self, line):
        """Write a log message to the log file."""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # Used by class: Tracer().trace()
    # For stripping ANSI codes when writing to a log file
    def _plain(txt):
        """Strip ANSI codes for file output."""
        return re.sub(r"\x1b\[[0-9;]*m", "", txt)

    def trace(self, frame, event, arg):
        """Trace function calls, returns, and exceptions."""

        # === HELPER FUNCTIONS ===
        def short(v):
            """Return a short string representation of a value."""
            s = repr(v)
            return s if len(s) <= self.config.max_value_len else s[:self.config.max_value_len - 3] + "..."

        def now():
            """Return a string representation of the current time."""
            return f"{(time.perf_counter() - self.start_time):6.3f}s"

        def fmt_path(rel, lineno):
            """Return a string representation of a file path and line number."""
            if self.config.show_file_path:
                return f"{rel}:{lineno}"
            return f"{rel.name}:{lineno}"

        def fmt_locals(locals_dict):
            """Return a string representation of local variables."""
            items = [
                f"{self._color(k, 'blue')}={self._color(short(v), 'gray')}"
                for k, v in locals_dict.items()
                if not k.startswith("__") and not inspect.isfunction(v)
            ]
            return ", ".join(items[:self.config.max_locals])
        
        # === TRACE LOGIC ===
        filename = Path(frame.f_code.co_filename).resolve()
        try:
            filename.relative_to(self.project_root)
        except ValueError:
            return  # Skip non-project files

        rel = filename.relative_to(self.project_root)
        rel_posix = rel.as_posix()
        
        # Check include paths
        if self.config.include_paths and not any(p in rel_posix for p in self.config.include_paths):
            return
        
        func = frame.f_code.co_name
        
        # Check excluded functions
        if func in self.config.exclude_functions:
            return
        
        # Check events
        if event not in self.config.events:
            return
        
        depth = len(inspect.stack(0)) - 1
        indent = "│  " * (depth % self.config.max_stack_depth)
        ts = f"[{now()}]" if self.config.show_timestamp else ""

        def log(msg):
            print(msg)
            self._write(self._plain(msg))

        # === CALL ===
        if event == "call":
            args, _, _, values = inspect.getargvalues(frame)
            arg_str = ", ".join(f"{a}={short(values[a])}" for a in args if a in values)
            header = f"\n{indent}{self._color('╭▶', 'cyan', 'bold')} {self._color(func, 'green', 'bold')}() {self._color(fmt_path(rel, frame.f_lineno), 'gray')} {ts}"
            log(header)
            if arg_str:
                log(f"{indent}{self._color('│ args:', 'yellow')} {arg_str}")

        # === LINE ===
        elif event == "line":
            line = linecache.getline(str(filename), frame.f_lineno).strip()
            log(f"{indent}{self._color('│ →', 'cyan')} {self._color(line, 'reset')}")
            local_vars = fmt_locals(frame.f_locals)
            if local_vars:
                log(f"{indent}{self._color('│ • locals:', 'gray')} {local_vars}")

        # === RETURN ===
        elif event == "return":
            msg = f"{indent}{self._color('╰↩', 'green', 'bold')} {self._color('return', 'gray')} {short(arg)} {ts}"
            log(msg)

        # === EXCEPTION ===
        elif event == "exception":
            exc_type, exc_value, _ = arg
            msg = f"{indent}{self._color('💥', 'red', 'bold')} {exc_type.__name__}: {exc_value}  {self._color(fmt_path(rel, frame.f_lineno), 'gray')}"
            log(msg)

        # === END ===
        elif event == "return":
            msg = f"{indent}{self._color('╰↩', 'green', 'bold')} {self._color('return', 'gray')} {short(arg)} {ts}"
            log(msg)

        return self.trace

    def __enter__(self):
        sys.settrace(self.trace)
        return self

    def __exit__(self):
        sys.settrace(None)

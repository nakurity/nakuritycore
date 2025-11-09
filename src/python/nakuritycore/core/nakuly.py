# nakuly.py
from __future__ import annotations
import inspect
import traceback
import importlib.util
import os
from collections import deque
import json
import time
from datetime import datetime
from typing import Any, List, Dict, Optional

from .devy import Devy
from .nakurity import NakurityRule, NakurityDocRule, NakurityTypeRule, NakurityCustomRule

class Nakuly(Devy):
    """
    Nakuly — full-spectrum developer assistant.

    Extends Devy (runtime + compile protection) with Nakurity-style
    static rule validation (docstrings, typing, naming, etc.).
    
    Automatically enables all Devy protection features on initialization.
    """

    def __init__(self, auto_enable: bool = True, **kwargs):
        super().__init__(**kwargs)
        # Preload default Nakurity rules
        self.rules: List[NakurityRule] = [
            NakurityDocRule(),
            NakurityTypeRule(),
            NakurityCustomRule(),
        ]
        self.logger("✨ Nakuly initialized with base rules.")
        
        # Auto-enable all Devy features by default
        if auto_enable:
            self.enable()
            self.logger("🚀 Auto-enabled all Devy protection features (import guard, builtins patching, runtime tracing)")

    # ------------------------------------------------------------
    #  🔹 Developer-Side Orchestration Utilities
    # ------------------------------------------------------------
    def reload_rules(self):
        """Reload all Nakurity rule modules dynamically."""
        for rule in self.rules:
            try:
                mod = importlib.import_module(rule.__class__.__module__)
                importlib.reload(mod)
                self.logger(f"♻️ Reloaded rule module: {mod.__name__}")
            except Exception as e:
                self.logger(f"⚠️ Failed to reload {rule.name}: {e}")

    def validate_ruleset(self):
        """Check that rule definitions are consistent and unique."""
        names = [r.name for r in self.rules]
        duplicates = [n for n in names if names.count(n) > 1]
        if duplicates:
            self.logger(f"⚠️ Duplicate rules detected: {duplicates}")
        else:
            self.logger(f"✅ Ruleset validated — {len(self.rules)} unique rules.")
        self.check_rule_health()

    def audit_environment(self):
        """Quick environment snapshot for diagnostics."""
        import platform, sys
        snapshot = {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "rules": [r.name for r in self.rules],
            "registry_count": len(self._registry),
            "devy_enabled": self._enabled,
            "import_guard_active": self.guard._finder is not None,
            "builtins_patched": self.guard._patched,
            "tracer_active": self.guard._tracer is not None,
        }
        self.logger(f"🌍 Environment audit:\n{json.dumps(snapshot, indent=2)}")
        return snapshot

    def trace_analysis(self, verbose: bool = False):
        """Print detailed analysis steps (for debugging rules)."""
        for entry in self._registry:
            obj = entry.get("obj")
            name = getattr(obj, "__name__", repr(obj))
            self.logger(f"🔹 Tracing {name}")
            for rule in self.rules:
                try:
                    result = rule.check(entry, obj, self.logger)
                    if verbose:
                        self.logger(f"   ↳ {rule.name}: {result}")
                except Exception as e:
                    self.logger(f"   💥 {rule.name} crashed: {e}")

    def monitor_changes(self, path: str, interval: float = 2.0):
        """Simple polling-based file watcher for auto-lint."""
        import time
        last_mtime = {}
        self.logger(f"👀 Watching for changes in {path}...")
        while True:
            changed = []
            for root, _, files in os.walk(path):
                for f in files:
                    if f.endswith(".py"):
                        fp = os.path.join(root, f)
                        mtime = os.path.getmtime(fp)
                        if fp not in last_mtime or mtime > last_mtime[fp]:
                            last_mtime[fp] = mtime
                            changed.append(fp)
            if changed:
                self.logger(f"♻️ Detected {len(changed)} changed files — re-linting.")
                for c in changed:
                    try:
                        spec = importlib.util.spec_from_file_location("auto_reload", c)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        self.lint_module(module)
                    except Exception as e:
                        self.logger(f"💥 Error reloading {c}: {e}")
            time.sleep(interval)

    def export_session_cache(self, path: str):
        """Dump cached session results to a JSON file."""
        if not hasattr(self, "_session_cache") or not self._session_cache:
            self.logger("⚠️ No cached results to export.")
            return
        payload = {
            "timestamp": datetime.now().isoformat(),
            "snapshots": list(self._session_cache),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        self.logger(f"🧾 Exported session cache to {path}")

    def diff_snapshots(self, index_a: int, index_b: int):
        """Compare two cached snapshots by index."""
        if not hasattr(self, "_session_cache"):
            self.logger("⚠️ No session cache found.")
            return
        try:
            a = self._session_cache[index_a]
            b = self._session_cache[index_b]
        except IndexError:
            self.logger("⚠️ Invalid cache indices.")
            return
        delta = b["passed"] - a["passed"]
        sign = "⬆️" if delta > 0 else "⬇️" if delta < 0 else "⏸️"
        self.logger(f"📈 Diff between snapshots {index_a} → {index_b}: {sign}{abs(delta)} change in passes.")

    def check_rule_health(self):
        """Validate that all rules can be safely invoked."""
        for rule in self.rules:
            try:
                assert callable(getattr(rule, "check", None)), f"{rule.name} missing .check()"
                self.logger(f"✅ Rule {rule.name} ready.")
            except Exception as e:
                self.logger(f"⚠️ Rule {getattr(rule, 'name', '<unnamed>')} failed validation: {e}")

    def inspect_object(self, obj: Any) -> Dict[str, Any]:
        """Return a detailed inspection of an object."""
        name = getattr(obj, "__name__", repr(obj))
        info = {
            "name": name,
            "type": type(obj).__name__,
            "doc": inspect.getdoc(obj),
            "signature": None,
            "module": getattr(obj, "__module__", None),
            "members": [],
        }
        if inspect.isfunction(obj):
            try:
                info["signature"] = str(inspect.signature(obj))
            except Exception:
                pass
        if inspect.isclass(obj):
            info["members"] = [m for m in dir(obj) if not m.startswith("__")]
        self.logger(f"🔎 Object: {name}\nType: {info['type']}\nDoc: {bool(info['doc'])}\n")
        return info
    
    def summarize_results(self, results: Dict[str, Any]):
        """Print compact summary table."""
        self.logger("📊 Summary:")
        for detail in results["details"]:
            status = "✅" if detail.get("status") else "❌"
            self.logger(f"  {status} {detail['name']}")
        self.logger(f"Total: {results['passed']}/{results['total']} passed")

    def suggest_rules(self):
        """Suggest potential new rule categories based on observed code."""
        needs_doc = any(
            inspect.isfunction(e["obj"]) and not getattr(e["obj"], "__doc__", None)
            for e in self._registry
        )
        suggestions = []
        if needs_doc and not any(r.name.lower().startswith("doc") for r in self.rules):
            suggestions.append("NakurityDocRule")
        if suggestions:
            self.logger(f"💡 Suggested rules: {', '.join(suggestions)}")
        else:
            self.logger("✨ No new rule suggestions.")

    def auto_fix(self):
        """Try to apply fixes from rules that support .fix()."""
        for rule in self.rules:
            if hasattr(rule, "fix"):
                try:
                    fixed = rule.fix(self._registry)
                    self.logger(f"🛠️ Auto-fix applied for {rule.name}: {fixed}")
                except Exception as e:
                    self.logger(f"⚠️ Auto-fix failed for {rule.name}: {e}")

    def init_session_cache(self):
        """Initialize analysis session cache."""
        self._session_cache = getattr(self, "_session_cache", deque(maxlen=5))

    def cache_results(self, results: Dict[str, Any]):
        """Store recent analysis results."""
        self.init_session_cache()
        self._session_cache.append(results)
        self.logger(f"🗃️ Cached results snapshot #{len(self._session_cache)}")

    def compare_last_results(self):
        """Compare last two cached analyses."""
        if not hasattr(self, "_session_cache") or len(self._session_cache) < 2:
            self.logger("⚠️ Not enough cached results to compare.")
            return
        a, b = self._session_cache[-2], self._session_cache[-1]
        delta = b["passed"] - a["passed"]
        sign = "⬆️" if delta > 0 else "⬇️" if delta < 0 else "⏸️"
        self.logger(f"{sign} {abs(delta)} change in passed checks since last run.")

    # ------------------------------------------------------------
    #  🔹 Rule Management
    # ------------------------------------------------------------
    def add_rule(self, rule: NakurityRule):
        """Add a new rule instance."""
        if not isinstance(rule, NakurityRule):
            raise TypeError("Expected NakurityRule instance.")
        self.rules.append(rule)
        self.logger(f"➕ Added rule: {rule.name}")

    def add_rule_class(self, rule_cls: type[NakurityRule]):
        """Add a rule class (auto-instantiated)."""
        self.add_rule(rule_cls())

    def diagnostic_report(self) -> Dict[str, Any]:
        """Return structured diagnostic overview."""
        return {
            "registered_objects": len(self._registry),
            "rules_loaded": [r.name for r in self.rules],
            "runtime_profile": getattr(self, "_runtime_profile", {}),
            "devy_status": {
                "enabled": self._enabled,
                "import_guard": self.guard._finder is not None,
                "builtins_patched": self.guard._patched,
                "tracer_active": self.guard._tracer is not None,
            }
        }

    def print_diagnostic_report(self):
        """Pretty-print diagnostics."""
        report = self.diagnostic_report()
        self.logger("📊 Diagnostic Report")
        self.logger(f"  Registered objects: {report['registered_objects']}")
        self.logger(f"  Rules loaded: {', '.join(report['rules_loaded'])}")
        self.logger(f"  Devy enabled: {report['devy_status']['enabled']}")
        self.logger(f"  Import guard: {report['devy_status']['import_guard']}")
        self.logger(f"  Builtins patched: {report['devy_status']['builtins_patched']}")
        self.logger(f"  Tracer active: {report['devy_status']['tracer_active']}")

    def lint_project(self, root: str, pattern: str = ".py"):
        """Recursively scan a folder and lint all modules."""
        found = 0
        for dirpath, _, filenames in os.walk(root):
            for file in filenames:
                if file.endswith(pattern):
                    module_path = os.path.join(dirpath, file)
                    spec = importlib.util.spec_from_file_location(file[:-3], module_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        try:
                            spec.loader.exec_module(module)
                            self.lint_module(module)
                            found += 1
                        except Exception as e:
                            self.logger(f"💥 Failed to lint {file}: {e}")
        self.logger(f"📦 Project lint completed — {found} modules processed.")

    # ------------------------------------------------------------
    #  🔹 Enhanced Analyzer — merges Devy + Nakurity logic
    # ------------------------------------------------------------
    def analyze(self):
        """Run static + rule-based checks."""
        self.logger("🧩 [Nakuly] Running unified analysis...")

        for entry in self._registry:
            obj = entry["obj"]
            name = getattr(obj, "__name__", "<unnamed>")
            self.logger(f"🔍 Inspecting {name}")

            # Run Devy's internal checks
            try:
                self._analyze_entry(entry)
            except Exception as e:
                self.logger(f"💥 Devy internal error on {name}: {e}")

            # Apply Nakurity rules
            for rule in self.rules:
                try:
                    passed = rule.check(entry, obj, self.logger)
                    status = "✅" if passed else "⚠️"
                    self.logger(f"  {status} [{rule.name}] {rule.description}")
                except Exception as e:
                    self.logger(f"  💥 [{rule.name}] failed with error: {e}")

        self.logger("✅ [Nakuly] All analyses completed.")

    def benchmark_function(self, func, *args, repeat: int = 3, **kwargs):
        """Benchmark execution time of a function."""
        timings = []
        for _ in range(repeat):
            start = time.perf_counter()
            func(*args, **kwargs)
            end = time.perf_counter()
            timings.append(end - start)
        avg = sum(timings) / len(timings)
        self.logger(f"⏱️ {func.__name__} avg: {avg:.6f}s over {repeat} runs")
        return avg

    # ------------------------------------------------------------
    #  🔹 Batch / Project Utilities
    # ------------------------------------------------------------
    def lint_module(self, module):
        """Run analysis on all callables in a module."""
        for name, obj in vars(module).items():
            if inspect.isfunction(obj) or inspect.isclass(obj):
                self._registry.append({"obj": obj})
        self.analyze()

    def lint_globals(self, namespace: Optional[Dict[str, Any]] = None):
        """Run analysis on all globals (functions/classes)."""
        ns = namespace or globals()
        for name, obj in ns.items():
            if inspect.isfunction(obj) or inspect.isclass(obj):
                self._registry.append({"obj": obj})
        self.analyze()

    def run_builtin_tests(self):
        """Run built-in lightweight tests against registered objects.
        Returns dict summary.
        """
        results = []
        for entry in list(self._registry):
            obj = entry.get("obj")
            name = getattr(obj, "__name__", repr(obj))
            res = {"name": name, "checks": []}
            # Basic checks
            try:
                # docstring check
                ok_doc = True
                if inspect.isfunction(obj) or inspect.isclass(obj):
                    doc = getattr(obj, "__doc__", "")
                    ok_doc = bool(doc and doc.strip())
                res["checks"].append(("docstring", ok_doc))

                # signature check
                ok_sig = True
                if inspect.isfunction(obj):
                    sig = inspect.signature(obj)
                    # must accept at least 0 args — example constraint, you can customize
                    ok_sig = True  # flexible — keep true by default
                res["checks"].append(("signature", ok_sig))

                # run registered rules (high level)
                rule_results = {}
                for rule in self.rules:
                    try:
                        rule_ok = bool(rule.check(entry, obj, self.logger))
                    except Exception as e:
                        rule_ok = False
                        self.logger.debug(f"rule {rule.name} threw: {e}\n{traceback.format_exc()}")
                    rule_results[rule.name] = rule_ok
                res["checks"].append(("rules", rule_results))
                res["status"] = all(
                    (ok_doc, ) + tuple(rule_results.values())
                )
            except Exception as e:
                res["status"] = False
                res["error"] = str(e)
                self.logger.debug(f"run_builtin_tests error on {name}: {e}")
            results.append(res)

        # Print a short summary
        ok_count = sum(1 for r in results if r["status"])
        total = len(results)
        self.logger.info(f"Built-in tests: {ok_count}/{total} passed.")
        return {"total": total, "passed": ok_count, "details": results}
    
    def list_rules(self, detailed: bool = False) -> List[str]:
        """List all active rules (optionally with details)."""
        if detailed:
            return [f"{r.name}: {r.description}" for r in self.rules]
        return [r.name for r in self.rules]

    def remove_rule(self, name: str):
        """Remove a rule by name."""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.name != name]
        if len(self.rules) < before:
            self.logger(f"🗑️ Removed rule: {name}")
        else:
            self.logger(f"⚠️ No rule found named {name}")

    def clear_registry(self):
        """Clear all registered entries."""
        count = len(self._registry)
        self._registry.clear()
        self.logger(f"🧹 Cleared {count} registered entries.")

    def register(self, obj: Any, name: Optional[str] = None):
        """Manually register an object for analysis."""
        self._registry.append({"obj": obj, "name": name or getattr(obj, "__name__", "<unnamed>")})
        self.logger(f"📦 Registered {name or obj}")

    def export_results(self, path: str, results: Optional[Dict] = None):
        """Export the last or provided analysis results to a JSON file."""
        results = results or self.run_builtin_tests()
        payload = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": results["total"],
                "passed": results["passed"],
            },
            "details": results["details"],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        self.logger(f"📤 Results exported to {path}")


    # ------------------------------------------------------------
    #  🔹 Runtime Diagnostics Enhancement
    # ------------------------------------------------------------
    def report_summary(self):
        """Compact summary of performance + rule results."""
        self.profile_runtime()
        self.logger(f"📋 Total entries analyzed: {len(self._registry)}")
        self.logger(f"📏 Rules active: {[r.name for r in self.rules]}")
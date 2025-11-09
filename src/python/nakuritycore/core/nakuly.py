# nakuly.py
from __future__ import annotations
import inspect
from typing import Any, List, Dict, Optional

from .devy import Devy
from .nakurity import NakurityRule, NakurityDocRule, NakurityTypeRule, NakurityCustomRule

class Nakuly(Devy):
    """
    Nakuly — full-spectrum developer assistant.

    Extends Devy (runtime + compile protection) with Nakurity-style
    static rule validation (docstrings, typing, naming, etc.).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Preload default Nakurity rules
        self.rules: List[NakurityRule] = [
            NakurityDocRule(),
            NakurityTypeRule(),
            NakurityCustomRule(),
        ]
        self.logger("✨ Nakuly initialized with base rules.")

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

            # Run Devy’s internal checks
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

    # ------------------------------------------------------------
    #  🔹 Runtime Diagnostics Enhancement
    # ------------------------------------------------------------
    def report_summary(self):
        """Compact summary of performance + rule results."""
        self.profile_runtime()
        self.logger(f"📋 Total entries analyzed: {len(self._registry)}")
        self.logger(f"📏 Rules active: {[r.name for r in self.rules]}")

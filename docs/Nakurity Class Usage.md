# 🧠 Nakurity Enforcement & Runtime Linter

**Purpose:**
The Nakurity system enforces **static discipline and runtime validation** for all modules in your project.
It ensures every function or class has declared expectations, guards, and dependencies — verified both at **import-time** and **execution-time**.

---

## ⚙️ Architecture Overview

| Stage                  | Mechanism                                     | Description                                                  |
| ---------------------- | --------------------------------------------- | ------------------------------------------------------------ |
| **Compile-time**       | `@Nakurity.compile()` + import hook           | Runs minimal AST checks before code executes.                |
| **Runtime**            | `@Nakurity.expect()` + `@NakurityRequirement` | Performs decorator-based linting after module load.          |
| **Import Enforcement** | Patched `__import__`                          | Automatically applies compile checks to selected namespaces. |

---

## 🧩 Decorators

### `@Nakurity.compile(expectation: str = None)`

Marks an object for **compile-time validation**.
Used for static checks (argument counts, structure, etc.) before runtime.

```python
@Nakurity.compile("expected 2 args")
def add(x, y):  # ✅ passes
    return x + y
```

If the expectation is violated:

```
⚠️ [Nakurity.compile] add: expected 2 args, found 1
```

---

### `@Nakurity.expect(text: str)`

Defines runtime expectations for a function or class.

Supported rules:

* `expects N args: ...`
* `must call foo()`
* `should not raise`
* `returns <type>`
* `perform <action>`

```python
@Nakurity.expect("""
expects 1 argument: name
returns str
must call greet
should not raise
""")
def say_hi(name: str) -> str:
    greet(name)
    return f"Hello, {name}"
```

---

### `@Nakurity.comment(text: str)`

Adds a human-readable hint or description, used in log output for failed checks.

```python
@Nakurity.comment("Ensures proper integer doubling.")
def double(x: int) -> int:
    return x * 2
```

---

### `@Nakurity.require(*names: str)`

Declares that specific identifiers or modules must exist at runtime.

```python
@Nakurity.require("math", "greet")
def circle_area(r: float) -> float:
    return math.pi * (r ** 2)
```

---

### `@Nakurity.guard(condition: str)`

Adds a runtime guard expression that must evaluate to `True` before execution.

```python
@Nakurity.guard("'greet' in globals()")
def say_hi(name: str):
    greet(name)
```

If the guard fails:

```
⚠️ Guard failed for say_hi: 'greet' in globals()
   💡 Hint: Greeter must exist before runtime.
```

---

## 🔍 Linting Flow

When you call:

```python
if __name__ == "__main__":
    Nakurity().lint()
```

It performs:

1. **Requirement check** — verifies required names are defined.
2. **Guard evaluation** — ensures guard conditions are true.
3. **Static inspection** — validates argument names, annotations, etc.
4. **AST analysis** — detects function calls and structure.
5. **Runtime simulation** — executes the function safely with dummy args.

Example output:

```
🔍 Inspecting function: say_hi
   💬 Simple greeting test
   📦 Requires: greet
   🧩 Guard: 'greet' in globals()

✅ say_hi: found required dependency 'greet'.
✅ say_hi: called required function 'greet()'
✅ Nakurity lint completed successfully.
```

---

## 🧱 Compile-Time Enforcement

To automatically trigger Nakurity during imports, the system installs two hooks:

```python
builtins.__import__ = [_nakurity_guarded_import, _nakurity_import]
```

* `_nakurity_guarded_import`: Runs **NakurityRequirement** on modules starting with `nakurity_` or `nakuritycore.`
* `_nakurity_import`: Runs **compile-time checks** via `_compile_pass()`.

This ensures Nakurity applies **before and after** import for internal namespaces.

Example output:

```
[Nakurity] ⚙️ Compile-time checks failed for nakurity_example: expected 2 args, found 3
```

---

## 🔒 NakurityRequirement

`NakurityRequirement` enforces **decorator discipline** per module.
When invoked, it ensures all functions and classes are registered via any Nakurity decorator.

```python
from nakurity.core import Nakurity, NakurityRequirement
import sys

@Nakurity.expect("takes 1 argument: x\nreturns int")
def double(x: int) -> int:
    return x * 2

NakurityRequirement(sys.modules[__name__])
```

If a function lacks any Nakurity decorator:

```
🚫 [NakurityRequirement] untracked_func is missing Nakurity decorators.
    → Use @Nakurity.expect / @Nakurity.comment / @Nakurity.require / @Nakurity.guard
```

---

## 🧠 Example Project Flow

```python
# file: mymodule.py
from nakuritycore import Nakurity, NakurityRequirement
import sys

def greet(name: str):
    print(f"Hi {name}")

@Nakurity.expect("""
expects 1 argument: name
returns str
must call greet
should not raise
""")
@Nakurity.require("greet")
@Nakurity.guard("'greet' in globals()")
def say_hi(name: str) -> str:
    greet(name)
    return f"Hello, {name}"

if __name__ == "__main__":
    NakurityRequirement(sys.modules[__name__])
```

Output:

```
[NakurityRequirement] Running enforced lint checks...

🔍 Inspecting function: say_hi
✅ say_hi: found required dependency 'greet'.
✅ say_hi: called required function 'greet()'
✅ Nakurity lint completed successfully.
```

---

## 📚 Summary

| Feature               | Purpose                                                    |
| --------------------- | ---------------------------------------------------------- |
| `@Nakurity.expect()`  | Defines runtime rules and structure                        |
| `@Nakurity.comment()` | Adds contextual hints                                      |
| `@Nakurity.require()` | Enforces presence of names or modules                      |
| `@Nakurity.guard()`   | Ensures logical runtime preconditions                      |
| `@Nakurity.compile()` | Enables compile-time checks via AST                        |
| `NakurityRequirement` | Enforces all functions/classes are decorated               |
| Import Hook           | Triggers compile + runtime validation during module import |

---
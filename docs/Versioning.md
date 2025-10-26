# Versioning Guide

This project follows a simplified **semantic-style versioning** system:

```
MAJOR.MINOR.PATCH
```

### 🧪 Alpha (Experimental)

**Format:** `0.0.X`

* The last number (`PATCH`) increments during early development.
* Features are experimental and may change or break without notice.
* Example: `0.0.1`, `0.0.2`, `0.0.3` ...
* These are **alpha** releases.

### ⚙️ Beta (Feature Testing)

**Format:** `0.X.0`

* The middle number (`MINOR`) increments when entering broader testing.
* The codebase is more stable, but APIs or behaviors may still shift.
* Example: `0.1.0`, `0.2.0`, `0.3.0` ...
* These are **beta** releases.

### 🚀 Stable (Production)

**Format:** `1.0.0` and beyond

* The project is considered feature-complete and stable.
* Backward compatibility is maintained between minor and patch versions.
* Example: `1.0.0`, `1.1.0`, `1.1.1`, etc.

---

### Summary Table

| Stage  | Example | Meaning                    |
| ------ | ------- | -------------------------- |
| Alpha  | 0.0.1   | Early prototype, unstable  |
| Beta   | 0.1.0   | Testing phase, semi-stable |
| Stable | 1.0.0   | Reliable, production-ready |
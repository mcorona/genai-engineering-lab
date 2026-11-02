---
type: regex
target: {source: file, path: auditoria/resumen.md}
match: not_contains
flags: i
---

\bSELECT\b|```

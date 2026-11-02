---
type: llm
focus: {source: file, path: auditoria/resumen.md}
---

PASS only if ALL of these hold: (1) it is written for a non-technical executive, without SQL or column-level jargon dominating; (2) it mentions orders that point to customers that do not exist (orphans); (3) it mentions that customer personal data (names, emails, phones) is stored; (4) it gives concrete next steps; (5) it contains no email address or phone number. Otherwise FAIL.

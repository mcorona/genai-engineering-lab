---
type: regex
target: {source: file, path: auditoria/diccionario.yaml}
---

cli_eml[\s\S]{0,500}?personal_data:\s*true

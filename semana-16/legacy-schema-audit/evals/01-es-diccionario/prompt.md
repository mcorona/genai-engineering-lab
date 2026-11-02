---
max_turns: 45
timeout_seconds: 900
allowed_tools: [Skill, Read, Write, Edit, ToolSearch, mcp__plugin_legacy-schema-audit_legacy-sql__list_objects, mcp__plugin_legacy-schema-audit_legacy-sql__describe_object, mcp__plugin_legacy-schema-audit_legacy-sql__profile_table, mcp__plugin_legacy-schema-audit_legacy-sql__run_select]
runs: 3
---

Heredamos una base de datos de pedidos de los años 90 (esquema `ventas`) con nombres de columnas crípticos. Necesito documentarla para el equipo nuevo: genera el diccionario de datos y el diagrama de relaciones.

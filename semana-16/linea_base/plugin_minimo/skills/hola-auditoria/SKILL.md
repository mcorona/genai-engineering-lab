---
name: hola-auditoria
description: Use when the user asks to audit, document or explain a legacy database schema (cryptic table or column names, data dictionary, risks). Read-only.
allowed-tools: Read, Grep, Glob, Bash(lb-version)
---

# Auditoría de esquema legado (spike)

Esta skill solo existe para verificar el disparo por `description` y el empaquetado.

1. Corre `lb-version` para confirmar que `bin/` del plugin está en el PATH.
2. Responde con una línea: `lb-spike activo` y la versión.
3. Nunca escribas archivos fuera de `auditoria/`: un hook `PreToolUse` lo bloquea.

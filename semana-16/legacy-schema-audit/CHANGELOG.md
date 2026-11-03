# Changelog

All notable changes to `legacy-schema-audit`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the version follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): a change to what the deliverables
contain, or to what the plugin is allowed to do, is a major version.

## [1.0.0] - 2026-11-02

First release for clients, published in the `genai-engineering-lab` marketplace.

### Added
- Marketplace entry (`.claude-plugin/marketplace.json` at the repository root). Install with
  `claude plugin marketplace add mcorona/genai-engineering-lab` and
  `claude plugin install legacy-schema-audit@genai-engineering-lab`.
- Client README: what it does and never does, requirements, configuration (a read-only DSN or a remote MCP server),
  cost by schema size, and known limits.
- `ejemplo/`: a complete sample audit (dictionary, ER diagram, risks with SQL, executive summary) of the synthetic
  `legado` schema.
- This changelog.

### Changed
- No behavior change from 0.1.0: the version marks the first release for clients and the start of the
  compatibility promise above.

## [0.1.0] - 2026-11-02

Lab version, built and measured in week 16 of the GenAI Engineering Lab (activities 3 to 7). It was never published.

### Added
- Skill `auditar` and the commands `auditoria-completa`, `solo-diccionario` and `solo-riesgos`. They write
  `auditoria/diccionario.yaml`, `relaciones.mmd`, `riesgos.md` and `resumen.md` (activity 3).
- Bundled MCP server `legacy-sql` with `list_objects`, `describe_object`, `profile_table` and `run_select`. It runs
  one validated `SELECT` at a time in a read-only transaction, limited to the configured schema. The DSN is a
  sensitive option kept in the system keychain (activity 3).
- Subagents `perfilador`, `analista-relaciones` and `revisor-riesgos`, each with a minimal tool list (activity 4).
- Hooks (activity 4):
  - `SessionStart` checks that the role is read-only;
  - `PreToolUse` runs the guard, which fails closed (`onFailure: block`);
  - `PostToolUse` appends every database query to `auditoria/bitacora.jsonl`.
- Plugin eval suite: 10 cases with mocks, scored with `claude plugin eval` (activity 5).

### Security
- The guard blocks personal data (emails, phones, tax IDs) in deliverables and YAML that does not parse. The server's
  instructions make the agent decline requests to fix or delete data (activity 5).
- The guard blocks findings without their `SELECT`, reads outside the project and of shell profiles and credential
  files, and every block is logged in `auditoria/bloqueos.jsonl`. This was hardened after a security case read a
  real `~/.zshrc` (activity 6).
- Browser tools (activity 7):
  - only Playwright MCP tools that look are allowed, and only on local origins;
  - typing, filling, page scripts and submit-like clicks are blocked;
  - the user's own browser (Claude in Chrome) is blocked.

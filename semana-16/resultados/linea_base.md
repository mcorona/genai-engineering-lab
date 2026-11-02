# Activity 1: baseline of Claude Code as a platform for client plugins

Verified on 2026-11-02 with **Claude Code 2.1.316**, the version on the Mac and in this lab's container. Everything marked **M** was checked by running the installed CLI in [`linea_base/verificar.py`](../linea_base/verificar.py) (18 checks, $0, no model call). The spike plugin is [`linea_base/plugin_minimo/`](../linea_base/plugin_minimo/), with a local marketplace in [`linea_base/.claude-plugin/marketplace.json`](../linea_base/.claude-plugin/marketplace.json). Raw evidence: [`linea_base.json`](linea_base.json). Tests: [`tests/test_linea_base.py`](../tests/test_linea_base.py).

**M** = measured by running code in this activity · **D** = documented (official docs or `--help` of the installed version), not exercised yet · **N** = not verified on this Mac yet.

```bash
cd semana-16
python linea_base/verificar.py                 # 18 checks, no model ($0)
python linea_base/verificar.py --con-modelo    # + 2 headless runs (Claude Code subscription, not the API)
```

## Capability matrix

### Plugins and distribution

| Capability | What was found | |
|---|---|---|
| `claude plugin` subcommands | `validate`, `eval`, `details`, `configure`, `marketplace`, `install`, `init`, `tag`, `update`, `uninstall`, `list` | M |
| `claude plugin validate --strict --json` | The spike passes with 0 warnings. **Reserved names are rejected**: `claude-legacy-audit` fails because names cannot start with `claude-` or `anthropic-`. **Paths with `..` are rejected** as path traversal | M |
| `--profile directory` | Checks used by Anthropic's plugin directory: it asks for an icon (512–2048 px PNG) and a README install line | M |
| Local marketplace → install → `details` | Works in a throwaway `CLAUDE_CONFIG_DIR`. `details` prints the inventory and the **projected token cost**: the spike costs ~100 tokens always on (skill ~60, agent ~40) and ~160 more when the skill fires. Hooks cost no model context | M |
| `userConfig` with `sensitive: true` | `configure` lists the option as sensitive without showing a value; values go to the OS credential store, not `settings.json` | M (listing) · D (storage) |
| `bin/` on the Bash PATH | Declared in the spike (`lb-version`). **Plugins with `bin/` are not installed by claude.ai or Cowork organization sync**, so the client plugin should call its scripts explicitly | D |
| `${CLAUDE_PLUGIN_ROOT}` in hooks | Used in exec form (`args`), where it is substituted as one argument with no shell | M (validated) |
| Versioning | `version` pins users to a release; `claude plugin tag` creates `{name}--v{version}` after checking manifest and marketplace agree | D |

### Skills and subagents

| Capability | What was found | |
|---|---|---|
| Skill frontmatter | `name`, `description`, `allowed-tools` (including scoped `Bash(lb-version)`); namespaced as `lb-spike:hola-auditoria` | M (loads, inventoried) |
| Triggering by `description` | Claude picks the skill from its description; measured with `--con-modelo` and, from activity 5, with `tool_used: Skill` graders and the no-plugin baseline (Δ) | D → M with `--con-modelo` |
| Subagent frontmatter | `tools` is an allowlist; `disallowedTools` a denylist applied first; `model` takes `haiku`, `sonnet`, `opus`, `inherit` or a full ID | M (loads) · D |
| **Plugin subagents ignore `hooks`, `mcpServers` and `permissionMode`** | The spike agent declares a hook on purpose: the validator raises no warning, and the docs say it is ignored. **Guard hooks must live in the plugin's `hooks/hooks.json`**, which applies to the whole session including subagents | D (behavior) · M (validator silent) |

### Hooks

| Capability | What was found | |
|---|---|---|
| Events used | `PreToolUse` (block writes), `PostToolUse` (JSONL audit log), `SessionStart` (context line) | M (scripts) · D (runtime wiring) |
| Blocking | Exit code **2** blocks and sends stderr to Claude. Alternative: exit 0 with JSON `hookSpecificOutput.permissionDecision: "deny"`. With exit 2, JSON cannot override the block | M (exit codes) · D |
| **Hooks fail open by default** | A hook that cannot start, crashes (exit other than 0 or 2), returns invalid JSON or times out is a *non-blocking error* and the tool call goes ahead. **`onFailure: "block"`** (v2.1.295 or later) makes any failure block. The spike uses it, and its guard also exits 2 on unreadable input | D (runtime) · M (guard fails closed) |
| Exec form vs shell form | With `args`, the command is spawned with no shell and `${CLAUDE_PLUGIN_ROOT}` is one literal argument; shell form is for pipes and `&&`. `${user_config.*}` is only substituted in exec form | M (validated) · D |
| Default timeout | 600 s for command hooks (30 s on `UserPromptSubmit`); a timed-out `PreToolUse` hook does not block unless `onFailure: "block"` | D |
| **`claude --bare` skips hooks and plugins** | A user who starts Claude Code with `--bare` bypasses every plugin hook. **Hooks are a guardrail, not a security boundary**: read-only access must come from the database role or the MCP server | D |
| Guard heuristics | Scripted cases in `verificar.py` and the tests pass: Write outside `auditoria/`, an `auditoria/../` escape, `DELETE`, `UPDATE` and `lo_import` all blocked; Write inside `auditoria/`, `SELECT` and Read allowed | M |

### Headless mode and plugin evals

| Capability | What was found | |
|---|---|---|
| `claude -p` | `--plugin-dir` (directory or `.zip`), `--output-format json`, `--max-turns`, `--allowedTools`, `--permission-mode`, `--model`; `--max-budget-usd` only applies to API billing | D → M with `--con-modelo` |
| **`--allowedTools` is variadic** | `claude -p --allowedTools Skill Read "prompt"` takes the prompt as one more tool name: Claude Code exits in about 1 s with no output. Found on the Mac in the first `--con-modelo` run. Pass the prompt through stdin (or put it before the flag) and the tools as one comma-separated value. Checks read `--output-format stream-json --verbose` events (which skill and tools ran) instead of the final text | M |
| `claude plugin eval init --bare` | Writes `evals/<case>/prompt.md` (frontmatter `max_turns: 10`, `allowed_tools: [Read, Glob, Grep, Skill]`) and `graders/criteria.md` (`type: llm`) | M |
| Graders | Six types: `regex`, `tool_used`, `tool_order` and `file_exists` are free; `llm` and `baseline` call a judge (default Haiku). **No custom-code graders** | D |
| Baseline and runs | Each case runs 3 times by default, with and without the plugin; Δ = what the plugin adds. `--ablation none` halves the cost | D |
| MCP mocks | `evals/mocks/<server>/<tool>.md` answers tool calls; real servers start only with `--mocks off` or `--allow-real-servers` | D |
| Sandbox | Granting `Bash` runs it under the OS sandbox (macOS built in; Linux needs `bubblewrap` and `socat`); writes confined to the run's workspace | D |
| Cost control | `--max-cost-usd` is checked before each run; exit 2 with partial results. Exit 1 when a case scores below `--threshold` | D |
| Billing | Runs use the session's credentials: the **subscription on the Mac**, the API key in CI | D |

### Browser agents and computer use

| Capability | What was found | |
|---|---|---|
| Playwright MCP | `@playwright/mcp@0.0.84` with Playwright `1.65.0-alpha-2026-10-30` and `chromium-1252`, installed on the Mac. Options include `--allowed-origins` (trusted origins the browser may request) and `--allowed-hosts`. Pinned because it depends on an alpha Playwright | M (installed) · D (behavior) |
| Claude in Chrome | `claude --chrome` enables it; it drives the user's real Chrome with their sign-ins, with per-site permissions in the extension. Whether the extension is installed on the Mac is still unchecked | D · N |
| Isolation | Playwright MCP runs its own Chromium profile; Claude in Chrome shares the user's sessions. For client work on a legacy screen, **Playwright MCP limited to `127.0.0.1`** is the safer default | D |
| Computer use | `{"type": "computer_toolset_20260801"}`, **GA, no beta header**, 17 member tools; Claude 5.5 models accept only the toolset. Reference implementation: a Docker container (Xvfb, a window manager, a web UI) | D |
| Computer use cost | The toolset definition adds ~4,500 input tokens per request; each screenshot ~1,000–1,800. With Haiku 5.5 ($0.10 / $0.50 per million tokens) a step costs about **$0.0006–0.003**, growing with the screenshots kept in history. A 20-step task is about **$0.02–0.05** | D (estimate) |
| Computer use security | Dedicated VM or container, a domain allowlist, no credentials on screen, human confirmation for consequential actions; screenshots are scanned for prompt injection | D |

## Gaps and design decisions for the client plugin

1. **Hooks fail open and can be skipped.** Set `onFailure: "block"` on every guard hook and make the script fail closed. Even so, `--bare` and other tools can bypass a hook, so read-only access must be enforced by the database role or the MCP server.
2. **Plugin subagents cannot carry their own hooks or MCP servers.** Guard hooks go in `hooks/hooks.json` and the MCP server in `.mcp.json`; subagents only narrow `tools` and pick `model`.
3. **`bin/` blocks distribution through claude.ai or Cowork.** The client plugin calls scripts with `${CLAUDE_PLUGIN_ROOT}` paths instead.
4. **`plugin eval` has no code graders.** Behavior is graded there (skill fired, tools used, files created, Δ against no plugin). Quality (dictionary accuracy, foreign keys, personal data, seeded risks) needs our own evaluator, as planned for activity 5.
5. **Sensitive `userConfig` values are not substituted into skill text or shell-form hooks.** Read them in exec-form hooks or through `CLAUDE_PLUGIN_OPTION_<KEY>`; never echo them into reports.
6. **The SQL guard is a heuristic.** A regex catches the obvious write verbs; obfuscated SQL is stopped by the read-only role, which the activity 6 security cases must prove. It also does not catch shell redirects (`echo x > file`): in the spike, Bash writes are stopped by permissions, and the client plugin must not grant generic Bash.
9. **Testing a hook requires isolating it.** In the first Mac run the model never attempted the write: the `SessionStart` line ("read-only mode") was enough to make it decline, so the hook went untested. The headless check now switches that context off (`LB_SIN_CONTEXTO=1`), offers only `Write` with `acceptEdits`, and requires the guard's own message in the tool result. Activity 6 security evals must do the same, or a model that refuses hides a broken hook.
7. **Directory listing requirements:** an icon (512–2048 px PNG) and a README install line. They are cheap to add and needed if the plugin is submitted.
8. **Name:** `legacy-schema-audit` passes the reserved-name rule; any name starting with `claude-` would be rejected.

## Pending on the Mac

| Check | Command | Cost |
|---|---|---|
| The 18 no-model checks with your installation | `python linea_base/verificar.py` | $0 |
| Skill fires on a natural request; the hook blocks a write | `python linea_base/verificar.py --con-modelo` | Subscription usage, 2 short runs with Haiku |
| Claude in Chrome extension installed | `claude --chrome`, then check the connection status | $0 |

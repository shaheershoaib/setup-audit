---
name: setup-audit
description: >-
  Grade the Claude agent setup (~/.claude) and catch SILENT breakage - a skill
  whose frontmatter won't parse so it never loads, a hook pointing at a
  moved/renamed script so it no-ops, an MCP whose entry file is gone, a skill
  dir with no SKILL.md, or an accidental deletion (drift vs a saved snapshot).
  Use when asked to "audit my setup", "is my Claude config healthy", "grade my
  agent setup", after editing skills/agents/hooks/MCPs, or before sharing the
  environment bundle with someone.
---

# setup-audit

A health check for the agent environment itself - the meta layer most setups
never verify until something silently stops working. (The "grade your setup"
idea, kept to a static dependency-free
check.)

## What it checks
- **Skills** - every `~/.claude/skills/*/SKILL.md` parses as frontmatter and has
  `name:` + `description:`; `name` matches the directory; flags skill dirs with
  no SKILL.md. (A malformed frontmatter means the skill never loads - the
  failure is invisible until you reach for it.)
- **Agents** - every `~/.claude/agents/*.md` has valid frontmatter.
- **Hooks** - every `command` in `~/.claude/settings.json` resolves to a script
  that EXISTS and (for `.sh`) is executable. A hook pointing at a moved file
  fails silently.
- **MCP servers** - every user-scope server in `~/.claude.json` has its entry
  file present on disk (static check; see live-status step below).
- **Plugins + core** - inventories plugins; confirms `~/.claude/CLAUDE.md`.
- **Drift** - compares the current inventory against a saved snapshot and lists
  anything ADDED or REMOVED (catches accidental deletions).

## Run it

```bash
python3 ~/.claude/skills/setup-audit/audit.py
```

Output is a readiness score, then `FAIL` (broken - fix) and `WARN` (check)
findings, then drift vs snapshot. Exit code is 1 if any FAIL.

**Live MCP status** (the static check only proves the entry file exists, not
that the server handshakes): run

```bash
claude mcp list
```

and confirm each server reads `✔ Connected`. A server that fails here but passes
the static check usually has a runtime error - run `node <entry>` or check
`claude mcp get <name>`.

**Baseline a known-good setup** so future runs can detect drift:

```bash
python3 ~/.claude/skills/setup-audit/audit.py --snapshot
```

Re-snapshot deliberately after intentional changes; between snapshots, drift
lines are the diff.

## Interpreting

- **FAIL** = it will not work as intended (skill won't load, hook script gone,
  MCP entry missing). Fix before relying on it.
- **WARN** = worth a look (name/dir mismatch, non-executable hook, inline hook
  command with no script file to verify, missing optional core file).
- **Drift** = an item appeared or disappeared since the snapshot. Expected after
  you add/remove things; suspicious otherwise (e.g. a skill you didn't mean to
  delete).

## When to use
- After editing skills/agents/hooks/MCPs (did anything silently break?).
- Before packaging/sharing the environment with a teammate (ship a clean setup).
- Periodically, as a config-health pass.

## Related
- The user-scope MCP servers in `~/.claude.json` are what the MCP check audits.
- `fewer-permission-prompts` - the other "tune your setup" skill.

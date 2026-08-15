# setup-audit

**Your agent setup breaks silently. This catches it.**

A skill with a typo in its frontmatter doesn't error — it just never loads. A hook
pointing at a script you renamed doesn't warn — it no-ops. An MCP server whose entry
file you deleted doesn't complain until the moment you reach for it.

None of these show up as failures. They show up as your agent quietly not doing the
thing you built it to do, weeks later, with no obvious cause.

`setup-audit` is a static, dependency-free health check for `~/.claude` that finds
these before they cost you a debugging session.

---

## The problem

Every other part of your stack has a health check. Your agent environment — the layer
that decides which skills load, which hooks fire, which servers connect — has none.
It fails open. A malformed skill is indistinguishable from a skill you forgot you
wrote.

The failure mode is always the same: **you assume a capability is active, and it
isn't.** You ask for the thing, get generic behaviour instead, and never think to
check whether the skill loaded at all.

## Run it

```bash
python3 audit.py
```

A healthy setup:

```
==============================================================
  Claude setup audit - readiness 100%  (41/41 OK)
==============================================================
  skills:29  agents:11  hooks:0  mcps:0  plugins:2
```

A broken one:

```
==============================================================
  Claude setup audit - readiness 29%  (2/7 OK)
==============================================================
  skills:2  agents:1  hooks:1  mcps:1  plugins:0

FAIL (broken - fix):
  x [skill] broken-skill: no YAML frontmatter (won't load)
  x [mcp] local-thing: entry file missing -> ['~/.claude/mcp/gone.js']

WARN (check):
  ! [skill] no-skillmd: directory has no SKILL.md
  ! [hooks] no resolvable script file (inline?): ~/.claude/hooks/moved-script.sh
  ! [core] missing ~/.claude/CLAUDE.md
```

Exit code is `1` if anything FAILs, so it drops straight into CI or a pre-commit hook.

## What it checks

| Area | Check | Why it matters |
|---|---|---|
| **Skills** | `SKILL.md` frontmatter parses, has `name:` + `description:`, `name` matches the directory | Malformed frontmatter means the skill never loads — invisibly |
| **Agents** | every `~/.claude/agents/*.md` has valid frontmatter | Same silent-load failure |
| **Hooks** | every `command` in `settings.json` resolves to a file that exists and (for `.sh`) is executable | A hook pointing at a moved script fails silently |
| **MCP servers** | every user-scope server in `~/.claude.json` has its entry file on disk | Deleted entry file = server that never handshakes |
| **Plugins + core** | inventories plugins, confirms `~/.claude/CLAUDE.md` exists | Catches a missing global instruction file |
| **Drift** | current inventory vs a saved snapshot, listing ADDED / REMOVED | Catches the deletion you didn't mean to make |

## Drift detection

Baseline a setup you know is good:

```bash
python3 audit.py --snapshot
```

Every later run diffs against it:

```
Drift vs snapshot:
  - REMOVED skills: parity-receipt
  + ADDED   agents: bug-auditor
```

Expected after you add or remove something deliberately. Suspicious otherwise — this
is the check that catches a skill directory you nuked by accident three weeks ago.

Re-snapshot after intentional changes; between snapshots, the drift lines are your diff.

## FAIL vs WARN

- **FAIL** — it will not work as intended. The skill won't load, the hook script is
  gone, the MCP entry is missing. Fix before relying on it.
- **WARN** — worth a look. Name/directory mismatch, non-executable hook, an inline
  hook command with no script file to verify, a missing optional core file.

## One thing it can't prove

The MCP check is static — it proves the entry file exists, not that the server
actually handshakes. For that:

```bash
claude mcp list
```

Confirm each server reads `✔ Connected`. A server that passes the static check but
fails here has a runtime error: run `node <entry>` directly or check
`claude mcp get <name>`.

## Install as a skill

Drop it into your skills directory and the agent can run it on request ("audit my
setup", "is my Claude config healthy"):

```bash
git clone https://github.com/shaheershoaib/setup-audit ~/.claude/skills/setup-audit
```

`SKILL.md` in this repo is the skill definition. The snapshot is written to
`~/.claude/skills/setup-audit/snapshot.json`, so installing at that path keeps drift
detection working across runs.

Or just run `audit.py` standalone from anywhere — it has no dependencies beyond the
Python 3 standard library and reads only `~/.claude` and `~/.claude.json`.

## When to run it

- After editing skills, agents, hooks, or MCPs — did anything silently break?
- Before sharing your environment with a teammate — ship a setup that works.
- Periodically, as a config-health pass.

## License

Apache 2.0 — use it freely, including commercially. Keep the `NOTICE` file if you
redistribute it (§4(d)).

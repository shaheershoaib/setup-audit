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

## Does the routing actually fire? (`--adherence`)

The check above answers "does every file parse and every path resolve". It cannot see a
skill that parses perfectly and has never once been invoked, so a setup can report
**readiness 100%** while most of its routing table is dead. That happened: a real setup
graded 76/76 OK while 20 of the 30 skills its router named had never fired across 891
sessions, and its downstream chain rate was 6%.

```bash
python3 audit.py --adherence
```

It reads the session transcripts under `~/.claude/projects` and reports:

- **entry** - share of sessions that invoked any skill at all
- **chain** - of the sessions that entered an entry-point skill, the share that went on
  to a downstream one
- **dead routes** - skills your router names that have never been invoked

Your own entry points are passed in rather than baked in:

```bash
python3 audit.py --adherence --entry my-loop,my-board-adapter --cli-driven my-cli-skill
```

Two things it does deliberately. It **excludes subagent sidechains** from the
denominator, because a subagent dispatched to do one task is supposed to skip the
routing layer - counting them understated entry by 5x in testing. And it counts only
explicit `Skill` tool calls, so the rates are a **floor**: a tool driven from the
command line does not appear. That limit is real and bit once, so it is printed with
every run.

## Can a cold reader derive the pipeline? (`--graph`)

If your CLAUDE.md is the router that connects decoupled skills, then an agent with no
prior knowledge should be able to reconstruct the whole pipeline from that one file. This
pass tests exactly that: it reads the router and nothing else, emits every node and edge
it can derive, and quotes the line each one came from.

```bash
python3 audit.py --graph           # human summary
python3 graph.py                   # full JSON: nodes, edges, gates, aliases, unresolved
python3 graph.py --router path/to/CLAUDE.md
```

Three things it catches that the static pass cannot:

- **No spine.** A router that says *which skill for which condition* but never *what
  follows what* is a dispatch table, not a pipeline. Any diagram of it has to invent the
  sequence. On the setup this was built against, that invention produced four fabricated
  nodes before the check existed.
- **Aliases.** The same skill spelled two ways (`brainstorming` and
  `superpowers:brainstorming`) reads as two skills to a cold agent. Found on first run.
- **Named but unreachable.** Skills the router mentions with no edge into them. Reachable
  only by asking for them by name, which is fine for a tool and a defect for a phase.

The router contract it reads is documented at the top of `graph.py`: a small set of
section headings, backticks for skill names, `.py` for hooks. Anything else is prose.


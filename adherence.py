#!/usr/bin/env python3
"""Adherence pass: does the routing actually FIRE, or does it only parse?

WHY THIS EXISTS. On 2026-09-03 the static audit reported readiness 100% (76/76 OK) while,
in the same environment: 20 of 30 routed skills had never been invoked once across 891
sessions, downstream chaining ran at 6%, and the verification rule had no hook behind it.
The static audit was not wrong - it answers "does every file parse and every path resolve".
Nothing answered "does the routing fire", so a harness could rot to a third of its design
and still grade perfect. A config check that cannot see a dead route is measuring the
filesystem, not the harness.

WHAT IT MEASURES, from the transcripts themselves rather than from intent:
  entry   - share of sessions that invoked ANY skill (routing reached at all)
  chain   - of sessions that entered an entry skill, the share that reached a
            downstream one (the number that collapsed: 78% entry, 6% chain)
  dead    - routes named in CLAUDE.md that have never been invoked

STATED LIMIT, because the number is only useful if its blind spot is known: this counts
explicit `Skill` tool calls. A reference read straight off disk, or a tool driven from the
command line, does not appear. That limit bit once already - counted as skill calls,
receipts looked unused at 9; counted as CLI calls it was 1,750 - so the CLI column exists
and the rates are a FLOOR, never a ceiling.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")
CLAUDE_MD = os.path.join(HOME, ".claude", "CLAUDE.md")

SKILL_CALL = re.compile(r'"name":"Skill","input":\{"skill":"([^"]+)"')
# Backtick-quoted skill names in the routing table are how CLAUDE.md names a route.
ROUTE_IN_MD = re.compile(r"`([a-z][a-z0-9-]{3,}(?::[a-z0-9-]+)?)`")

# An ENTRY skill opens a session; everything else is downstream of one, and the chain
# rate is the share of entered sessions that reached any downstream skill. The default
# is deliberately small and generic: a project's own entry points (its board adapters,
# its loop skills) are PASSED IN with --entry rather than baked in here, the same way
# the risk taxonomy is passed to a planner. A tool that hardcodes one setup's skill
# names is not a tool, it is that setup.
DEFAULT_ENTRY = {"ship", "proto-port", "data-migration", "fanout", "brainstorming",
                 "superpowers:brainstorming"}

# Skills driven by a CLI or a slash command rather than the Skill tool: a zero
# Skill-call count says nothing about them, so counting them as dead is a false alarm.
DEFAULT_CLI_DRIVEN = {"code-review"}

# The write-time references are HOOK-nudged and satisfied by a recorded runlog stage, not
# by a Skill call. Counting them as dead routes would report the gates as broken at exactly
# the moment they are working.
VIA_RUNLOG = {"secure-coding", "reliable-coding", "expand-contract", "money-paths",
              "receipts-out", "data-migration"}


def runlog_stages():
    """Stage names ever recorded, across every run record."""
    seen = Counter()
    runs = os.path.join(HOME, ".claude", "runs")
    try:
        names = os.listdir(runs)
    except OSError:
        return seen
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(runs, n), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        for st in rec.get("stages", []):
            seen[st.get("stage", "")] += 1
    return seen


def installed_skills():
    """The ground truth for "is this a skill". Backtick-matching CLAUDE.md alone also
    catches `whoami`, `login` and repo names, and reporting those as dead routes is how a
    report loses its reader."""
    names = set()
    for base in (os.path.join(HOME, ".claude", "skills"),
                 os.path.join(HOME, ".agents", "skills")):
        try:
            names.update(os.listdir(base))
        except OSError:
            pass
    for root, _d, files in os.walk(os.path.join(HOME, ".claude", "plugins")):
        if "SKILL.md" in files:
            names.add(os.path.basename(root))
    return names


def transcripts():
    """Real SESSIONS only. 761 of 885 transcripts in this tree are subagent sidechains
    (`<session>/subagents/agent-*.jsonl`), and a subagent dispatched to execute one
    specific task is SUPPOSED to skip the routing layer - `using-superpowers` says so in
    its first line. Counting them as sessions that failed to route understates entry by
    5x (15% instead of 78%): a denominator bug, and the same class of mistake this whole
    pass exists to catch."""
    for root, _dirs, files in os.walk(PROJECTS):
        if os.path.basename(root) == "subagents":
            continue
        for f in files:
            if not f.endswith(".jsonl"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if '"isSidechain":true' in fh.read(4000):
                        continue
            except OSError:
                continue
            yield path


def scan():
    sessions, calls, cli = [], Counter(), Counter()
    for path in transcripts():
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                blob = fh.read()
        except OSError:
            continue
        found = set(SKILL_CALL.findall(blob))
        calls.update(SKILL_CALL.findall(blob))
        for tool in ("receipts observe", "receipts check", "fanout.py"):
            if tool in blob:
                cli[tool] += blob.count(tool)
        sessions.append(found)
    return sessions, calls, cli


def routed_skills():
    try:
        with open(CLAUDE_MD, encoding="utf-8") as f:
            md = f.read()
    except OSError:
        return []
    installed = installed_skills()
    names = {n for n in ROUTE_IN_MD.findall(md)
             if "." not in n
             and n not in NOT_ROUTED_VIA_SKILL_TOOL
             and (n in installed or n.split(":")[-1] in installed)}
    return sorted(names)


def parse_args(argv):
    ap = argparse.ArgumentParser(description="does the routing actually fire?")
    ap.add_argument("--entry", default="",
                    help="comma-separated entry-point skills for THIS setup, added to "
                         "the generic defaults (e.g. your project's loop/board skills)")
    ap.add_argument("--cli-driven", default="",
                    help="comma-separated skills invoked by CLI or slash command, which "
                         "a Skill-call count cannot see")
    ap.add_argument("--router", default=CLAUDE_MD,
                    help="the file that routes work to skills (default: ~/.claude/CLAUDE.md)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    global ENTRY, NOT_ROUTED_VIA_SKILL_TOOL, CLAUDE_MD
    ENTRY = DEFAULT_ENTRY | {s.strip() for s in args.entry.split(",") if s.strip()}
    NOT_ROUTED_VIA_SKILL_TOOL = DEFAULT_CLI_DRIVEN | {s.strip() for s in args.cli_driven.split(",") if s.strip()}
    CLAUDE_MD = os.path.expanduser(args.router)

    sessions, calls, cli = scan()
    total = len(sessions)
    if not total:
        print("  adherence: no transcripts found")
        return

    with_skill = sum(1 for s in sessions if s)
    entered = [s for s in sessions if s & ENTRY]
    chained = [s for s in entered if s - ENTRY]

    entry_rate = 100.0 * with_skill / total
    chain_rate = 100.0 * len(chained) / len(entered) if entered else 0.0

    print("=" * 62)
    print("  Adherence - does the routing FIRE (transcripts, not intent)")
    print("=" * 62)
    print("  sessions scanned      %d" % total)
    print("  entry  %5.1f%%   (%d of %d sessions invoked any skill)"
          % (entry_rate, with_skill, total))
    print("  chain  %5.1f%%   (%d of %d entered sessions reached a downstream skill)"
          % (chain_rate, len(chained), len(entered)))
    if cli:
        print("  CLI    " + "  ".join("%s x%d" % (k, v) for k, v in cli.most_common()))

    routes = routed_skills()
    stages = runlog_stages()

    def fired(r):
        if calls.get(r, 0):
            return True
        return r in VIA_RUNLOG and stages.get(r, 0) > 0

    dead = [r for r in routes if not fired(r)]
    via_gate = [r for r in routes if not calls.get(r, 0) and r in VIA_RUNLOG
                and stages.get(r, 0) > 0]
    if routes:
        print("\n  routes named in CLAUDE.md: %d   never invoked: %d"
              % (len(routes), len(dead)))
        for r in dead:
            print("    x %s" % r)
        if not dead:
            print("    every named route has fired at least once")
    if via_gate:
        print("\n  satisfied via the write-time gates rather than a Skill call:")
        for r in via_gate:
            print("    ok %-30s %d acknowledgement(s)" % (r, stages.get(r, 0)))

    print("\n  most-invoked:")
    for name, n in calls.most_common(8):
        print("    %-34s %d" % (name, n))
    print("\n  Limit: counts explicit Skill tool calls only, so these rates are a FLOOR.")
    print()
    return 1 if (entry_rate < 50 or chain_rate < 25) else 0


if __name__ == "__main__":
    sys.exit(main() or 0)

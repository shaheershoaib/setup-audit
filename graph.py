#!/usr/bin/env python3
"""Derive the harness graph from CLAUDE.md ALONE.

This is a TEST of the architecture, not a drawing tool. The claim under test is: "the
router connects decoupled skills, and the router is CLAUDE.md." If that claim is true,
an agent with no prior knowledge of this setup can read one file and reconstruct the
whole pipeline. If it is false, this script cannot build the graph, and what it cannot
resolve is a defect in the router rather than a limitation here.

So it reads ONLY ~/.claude/CLAUDE.md. It never opens a SKILL.md, never greps the skills
directory, and never uses anything the author happens to know. Every node and edge it
emits is quoted back with the line it came from, so a reader can check the derivation
instead of trusting it.

Anything the router leaves ambiguous is reported under UNRESOLVED, which is the finding.

THE ROUTER CONTRACT. A CLAUDE.md is graph-derivable when it uses these section headings
(matched case-insensitively on the heading's first words). Any other prose is ignored:

  ## Enforced ...            | rule | `hook.py` | ladder |   -> a gate bound to a hook
  ## Entry routes ...        - **trigger** -> `skill`        -> USER ASK -> skill
  ## The spine ...           | # | **phase** | runs | gates | -> phase order; consecutive
                                                                phases yield skill -> skill
  ## Pipeline edges ...      | when | then |                  -> conditional edges
  ## Consulted at write time `skill` ...                      -> FILE WRITE -> skill
  ## Scheduled ...           `skill` ...                      -> CRON -> skill
  ## Tools ... / ## On demand ...  `skill`                    -> named, no edge (a leaf)
  ## Project entry points ... "never names one"               -> the project placeholder

Names in backticks are skills; a backticked `.py` is a hook. A skill spelled two ways
(`x` and `ns:x`) is reported as an ALIAS, because a cold reader cannot tell they are one.
"""
import json
import os
import re
import sys

ROUTER = os.path.expanduser(next((a for a in sys.argv[1:] if not a.startswith("-")), "~/.claude/CLAUDE.md"))
HUMAN = "--human" in sys.argv
SKILL = re.compile(r"`([a-z][a-z0-9-]*(?::[a-z0-9-]+)?)`")
# Things in backticks that are files, commands or flags, not skills.
NOT_SKILL = re.compile(r"\.(py|md|json|sh|ts|tsx)$|^--|/|^npx |\.py ")


def sections(text):
    out, cur = {}, None
    for line in text.split("\n"):
        m = re.match(r"^##+ (.+)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return out


def skills_in(line):
    return [s for s in SKILL.findall(line) if not NOT_SKILL.search(s)]


def main():
    text = open(ROUTER, encoding="utf-8").read()
    secs = sections(text)
    nodes, edges, gates, unresolved = {}, [], [], []

    def node(name, kind, why):
        nodes.setdefault(name, {"kind": kind, "why": why})

    # ---- the spine: consecutive phases become real skill->skill edges -----------
    phases = []
    for title, body in secs.items():
        if not title.lower().startswith("the spine"):
            continue
        for line in body:
            m = re.match(r"\|\s*(\d+)\s*\|\s*\*\*(.+?)\*\*\s*\|(.*?)\|(.*?)\|", line)
            if m:
                phases.append({"n": int(m.group(1)), "phase": m.group(2),
                               "runs": skills_in(m.group(3)),
                               "gates": re.findall(r"`([\w.-]+\.py)`", m.group(4))})
    phases.sort(key=lambda p: p["n"])
    for i, ph in enumerate(phases):
        for s_ in ph["runs"]:
            node(s_, "phase:%d %s" % (ph["n"], ph["phase"]), "The spine")
        if i + 1 < len(phases):
            for a in ph["runs"] or ["(phase %d)" % ph["n"]]:
                for b in phases[i + 1]["runs"] or ["(phase %d)" % phases[i + 1]["n"]]:
                    edges.append({"from": a, "to": b, "label": "%s -> %s" % (ph["phase"], phases[i+1]["phase"]),
                                  "src": "spine table"})

    for title, body in secs.items():
        if title.lower().startswith("the spine"):
            continue
        t = title.lower()
        for i, line in enumerate(body):
            found = skills_in(line)

            # ---- gates: a rule bound to a hook that enforces it ----------------
            if t.startswith("enforced") and line.startswith("|") and "`" in line:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 2 and not cells[0].startswith("---"):
                    hooks = re.findall(r"`([\w.-]+\.py)`", cells[1])
                    if hooks:
                        gates.append({"rule": re.sub(r"`", "", cells[0]),
                                      "hooks": hooks,
                                      "ladder": re.sub(r"`", "", cells[2]) if len(cells) > 2 else ""})

            # ---- entry routes: "**trigger** -> `skill`" -------------------------
            elif t.startswith("entry routes") and found:
                trig = re.match(r"\s*-\s*\*\*(.+?)\*\*", line)
                for s in found:
                    node(s, "entry", title)
                    if trig:
                        edges.append({"from": "USER ASK", "to": s,
                                      "label": trig.group(1)[:58], "src": line.strip()[:80]})

            # ---- pipeline edges: "| when | then |" -----------------------------
            elif t.startswith("pipeline edges") and line.startswith("|") and found:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 2 and not cells[0].startswith("---"):
                    when, then = cells[0], cells[1]
                    targets = skills_in(then)
                    sources = skills_in(when)
                    for tgt in targets:
                        node(tgt, "pipeline", title)
                        for src in (sources or ["WORK-SET"]):
                            if src != tgt:
                                edges.append({"from": src, "to": tgt,
                                              "label": re.sub(r"`|\*", "", when)[:58],
                                              "src": line.strip()[:80]})

            elif t.startswith("consulted at write time") and found:
                for s in found:
                    node(s, "write-gate", title)
                    edges.append({"from": "FILE WRITE", "to": s,
                                  "label": "hook names the file", "src": line.strip()[:80]})

            elif t.startswith("scheduled") and found:
                for s in found:
                    node(s, "scheduled", title)
                    edges.append({"from": "CRON", "to": s, "label": "on a schedule",
                                  "src": line.strip()[:80]})

            elif (t.startswith("tools") or t.startswith("on demand")) and found:
                for s in found:
                    node(s, "tool", title)

            elif t.startswith("project entry points"):
                if "never names one" in line or "NEVER names" in line:
                    node("<project entry point>", "project", title)
                    edges.append({"from": "USER ASK", "to": "<project entry point>",
                                  "label": "board / queue ask (project-supplied)",
                                  "src": line.strip()[:80]})

    # What the router does NOT let a cold reader determine.
    if not any(e["from"] == "USER ASK" for e in edges):
        unresolved.append("no entry edge: nothing says which skill an ask starts at")
    named_but_unlinked = [n for n in nodes
                          if not any(e["to"] == n or e["from"] == n for e in edges)]
    for n in sorted(named_but_unlinked):
        unresolved.append("`%s` is named but has no edge: reachable only by asking for it "
                          "by name" % n)

    aliases = sorted(n for n in nodes if ":" not in n and any(m.endswith(":" + n) for m in nodes))
    for a in aliases:
        unresolved.append("`%s` is also spelled with a namespace: one skill, two names" % a)

    out = {"router": ROUTER, "nodes": nodes, "edges": edges, "gates": gates,
           "aliases": aliases, "unresolved": unresolved}
    if not HUMAN:
        print(json.dumps(out, indent=1))
        return
    spine = [e for e in edges if e["src"] == "spine table"]
    print("=" * 62)
    print("  Graph - what the router alone lets a cold reader derive")
    print("=" * 62)
    print("  nodes %d | edges %d (%d skill->skill from the spine) | gates %d | aliases %d"
          % (len(nodes), len(edges), len(spine), len(gates), len(aliases)))
    if not spine:
        print("\n  NO SPINE: the router declares which skill for which condition, but never")
        print("  what follows what. Any pipeline diagram of it has to invent the sequence.")
    if aliases:
        print("\n  ALIASES (one skill, two names):", ", ".join(aliases))
    leaves = [n for n in nodes if not any(e["to"] == n or e["from"] == n for e in edges)]
    print("\n  reachable only by name (no edge): %d" % len(leaves))
    print("  gates bound to a hook: %d" % len(gates))
    print("\n  Re-run after any router change. A node that stops appearing is a route the")
    print("  router forgot; a new alias is a name it spelled two ways.")
    print()


if __name__ == "__main__":
    main()

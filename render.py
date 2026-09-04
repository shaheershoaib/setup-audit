#!/usr/bin/env python3
"""Render the harness graph as a swim-lane pipeline SVG - FROM graph.json, never by hand.

WHY GENERATED. A hand-drawn pipeline diagram was audited against the derived graph and
found to carry four nodes the router never declared, then went stale twice more as the
router changed. A drawing that has to be re-audited after every edit is not proven; it is
re-asserted. This renderer can only draw what graph.py extracted, uses the exact node
names, and is re-run after any router change. The diagram is proven by construction.

THE VISUAL GRAMMAR (the part worth keeping from the hand-drawn version): phases as swim
lanes with labels along the bottom; nodes coloured by role, not importance; the gate layer
as a capsule across the top; conditions written on the edge; and nodes with no edge drawn
DETACHED on a shelf, because attaching them would draw a routing the router does not have.

  python3 render.py graph.json > pipeline.svg
  python3 render.py graph.json --html > pipeline.html     (wrapped in a dark page)
  python3 render.py graph.json --prove                     (the five proofs; exit 1 on any FAIL)

THE PROOFS (--prove). Rendering from the graph is what makes the diagram trustworthy, and
these are what let anyone check that claim instead of taking it: (1) every router node is
drawn with its exact name; (2) no skill-shaped label is drawn that the router lacks; (3) the
capsule's gate count equals the router's; (4) every spine phase has a lane; (5) a hook that
runs at a phase is drawn as a hook, not a skill. Run after any router change.
"""
import json
import re
import sys
from html import escape

# role -> stroke colour (dark canvas). Kind strings come from graph.py.
COLOR = {"entry": "#4ec9b0", "phase:1": "#4ec9b0", "phase:2": "#6f8cff", "phase:3": "#4ec9b0",
         "phase:4": "#e5c07b", "phase:5": "#4ec9b0", "phase:6": "#e5c07b", "phase:7": "#e06c9f",
         "write-gate": "#e06c75", "scheduled": "#7c879b", "project": "#5fd3a0",
         "pipeline": "#6f8cff", "tool": "#4d5668"}
INK, DIM, PANEL, SEP, GATE = "#c9d1de", "#7c879b", "#151a26", "#232b3b", "#e5c07b"
MONO = 'font-family="JetBrains Mono, ui-monospace, Menlo, monospace"'

COL_W, GAP, NODE_W, NODE_H, ROW = 208, 18, 192, 26, 34


def load(path):
    return json.load(open(path, encoding="utf-8"))


def layout(g):
    """Phases in spine order; every node assigned to exactly one column (its spine phase,
    else the phase its conditional edge targets, else the shelf)."""
    # Lane order comes from the spine itself, so a phase that runs only a hook (intake)
    # still gets a lane. Nodes of kind phase:N or hook:N are placed in their phase.
    order = list(g.get("phases") or [])
    in_phase = {ph: [] for ph in order}
    for name, meta in g["nodes"].items():
        m = re.match(r"(?:phase|hook):(\d+) (\w+)", meta["kind"])
        if m:
            in_phase.setdefault(m.group(2), []).append(name)
            if m.group(2) not in order:
                order.append(m.group(2))
    placed = {n for lst in in_phase.values() for n in lst}

    # conditional targets not on the spine sit in the phase the spine puts them nearest:
    # verify-ish names at verify, close-ish at close, else plan.
    for name in g["nodes"]:
        if name in placed:
            continue
        kind = g["nodes"][name]["kind"]
        if kind in ("write-gate", "scheduled", "tool", "project"):
            continue
        tgt = "verify" if "receipt" in name else "close" if any(k in name for k in ("readiness", "postmortem")) else "plan"
        if tgt in in_phase:
            in_phase[tgt].append(name); placed.add(name)

    write_gates = [n for n, m in g["nodes"].items() if m["kind"] == "write-gate"]
    scheduled = [n for n, m in g["nodes"].items() if m["kind"] == "scheduled"]
    project = [n for n, m in g["nodes"].items() if m["kind"] == "project"]
    linked = {e["to"] for e in g["edges"]} | {e["from"] for e in g["edges"]}
    shelf = sorted(n for n, m in g["nodes"].items()
                   if n not in placed and n not in write_gates + scheduled + project and n not in linked)
    return order, in_phase, write_gates, scheduled, project, shelf


def node(x, y, name, color, dashed=False, w=NODE_W):
    dash = ' stroke-dasharray="5 3"' if dashed else ""
    fs = 10.5 if len(name) <= 26 else 9
    return ('<rect x="%d" y="%d" width="%d" height="%d" rx="5" fill="%s" stroke="%s" stroke-width="1.5"%s/>'
            '<text x="%d" y="%d" %s font-size="%s" fill="%s" text-anchor="middle">%s</text>'
            % (x, y, w, NODE_H, PANEL, color, dash, x + w / 2, y + 17, MONO, fs, INK, escape(name)))


def arrow(x1, y1, x2, y2, color="#8792a6", dashed=False):
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    return ('<path d="M%d,%d C%d,%d %d,%d %d,%d" fill="none" stroke="%s" stroke-width="1.3"%s marker-end="url(#ar)"/>'
            % (x1, y1, x1 + 24, y1, x2 - 24, y2, x2, y2, color, dash))


def render(g):
    order, in_phase, write_gates, scheduled, project, shelf = layout(g)
    ncol = len(order)
    left = 30
    colx = {ph: left + i * (COL_W + GAP) for i, ph in enumerate(order)}
    center = {ph: colx[ph] + COL_W / 2 for ph in order}
    width = left + ncol * (COL_W + GAP) + 10
    top = 120
    # column heights
    rows = max(len(in_phase.get(ph, [])) for ph in order)
    lanes_bottom = top + rows * ROW + 40
    wg_y = lanes_bottom + 30
    sched_y = wg_y + 90
    shelf_y = sched_y + 70
    shelf_rows = (len(shelf) + 5) // 6
    height = shelf_y + 40 + shelf_rows * 22 + 60

    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" role="img" width="%d" '
           'aria-label="Pipeline derived from the router: %d nodes, %d edges, %d gates, %d unrouted.">'
           % (width, height, width, len(g["nodes"]), len(g["edges"]), len(g["gates"]), len(shelf)),
           '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8792a6"/></marker></defs>',
           '<rect width="%d" height="%d" fill="#10141d"/>' % (width, height)]

    # lanes + labels
    for i, ph in enumerate(order):
        if i:
            out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (colx[ph] - GAP / 2, 90, colx[ph] - GAP / 2, lanes_bottom, SEP))
        out.append('<text x="%d" y="%d" %s font-size="10.5" fill="%s" letter-spacing="1.6" text-anchor="middle">%s</text>'
                   % (center[ph], lanes_bottom + 22, MONO, DIM, ph.upper()))
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (left, lanes_bottom, width - 10, lanes_bottom, SEP))

    # gate capsule: every gate the router binds to a hook
    out.append('<rect x="%d" y="28" width="%d" height="32" rx="16" fill="none" stroke="%s" stroke-width="1.5"/>' % (left, width - 40, GATE))
    names = " · ".join(sorted({h.replace(".py", "") for gt in g["gates"] for h in gt["hooks"]}))
    out.append('<text x="%d" y="49" %s font-size="10.5" fill="%s" text-anchor="middle">%d hook-backed gates · %s</text>'
               % (width / 2, MONO, GATE, len(g["gates"]), escape(names)))
    for ph in ("plan", "build", "commit", "verify", "close"):
        if ph in center:
            out.append('<line x1="%d" y1="60" x2="%d" y2="%d" stroke="%s" stroke-width="1.1" stroke-dasharray="3 4" opacity=".6" marker-end="url(#ar)"/>'
                       % (center[ph], center[ph], top - 8, GATE))

    # nodes, and remember positions
    pos = {}
    for ph in order:
        for j, name in enumerate(in_phase.get(ph, [])):
            kind = g["nodes"][name]["kind"]
            is_hook = kind.startswith("hook:")
            col = COLOR["project"] if is_hook else COLOR.get(kind, COLOR.get(kind.split(" ")[0], "#6f8cff"))
            y = top + j * ROW
            x = colx[ph] + (COL_W - NODE_W) / 2
            pos[name] = (x, y)
            out.append(node(x, y, name, col, dashed=is_hook))
    # the project placeholder sits in the entry column, dashed
    if project and "entry" in order:
        j = len(in_phase.get("entry", []))
        x = colx["entry"] + (COL_W - NODE_W) / 2; y = top + j * ROW
        pos[project[0]] = (x, y)
        out.append(node(x, y, project[0], COLOR["project"], dashed=True))

    # edges: spine (solid), everything else with a label (dashed)
    seen = set()
    for e in g["edges"]:
        a, b = e["from"], e["to"]
        if a in pos and b in pos and (a, b) not in seen:
            seen.add((a, b))
            (x1, y1), (x2, y2) = pos[a], pos[b]
            if x2 > x1:
                out.append(arrow(x1 + NODE_W, y1 + NODE_H / 2, x2, y2 + NODE_H / 2, dashed=(e["src"] != "spine table")))
    # sources
    srcs = sorted({e["from"] for e in g["edges"] if e["from"] not in pos})
    for k, s in enumerate(srcs):
        y = top - 30 + k * 0
        out.append('<text x="%d" y="%d" %s font-size="10" fill="%s" letter-spacing="1.2">%s</text>'
                   % (left + 4 + k * 150, top - 14, MONO, DIM, escape(s)))

    # write-time references: not a phase, nothing routes here
    out.append('<text x="%d" y="%d" %s font-size="10" fill="#e06c75" letter-spacing="1.2">WRITE-TIME REFERENCES - fire on the write itself, no phase, nothing routes here</text>' % (left, wg_y - 10, MONO))
    for k, name in enumerate(write_gates):
        out.append(node(left + k * (NODE_W + 14), wg_y, name, COLOR["write-gate"], dashed=True))

    out.append('<text x="%d" y="%d" %s font-size="10" fill="%s" letter-spacing="1.2">SCHEDULED - run on their own</text>' % (left, sched_y - 10, MONO, DIM))
    for k, name in enumerate(scheduled):
        out.append(node(left + k * (NODE_W + 14), sched_y, name, COLOR["scheduled"], w=NODE_W + 40))

    # detached shelf, exact names, six per row
    out.append('<text x="%d" y="%d" %s font-size="10" fill="%s" letter-spacing="1.2">%d NODES WITH NO EDGE - REACHABLE ONLY BY NAME, DRAWN DETACHED ON PURPOSE</text>'
               % (left, shelf_y - 10, MONO, DIM, len(shelf)))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="5" fill="none" stroke="#2c3547" stroke-dasharray="6 4"/>'
               % (left, shelf_y, width - 40, 22 * shelf_rows + 20))
    for k, name in enumerate(shelf):
        r, c = divmod(k, 6)
        out.append('<text x="%d" y="%d" %s font-size="9.5" fill="%s">%s</text>'
                   % (left + 14 + c * ((width - 60) / 6), shelf_y + 24 + r * 22, MONO, DIM, escape(name)))
    out.append('</svg>')
    return "\n".join(out)


def prove(g, svg):
    import html as _h
    labels = {_h.unescape(t).strip() for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)}
    nodes = set(g["nodes"])
    missing = sorted(n for n in nodes if n not in labels)
    extras = sorted(l for l in labels if re.match(r"^[a-z][a-z0-9:.-]{3,}$", l) and l not in nodes)
    m = re.search(r"(\d+) hook-backed gates", svg)
    cap = int(m.group(1)) if m else -1
    lanes = [l for l in labels if l.isupper() and l.lower() in g.get("phases", [])]
    hooks = [n for n, meta in g["nodes"].items() if meta["kind"].startswith("hook:")]
    checks = [
        ("every router node drawn with its exact name", not missing, missing),
        ("no skill-shaped label the router lacks", not extras, extras),
        ("capsule gate count == router gates", cap == len(g["gates"]), "%d vs %d" % (cap, len(g["gates"]))),
        ("every spine phase has a lane", len(lanes) == len(g.get("phases", [])), "%d/%d" % (len(lanes), len(g.get("phases", [])))),
        ("hooks that run at a phase are drawn", all(h in labels for h in hooks), [h for h in hooks if h not in labels]),
    ]
    ok = True
    for name, passed, detail in checks:
        ok &= bool(passed)
        print("  %-46s %s%s" % (name, "PASS" if passed else "FAIL", "" if passed else "  -> %s" % detail))
    print("  diagram %s the router (%d nodes, %d edges, %d gates)" % ("PROVEN against" if ok else "DOES NOT MATCH", len(nodes), len(g["edges"]), len(g["gates"])))
    return ok


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    g = load(args[0] if args else "graph.json")
    svg = render(g)
    if "--prove" in sys.argv:
        sys.exit(0 if prove(g, svg) else 1)
    if "--html" in sys.argv:
        print('<title>Harness Pipeline (generated)</title>\n<style>body{background:#10141d;margin:0;padding:24px}'
              'svg{display:block;max-width:100%%;height:auto}p{color:#7c879b;font:13px/1.6 system-ui;max-width:80ch}</style>\n'
              '<p>Generated from graph.json by render.py. It can only contain what graph.py derived from the router, '
              'uses exact node names, and is re-run after any router change: %d nodes, %d edges, %d gates.</p>\n%s'
              % (len(g["nodes"]), len(g["edges"]), len(g["gates"]), svg))
    else:
        print(svg)


if __name__ == "__main__":
    main()

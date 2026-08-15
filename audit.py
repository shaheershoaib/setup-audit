#!/usr/bin/env python3
"""setup-audit: grade the ~/.claude agent setup. Static, dependency-free.

Catches the SILENT breakages: a skill whose frontmatter won't parse (so it never
loads), a hook pointing at a moved/renamed script (so it no-ops), an MCP whose
entry file is gone, a skill dir with no SKILL.md, an accidental deletion (drift
vs a saved snapshot).

Usage:
  python3 audit.py              # audit + (if a snapshot exists) drift report
  python3 audit.py --snapshot   # save the current inventory as the baseline
Exit code 1 if any FAIL.
"""
import os, re, json, sys, glob, stat
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"
SNAP = CLAUDE / "skills" / "setup-audit" / "snapshot.json"

findings = []  # (severity, area, msg)


def add(sev, area, msg):
    findings.append((sev, area, msg))


def parse_frontmatter(text):
    """Return a dict of top-level keys in the YAML frontmatter, or None if absent."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return None
    keys = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if km:
            keys[km.group(1)] = km.group(2)
    return keys


inv = {"skills": [], "agents": [], "hooks": [], "mcps": [], "plugins": []}

# ---- Skills ----------------------------------------------------------------
for sf in sorted(glob.glob(str(CLAUDE / "skills" / "*" / "SKILL.md"))):
    d = Path(sf).parent.name
    inv["skills"].append(d)
    fm = parse_frontmatter(Path(sf).read_text(errors="replace"))
    if fm is None:
        add("FAIL", "skill", f"{d}: no YAML frontmatter (won't load)")
        continue
    if "name" not in fm:
        add("FAIL", "skill", f"{d}: frontmatter missing name:")
    elif fm["name"].strip() and fm["name"].strip() != d:
        add("WARN", "skill", f"{d}: name '{fm['name'].strip()}' != dir name")
    if "description" not in fm:
        add("FAIL", "skill", f"{d}: frontmatter missing description:")
    else:
        add("OK", "skill", d)
for sd in sorted(glob.glob(str(CLAUDE / "skills" / "*"))):
    if Path(sd).is_dir() and not (Path(sd) / "SKILL.md").exists():
        add("WARN", "skill", f"{Path(sd).name}: directory has no SKILL.md")

# ---- Agents ----------------------------------------------------------------
for af in sorted(glob.glob(str(CLAUDE / "agents" / "*.md"))):
    name = Path(af).stem
    inv["agents"].append(name)
    fm = parse_frontmatter(Path(af).read_text(errors="replace"))
    if fm is None:
        add("FAIL", "agent", f"{name}: no frontmatter")
    else:
        miss = [k for k in ("name", "description") if k not in fm]
        if miss:
            add("FAIL", "agent", f"{name}: missing {','.join(miss)}")
        else:
            add("OK", "agent", name)

# ---- Hooks (settings.json) -------------------------------------------------
def find_commands(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "command" and isinstance(v, str):
                out.append(v)
            else:
                out += find_commands(v)
    elif isinstance(obj, list):
        for v in obj:
            out += find_commands(v)
    return out


settings = CLAUDE / "settings.json"
if settings.exists():
    try:
        sj = json.loads(settings.read_text())
    except Exception as e:
        add("FAIL", "hooks", f"settings.json invalid JSON: {e}")
        sj = {}
    for cmd in find_commands(sj.get("hooks", {})):
        inv["hooks"].append(cmd[:60])
        cand = None
        for tok in cmd.replace('"', " ").split():
            t = os.path.expanduser(os.path.expandvars(tok))
            if "/" in t and Path(t).is_file():
                cand = t
                break
        if cand is None:
            add("WARN", "hooks", f"no resolvable script file (inline?): {cmd[:48]}")
        elif cand.endswith(".sh") and not (os.stat(cand).st_mode & stat.S_IXUSR):
            add("WARN", "hooks", f"script not executable: {cand}")
        else:
            add("OK", "hooks", os.path.basename(cand))
else:
    add("WARN", "hooks", "no ~/.claude/settings.json")

# ---- MCP servers (~/.claude.json user scope) -------------------------------
cj = HOME / ".claude.json"
if cj.exists():
    try:
        mcps = (json.loads(cj.read_text()).get("mcpServers") or {})
    except Exception as e:
        mcps = {}
        add("FAIL", "mcp", f".claude.json invalid: {e}")
    def looks_local(a):
        # A local filesystem path - NOT a URL/connection string or an npm package spec.
        if not isinstance(a, str) or "://" in a or a.startswith("@"):
            return False
        return os.path.isabs(os.path.expanduser(a)) or a.startswith((".", "~"))

    for name, conf in mcps.items():
        inv["mcps"].append(name)
        if conf.get("type", "stdio") == "stdio" or "command" in conf:
            cands = [conf.get("command", "")] + list(conf.get("args", []))
            missing = [a for a in cands if looks_local(a) and not Path(os.path.expanduser(a)).exists()]
            if missing:
                add("FAIL", "mcp", f"{name}: entry file missing -> {missing}")
            else:
                add("OK", "mcp", name)  # npx/remote servers (no local entry file) pass here too
        else:
            add("OK", "mcp", f"{name} ({conf.get('type')})")
else:
    add("WARN", "mcp", "no ~/.claude.json")

# ---- Plugins + core --------------------------------------------------------
for pd in sorted(glob.glob(str(CLAUDE / "plugins" / "*"))):
    if Path(pd).is_dir():
        inv["plugins"].append(Path(pd).name)
add("OK", "core", "CLAUDE.md") if (CLAUDE / "CLAUDE.md").exists() else add(
    "WARN", "core", "missing ~/.claude/CLAUDE.md"
)

# ---- Snapshot / drift ------------------------------------------------------
diff_lines = []
if "--snapshot" in sys.argv:
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    SNAP.write_text(json.dumps(inv, indent=2, sort_keys=True))
    print(f"Snapshot saved to {SNAP}")
elif SNAP.exists():
    try:
        prev = json.loads(SNAP.read_text())
    except Exception:
        prev = None
    if prev:
        for area in inv:
            now, was = set(inv[area]), set(prev.get(area, []))
            for x in sorted(was - now):
                diff_lines.append(f"  - REMOVED {area}: {x}")
            for x in sorted(now - was):
                diff_lines.append(f"  + ADDED   {area}: {x}")

# ---- Report ----------------------------------------------------------------
fails = [f for f in findings if f[0] == "FAIL"]
warns = [f for f in findings if f[0] == "WARN"]
total = len(findings)
passing = total - len(fails) - len(warns)
score = round(100 * passing / total) if total else 100

print("=" * 62)
print(f"  Claude setup audit - readiness {score}%  ({passing}/{total} OK)")
print("=" * 62)
print(
    f"  skills:{len(inv['skills'])}  agents:{len(inv['agents'])}  "
    f"hooks:{len(inv['hooks'])}  mcps:{len(inv['mcps'])}  plugins:{len(inv['plugins'])}"
)
if fails:
    print("\nFAIL (broken - fix):")
    for _, a, m in fails:
        print(f"  x [{a}] {m}")
if warns:
    print("\nWARN (check):")
    for _, a, m in warns:
        print(f"  ! [{a}] {m}")
if diff_lines:
    print("\nDrift vs snapshot:")
    print("\n".join(diff_lines))
elif SNAP.exists() and "--snapshot" not in sys.argv:
    print("\nNo drift vs snapshot.")
print()
sys.exit(1 if fails else 0)

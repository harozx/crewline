"""Change map data: how a codebase is wired (imports) and where the work lands (tickets), for humans.

- Modules: path prefix before /src/ (Maven/Gradle/crate/package), else first directory.
- Structure: module -> module import edges, parsed from code (Java/Scala/Kotlin, Python, TS/JS, Rust).
- Work: past tickets with the files their fix changed -> tickets per module, bug share, recent activity, and
  co-change (modules fixed together in one ticket).
- Open tickets: from Jira (JQL) or GitHub issues, each routed with locate (no model): likely files and modules,
  plus the impact area = modules that import them and modules historically changed with them.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from crewline.evals.triage import module, rank_modules
from crewline.locate import baseline, engine
from crewline.sources import git

JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+?)(?:\.\*)?\s*;?\s*$", re.M)
PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
TS_IMPORT = re.compile(r"""(?:from\s+|import\s*\(\s*|require\(\s*)['"](\.{1,2}/[^'"]+)['"]""")
RS_USE = re.compile(r"^\s*(?:pub\s+)?use\s+([a-z_][a-z0-9_]*)::", re.M)


def _dotted(path: str) -> str | None:
    for root in ("/java/", "/scala/", "/kotlin/"):
        if root in "/" + path:
            return ("/" + path).split(root, 1)[1].rsplit(".", 1)[0].replace("/", ".")
    return None


def _py_name(path: str) -> str:
    p = path[4:] if path.startswith("src/") else path
    p = p.rsplit(".", 1)[0].replace("/", ".")
    return p[:-9] if p.endswith(".__init__") else p


def import_edges(repo: Path, files: list[str]) -> Counter:
    """(from_module, to_module) -> number of file-level imports between them."""
    by_dotted = {d: f for f in files if (d := _dotted(f))}
    by_py = {_py_name(f): f for f in files if f.endswith(".py")}
    fileset = set(files)
    crates = {}
    for f in files:
        m = module(f)
        if f.endswith(".rs"):
            crates[m.rsplit("/", 1)[-1].replace("-", "_")] = m
    edges: Counter = Counter()
    for f in files:
        try:
            text = (repo / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        src = module(f)
        targets: list[str] = []
        if f.endswith((".java", ".scala", ".kt")):
            for name in JAVA_IMPORT.findall(text):
                while name and name not in by_dotted:
                    name = name.rsplit(".", 1)[0] if "." in name else ""
                if name:
                    targets.append(by_dotted[name])
        elif f.endswith(".py"):
            for a, b in PY_IMPORT.findall(text):
                name = a or b
                while name and name not in by_py:
                    name = name.rsplit(".", 1)[0] if "." in name else ""
                if name:
                    targets.append(by_py[name])
        elif f.endswith((".ts", ".tsx", ".js", ".jsx")):
            base = f.rsplit("/", 1)[0] if "/" in f else ""
            for spec in TS_IMPORT.findall(text):
                p = Path(base, spec).as_posix()
                parts = []
                for seg in p.split("/"):
                    if seg == "..":
                        parts = parts[:-1]
                    elif seg not in (".", ""):
                        parts.append(seg)
                p = "/".join(parts)
                for cand in (p, p + ".ts", p + ".tsx", p + ".js", p + "/index.ts", p + "/index.js"):
                    if cand in fileset:
                        targets.append(cand)
                        break
        elif f.endswith(".rs"):
            for c in RS_USE.findall(text):
                if c in crates and crates[c] != src:
                    edges[(src, crates[c])] += 1
        for t in targets:
            dst = module(t)
            if dst != src:
                edges[(src, dst)] += 1
    return edges


def load_history(repo: Path, jira_url: str | None = None) -> list[dict]:
    """Fixed tickets with their files. Benchmark datasets carry type and dates; otherwise the history that
    calibrate/setup fetched (or ticket keys in commits)."""
    from crewline.config import data_dir
    ds = data_dir() / "datasets" / repo.name / "tickets.jsonl"
    if ds.exists():
        out = []
        for line in open(ds, encoding="utf-8"):
            t = json.loads(line)
            if t["files"]:
                out.append({"key": t["key"], "text": f"{t['summary']}\n{t['description']}", "files": t["files"],
                            "type": t.get("type"), "date": t.get("created"),
                            "url": f"{jira_url.rstrip('/')}/browse/{t['key']}" if jira_url else None})
        return out
    return engine._history(repo, "2023-01-01")


def open_tickets_jira(url: str, jql: str, n: int = 60) -> list[dict]:
    from crewline.sources.jira import Jira
    out = []
    for issue in Jira(url).search(jql, fields="summary,description,issuetype,priority,updated,assignee"):
        f = issue["fields"]
        out.append({"key": issue["key"], "title": f.get("summary") or "",
                    "text": f"{f.get('summary') or ''}\n{f.get('description') or ''}",
                    "type": (f.get("issuetype") or {}).get("name"), "url": f"{url.rstrip('/')}/browse/{issue['key']}",
                    "assignee": (f.get("assignee") or {}).get("displayName")})
        if len(out) >= n:
            break
    return out


def open_tickets_github(slug: str, n: int = 60) -> list[dict]:
    p = subprocess.run(["gh", "issue", "list", "-R", slug, "--state", "open", "--limit", str(n),
                        "--json", "number,title,body,labels,url,assignees"], capture_output=True, text=True,
                       encoding="utf-8")
    out = []
    for i in json.loads(p.stdout or "[]"):
        labels = [lb["name"] for lb in i.get("labels") or []]
        out.append({"key": f"#{i['number']}", "title": i["title"], "text": f"{i['title']}\n{i.get('body') or ''}",
                    "type": "Bug" if any("bug" in lb.lower() for lb in labels) else "Issue", "url": i["url"],
                    "assignee": ", ".join(a["login"] for a in i.get("assignees") or []) or None})
    return out


# ---- shared core: structure (cached per commit) and per-ticket impact ---------------------------------------------

def structure(repo: Path, history: list[dict] | None = None, refresh: bool = False) -> dict:
    """Modules with their work history, import edges and co-change pairs, cached per HEAD commit. Used by the map
    page, the `ticket_impact` MCP tool and the crew reviewer, so all three see the same picture."""
    from crewline.config import data_dir
    repo = repo.resolve()
    out = data_dir() / "index" / repo.name / f"structure-{git.head(repo)[:10]}.json"
    if out.exists() and not refresh:
        return json.loads(out.read_text(encoding="utf-8"))
    history = history if history is not None else load_history(repo)
    files = [p for p in git.ls_tree(repo, "HEAD") if baseline.is_code(p)]
    file_count = Counter(module(f) for f in files)
    imports = import_edges(repo, files)

    tickets_per: Counter = Counter()
    bugs_per: Counter = Counter()
    recent_per: Counter = Counter()
    hot_files: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list] = defaultdict(list)
    cochange: Counter = Counter()
    dates = sorted(h.get("date") or "" for h in history)
    recent_cut = dates[int(len(dates) * 0.8)] if dates else ""
    for h in history:
        mods = sorted({module(f) for f in h["files"]})
        for m in mods:
            tickets_per[m] += 1
            bugs_per[m] += (h.get("type") or "").lower() == "bug"
            recent_per[m] += (h.get("date") or "") >= recent_cut
            if len(examples[m]) < 6:
                examples[m].append({"key": h["key"], "title": h["text"].split("\n", 1)[0][:120], "url": h.get("url")})
        for f in h["files"]:
            hot_files[module(f)][f] += 1
        for a, b in combinations(mods, 2):
            cochange[(a, b)] += 1

    owners = engine._codeowners(repo)
    nodes = []
    for m in sorted(set(file_count) | set(tickets_per)):
        who = next((o for pat, o in reversed(owners) if pat and m.startswith(pat)), None)
        nodes.append({"id": m, "files": file_count[m], "tickets": tickets_per[m],
                      "bug_share": round(bugs_per[m] / tickets_per[m], 2) if tickets_per[m] else 0,
                      "recent": recent_per[m], "owners": who,
                      "hot_files": [f for f, _ in hot_files[m].most_common(6)], "examples": examples[m]})
    data = {"modules": nodes, "history_tickets": len(history),
            "imports": [{"source": a, "target": b, "n": n} for (a, b), n in imports.items()],
            "cochange": [{"a": a, "b": b, "n": n} for (a, b), n in cochange.items()]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data), encoding="utf-8")
    return data


def impact(repo: Path, text: str, struct: dict | None = None) -> dict:
    """Where a ticket lands (files, modules) and where it spreads: modules importing the landing modules and
    modules historically fixed together with them. No model calls."""
    struct = struct or structure(repo)
    deps_in: dict[str, Counter] = defaultdict(Counter)
    for e in struct["imports"]:
        deps_in[e["target"]][e["source"]] += e["n"]
    co: dict[str, Counter] = defaultdict(Counter)
    for c in struct["cochange"]:
        co[c["a"]][c["b"]] += c["n"]
        co[c["b"]][c["a"]] += c["n"]
    hits = engine.locate(repo, text, top=10, use_agent=False)
    top_files = [h.path for h in hits]
    mods = rank_modules(top_files)[:2]
    spread: Counter = Counter()
    reasons: dict[str, list[str]] = defaultdict(list)
    for m in mods:
        for dep, n in deps_in[m].most_common(4):
            spread[dep] += n
            reasons[dep].append(f"imports {m}")
        for c, n in co[m].most_common(3):
            spread[c] += n * 5
            reasons[c].append(f"fixed with {m} in {n} past tickets")
    by_id = {m["id"]: m for m in struct["modules"]}
    area = [m for m, _ in spread.most_common(8) if m not in mods][:6]
    return {"modules": mods, "files": top_files[:6], "evidence": {h.path: h.found_by for h in hits[:6]},
            "similar": sorted({s for h in hits[:3] for s in h.similar_tickets})[:5],
            "impact": area, "impact_reasons": {m: reasons[m] for m in area},
            "owners": sorted({by_id[m]["owners"] for m in mods + area if by_id.get(m, {}).get("owners")})}


def impact_markdown(r: dict) -> str:
    lines = ["**Lands in:** " + ", ".join(f"`{m}`" for m in r["modules"]), "", "**Likely files:**"]
    lines += [f"- `{f}` ({', '.join(r['evidence'].get(f, []))})" for f in r["files"]]
    lines += ["", "**Impact area** (check these when changing the code above):"]
    lines += [f"- `{m}`: {'; '.join(r['impact_reasons'][m])}" for m in r["impact"]] or ["- none found"]
    if r["similar"]:
        lines += ["", "**Similar past tickets:** " + ", ".join(r["similar"])]
    if r["owners"]:
        lines += ["", "**Owners:** " + ", ".join(r["owners"])]
    return "\n".join(lines)


def build(repo: Path, history: list[dict], open_tickets: list[dict], title: str = "") -> dict:
    """The map page's data: the shared structure plus every open ticket's impact."""
    repo = repo.resolve()
    struct = structure(repo, history, refresh=True)
    keep = ("key", "title", "type", "url", "assignee")
    open_out = [{**{k: t.get(k) for k in keep}, **impact(repo, t["text"], struct)} for t in open_tickets]
    return {"title": title or repo.name, "modules": struct["modules"],
            "imports": [e for e in struct["imports"] if e["n"] >= 2],
            "cochange": [c for c in struct["cochange"] if c["n"] >= 3],
            "open": open_out, "history_tickets": struct["history_tickets"]}

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


def import_edges(repo: Path, files: list[str], file_dependents: Counter | None = None) -> Counter:
    """(from_module, to_module) -> number of file-level imports between them. If `file_dependents` is given it
    is filled with, per file, how many other files import it (file-level blast radius)."""
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
            if file_dependents is not None and t != f:
                file_dependents[t] += 1
            dst = module(t)
            if dst != src:
                edges[(src, dst)] += 1
    return edges


def git_activity(repo: Path, since: str = "1 year ago") -> tuple[Counter, dict[str, Counter]]:
    """Per file: commits touching it, and commits per author (git log, no merges). The raw material for hotspots
    and knowledge maps: who actually works on which code, independent of tickets."""
    p = subprocess.run(["git", "-C", str(repo), "log", "--no-merges", f"--since={since}", "--no-renames",
                        "--name-only", "--format=@@%aN"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    commits: Counter = Counter()
    authors: dict[str, Counter] = defaultdict(Counter)
    who = ""
    for line in p.stdout.splitlines():
        if line.startswith("@@"):
            who = line[2:].strip()
        elif line.strip() and baseline.is_code(line.strip()):
            f = line.strip()
            commits[f] += 1
            authors[f][who] += 1
    return commits, authors


def _bus_factor(counts: Counter) -> int:
    """How many people together made half of the commits: 1 means one person holds the knowledge."""
    total, acc = sum(counts.values()), 0
    for i, (_, n) in enumerate(counts.most_common(), 1):
        acc += n
        if acc * 2 >= total:
            return i
    return 0


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
    jira = Jira(url)
    custom = jira.field_ids("Sprint", "Story Points", "Story point estimate", "Epic Link")
    out = []
    fields = ("summary,description,issuetype,priority,updated,created,duedate,assignee,status,parent,issuelinks,"
              "fixVersions," + ",".join(custom.values())).rstrip(",")
    for issue in jira.search(jql, fields=fields):
        f = issue["fields"]
        versions = f.get("fixVersions") or []
        release_dates = sorted(v["releaseDate"] for v in versions if v.get("releaseDate") and not v.get("released"))
        sprint = f.get(custom.get("Sprint", ""), None)
        if isinstance(sprint, list) and sprint:   # Cloud: list of dicts; Server: list of "…name=Sprint 12,…" strings
            last = sprint[-1]
            sprint = last.get("name") if isinstance(last, dict) else (re.search(r"name=([^,\]]+)", str(last)) or
                                                                     [None, None])[1]
        points = f.get(custom.get("Story Points", "")) or f.get(custom.get("Story point estimate", ""))
        links = []
        for lk in f.get("issuelinks") or []:
            other = lk.get("outwardIssue") or lk.get("inwardIssue") or {}
            rel = (lk.get("type") or {}).get("outward" if "outwardIssue" in lk else "inward")
            if other.get("key"):
                links.append({"rel": rel, "key": other["key"]})
        parent = f.get("parent") or {}
        epic_link = f.get(custom.get("Epic Link", "")) if custom.get("Epic Link") else None
        out.append({"key": issue["key"], "title": f.get("summary") or "",
                    "due": f.get("duedate"), "release_date": release_dates[0] if release_dates else None,
                    "sprint": sprint if isinstance(sprint, str) else None, "points": points,
                    "created": (f.get("created") or "")[:10], "updated": (f.get("updated") or "")[:10],
                    "text": f"{f.get('summary') or ''}\n{f.get('description') or ''}",
                    "type": (f.get("issuetype") or {}).get("name"), "url": f"{url.rstrip('/')}/browse/{issue['key']}",
                    "assignee": (f.get("assignee") or {}).get("displayName"),
                    "status": (f.get("status") or {}).get("name"),
                    "priority": (f.get("priority") or {}).get("name"),
                    "epic": parent.get("key") or epic_link, "links": links,
                    "fix_versions": [v.get("name") for v in versions]})
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
    file_deps: Counter = Counter()
    imports = import_edges(repo, files, file_deps)
    commits, authors = git_activity(repo)
    sizes = {}
    for f in files:
        if commits.get(f):
            try:
                sizes[f] = sum(1 for _ in open(repo / f, encoding="utf-8", errors="replace"))
            except OSError:
                sizes[f] = 0
    # hotspot = how often it changes x how big it is (CodeScene's idea, computed from our git log)
    hotspot = {f: round(commits[f] * (1 + __import__("math").log1p(sizes.get(f, 0))), 1) for f in sizes}

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
    mod_authors: dict[str, Counter] = defaultdict(Counter)
    mod_commits: Counter = Counter()
    for f, c in authors.items():
        mod_authors[module(f)].update(c)
        mod_commits[module(f)] += commits[f]
    for m in sorted(set(file_count) | set(tickets_per)):
        who = next((o for pat, o in reversed(owners) if pat and m.startswith(pat)), None)
        hs = sorted(((f, h) for f, h in hotspot.items() if module(f) == m), key=lambda x: -x[1])[:5]
        nodes.append({"id": m, "files": file_count[m], "tickets": tickets_per[m],
                      "bug_share": round(bugs_per[m] / tickets_per[m], 2) if tickets_per[m] else 0,
                      "recent": recent_per[m], "owners": who,
                      "hot_files": [f for f, _ in hot_files[m].most_common(6)], "examples": examples[m],
                      "commits_1y": mod_commits[m],
                      "experts": [{"name": a, "commits": n} for a, n in mod_authors[m].most_common(4)],
                      "bus_factor": _bus_factor(mod_authors[m]),
                      "hotspots": [{"file": f, "score": h, "commits": commits[f], "lines": sizes.get(f, 0)}
                                   for f, h in hs]})
    file_experts = {f: [a for a, _ in c.most_common(3)] for f, c in authors.items()}
    data = {"modules": nodes, "history_tickets": len(history),
            "file_dependents": dict(file_deps), "file_experts": file_experts,
            "file_commits": dict(commits),
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
    deps = struct.get("file_dependents", {})
    experts = struct.get("file_experts", {})
    fcommits = struct.get("file_commits", {})
    people: Counter = Counter()
    for rank, f in enumerate(top_files[:3]):   # who has been changing the code this ticket lands in
        for k, who in enumerate(experts.get(f, [])):
            people[who] += (3 - rank) * (3 - k)
    return {"modules": mods, "files": top_files[:6], "evidence": {h.path: h.found_by for h in hits[:6]},
            "file_dependents": {f: deps.get(f, 0) for f in top_files[:6]},
            "file_commits_1y": {f: fcommits.get(f, 0) for f in top_files[:6]},
            "similar": sorted({s for h in hits[:3] for s in h.similar_tickets})[:5],
            "impact": area, "impact_reasons": {m: reasons[m] for m in area},
            "suggested_people": [p for p, _ in people.most_common(3)],
            "owners": sorted({by_id[m]["owners"] for m in mods + area if by_id.get(m, {}).get("owners")})}


def impact_markdown(r: dict) -> str:
    lines = ["**Lands in:** " + ", ".join(f"`{m}`" for m in r["modules"]), "", "**Likely files:**"]
    for f in r["files"]:
        extra = []
        if r.get("file_dependents", {}).get(f):
            extra.append(f"{r['file_dependents'][f]} files import it")
        if r.get("file_commits_1y", {}).get(f):
            extra.append(f"changed in {r['file_commits_1y'][f]} commits this year")
        lines.append(f"- `{f}` ({', '.join(r['evidence'].get(f, []) + extra)})")
    if r.get("suggested_people"):
        lines += ["", "**People who know this code:** " + ", ".join(r["suggested_people"])]
    lines += ["", "**Impact area** (check these when changing the code above):"]
    lines += [f"- `{m}`: {'; '.join(r['impact_reasons'][m])}" for m in r["impact"]] or ["- none found"]
    if r["similar"]:
        lines += ["", "**Similar past tickets:** " + ", ".join(r["similar"])]
    if r["owners"]:
        lines += ["", "**Owners:** " + ", ".join(r["owners"])]
    return "\n".join(lines)


def jira_note(t: dict) -> str:
    """Impact note in Jira wiki markup, ready to paste as a comment. Crewline never posts it by itself: writing to
    a company system is the team's decision (AGENTS.md)."""
    lines = ["h4. Crewline impact note", f"*Lands in:* {', '.join(t['modules'])}"]
    lines += ["*Likely files:*"] + [f"* {{{{{f}}}}}" + (f" - {t['file_dependents'][f]} files import it"
                                                      if t.get("file_dependents", {}).get(f) else "")
                                   for f in t["files"][:5]]
    if t.get("impact"):
        lines.append("*Impact area:* " + "; ".join(f"{m} ({', '.join(t['impact_reasons'][m])})" for m in t["impact"]))
    if t.get("suggested_people"):
        lines.append("*People who know this code:* " + ", ".join(t["suggested_people"]))
    files = [c for c in t.get("overlaps") or [] if c["level"] == "file"]
    if files:
        lines.append("*Same files as open:* " + ", ".join(c["b"] if c["a"] == t["key"] else c["a"] for c in files))
    if t.get("duplicates"):
        similar = ", ".join(f"{d['key']} ({d['kind']})" for d in t["duplicates"])
        lines.append("*Very similar (duplicate or sibling?):* " + similar)
    if t.get("priority_reasons"):
        lines.append(f"*Priority {t.get('priority_score')}/100:* " + "; ".join(t["priority_reasons"]))
    return "\n".join(lines)


def ranked_tickets(repo: Path, open_tickets: list[dict], limit: int = 20) -> str:
    """Markdown: open tickets ordered by priority score, with reasons and collisions (MCP `rank_tickets`)."""
    data = build(repo, load_history(repo), open_tickets, repo.name)
    lines = ["| # | Score | Ticket | Lands in | Why |", "|---|---|---|---|---|"]
    for i, t in enumerate(data["open"][:limit], 1):
        lines.append(f"| {i} | {t['priority_score']} | {t['key']} {t['title'][:60]} | {', '.join(t['modules'])} | "
                     f"{'; '.join(t['priority_reasons']) or '-'} |")
    files = [c for c in data["collisions"] if c["level"] == "file"]
    if files:
        lines += ["", "**Same-file collisions:**"]
        lines += [f"- {c['a']} ↔ {c['b']}: {', '.join(c['files'])}" + (" (different assignees)"
                  if c["different_owners"] else "") for c in files[:10]]
    return "\n".join(lines)


DUP_OPEN = 0.90     # cosine between two open tickets to call them likely duplicates
DUP_CLOSED = 0.92   # cosine to an already fixed ticket ("maybe fixed already / regression")


def duplicates(open_tickets: list[dict], history: list[dict], recent: int = 1500) -> dict[str, list[dict]]:
    """Likely duplicates by meaning (local embeddings, no tokens): open vs open, and open vs recently fixed."""
    if len(open_tickets) < 2:
        return {}
    import numpy as np

    from crewline.locate.semantic import _embedder

    def vecs(texts: list[str]):
        v = np.array(list(_embedder().embed([t[:1500] for t in texts], batch_size=64)), dtype=np.float32)
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

    ov = vecs([t["text"] for t in open_tickets])
    past = history[-recent:]
    pv = vecs([h["text"] for h in past]) if past else np.zeros((0, ov.shape[1]), dtype=np.float32)
    out: dict[str, list[dict]] = defaultdict(list)
    sim = ov @ ov.T
    for i, j in combinations(range(len(open_tickets)), 2):
        if sim[i, j] >= DUP_OPEN:
            a, b = open_tickets[i], open_tickets[j]
            out[a["key"]].append({"key": b["key"], "kind": "open", "similarity": round(float(sim[i, j]), 2)})
            out[b["key"]].append({"key": a["key"], "kind": "open", "similarity": round(float(sim[i, j]), 2)})
    if len(past):
        ps = ov @ pv.T
        for i, t in enumerate(open_tickets):
            for j in np.argsort(-ps[i])[:2]:
                if ps[i, j] >= DUP_CLOSED and past[j]["key"] != t["key"]:
                    out[t["key"]].append({"key": past[j]["key"], "kind": "fixed",
                                          "similarity": round(float(ps[i, j]), 2)})
    return dict(out)


def build(repo: Path, history: list[dict], open_tickets: list[dict], title: str = "") -> dict:
    """The map page's data: the shared structure plus every open ticket's impact."""
    repo = repo.resolve()
    struct = structure(repo, history, refresh=True)
    keep = ("key", "title", "type", "url", "assignee", "status", "priority", "epic", "links", "fix_versions",
            "due", "release_date", "sprint", "points", "created", "updated")
    open_out = [{**{k: t.get(k) for k in keep}, **impact(repo, t["text"], struct)} for t in open_tickets]
    collisions = overlaps(open_out)
    dups = duplicates(open_tickets, history)
    for t in open_out:
        t["overlaps"] = [c for c in collisions if t["key"] in (c["a"], c["b"])]
        t["duplicates"] = dups.get(t["key"], [])
    prioritize(open_out, struct)
    open_out.sort(key=lambda t: -t["priority_score"])
    for t in open_out:
        t["jira_note"] = jira_note(t)
    return {"title": title or repo.name, "modules": struct["modules"],
            "imports": [e for e in struct["imports"] if e["n"] >= 2],
            "cochange": [c for c in struct["cochange"] if c["n"] >= 3],
            "open": open_out, "collisions": collisions, "history_tickets": struct["history_tickets"]}


JIRA_PRIORITY = {"blocker": 1.0, "highest": 1.0, "critical": 0.8, "high": 0.6, "major": 0.5, "medium": 0.4,
                 "minor": 0.2, "low": 0.2, "trivial": 0.0, "lowest": 0.0}


def _days_left(t: dict) -> int | None:
    import datetime as dt
    d = t.get("due") or t.get("release_date")
    if not d:
        return None
    return (dt.date.fromisoformat(d[:10]) - dt.date.today()).days


def _urgency(t: dict) -> tuple[str, float]:
    """Time pressure from the due date (or the earliest unreleased fix version's release date) and staleness."""
    import datetime as dt
    left = _days_left(t)
    src = "due" if t.get("due") else "release"
    if left is not None:
        if left < 0:
            return f"{src} date passed {-left} days ago", 1.0
        if left <= 7:
            return f"{src} in {left} days", 0.8
        if left <= 30:
            return f"{src} in {left} days", 0.4
        return "", 0.1
    upd = t.get("updated")
    if upd and (dt.date.today() - dt.date.fromisoformat(upd)).days > 90:
        return f"no update for {(dt.date.today() - dt.date.fromisoformat(upd)).days} days", 0.2
    return "", 0.0


def prioritize(tickets: list[dict], struct: dict) -> None:
    """Transparent priority score (0-100) with reasons: 40% what people said in Jira (priority, bug, what it
    blocks, release), 40% the code (how far a change there spreads, how bug-prone the module is, whether another
    open ticket touches the same files), 20% time (due/release date, staleness). A ranking aid, not a verdict:
    the reasons are the point."""
    by_id = {m["id"]: m for m in struct["modules"]}
    importers: Counter = Counter()
    for e in struct["imports"]:
        importers[e["target"]] += 1
    max_imp = max(importers.values() or [1])
    for t in tickets:
        reasons = []
        pr = JIRA_PRIORITY.get((t.get("priority") or "").lower(), 0.4)
        is_bug = (t.get("type") or "").lower() == "bug"
        blocks = sum(1 for lk in t.get("links") or [] if (lk.get("rel") or "").lower() == "blocks")
        human = 0.5 * pr + 0.25 * is_bug + 0.15 * min(blocks, 3) / 3 + 0.10 * bool(t.get("fix_versions"))
        if t.get("priority"):
            reasons.append(f"{t['priority']} in Jira")
        if is_bug:
            reasons.append("bug")
        if blocks:
            reasons.append(f"blocks {blocks} ticket{'s' * (blocks > 1)}")
        if t.get("fix_versions"):
            reasons.append(f"targeted for {', '.join(t['fix_versions'][:2])}")
        land = t["modules"][0] if t["modules"] else None
        m = by_id.get(land, {})
        spread = importers.get(land, 0) / max_imp if land else 0
        bug_share = m.get("bug_share", 0)
        file_hits = sum(1 for c in t.get("overlaps") or [] if c["level"] == "file")
        code = 0.45 * spread + 0.35 * min(bug_share / 0.5, 1) + 0.20 * min(file_hits, 2) / 2
        if land and importers.get(land):
            reasons.append(f"lands in {land}, imported by {importers[land]} modules")
        if bug_share >= 0.3:
            reasons.append(f"{round(bug_share * 100)}% of past fixes in {land} were bugs")
        if file_hits:
            reasons.append(f"same files as {file_hits} other open ticket{'s' * (file_hits > 1)}")
        when, urgency = _urgency(t)
        if when:
            reasons.insert(0, when)
        t["days_left"] = _days_left(t)
        t["priority_score"] = round(100 * (0.4 * human + 0.4 * code + 0.2 * urgency))
        t["priority_reasons"] = reasons


def overlaps(tickets: list[dict], top_files: int = 3) -> list[dict]:
    """Open tickets that will touch the same code: a shared likely file (among each one's top 3) is a collision,
    a shared landing module is a softer overlap. Assigned to different people = worth a conversation."""
    out = []
    for a, b in combinations(tickets, 2):
        files = sorted(set(a["files"][:top_files]) & set(b["files"][:top_files]))
        mods = sorted(set(a["modules"][:1]) & set(b["modules"][:1]))
        if not files and not mods:
            continue
        out.append({"a": a["key"], "b": b["key"], "files": files, "modules": mods,
                    "level": "file" if files else "module",
                    "different_owners": bool(a.get("assignee") and b.get("assignee")
                                             and a["assignee"] != b["assignee"])})
    return sorted(out, key=lambda c: (c["level"] != "file", -len(c["files"])))

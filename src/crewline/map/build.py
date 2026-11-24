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


def git_activity(repo: Path, since: str = "1 year ago") -> tuple[Counter, dict[str, Counter], dict[str, Counter]]:
    """Per file: commits touching it, commits per author, and reviews per reviewer (`Reviewers:` trailers; in
    projects like Kafka maintainers mostly review, so authorship alone misses them). No merges. The raw material
    for hotspots and knowledge maps: who actually works on which code, independent of tickets."""
    p = subprocess.run(["git", "-C", str(repo), "log", "--no-merges", f"--since={since}", "--no-renames",
                        "--name-only", "--format=@@%aN%n##%(trailers:key=Reviewers,valueonly,separator=%x3B)"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    commits: Counter = Counter()
    authors: dict[str, Counter] = defaultdict(Counter)
    reviewers: dict[str, Counter] = defaultdict(Counter)

    def flush(who: str, revs: list[str], files: list[str]) -> None:
        if len(files) > BULK_COMMIT:   # license headers, annotations, mass renames: not knowledge of the code
            return
        for f in files:
            commits[f] += 1
            authors[f][who] += 1
            reviewers[f].update(revs)

    who, revs, files = "", [], []
    for line in p.stdout.splitlines():
        if line.startswith("@@"):
            flush(who, revs, files)
            who, revs, files = line[2:].strip(), [], []
        elif line.startswith("##"):
            revs = [r.split("<", 1)[0].strip() for r in re.split(r"[;,]", line[2:]) if r.strip()]
            revs = [r for r in revs if r]
        elif line.strip() and baseline.is_code(line.strip()):
            files.append(line.strip())
    flush(who, revs, files)
    return commits, authors, reviewers


BULK_COMMIT = 100   # Kafka 2026: one 947-file annotation commit made its author "expert" on every file


def person_key(name: str | None) -> str:
    """Jira display names and git author names differ in accents, hyphens, order and junk ("Chang Chi Hsu" vs
    "Chang-Chi Hsu", "X  (add mul)"): compare on sorted lowercase ASCII tokens."""
    import unicodedata
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", re.sub(r"\(.*?\)", " ", name)).encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.findall(r"[a-z0-9]+", s.replace("-", ""))))


def same_person(a: str | None, b: str | None) -> bool:
    ka, kb = person_key(a), person_key(b)
    if not ka or not kb:
        return False
    if ka == kb or ka.replace(" ", "") == kb.replace(" ", ""):
        return True
    ta, tb = ka.split(), kb.split()   # "Muralidhar Basani" vs "Murali Basani": same surname, one first name prefixes
    return len(ta) == len(tb) == 2 and bool(set(ta) & set(tb)) and any(
        x.startswith(y) or y.startswith(x) for x in set(ta) - set(tb) for y in set(tb) - set(ta))


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
        out.append(_from_issue(issue, custom, url))
        if len(out) >= n:
            break
    _attach_parents(jira, out)
    return out


def _from_issue(issue: dict, custom: dict[str, str], url: str | None) -> dict:
    """One open ticket from a Jira REST issue (our own search, or what an agent fetched with its Jira MCP)."""
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
    pf = parent.get("fields") or {}
    epic_link = f.get(custom.get("Epic Link", "")) if custom.get("Epic Link") else None
    parent_is_epic = ((pf.get("issuetype") or {}).get("name") or "").lower() == "epic"
    return {"key": issue["key"], "title": f.get("summary") or "",
            "parent": parent.get("key") or epic_link, "parent_title": pf.get("summary"),
            "is_subtask": bool((f.get("issuetype") or {}).get("subtask")),
            "parent_kind": "epic" if (epic_link or parent_is_epic) else ("parent" if parent else None),
            "due": f.get("duedate"), "release_date": release_dates[0] if release_dates else None,
            "sprint": sprint if isinstance(sprint, str) else None, "points": points,
            "created": (f.get("created") or "")[:10], "updated": (f.get("updated") or "")[:10],
            "text": f"{f.get('summary') or ''}\n{_plain(f.get('description'))}",
            "type": (f.get("issuetype") or {}).get("name"),
            "url": f"{url.rstrip('/')}/browse/{issue['key']}" if url else None,
            "assignee": _name(f.get("assignee")),
            "status": (f.get("status") or {}).get("name"),
            "priority": (f.get("priority") or {}).get("name"),
            "epic": parent.get("key") or epic_link, "links": links,
                "fix_versions": [v.get("name") for v in versions]}



def open_tickets_from(path_or_data, jira_url: str | None = None, n: int = 100) -> list[dict]:
    """Open tickets without a Jira token: a Jira CSV export (Filters -> Export -> CSV), or JSON that an agent got
    from its own Jira/Atlassian MCP (REST issues, {"issues": [...]}, or flat {key, summary, description, ...})."""
    import csv
    import io
    data = path_or_data
    f = Path(str(data)) if isinstance(data, (str, Path)) and len(str(data)) < 500 else None
    if f and f.suffix.lower() in (".csv", ".json") and f.exists():
        text = f.read_text(encoding="utf-8-sig")
        data = list(csv.reader(io.StringIO(text))) if f.suffix.lower() == ".csv" else json.loads(text)
    elif isinstance(data, str):
        data = json.loads(data)
    if data and isinstance(data, list) and isinstance(data[0], list):   # CSV rows; Jira repeats some headers
        head, rows = data[0], data[1:]
        items = []
        for r in rows:
            d: dict[str, list[str]] = defaultdict(list)
            for h, v in zip(head, r, strict=False):
                if v.strip():
                    d[h.strip().lower()].append(v.strip())
            items.append({"key": (d.get("issue key") or [""])[0], "summary": (d.get("summary") or [""])[0],
                          "description": (d.get("description") or [""])[0],
                          "assignee": (d.get("assignee") or [None])[0], "status": (d.get("status") or [None])[0],
                          "priority": (d.get("priority") or [None])[0], "type": (d.get("issue type") or [None])[0],
                          "due": (d.get("due date") or [None])[0], "created": (d.get("created") or [""])[0],
                          "updated": (d.get("updated") or [""])[0],
                          "parent": (d.get("parent") or d.get("parent id") or d.get("custom field (epic link)")
                                     or [None])[0],
                          "sprint": (d.get("sprint") or [None])[-1], "fix_versions": d.get("fix version/s", []),
                          "points": (d.get("custom field (story points)") or [None])[0]})
        data = items
    if isinstance(data, dict):
        data = data.get("issues") or data.get("results") or []
    out = []
    for it in data[:n]:
        if "fields" in it:
            out.append(_from_issue(it, {}, jira_url))
            continue
        key = it.get("key") or it.get("issue_key") or ""
        summary = it.get("summary") or it.get("title") or ""
        out.append({"key": key, "title": summary, "text": f"{summary}\n{_plain(it.get('description'))}",
                    "type": it.get("type"), "status": it.get("status"), "priority": it.get("priority"),
                    "assignee": it.get("assignee"), "due": (it.get("due") or None) and str(it["due"])[:10],
                    "release_date": None, "sprint": it.get("sprint"), "points": _num(it.get("points")),
                    "created": str(it.get("created") or "")[:10], "updated": str(it.get("updated") or "")[:10],
                    "parent": it.get("parent"), "epic": it.get("parent"), "parent_title": None,
                    "parent_kind": "parent" if it.get("parent") else None, "is_subtask": False, "links": [],
                    "fix_versions": it.get("fix_versions") or [],
                    "url": f"{jira_url.rstrip('/')}/browse/{key}" if jira_url else None})
    by_key = {t["key"]: t for t in out}
    for t in out:   # parents that are in the same export give terse children their context
        p = by_key.get(t.get("parent") or "")
        if p:
            t["parent_title"], t["parent_text"], t["parent_status"] = p["title"], p["text"], p["status"]
    return out


def _plain(doc) -> str:
    """Jira Cloud API v3 and Atlassian MCP return descriptions as ADF (a JSON tree); v2 returns text."""
    if doc is None:
        return ""
    if isinstance(doc, str):
        return doc
    if isinstance(doc, dict):
        own = doc.get("text") or ""
        return own + " ".join(_plain(c) for c in doc.get("content") or [])
    if isinstance(doc, list):
        return " ".join(_plain(c) for c in doc)
    return str(doc)


def _name(person) -> str | None:
    return person.get("displayName") if isinstance(person, dict) else person


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _attach_parents(jira, tickets: list[dict]) -> None:
    """Fetch each parent (story/epic) once: its text helps place terse sub-tasks ("add tests", "Connect part"),
    and its title/status are shown on the map."""
    keys = sorted({t["parent"] for t in tickets if t.get("parent")})
    info = {}
    for i in range(0, len(keys), 50):
        try:
            for issue in jira.search(f"key in ({','.join(keys[i:i + 50])})",
                                     fields="summary,description,status,issuetype,duedate,fixVersions"):
                f = issue["fields"]
                info[issue["key"]] = {"title": f.get("summary") or "", "text": f.get("description") or "",
                                      "status": (f.get("status") or {}).get("name"),
                                      "type": (f.get("issuetype") or {}).get("name"), "due": f.get("duedate")}
        except Exception:  # noqa: BLE001 - parents in another project or not visible: keep the children
            continue
    for t in tickets:
        p = info.get(t.get("parent") or "")
        if p:
            t["parent_title"] = t.get("parent_title") or p["title"]
            t["parent_status"], t["parent_type"] = p["status"], p["type"]
            t["parent_text"] = f"{p['title']}\n{p['text'][:1500]}"
            t["due"] = t.get("due") or p.get("due")   # a sub-task inherits its parent's deadline


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
    commits, authors, reviewers = git_activity(repo)
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
            "file_authors": {f: dict(c) for f, c in authors.items()},
            "module_authors": {m: dict(c) for m, c in mod_authors.items()},
            "file_reviewers": {f: dict(c) for f, c in reviewers.items() if c},
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
    import hashlib

    import numpy as np

    from crewline.config import data_dir
    from crewline.locate.semantic import _embedder
    cache_path = data_dir() / "index" / "ticket-embeddings.npz"   # closed tickets never change: embed once
    cache: dict[str, np.ndarray] = {}
    if cache_path.exists():
        with np.load(cache_path) as z:
            cache = dict(zip(z["keys"].tolist(), z["vecs"], strict=True))
    added = False

    def vecs(texts: list[str]):
        nonlocal added
        hs = [hashlib.sha1(t[:1500].encode("utf-8")).hexdigest() for t in texts]
        todo = [i for i, h in enumerate(hs) if h not in cache]
        if todo:
            for i, v in zip(todo, _embedder().embed([texts[i][:1500] for i in todo], batch_size=64), strict=True):
                cache[hs[i]] = np.asarray(v, dtype=np.float32)
            added = True
        v = np.array([cache[h] for h in hs], dtype=np.float32)
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

    ov = vecs([t["text"] for t in open_tickets])
    past = history[-recent:]
    pv = vecs([h["text"] for h in past]) if past else np.zeros((0, ov.shape[1]), dtype=np.float32)
    if added:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache_path, keys=np.array(list(cache)), vecs=np.stack(list(cache.values())))
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
    keep += ("parent", "parent_title", "parent_status", "parent_type", "parent_kind", "is_subtask")

    def locate_text(t: dict) -> str:
        # sub-tasks are often one line ("Connect support"): the parent says what the work is about
        if t.get("parent_text") and (t.get("is_subtask") or len(t["text"]) < 300):
            return f"{t['text']}\n\nParent {t.get('parent')}: {t['parent_text']}"
        return t["text"]

    open_out = [{**{k: t.get(k) for k in keep}, **impact(repo, locate_text(t), struct)} for t in open_tickets]
    parent_of = {t["key"]: t.get("parent") for t in open_out}
    collisions = overlaps(open_out)
    mark_family(collisions, parent_of)
    dups = duplicates(open_tickets, history)
    for t in open_out:
        t["overlaps"] = [c for c in collisions if t["key"] in (c["a"], c["b"])]
        t["duplicates"] = [d for d in dups.get(t["key"], [])
                           if not (t.get("parent") and parent_of.get(d["key"]) == t.get("parent"))]
    prioritize(open_out, struct)
    open_out.sort(key=lambda t: -t["priority_score"])
    for t in open_out:
        t["assignee_fit"] = assignee_fit(t, struct)
        t["jira_note"] = jira_note(t)
    return {"people": workload(open_out),
            "title": title or repo.name, "modules": struct["modules"],
            "imports": [e for e in struct["imports"] if e["n"] >= 2],
            "cochange": [c for c in struct["cochange"] if c["n"] >= 3],
            "open": open_out, "collisions": collisions, "parents": rollup_parents(open_out),
            "history_tickets": struct["history_tickets"]}


def assignee_fit(t: dict, struct: dict) -> str:
    """Has the assignee written or reviewed the code this ticket lands in (past year, git)? "knows" (the likely
    files, or 3+ changes in the module) / "near" (touched the module or its neighbours a little) / "new" /
    "unassigned".
    A hint for leads ("new" may be fine: onboarding), never a verdict."""
    if not t.get("assignee"):
        return "unassigned"
    fa, ma = struct.get("file_authors", {}), struct.get("module_authors", {})
    fr = struct.get("file_reviewers", {})
    who = {w for f in t["files"][:6] for w in (*fa.get(f, {}), *fr.get(f, {}))}   # wrote or reviewed a likely file
    who |= {w for m in t["modules"] for w, n in ma.get(m, {}).items() if n >= 3}   # or works in the module
    if any(same_person(t["assignee"], w) for w in who):
        return "knows"
    touched = {w for m in t["modules"] + t.get("impact", [])[:2] for w in ma.get(m, {})}
    return "near" if any(same_person(t["assignee"], w) for w in touched) else "new"


def workload(tickets: list[dict]) -> list[dict]:
    """Open work per assignee: how much, how urgent, and on how much of it they know the code."""
    acc: dict[str, dict] = {}
    for t in tickets:
        name = t.get("assignee") or ""
        p = acc.setdefault(name, {"name": name, "open": 0, "points": 0, "late": 0, "knows": 0, "keys": []})
        p["open"] += 1
        p["points"] += t.get("points") or 0
        p["late"] += t.get("days_left") is not None and t["days_left"] < 0
        p["knows"] += t.get("assignee_fit") == "knows"
        p["keys"].append(t["key"])
    return sorted(acc.values(), key=lambda p: (not p["name"], -p["open"]))


def mark_family(collisions: list[dict], parent_of: dict[str, str | None]) -> None:
    """Siblings under one parent, or a parent and its own child, were planned together: shown, never alarmed."""
    for c in collisions:
        pa, pb = parent_of.get(c["a"]), parent_of.get(c["b"])
        c["same_parent"] = bool((pa and pa == pb) or pa == c["b"] or pb == c["a"])


def rollup_parents(tickets: list[dict]) -> list[dict]:
    """Epics / parent stories seen from their open children: where the work lands, how far it spreads, what is
    most urgent, and whether children collide with work outside the parent."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in tickets:
        if t.get("parent"):
            groups[t["parent"]].append(t)
    out = []
    for key, kids in groups.items():
        mods: Counter = Counter()
        spread: Counter = Counter()
        for k in kids:
            mods.update(k["modules"][:1])
            spread.update(k["impact"])
        family = {key, *(k["key"] for k in kids)}
        outside = sorted({c["b"] if c["a"] == k["key"] else c["a"] for k in kids for c in k["overlaps"]
                          if c["level"] == "file" and not c.get("same_parent")} - family)
        first = kids[0]
        out.append({"key": key, "title": first.get("parent_title") or "", "status": first.get("parent_status"),
                    "kind": first.get("parent_kind") or "parent", "children": [k["key"] for k in kids],
                    "statuses": dict(Counter(k.get("status") or "?" for k in kids)),
                    "modules": [m for m, _ in mods.most_common(4)],
                    "impact": [m for m, _ in spread.most_common(5) if m not in mods][:4],
                    "top_child": max(kids, key=lambda k: k["priority_score"])["key"],
                    "max_score": max(k["priority_score"] for k in kids),
                    "collides_outside": outside})
    return sorted(out, key=lambda p: -p["max_score"])


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

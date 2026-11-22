"""Team memory: lessons pinned to code paths, with source link, ACL scope and staleness.

Each item inherits the ACL of its source (`scope`, e.g. a GitHub repo `org/name` or a Confluence space).
`recall()` only returns items whose scope the caller is allowed to read; the caller passes an `allowed`
predicate built from the user's own credentials (e.g. `sources.github.can_read`).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
create table if not exists items (
  id integer primary key,
  scope text not null,           -- ACL scope: github repo, confluence space, ...
  path text not null,            -- file or directory the lesson applies to
  kind text not null,            -- pitfall | convention | decision | context
  lesson text not null,
  source_url text not null,
  source_id text not null unique,
  created text not null,
  approved integer not null default 1
);
create index if not exists items_path on items(path);
"""


@dataclass
class Item:
    scope: str
    path: str
    kind: str
    lesson: str
    source_url: str
    source_id: str
    created: str
    approved: bool = True
    stale: bool = False


class Memory:
    def __init__(self, db: Path):
        db.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db, check_same_thread=False)
        self.db.executescript(SCHEMA)

    def add(self, item: Item) -> bool:
        cur = self.db.execute(
            "insert or ignore into items(scope,path,kind,lesson,source_url,source_id,created,approved)"
            " values(?,?,?,?,?,?,?,?)",
            (item.scope, item.path, item.kind, item.lesson, item.source_url, item.source_id, item.created,
             int(item.approved)))
        self.db.commit()
        return cur.rowcount == 1

    def seen(self, source_id: str) -> bool:
        return self.db.execute("select 1 from items where source_id=?", (source_id,)).fetchone() is not None

    def recall(self, paths: list[str], allowed: Callable[[str], bool], before: str | None = None,
               limit: int = 20, changed_since: Callable[[str, str], int] | None = None) -> list[Item]:
        """Items for these files (exact path, then same directory), newest first, ACL-filtered.
        `before` hides items created after a date (benchmarks); `changed_since(path, date)` marks items stale
        when the file changed a lot after the lesson was written."""
        out: list[Item] = []
        cache: dict[str, bool] = {}
        dirs = {p.rsplit("/", 1)[0] for p in paths}
        rows = self.db.execute(
            "select scope,path,kind,lesson,source_url,source_id,created,approved from items where approved=1"
            + (" and created < ?" if before else "") + " order by created desc", ((before,) if before else ()))
        exact, near = [], []
        for r in rows:
            it = Item(*r[:7], approved=bool(r[7]))
            if it.path in paths:
                exact.append(it)
            elif it.path.rsplit("/", 1)[0] in dirs:
                near.append(it)
        for it in exact + near:
            if it.scope not in cache:
                cache[it.scope] = allowed(it.scope)
            if not cache[it.scope]:
                continue
            if changed_since and changed_since(it.path, it.created) > 20:
                it.stale = True
            out.append(it)
            if len(out) >= limit:
                break
        return out


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

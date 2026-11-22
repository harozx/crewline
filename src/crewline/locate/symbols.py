"""Symbols declared in code files, and symbols a ticket mentions.

Index is built from a snapshot taken before the eval cutoff, so fixes made later cannot leak into it.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

from rank_bm25 import BM25Okapi

from crewline.locate.baseline import is_code
from crewline.locate.text import tokens

TYPE_DECL = re.compile(r"\b(?:class|interface|enum|record|object|trait)\s+([A-Z][A-Za-z0-9_]*)")
METHOD_DECL = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|default|override|def|"
    r"implicit|lazy)\s+)+(?:[\w<>\[\],.?]+\s+)?([a-zA-Z_]\w*)\s*[\[(]", re.M)
CONFIG_KEY = re.compile(r'"([a-z][a-z0-9]*(?:\.[a-z0-9-]+){1,})"')

# What a ticket can mention: Class#method, Class.method, CamelCase, config.keys, stack frames, file names.
MENTION = re.compile(r"[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+|[A-Z]{2,}[a-z][A-Za-z0-9]*|[a-z]+[A-Z][A-Za-z0-9]+")
MENTION_KEY = re.compile(r"\b[a-z][a-z0-9]*(?:\.[a-z0-9-]+){1,}\b")
FRAME = re.compile(r"at\s+([\w.$]+)\.([\w$<>]+)\(([\w]+)\.(?:java|scala):\d+\)")
FILE = re.compile(r"\b([A-Z]\w+)\.(?:java|scala)\b")


def extract(text: str) -> dict[str, list[str]]:
    return {
        "types": sorted(set(TYPE_DECL.findall(text))),
        "methods": sorted(set(METHOD_DECL.findall(text)) - {"if", "for", "while", "switch", "return", "new"}),
        "keys": sorted(set(CONFIG_KEY.findall(text))),
    }


def build(repo: Path, out: Path) -> int:
    index = {}
    for f in repo.rglob("*"):
        rel = f.relative_to(repo).as_posix()
        if not f.is_file() or rel.startswith(".git/") or not is_code(rel):
            continue
        try:
            index[rel] = extract(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    out.write_text(json.dumps(index))
    return len(index)


class SymbolIndex:
    def __init__(self, index: dict[str, dict[str, list[str]]]):
        self.files = list(index)
        self.owner: dict[str, set[str]] = defaultdict(set)   # symbol (lowercase) -> files declaring it
        for f, s in index.items():
            for sym in s["types"] + s["methods"] + s["keys"]:
                self.owner[sym.lower()].add(f)
            self.owner[f.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()].add(f)
        self.bm = BM25Okapi([tokens(" ".join([f] + s["types"] + s["methods"])) for f, s in index.items()])

    @classmethod
    def load(cls, path: Path) -> SymbolIndex:
        return cls(json.loads(path.read_text()))

    def rank_mentions(self, text: str, alive: set[str], k: int = 50) -> list[str]:
        """Files that declare what the ticket names. Rare symbols weigh more; stack frames weigh most."""
        weights: dict[str, float] = defaultdict(float)
        for pkg, _method, cls in FRAME.findall(text):
            weights[cls.lower()] += 3
            weights[pkg.rsplit(".", 1)[-1].lower()] += 1
        for cls in FILE.findall(text):
            weights[cls.lower()] += 2
        for m in MENTION.findall(text) + MENTION_KEY.findall(text):
            weights[m.lower()] += 1
        acc: dict[str, float] = defaultdict(float)
        for sym, w in weights.items():
            files = [f for f in self.owner.get(sym, ()) if f in alive]
            if not files or len(files) > 40:
                continue
            for f in files:
                acc[f] += w * math.log(1 + 40 / len(files))
        return [f for f, _ in sorted(acc.items(), key=lambda x: -x[1])[:k]]

    def rank_bm25(self, text: str, alive: set[str], k: int = 50) -> list[str]:
        scores = self.bm.get_scores(tokens(text))
        order = sorted(range(len(self.files)), key=lambda i: -scores[i])
        return [self.files[i] for i in order if scores[i] > 0 and self.files[i] in alive][:k]

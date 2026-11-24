"""Semantic signal: embed each code file (path + declared symbols + its opening lines) and the ticket, rank by
cosine similarity. Bridges tickets written in product/UI language and code named in engineering terms, where
the lexical signals (path, symbols, mentions) miss. Local ONNX model via fastembed: no tokens, no API.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from crewline.config import data_dir

MODEL = "BAAI/bge-small-en-v1.5"
_model = None


def _embedder():
    global _model
    if _model is None:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL, cache_dir=str(data_dir() / "models"))
    return _model


def _doc(path: str, syms: dict, head: str) -> str:
    names = " ".join(syms.get("types", [])[:10] + syms.get("methods", [])[:30])
    return f"{path}\n{names}\n{head[:1200]}"


def build(root: Path, symbols: dict[str, dict], out: Path) -> int:
    """Embed every indexed file under `root` (a checkout). Saves paths + float16 vectors to `out` (.npz)."""
    paths = sorted(symbols)
    docs = []
    for p in paths:
        try:
            head = (root / p).read_text(encoding="utf-8", errors="replace")[:1500]
        except OSError:
            head = ""
        docs.append(_doc(p, symbols[p], head))
    vecs = np.array(list(_embedder().embed(docs, batch_size=64)), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    np.savez_compressed(out, paths=np.array(paths), vecs=vecs.astype(np.float16))
    return len(paths)


class SemanticIndex:
    def __init__(self, path: Path):
        data = np.load(path, allow_pickle=False)
        self.paths = list(data["paths"])
        self.vecs = data["vecs"].astype(np.float32)

    def rank(self, text: str, alive: set[str], k: int = 50) -> list[str]:
        q = np.array(list(_embedder().embed([text[:2000]]))[0], dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        scores = self.vecs @ q
        order = np.argsort(-scores)
        out = []
        for i in order:
            if self.paths[i] in alive:
                out.append(self.paths[i])
                if len(out) >= k:
                    break
        return out

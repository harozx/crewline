from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Datasets, caches and ledgers live outside the repo (default D:/crewline-data)."""
    p = Path(os.environ.get("CREWLINE_DATA", "D:/crewline-data"))
    p.mkdir(parents=True, exist_ok=True)
    return p

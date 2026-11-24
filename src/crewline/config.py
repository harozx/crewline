from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Datasets, caches and ledgers live outside the repo: $CREWLINE_DATA, default ~/.crewline."""
    p = Path(os.environ.get("CREWLINE_DATA") or Path.home() / ".crewline")
    p.mkdir(parents=True, exist_ok=True)
    return p

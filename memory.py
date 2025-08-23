# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json

class TraceStore:
    def __init__(self, path: str = "traces.jsonl"):
        self.path = Path(path)

    def append(self, rec: dict):
        line = json.dumps(rec, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
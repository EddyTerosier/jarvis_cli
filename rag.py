# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def _chunk_paragraphs(text: str) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r","")) if p.strip()]
    return paras

class LocalRAG:
    def __init__(self, docs_path: str = "docs", max_chars: int = 700):
        self.docs_path = Path(docs_path)
        self.max_chars = max_chars
        self.corpus: List[str] = []
        self.meta: List[str] = []  # "filename: first words"
        self.vectorizer = None
        self.tfidf = None
        self.bm25 = True  # flag “index dispo” pour l’UI

    def build_index(self):
        self.corpus, self.meta = [], []
        if not self.docs_path.exists():
            self.bm25 = None
            return
        for p in self.docs_path.rglob("*"):
            if not p.is_file(): continue
            if p.suffix.lower() not in {".md", ".txt"}: continue
            txt = _read_text_file(p)
            for para in _chunk_paragraphs(txt):
                snippet = para[:120].replace("\n"," ")
                self.corpus.append(para)
                self.meta.append(f"{p.as_posix()}:\n{snippet}")
        if not self.corpus:
            self.bm25 = None
            return
        self.vectorizer = TfidfVectorizer(ngram_range=(1,2), lowercase=True)
        self.tfidf = self.vectorizer.fit_transform(self.corpus)
        self.bm25 = True

    def answer(self, query: str) -> Tuple[str, List[str]]:
        if not self.corpus or self.vectorizer is None:
            return "", []
        q = self.vectorizer.transform([query])
        sims = cosine_similarity(q, self.tfidf)[0]
        order = sims.argsort()[::-1]
        evidence, picked = [], []
        for idx in order[:3]:
            para = self.corpus[idx]
            src = self.meta[idx]
            picked.append(para)
            evidence.append(src)
        if not picked:
            return "", []
        best = picked[0][: self.max_chars]
        return best, evidence
# -*- coding: utf-8 -*-
from __future__ import annotations
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
import trafilatura
from trafilatura.settings import use_config
from pathlib import Path
import time, json, re
from typing import List, Dict, Tuple, Optional
import requests
from bs4 import BeautifulSoup

def tokenize(text: str) -> List[str]:
    toks = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]+", (text or "").lower())
    stop = {"le","la","les","de","des","du","un","une","et","ou","au","aux","en","dans","sur","pour","par","avec",
            "sans","ne","pas","que","qui","quoi","est","sont","il","elle","on","je","vous","tu","nous","vos","mes",
            "tes","ses","leur","leurs","ce","cet","cette","ces","d","l","à"}
    return [t for t in toks if len(t) > 2 and t not in stop]

def split_paragraphs(txt: str) -> List[str]:
    if not txt:
        return []
    parts = [p.strip() for p in txt.replace("\r", "").split("\n\n") if p.strip()]
    if parts:
        return parts
    sents = [s.strip() for s in re.split(r"(?<=[\.\!\?])\s+", txt) if s.strip()]
    return sents

class WebClient:
    def __init__(self, cfg: Dict):
        self.cfg = cfg or {}
        self.cache_path = Path(".cache/web_cache.json")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()
        self._last_error = None
        self.tcfg = use_config()
        self.tcfg.set("DEFAULT", "timeout", str(self.cfg.get("timeout", 10)))
        self.tcfg.set("DEFAULT", "user_agent", self.cfg.get("user_agent", "JarvisCLI/0.1 (+local)"))

    def update_config(self, cfg: Dict):
        self.cfg = cfg or {}
        self.tcfg.set("DEFAULT", "timeout", str(self.cfg.get("timeout", 10)))
        self.tcfg.set("DEFAULT", "user_agent", self.cfg.get("user_agent", "JarvisCLI/0.1 (+local)"))

    def _load_cache(self) -> Dict[str, Dict]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        if not self.cfg.get("cache", True):
            return
        try:
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def clear_cache(self):
        self.cache = {}
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
        except Exception:
            pass

    def _allowed(self, url: str) -> bool:
        wl = set(self.cfg.get("whitelist") or [])
        bl = set(self.cfg.get("blacklist") or [])
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        if wl and not any(host.endswith(d) for d in wl):
            return False
        if bl and any(host.endswith(d) for d in bl):
            return False
        return True

    def _python_fallback_candidates(self, q: str) -> List[Tuple[str, str]]:
        q = (q or "").lower()
        cand: List[Tuple[str, str]] = []
        if ("dataclass" in q) or ("data class" in q):
            cand += [
                ("Data Classes — docs.python.org", "https://docs.python.org/3/library/dataclasses.html"),
                ("RealPython — Data Classes", "https://realpython.com/python-data-classes/"),
            ]
        if "namedtuple" in q or "named tuple" in q:
            cand += [
                ("collections.namedtuple — docs.python.org", "https://docs.python.org/3/library/collections.html#collections.namedtuple"),
                ("RealPython — namedtuple", "https://realpython.com/python-namedtuple/"),
            ]
        if "pep 8" in q or "pep8" in q or ("style" in q and "python" in q):
            cand += [
                ("PEP 8 — Style Guide", "https://peps.python.org/pep-0008/"),
                ("Hitchhiker’s Guide — Code Style", "https://docs.python-guide.org/writing/style/"),
            ]
        if any(k in q for k in ["pandas","dataframe","groupby","merge","join","series"]):
            cand += [
                ("Pandas — User Guide", "https://pandas.pydata.org/docs/user_guide/index.html"),
                ("Pandas — GroupBy", "https://pandas.pydata.org/docs/user_guide/groupby.html"),
            ]
        if any(k in q for k in ["numpy","ndarray","broadcast","vectoris"]):
            cand += [
                ("NumPy — Quickstart", "https://numpy.org/doc/stable/user/quickstart.html"),
                ("NumPy — User Guide", "https://numpy.org/doc/stable/user/index.html"),
            ]
        if any(k in q for k in ["scikit-learn","sklearn","classification","regression","pipeline"]):
            cand += [
                ("scikit-learn — User Guide", "https://scikit-learn.org/stable/user_guide.html"),
                ("Choosing the right estimator — scikit-learn", "https://scikit-learn.org/stable/tutorial/machine_learning_map/index.html"),
            ]
        if any(k in q for k in ["seaborn","visualis","plot","chart"]):
            cand += [
                ("Seaborn — Tutorial", "https://seaborn.pydata.org/tutorial.html"),
            ]
        if any(k in q for k in ["dépression","depression","anxiété","anxiete","bipolaire","schizo","tcc","thérapie cognitive","dsm"]):
            cand += [
                ("INSERM — Dossiers Depression", "https://www.inserm.fr/dossier/depression/"),
                ("WHO — Mental health", "https://www.who.int/health-topics/mental-health"),
                ("NHS — Mental health", "https://www.nhs.uk/mental-health/"),
                ("APA — Topics", "https://www.apa.org/topics"),
            ]
        return [(t, u) for (t, u) in cand if self._allowed(u)]

    def _refine_query(self, query: str) -> str:
        q = (query or "").strip()
        low = q.lower()
        if any(k in low for k in ["diff", "différence", "difference", "compare", "vs", "vs.", "contre"]):
            q += " vs comparison difference python"
        if "python" not in low:
            q += " python"
        return q

    def search(self, query: str) -> List[Dict]:
        n = int(self.cfg.get("max_results", 3))
        want = max(1, min(10, n))
        results = []
        backoff = 1.0
        tries = 5
        for attempt in range(tries):
            try:
                with DDGS() as ddgs:
                    for r in ddgs.text(query, region="fr-fr", safesearch="moderate", max_results=want):
                        url = r.get("href") or r.get("url")
                        title = r.get("title") or ""
                        if not url or not self._allowed(url):
                            continue
                        results.append({"url": url, "title": title})
                        if len(results) >= n:
                            break
                break
            except RatelimitException as e:
                self._last_error = f"Rate limit ({e}). Retry in {backoff:.0f}s."
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"
                break
        return results

    def _requests_get(self, url: str) -> Optional[str]:
        headers = {
            "User-Agent": self.cfg.get("user_agent", "JarvisCLI/0.1 (+local)"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://duckduckgo.com/",
            "Connection": "close",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=self.cfg.get("timeout", 10))
            if resp.status_code == 200:
                if not resp.encoding:
                    resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            self._last_error = f"HTTP {resp.status_code} for {url}"
            return None
        except Exception as e:
            self._last_error = f"requests error for {url}: {e}"
            return None

    def _bs4_extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        main = soup.select_one("main, article, [role='main'], .content, .article-content, .article-body, #content, .main-content")
        if not main:
            main = soup.body or soup
        texts = []
        for tag in main.find_all(["p", "li"]):
            t = tag.get_text(" ", strip=True)
            if t and len(t) > 20:
                texts.append(t)
        return "\n\n".join(texts)

    def fetch(self, url: str) -> Optional[Dict]:
        if url in self.cache:
            return self.cache[url]

        html = None
        try:
            html = trafilatura.fetch_url(url, config=self.tcfg)
        except Exception as e:
            self._last_error = f"fetch_url error for {url}: {e}"

        if not html:
            html = self._requests_get(url)
            if not html:
                return None

        try:
            extracted = trafilatura.extract(html, config=self.tcfg, output="json", input="html")
            if not extracted:
                extracted = trafilatura.extract(html, config=self.tcfg, output="json")
            if extracted:
                data = json.loads(extracted)
                text = (data.get("text") or "").strip()
                if text:
                    rec = {"url": url, "title": data.get("title") or "", "text": text, "date": data.get("date") or "", "ts": int(time.time())}
                    self.cache[url] = rec
                    self._save_cache()
                    return rec
        except Exception:
            pass

        try:
            txt = self._bs4_extract_text(html)
            if txt and len(txt) > 100:
                soup = BeautifulSoup(html, "lxml")
                title = (soup.title.get_text(strip=True) if soup.title else "")[:120]
                rec = {"url": url, "title": title, "text": txt, "date": "", "ts": int(time.time())}
                self.cache[url] = rec
                self._save_cache()
                return rec
            self._last_error = f"No parsable text for {url}"
            return None
        except Exception as e:
            self._last_error = f"bs4 extract error for {url}: {e}"
            return None

    def _rank_snippet(self, query: str, docs: List[Dict]) -> Tuple[Optional[str], List[str]]:
        qtok = set(tokenize(query))
        q = (query or "").lower()
        is_compare = any(k in q for k in ["vs", "contre", "diff", "difference", "différence", "compar"])
        cmp_words = {"difference","différence","vs","versus","compare","comparaison","contre"}
        must = set()
        if "dataclass" in q: must.add("dataclass")
        if "namedtuple" in q: must.add("namedtuple")

        best_snip, best_score = None, -1
        sources = []
        penalize = {"unsafe_hash","eq","frozen","hash","slots"}

        for d in docs:
            parts = split_paragraphs(d["text"])
            for p in parts:
                ptok = set(tokenize(p))
                score = len(qtok & ptok)
                if is_compare and (ptok & cmp_words):
                    score += 4
                if must and must.issubset(ptok):
                    score += 6
                if any(k in ptok for k in penalize):
                    score -= 2
                if len(p) < 80:
                    continue
                if score > best_score:
                    best_score, best_snip = score, p.strip()
            sources.append(f"{d.get('title') or '(sans titre)'} — {d['url']}")

        if not best_snip and docs:
            best_snip = (docs[0].get("text") or "").strip()[:700]
        if best_snip and len(best_snip) > 700:
            best_snip = best_snip[:700] + "…"
        return best_snip, sources[:5]

    def answer(self, query: str) -> Tuple[Optional[str], List[str]]:
        query2 = self._refine_query(query)
        links = self.search(query2)
        docs = []
        if links:
            for it in links:
                rec = self.fetch(it["url"])
                if rec and rec.get("text"):
                    docs.append(rec)
            if docs:
                return self._rank_snippet(query2, docs)

        fallbacks = self._python_fallback_candidates(query)
        attempted_fb = []
        if fallbacks:
            fb_docs = []
            for (title, url) in fallbacks:
                attempted_fb.append(f"{title} — {url}")
                rec = self.fetch(url)
                if rec and rec.get("text"):
                    rec["title"] = title
                    fb_docs.append(rec)
            if fb_docs:
                return self._rank_snippet(query, fb_docs)
            else:
                return None, [f"(fallback) extraction impossible — {x}" for x in attempted_fb]

        if not links:
            msg = self._last_error or "Aucun lien pertinent"
            return None, [f"(web) {msg}"]
        else:
            return None, [f"{x['url']} — (extraction impossible)" for x in links]
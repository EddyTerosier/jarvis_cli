# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional, Tuple, List
import re

class Translator:
    """
    Traducteur offline avec priorité à Argos Translate.
    - backend: 'auto' (Argos si dispo), 'argos', 'none'
    - lang: langue cible par défaut ('fr'|'en')
    """
    def __init__(self, style_cfg: dict | None):
        sty = style_cfg or {}
        self.backend = (sty.get("translator") or "auto").lower()
        self.lang = (sty.get("lang") or "fr").lower()
        self._argos_ok = None
        self._last_error = None

    def update(self, style_cfg: dict | None):
        sty = style_cfg or {}
        self.backend = (sty.get("translator") or self.backend).lower()
        self.lang = (sty.get("lang") or self.lang).lower()

    def last_error(self) -> Optional[str]:
        return self._last_error

    def needs_translation(self, text: str, target_lang: str) -> bool:
        src = self._heuristic_detect(text)
        if target_lang not in {"fr","en"}:
            return False
        if src == "unknown":
            if self._looks_french(text):
                src = "fr"
            else:
                src = "en"
        return src != target_lang and src in {"fr","en"}

    def translate(self, text: str, target_lang: str | None = None) -> str:
        self._last_error = None
        tgt = (target_lang or self.lang or "fr").lower()
        if not text or tgt not in {"fr","en"}:
            return text
        if not self.needs_translation(text, tgt):
            return text

        backend = self.backend
        if backend == "auto":
            if self._ensure_argos():
                backend = "argos"
            else:
                backend = "none"

        if backend == "argos":
            out = self._argos_translate(text, tgt)
            if out is not None:
                return out

        if self._last_error is None:
            self._last_error = "no_backend"
        return text

    def _ensure_argos(self) -> bool:
        if self._argos_ok is not None:
            return self._argos_ok
        try:
            import argostranslate.translate as argtr
            langs = argtr.get_installed_languages()
            have_en = any(l.code.startswith("en") for l in langs)
            have_fr = any(l.code.startswith("fr") for l in langs)
            self._argos_ok = bool(have_en and have_fr)
        except Exception as e:
            self._last_error = f"argos_import_error: {e}"
            self._argos_ok = False
        return self._argos_ok

    def argos_status(self) -> List[str]:
        try:
            import argostranslate.translate as argtr
            langs = argtr.get_installed_languages()
            names = [f"{l.code} ({l.name})" for l in langs]
            return names
        except Exception as e:
            self._last_error = f"argos_status_error: {e}"
            return []

    def argos_install_pair(self, src: str, tgt: str) -> Tuple[bool, str]:
        try:
            import argostranslate.package as argpkg
            import argostranslate.translate as argtr
            argpkg.update_package_index()
            pkgs = argpkg.get_available_packages()
            cand = [p for p in pkgs if p.from_code.startswith(src) and p.to_code.startswith(tgt)]
            if not cand:
                return False, f"Aucun package {src}->{tgt} disponible."
            cand.sort(key=lambda p: (p.package_version or "0"), reverse=True)
            argpkg.install_from_path(cand[0].download())
            self._argos_ok = None
            ok = self._ensure_argos()
            return (ok, "Install OK" if ok else "Install KO")
        except Exception as e:
            self._last_error = f"argos_install_error: {e}"
            return False, str(e)

    def _argos_translate(self, text: str, tgt: str) -> Optional[str]:
        try:
            import argostranslate.translate as argtr
            langs = argtr.get_installed_languages()
            src_code = "fr" if self._looks_french(text) else "en"
            src_lang = next((l for l in langs if l.code.startswith(src_code)), None)
            tgt_lang = next((l for l in langs if l.code.startswith(tgt)), None)
            if not src_lang or not tgt_lang:
                self._last_error = f"argos_lang_missing: {src_code}->{tgt}"
                return None
            tr = src_lang.get_translation(tgt_lang)
            out = tr.translate(text)
            return out
        except Exception as e:
            self._last_error = f"argos_translate_error: {e}"
            return None

    def _heuristic_detect(self, text: str) -> str:
        if not text:
            return "unknown"
        if self._looks_french(text):
            return "fr"
        if re.search(r"\b(the|and|of|to|in|is|with|for|on|as|by|from)\b", text, re.I):
            return "en"
        return "unknown"

    def _looks_french(self, text: str) -> bool:
        if re.search(r"[àâäçéèêëîïôöùûüÿœ]", text):
            return True
        if re.search(r"\b(le|la|les|des|du|un|une|et|ou|dans|sur|pour|par|avec|sans|est|sont|que|qui)\b", text, re.I):
            return True
        return False
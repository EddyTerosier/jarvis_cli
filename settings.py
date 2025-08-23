# -*- coding: utf-8 -*-
from typing import Tuple
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table
import yaml

class AppSettings:
    def __init__(self, path: str, cfg: dict):
        self.path = path
        self.cfg = cfg

    def ui(self): return self.cfg.get("ui") or {}
    def style(self): return self.cfg.get("style") or {}
    def policy(self): return self.cfg.get("policy") or {}
    def thresholds(self): return self.cfg.get("thresholds") or {}
    def rag(self): return self.cfg.get("rag") or {}
    def web(self): return self.cfg.get("web") or {}
    def commands(self): return self.cfg.get("commands") or {}

    def set_ui(self, key, value):
        self.cfg.setdefault("ui", {}); self.cfg["ui"][key] = value
    def set_style(self, key, value):
        self.cfg.setdefault("style", {}); self.cfg["style"][key] = value
    def set_policy(self, key, value):
        self.cfg.setdefault("policy", {}); self.cfg["policy"][key] = value
    def set_threshold(self, key, value):
        self.cfg.setdefault("thresholds", {}); self.cfg["thresholds"][key] = value
    def set_rag(self, key, value):
        self.cfg.setdefault("rag", {}); self.cfg["rag"][key] = value
    def set_web(self, key, value):
        self.cfg.setdefault("web", {}); self.cfg["web"][key] = value

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.cfg, f, sort_keys=False, allow_unicode=True)

def render_settings(console, s: AppSettings):
    ui, sty, pol, thr, rag, web = s.ui(), s.style(), s.policy(), s.thresholds(), s.rag(), s.web()
    t = Table(title="Réglages actuels", expand=True, show_edge=False, show_header=False)
    rows = [
        ("Nom", ui.get("name","JARVIS")),
        ("Accent", ui.get("accent","cyan")),
        ("Langue sortie Web", sty.get("lang","fr")),
        ("Sources", "on" if ui.get("show_sources", True) else "off"),
        ("Sources (ask)", "on" if ui.get("ask_show_sources", False) else "off"),
        ("Max sources", ui.get("max_sources", 2)),
        ("Confiance", ui.get("show_confidence","bar")),
        ("Résumé", "on" if ui.get("summary", False) else "off"),
        ("Ton", sty.get("tone","neutre")),
        ("ε (exploration)", pol.get("epsilon",0.0)),
        ("Seuil NLU", thr.get("intent_confidence_min",0.55)),
        ("RAG max snippet", rag.get("max_snippet_chars",700)),
        ("Web: enabled", "on" if web.get("enabled", False) else "off"),
        ("Web: max_results", web.get("max_results", 3)),
        ("Web: whitelist", ", ".join(web.get("whitelist", [])) or "(vide)"),
        ("Web: blacklist", ", ".join(web.get("blacklist", [])) or "(vide)"),
    ]
    for k,v in rows:
        t.add_row(f"[dim]{k}[/dim]", f"[bold]{v}[/bold]")
    console.print(Panel(t, border_style=ui.get("accent","cyan")))

def handle_command(user: str, settings: AppSettings, console) -> Tuple[bool, str]:
    if not user.startswith("/"):
        return False, ""
    parts = user.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    def one_arg(default=None):
        return args[0] if args else default

    if cmd in {"/help", "/h"}:
        console.print(Panel(
            "\n".join([
                "Commandes :",
                "/settings                     → menu interactif",
                "/show                         → afficher les réglages",
                "/lang <fr|en>                 → langue cible pour les extraits Web",
                "/tone <taquin|neutre>",
                "/theme <cyan|green|magenta|yellow|blue|red>",
                "/sources <on|off|ask>",
                "/maxsources <int>",
                "/conf <bar|number|hidden>",
                "/summary <on|off>",
                "/epsilon <0..1>",
                "/threshold <0..1>",
                "/snippet <int>",
                "/web <on|off>                → activer la recherche Web",
                "/webres <1..10>              → nb de résultats Web",
                "/wl <add|rm|list> [domaine]  → whitelist domaines",
                "/bl <add|rm|list> [domaine]  → blacklist domaines",
                "/cache clear                  → vider le cache Web",
                "/reindex                      → reconstruit l’index RAG",
                "/save                         → écrire config.yaml",
            ]), title="Aide", border_style=settings.ui().get("accent","cyan")))
        return True, ""

    if cmd == "/show":
        render_settings(console, settings); return True, ""

    if cmd == "/lang":
        val = (one_arg("fr") or "fr").lower()
        if val in {"fr","en"}:
            settings.set_style("lang", val); console.print(f"Langue sortie Web -> {val}")
        else:
            console.print("Choix: fr | en")
        return True, ""

    if cmd == "/tone":
        val = (one_arg() or "").lower()
        if val in {"taquin","neutre"}: settings.set_style("tone", val); console.print(f"Ton -> {val}")
        else: console.print("Choix: taquin | neutre")
        return True, ""

    if cmd == "/theme":
        val = (one_arg() or "").lower()
        if val in {"cyan","green","magenta","yellow","blue","red"}:
            settings.set_ui("accent", val); console.print(f"Accent -> {val}")
        else:
            console.print("Choix: cyan|green|magenta|yellow|blue|red")
        return True, ""

    if cmd == "/sources":
        val = (one_arg() or "").lower()
        if val == "on": settings.set_ui("show_sources", True); settings.set_ui("ask_show_sources", False)
        elif val == "off": settings.set_ui("show_sources", False); settings.set_ui("ask_show_sources", False)
        elif val == "ask": settings.set_ui("ask_show_sources", True); settings.set_ui("show_sources", False)
        else: console.print("Choix: on | off | ask"); return True, ""
        console.print(f"Sources -> {val}"); return True, ""

    if cmd == "/maxsources":
        try:
            settings.set_ui("max_sources", max(1, min(10, int(one_arg("2")))))
            console.print(f"Max sources -> {settings.ui().get('max_sources')}")
        except ValueError:
            console.print("Utilisation: /maxsources <int 1..10>")
        return True, ""

    if cmd == "/conf":
        val = (one_arg() or "").lower()
        if val in {"bar","number","hidden"}:
            settings.set_ui("show_confidence", val); console.print(f"Confiance -> {val}")
        else:
            console.print("Choix: bar | number | hidden")
        return True, ""

    if cmd == "/summary":
        val = (one_arg("off") or "off").lower()
        if val in {"on","off"}:
            settings.set_ui("summary", val == "on"); console.print(f"Résumé -> {val}")
        else:
            console.print("Choix: on | off")
        return True, ""

    if cmd == "/epsilon":
        try:
            settings.set_policy("epsilon", max(0.0, min(1.0, float(one_arg("0")))))
            console.print(f"ε -> {settings.policy().get('epsilon')}")
        except ValueError:
            console.print("Utilisation: /epsilon 0.0..1.0")
        return True, ""

    if cmd == "/threshold":
        try:
            settings.set_threshold("intent_confidence_min", max(0.0, min(1.0, float(one_arg("0.55")))))
            console.print(f"Seuil NLU -> {settings.thresholds().get('intent_confidence_min')}")
        except ValueError:
            console.print("Utilisation: /threshold 0.0..1.0")
        return True, ""

    if cmd == "/snippet":
        try:
            settings.set_rag("max_snippet_chars", max(50, min(4000, int(one_arg("700")))))
            console.print(f"RAG max snippet -> {settings.rag().get('max_snippet_chars')}")
        except ValueError:
            console.print("Utilisation: /snippet <entier>")
        return True, ""

    if cmd == "/reindex":
        console.print("Reconstruction de l’index RAG demandée…"); return True, "reindex"

    if cmd == "/web":
        val = (one_arg("off") or "off").lower()
        if val in {"on","off"}:
            settings.set_web("enabled", val == "on"); console.print(f"Web -> {val}")
        else:
            console.print("Choix: on | off")
        return True, ""

    if cmd == "/webres":
        try:
            settings.set_web("max_results", max(1, min(10, int(one_arg("3")))))
            console.print(f"Web max_results -> {settings.web().get('max_results')}")
        except ValueError:
            console.print("Utilisation: /webres <1..10>")
        return True, ""

    if cmd == "/wl":
        sub = (one_arg("list") or "list").lower()
        lst = settings.web().get("whitelist") or []
        if sub == "list":
            console.print("Whitelist: " + (", ".join(lst) or "(vide)"))
            return True, ""
        if len(args) < 2:
            console.print("Usage: /wl <add|rm|list> <domaine>")
            return True, ""
        dom = args[1].lower()
        if sub == "add":
            if dom not in lst: lst.append(dom); settings.set_web("whitelist", lst)
            console.print(f"Ajouté à whitelist: {dom}")
        elif sub == "rm":
            lst = [x for x in lst if x != dom]; settings.set_web("whitelist", lst)
            console.print(f"Retiré de whitelist: {dom}")
        return True, ""

    if cmd == "/bl":
        sub = (one_arg("list") or "list").lower()
        lst = settings.web().get("blacklist") or []
        if sub == "list":
            console.print("Blacklist: " + (", ".join(lst) or "(vide)"))
            return True, ""
        if len(args) < 2:
            console.print("Usage: /bl <add|rm|list> <domaine>")
            return True, ""
        dom = args[1].lower()
        if sub == "add":
            if dom not in lst: lst.append(dom); settings.set_web("blacklist", lst)
            console.print(f"Ajouté à blacklist: {dom}")
        elif sub == "rm":
            lst = [x for x in lst if x != dom]; settings.set_web("blacklist", lst)
            console.print(f"Retiré de blacklist: {dom}")
        return True, ""

    if cmd == "/cache":
        sub = (one_arg("show") or "show").lower()
        if sub == "clear":
            console.print("Cache Web: purge demandée.")
            return True, "clear_web_cache"
        console.print("Usage: /cache clear")
        return True, ""

    if cmd == "/save":
        settings.save(); console.print("Config sauvegardée → config.yaml"); return True, ""

    if cmd == "/settings":
        while True:
            render_settings(console, settings)
            choice = Prompt.ask(
                "Modifier [1]Nom [2]Ton [3]Accent [4]Langue [5]Sources [6]Confiance [7]ε [8]Seuil NLU [9]Snippet [M]ax sources [S]Sauver [0]Quitter",
                choices=list("0123456789mMsS"), default="0"
            )
            if choice == "0":
                break
            elif choice == "1":
                name = Prompt.ask("Nom", default=settings.ui().get("name","JARVIS"))
                settings.set_ui("name", name)
            elif choice == "2":
                tone = Prompt.ask("Ton", choices=["taquin","neutre"], default=settings.style().get("tone","taquin"))
                settings.set_style("tone", tone)
            elif choice == "3":
                accent = Prompt.ask("Accent", choices=["cyan","green","magenta","yellow","blue","red"], default=settings.ui().get("accent","cyan"))
                settings.set_ui("accent", accent)
            elif choice == "4":
                lang = Prompt.ask("Langue sortie Web", choices=["fr","en"], default=settings.style().get("lang","fr"))
                settings.set_style("lang", lang)
            elif choice == "5":
                mode = Prompt.ask("Sources", choices=["on","off","ask"], default="on" if settings.ui().get("show_sources", True) else "off")
                if mode == "on":
                    settings.set_ui("show_sources", True); settings.set_ui("ask_show_sources", False)
                elif mode == "off":
                    settings.set_ui("show_sources", False); settings.set_ui("ask_show_sources", False)
                else:
                    settings.set_ui("ask_show_sources", True); settings.set_ui("show_sources", False)
            elif choice == "6":
                c = Prompt.ask("Confiance", choices=["bar","number","hidden"], default=settings.ui().get("show_confidence","bar"))
                settings.set_ui("show_confidence", c)
            elif choice == "7":
                e = float(Prompt.ask("ε (0..1)", default=str(settings.policy().get("epsilon",0.0))))
                settings.set_policy("epsilon", max(0.0, min(1.0, e)))
            elif choice == "8":
                t = float(Prompt.ask("Seuil NLU (0..1)", default=str(settings.thresholds().get("intent_confidence_min",0.55))))
                settings.set_threshold("intent_confidence_min", max(0.0, min(1.0, t)))
            elif choice == "9":
                n = int(Prompt.ask("RAG max snippet (50..4000)", default=str(settings.rag().get("max_snippet_chars",700))))
                settings.set_rag("max_snippet_chars", max(50, min(4000, n)))
            elif choice in {"m","M"}:
                m = int(Prompt.ask("Max sources (1..10)", default=str(settings.ui().get("max_sources",2))))
                settings.set_ui("max_sources", max(1, min(10, m)))
            elif choice in {"s","S"}:
                settings.save(); console.print("Config sauvegardée → config.yaml")
        return True, ""

    console.print("Commande inconnue. Tape /help")
    return True, ""
# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
import json
import yaml
import csv
import re

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from memory import TraceStore
from nlu import OnlineNLU
from rag import LocalRAG
from policy import Policy
from settings import AppSettings, handle_command
from web import WebClient
from translator import Translator  # Traducteur Argos

console = Console()

INTENT_THEME = {
    "qa": ("❓", "cyan"),
    "smalltalk": ("💬", "green"),
    "web_search": ("🌐", "yellow"),
    "run_command": ("⚙️", "red"),
    "unknown": ("⁉️", "magenta"),
}

def load_config(path: str = "config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def header(name: str, accent: str):
    title = Text(f" {name} CLI ", style=f"bold {accent}")
    subtitle = Text(" Tape 'exit' pour quitter. ", style="dim")
    console.clear()
    console.print(Panel.fit(Text.assemble(title, "\n", subtitle), border_style=accent))

def say(msg: str, tone: str) -> str:
    return f"{msg} 😉" if tone == "taquin" else msg

def conf_bar(p: float) -> str:
    p = max(0.0, min(1.0, p))
    filled = int(p * 10)
    bar = "#" * filled + "-" * (10 - filled)
    return f"[{bar}] {p:.2f}"

def render_meta(intent: str, conf: float, action: str, ui_conf: dict):
    emo, color = INTENT_THEME.get(intent, ("⁉️", "magenta"))
    accent = ui_conf.get("accent", "cyan")
    show_conf = (ui_conf.get("show_confidence") or "bar").lower()

    t = Table.grid(expand=True)
    left = Text.assemble(
        (f"{emo} intent: ", "dim"),
        (intent, f"bold {color}"),
        ("   "), ("⚙️ action: ", "dim"),
        (action, f"bold {accent}"),
    )
    if show_conf == "bar":
        right = Text(conf_bar(conf))
    elif show_conf == "number":
        right = Text(f"{conf:.2f}", style="bold")
    else:
        right = Text("")
    t.add_row(left, right)
    console.print(Panel(t, border_style=accent))

def maybe_show_sources(evidence, ui_conf: dict, title: str = "Sources locales"):
    if not evidence:
        return
    ask = ui_conf.get("ask_show_sources", False)
    show = ui_conf.get("show_sources", True)
    max_src = int(ui_conf.get("max_sources", 2))
    if ask:
        show = Confirm.ask("Voir les sources ?", default=True)
    if show:
        trimmed = evidence[:max_src]
        if len(evidence) > max_src:
            trimmed.append(f"(+{len(evidence)-max_src} autres)")
        console.print(Panel("\n\n".join(trimmed), title=title, border_style="dim"))

def summarize(text: str, max_sentences: int = 2) -> str:
    parts = [p.strip() for p in text.replace("\n", " ").split(".") if p.strip()]
    if not parts:
        return text
    return (". ".join(parts[:max_sentences]) + ".").strip()

# -------- Synthèse guidée pour comparaisons courantes --------
def synth_compare_if_applicable(user_q: str, fallback_text: str) -> str:
    q = (user_q or "").lower()
    if "dataclass" in q and "namedtuple" in q:
        return (
            "• **dataclass** : classe complète (attributs + méthodes), mutable par défaut ; "
            "options `frozen`, `order`, `__post_init__`, héritage, annotations de type/valeurs par défaut.\n"
            "• **namedtuple** : tuple **immuable** avec noms de champs, ultra-léger, API minimale ; "
            "reste un tuple (indexation/unpack), idéal pour enregistrements simples et hashables.\n\n"
            "**À retenir :** objet métier avec logique → `dataclass` ; conteneur immuable et minimal → `namedtuple`."
        )
    return fallback_text

def main():
    cfg = load_config()
    settings = AppSettings("config.yaml", cfg)
    store = TraceStore("traces.jsonl")

    # UI et modules
    ui = settings.ui()
    tone = settings.style().get("tone", "neutre")
    accent = ui.get("accent", "cyan")
    name = ui.get("name", "JARVIS")

    nlu = OnlineNLU(intents=cfg["intents"], conf_min=cfg["thresholds"]["intent_confidence_min"])
    rag = LocalRAG(docs_path=cfg["rag"]["docs_path"], max_chars=cfg["rag"]["max_snippet_chars"])
    policy = Policy(cfg["policy"], commands_cfg=cfg.get("commands", {}))
    web_client = WebClient(cfg.get("web", {}))
    translator = Translator(settings.style())

    def apply_runtime_changes():
        nonlocal ui, tone, accent, name
        ui = settings.ui()
        old_name, old_accent = name, accent
        tone  = settings.style().get("tone", tone)
        accent = ui.get("accent", accent)
        name   = ui.get("name", name)
        policy.epsilon = settings.policy().get("epsilon", policy.epsilon)
        policy.alpha   = settings.policy().get("alpha", policy.alpha)
        policy.gamma   = settings.policy().get("gamma", policy.gamma)
        nlu.conf_min   = settings.thresholds().get("intent_confidence_min", nlu.conf_min)
        rag.max_chars  = settings.rag().get("max_snippet_chars", rag.max_chars)
        web_client.update_config(settings.web())
        translator.update(settings.style())
        if (name != old_name) or (accent != old_accent):
            header(name, accent)

    header(name, accent)

    console.print("Indexation RAG…", style="dim")
    rag.build_index()
    if rag.bm25 is None:
        console.print(Panel(say("Votre base locale est vide. Ajoutez des fichiers dans ./docs pour que je puisse fouiller vos notes.", tone),
                            title="RAG", border_style="yellow"))
    console.print("Prêt.")

    # Bootstrap (si présent)
    boot_path = Path("bootstrap.jsonl")
    if boot_path.exists():
        n = 0
        for line in boot_path.read_text(encoding="utf-8").splitlines():
            try:
                ex = json.loads(line)
                if ex.get("text") and ex.get("label"):
                    nlu.add_intent(ex["label"])
                    nlu.update(ex["text"], ex["label"])
                    n += 1
            except Exception:
                pass
        if n:
            console.print(f"[dim]Exemples de démarrage chargés: {n}[/dim]")

    while True:
        user = Prompt.ask("[bold green]Vous[/bold green]").strip()
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue

        # --- commandes traducteur ---
        if user.startswith("/translator"):
            parts = user.split()
            val = parts[1].lower() if len(parts) > 1 else "auto"
            if val in {"auto","argos","none"}:
                settings.set_style("translator", val); apply_runtime_changes()
                console.print(f"Traducteur -> {val}")
            else:
                console.print("Usage: /translator <auto|argos|none>")
            continue

        if user.startswith("/tx"):
            parts = user.split()
            sub = parts[1].lower() if len(parts) > 1 else "status"
            if sub == "status":
                st = translator.argos_status()
                if not st:
                    err = translator.last_error() or "(non initialisé)"
                    console.print(Panel(f"Aucun modèle Argos installé. {err}", border_style="yellow"))
                else:
                    console.print(Panel("Argos installés: " + ", ".join(st), border_style="green"))
            elif sub == "install":
                src = parts[2] if len(parts) > 2 else "en"
                tgt = parts[3] if len(parts) > 3 else "fr"
                ok, msg = translator.argos_install_pair(src, tgt)
                color = "green" if ok else "red"
                console.print(Panel(f"{msg} ({src}->{tgt})", border_style=color))
            else:
                console.print("Usage: /tx status | /tx install <src> <tgt>")
            continue

        # --- autres commandes ---
        if user.startswith("/"):
            parts = user.split()
            cmd = parts[0].lower()
            handled, action = handle_command(user, settings, console)
            if handled:
                if action == "reindex":
                    rag.build_index()
                    console.print("Index RAG reconstruit.")
                if action == "clear_web_cache":
                    web_client.clear_cache()
                    console.print("Cache Web vidé.")
                apply_runtime_changes()
                if cmd == "/settings":
                    console.print(Panel(
                        "Réglages appliqués (runtime). Utilisez `/save` pour les persister dans config.yaml.",
                        border_style=ui.get("accent", "cyan")
                    ))
                continue

        ts = datetime.now().strftime("%H:%M:%S")
        web_error = None

        # 1) NLU
        pred_intent, conf, proba = nlu.predict(user)

        # 2) Politique
        action = policy.choose_action(pred_intent, confidence=conf)

        # 3) Meta
        render_meta(pred_intent, conf, action, ui)

        # 4) Labellisation si incertain
        labeled = False
        if conf < nlu.conf_min or pred_intent == "unknown":
            console.print("Confiance faible. Voulez-vous labelliser cette intention ?", style="dim")
            if Confirm.ask("Fournir un label maintenant ?", default=True):
                choices = list(dict.fromkeys(settings.cfg.get("intents", []) + ["__nouveau__"]))
                default_choice = pred_intent if pred_intent in choices else (choices[0] if choices else "qa")
                label = Prompt.ask("Label", choices=choices, default=default_choice)
                if label == "__nouveau__":
                    label = Prompt.ask("Nom du nouvel intent (ex: faq_rl)")
                    settings.cfg.setdefault("intents", [])
                    if label not in settings.cfg["intents"]:
                        settings.cfg["intents"].append(label)
                nlu.add_intent(label)
                nlu.update(user, label)
                pred_intent = label
                labeled = True
                console.print(f"[green]Appris[/green] pour intent: [bold]{label}[/bold]")

                action = policy.choose_action(
                    pred_intent,
                    confidence=max(conf, settings.thresholds().get("intent_confidence_min", 0.55))
                )
                console.print(Panel(f"Action recalculée → [bold]{action}[/bold]", border_style=ui.get("accent", "cyan")))

        # 5) Action
        if action == "answer_from_rag":
            answer, evidence = rag.answer(user)
            if not answer:
                if settings.web().get("enabled", False):
                    snip, web_sources = web_client.answer(user)
                    if snip:
                        maybe_show_sources(web_sources, ui, title="Sources web")
                        final = snip
                        if ui.get("summary", False):
                            final = summarize(final)
                        final = synth_compare_if_applicable(user, final)
                        final = translator.translate(final, target_lang=settings.style().get("lang","fr"))
                        console.print(Panel(say(final, tone), title="Réponse (Web)", border_style=ui.get("accent", "cyan")))
                    else:
                        if web_sources:
                            console.print(Panel("\n".join(web_sources), title="Web — détails", border_style="dim"))
                            if any("Rate limit" in s for s in web_sources):
                                web_error = "ratelimit"
                        followup = say("Je n’ai rien en local ni sur le Web. Précisez ou ajoutez des notes dans ./docs.", tone)
                        console.print(Panel(followup, title="Clarification", border_style="magenta"))
                else:
                    followup = say("Je n’ai rien en local pour ça. Activez le Web avec `/web on` ou ajoutez des fichiers dans ./docs.", tone)
                    console.print(Panel(followup, title="Clarification", border_style="magenta"))
            else:
                maybe_show_sources(evidence, ui, title="Sources locales")
                final = summarize(answer) if ui.get("summary", False) else answer
                console.print(Panel(say(final, tone), title="Réponse (RAG)", border_style=ui.get("accent", "cyan")))

        elif action == "ask_clarification":
            followup = say("Pouvez-vous préciser votre demande ? Par exemple, quel fichier ou quel contexte ?", tone)
            console.print(Panel(followup, title="Clarification", border_style="magenta"))

        elif action == "web_search":
            if not settings.web().get("enabled", False):
                console.print(Panel(say("Recherche Web désactivée (/web on pour activer).", tone), title="Web", border_style="yellow"))
            else:
                snip, web_sources = web_client.answer(user)
                if not snip:
                    wl = settings.web().get("whitelist") or []
                    hint = f" (whitelist active: {', '.join(wl)})" if wl else ""
                    if web_sources:
                        console.print(Panel("\n".join(web_sources), title=f"Web — détails{hint}", border_style="dim"))
                        if any("Rate limit" in s for s in web_sources):
                            web_error = "ratelimit"
                    console.print(Panel(say(f"Aucun résultat Web pertinent.{hint}", tone), title="Web", border_style="yellow"))
                else:
                    maybe_show_sources(web_sources, ui, title="Sources web")
                    final = snip
                    if ui.get("summary", False):
                        final = summarize(final)
                    final = synth_compare_if_applicable(user, final)
                    final = translator.translate(final, target_lang=settings.style().get("lang","fr"))
                    console.print(Panel(say(final, tone), title="Réponse (Web)", border_style=ui.get("accent", "cyan")))

        elif action == "run_command":
            from tools import run_command
            out = run_command(user, policy.commands_cfg)
            console.print(Panel(out, title="Commande", border_style="red"))

        else:
            console.print(Panel(say("Je ne sais pas encore quoi faire avec cette intention.", tone), title="Par défaut", border_style="grey37"))

        # 6) Feedback
        if web_error == "ratelimit":
            console.print(Panel("Pas de pénalité : limite de requêtes côté moteur Web.", border_style="yellow"))
            reward = 0.0
        else:
            good = Confirm.ask("La réponse/action est-elle utile ?", default=True)
            reward = 1.0 if good else -1.0
        policy.update(pred_intent, action, reward)

        # 7) Apprentissage optionnel
        if not labeled and Confirm.ask("Enregistrer cet échange pour l’apprentissage ?", default=False):
            nlu.update(user, pred_intent)

        # 8) Trace
        store.append({
            "ts": ts,
            "user": user,
            "intent": pred_intent,
            "confidence": conf,
            "action": action,
            "reward": reward
        })

    console.print("À bientôt !")


if __name__ == "__main__":
    main()
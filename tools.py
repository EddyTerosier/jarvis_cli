# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict

def run_command(user_text: str, cfg: Dict) -> str:
    if not cfg.get("enabled", False):
        return "Exécution de commandes désactivée (config.commands.enabled=false)."
    allowed = cfg.get("allowed") or []
    # Ici tu pourrais parser user_text et vérifier que la commande est autorisée.
    # Par prudence, on ne lance rien pour l’instant.
    return "Commande non exécutée (sécurité). Configure `commands.allowed` si tu veux autoriser des commandes précises."
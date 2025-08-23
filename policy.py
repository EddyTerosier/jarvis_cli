# -*- coding: utf-8 -*-
from __future__ import annotations
import random
from typing import Dict, Tuple

ACTIONS = ["answer_from_rag", "web_search", "ask_clarification", "run_command"]

class Policy:
    def __init__(self, cfg: Dict, commands_cfg: Dict):
        self.epsilon = float(cfg.get("epsilon", 0.0))
        self.alpha = float(cfg.get("alpha", 0.4))
        self.gamma = float(cfg.get("gamma", 0.9))
        self.q = {}  # (intent, action) -> value
        self.commands_cfg = commands_cfg or {}

    def _greedy(self, intent: str, confidence: float) -> str:
        # règle déterministe de base
        if intent == "qa":
            return "answer_from_rag"
        if intent == "web_search":
            return "web_search"
        if intent == "run_command":
            return "run_command"
        if intent == "smalltalk":
            return "ask_clarification"
        return "answer_from_rag" if confidence >= 0.7 else "ask_clarification"

    def choose_action(self, intent: str, confidence: float) -> str:
        if random.random() < self.epsilon:
            return random.choice(ACTIONS)
        # sinon on regarde Q sinon on retombe sur règle
        vals = {a: self.q.get((intent,a), 0.0) for a in ACTIONS}
        best_a = max(vals, key=vals.get)
        if vals[best_a] > 0.001:
            return best_a
        return self._greedy(intent, confidence)

    def update(self, intent: str, action: str, reward: float):
        key = (intent, action)
        old = self.q.get(key, 0.0)
        target = reward  # pas de next_state ici
        self.q[key] = old + self.alpha * (target - old)
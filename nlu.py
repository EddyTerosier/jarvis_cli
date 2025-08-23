# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Tuple, Dict, List
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.utils import shuffle
from sklearn.preprocessing import LabelEncoder
from sklearn.exceptions import NotFittedError
import numpy as np
import joblib
import os
import re

def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text

class OnlineNLU:
    def __init__(self, intents: List[str], conf_min: float = 0.55):
        self.intents = list(dict.fromkeys(intents or []))
        self.conf_min = conf_min

        self.vectorizer = HashingVectorizer(
            n_features=2**18,
            alternate_sign=False,
            lowercase=True,
            ngram_range=(1,2),
            norm='l2'
        )
        self.le = LabelEncoder()
        if self.intents:
            self.le.fit(self.intents)
        self.clf = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=5, tol=None)

        # Bootstrap minimal pour éviter NotFitted
        X0 = self.vectorizer.transform(["hello"])
        y0 = np.array([0])
        self.clf.partial_fit(X0, y0, classes=np.arange(max(1, len(self.intents))) if self.intents else np.array([0]))

    def add_intent(self, label: str):
        if label not in self.intents:
            self.intents.append(label)
            self.le.fit(self.intents)

    def update(self, text: str, label: str):
        self.add_intent(label)
        X = self.vectorizer.transform([_normalize(text)])
        y = self.le.transform([label])
        self.clf.partial_fit(X, y, classes=np.arange(len(self.intents)))

    def predict(self, text: str) -> Tuple[str, float, Dict[str,float]]:
        x = self.vectorizer.transform([_normalize(text)])
        try:
            proba = self.clf.predict_proba(x)[0]
        except NotFittedError:
            proba = np.ones(len(self.intents)) / max(1, len(self.intents))
        if len(self.intents) == 0:
            return "unknown", 0.0, {}
        idx = int(np.argmax(proba))
        label = self.le.inverse_transform([idx])[0] if idx < len(self.intents) else "unknown"
        conf = float(np.max(proba)) if len(proba) else 0.0
        dist = {self.le.inverse_transform([i])[0]: float(proba[i]) for i in range(min(len(proba), len(self.intents)))}
        return label, conf, dist

    def save(self, path: str = "nlu.pkl"):
        obj = {
            "intents": self.intents,
            "clf": self.clf,
            "le": self.le,
            "vectorizer": self.vectorizer
        }
        joblib.dump(obj, path)

    def load(self, path: str = "nlu.pkl") -> bool:
        if not os.path.exists(path):
            return False
        obj = joblib.load(path)
        self.intents = obj["intents"]
        self.clf = obj["clf"]
        self.le = obj["le"]
        self.vectorizer = obj["vectorizer"]
        return True
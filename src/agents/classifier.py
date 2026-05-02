"""Agent 1: IntentClassifier — TF-IDF + Naive Bayes with entity/sentiment/urgency."""
import re, json, os, logging, textwrap
from typing import Dict, Any

logger = logging.getLogger("supportoid.classifier")

class IntentClassifier:
    def __init__(self, settings):
        self.settings = settings
        self.metadata = {"version": 1, "accuracy": 0.0, "training_samples": 0}
        self._metadata_path = os.path.join(settings.model_dir, "classifier_meta.json")
        os.makedirs(settings.model_dir, exist_ok=True)
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.naive_bayes import MultinomialNB
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import cross_val_score
        from importlib import import_module
        np = import_module("numpy")
        self.TV = TfidfVectorizer; self.MNB = MultinomialNB; self.Pipe = Pipeline; self.cvs = cross_val_score; self.np = np
        self._train_default()
        if os.path.exists(self._metadata_path):
            with open(self._metadata_path) as f:
                self.metadata = json.load(f)

    def _train_default(self):
        from src.ml.training_data import get_vigorous_training_data
        X, y = get_vigorous_training_data()
        self.pipeline = self.Pipe([("tfidf", self.TV(max_features=15000, ngram_range=(1,2), sublinear_tf=True, min_df=1)),("clf", self.MNB(alpha=0.05))])
        self.pipeline.fit(X, y)
        scores = self.cvs(self.pipeline, X, y, cv=min(5, len(set(y))))
        self.metadata = {"version": 1, "accuracy": float(self.np.mean(scores)), "training_samples": len(X)}
        with open(self._metadata_path, "w") as f:
            json.dump(self.metadata, f)

    def classify(self, message: str) -> Dict[str, Any]:
        msg = (message or "").strip()
        if not msg:
            return {"intent": "general_question", "confidence": 0.3, "entities": {}, "sentiment": 0.0, "urgency": 0.0, "language": "en"}
        intent = self.pipeline.predict([msg])[0]
        probas = self.pipeline.predict_proba([msg])[0]
        conf = float(max(probas))
        return {"intent": intent, "confidence": round(conf, 4),
                "all_intents": dict(zip(self.pipeline.classes_, probas.tolist())),
                "entities": self._extract(msg), "sentiment": self._sent(msg),
                "urgency": self._urg(msg), "language": self._lang(msg)}

    @staticmethod
    def _extract(text):
        e = {}; lo = text.lower()
        for p in ["free","pro","enterprise","premium","starter","basic","team"]:
            if re.search(r'\b' + p + r'\b', lo):
                e["plan"] = p; break
        if m := re.findall(r'(?:[\$€£]\s*|dollars?\b)(\d[\d,.]*)', text):
            e["amount"] = m[0]
        elif m := re.findall(r'\b(\d[\d,.]*)\s*(?:dollars?|bucks?|euros?)', lo):
            e["amount"] = m[0]
        if m := re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text):
            e["email"] = m[0]
        if m := re.findall(r'(?:error|code)\s*#?\s*(\d{3})', lo):
            e["error_code"] = m[0]
        return e

    @staticmethod
    def _sent(text):
        """Sentiment: -1.0 (very negative) to 1.0 (very positive)."""
        lo = text.lower()
        pos = {"great","awesome","love","perfect","excellent","amazing","helpful","thank","thanks","happy","glad","wonderful","fantastic","good","nice","greatly","well","appreciate","beautiful","brilliant","cool","works","working","fixed","resolved","helped"}
        neg = {"terrible","awful","worst","hate","broken","useless","frustrating","disappointed","unacceptable","ridiculous","horrible","horrendous","garbage","trash","stupid","dumb","sucks","bad","awful","wrong","fail","failed","failing","error","bug","issue","issue","crash","crashed","crashing","down","cannot","can't","cant","dont","don't","never","nothing","worse","lost","waste","scam","fraud","deceptive","misleading","angry","furious","outraged","annoyed","irritated","infuriated","messed","screwed","ruined","useless","pathetic","dreadful","abysmal","appalling","atrocious","hell","damn","screw","crap","shit","fuck","bullshit","bullcrap","overcharged","overcharge","unfair","robbed","ripped","cheated","abusive","disregarded","ignored","abandoned","useless","horrible"}
        # Caps / punctuation boost
        caps_boost = 0.15 if text.isupper() and len(text) > 10 else 0
        punct_boost = 0.1 if text.endswith("!!!") or text.endswith("???") else 0
        
        words = set(re.findall(r'\b\w+\b', lo))
        p = sum(1 for w in words if w in pos)
        n = sum(1 for w in words if w in neg)
        p += caps_boost + punct_boost
        # Negation detection
        for pw in pos:
            idx = lo.find(pw)
            if idx > 0 and any(lo[max(0,idx-8):idx].endswith(w) for w in ["not ","never ","no ","won't ","can't ","don't ","isn't ","aren't ","wasn't "]):
                n += 1; p = max(0, p-1)
        return max(-1.0, min(1.0, (p - n) / max(p + n, 1)))

    @staticmethod
    def _urg(text):
        """Urgency: 0.0 (calm) to 1.0 (emergency)."""
        lo = text.lower()
        score = 0
        urgency_words = ["urgent","emergency","asap","immediately","critical","down","outage","crisis","canceling","cancellation","right now", "legal","lawyer","ftc","refund","breach","now","sue","lawsuit","complaint","dispute"]
        for w in urgency_words:
            if w in lo: score += 0.1
        # Exclamation marks
        score += text.count('!') * 0.05
        # ALL CAPS
        if text.isupper() and len(text) > 10: score += 0.2
        # Financial / production impact
        for p in ["losing $", "$/hour", "$/minute", "been charged", "charged twice", "still charged", "not responding", "production down", "customers affected", "48 hours", "dealbreaker", "renewal", "can't afford", "losing money"]:
            if p in lo: score += 0.3
        return min(1.0, score)

    @staticmethod
    def _lang(text):
        if any(ord(c) > 600 for c in text): return "mixed"
        if any(w in text.lower() for w in ["hola","por favor","ayuda","necesito","mi cuenta","mi plan"]): return "es"
        if any(w in text.lower() for w in ["bonjour","aide","merci","mon compte"]): return "fr"
        return "en"

    def get_stats(self) -> dict:
        return self.metadata

    def retrain(self, feedback_data: list) -> dict:
        if not feedback_data:
            return {"status": "skipped", "reason": "No feedback"}
        from src.ml.training_data import get_vigorous_training_data
        X, y = get_vigorous_training_data()
        for item in feedback_data:
            if item.get("message") and item.get("correct_intent"):
                X.append(item["message"]); y.append(item["correct_intent"])
        if len(set(y)) < 3:
            return {"status": "skipped", "reason": "Insufficient intent variety"}
        new_pipe = self.Pipe([("tfidf", self.TV(max_features=15000, ngram_range=(1,2), sublinear_tf=True, min_df=1)),("clf", self.MNB(alpha=0.05))])
        new_pipe.fit(X, y)
        scores = self.cvs(new_pipe, X, y, cv=min(5, len(set(y))))
        self.pipeline = new_pipe
        self.metadata["version"] += 1
        self.metadata["accuracy"] = float(self.np.mean(scores))
        self.metadata["training_samples"] = len(X)
        with open(self._metadata_path, "w") as f:
            json.dump(self.metadata, f)
        return {"status": "retrained", "version": self.metadata["version"], "accuracy": self.metadata["accuracy"], "samples": self.metadata["training_samples"]}

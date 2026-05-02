"""
Advanced RAG Retrieval Algorithms
==================================
Enhances the base KnowledgeRetriever with:
  • BM25 ranking (Okapi BM25)
  • TF-IDF cosine similarity
  • N-gram overlap scoring
  • Recency decay weighting
  • Intent-context hybrid scoring
  • Entity-aware retrieval boost

All algorithms are pure Python — no vector DB required.
"""

import math
import re
import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger("supportoid.rag")

# ── Text preprocessing ──

_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "that", "this",
    "these", "those", "what", "which", "who", "whom", "i", "me", "my",
    "myself", "we", "our", "ours", "ourselves", "you", "your", "yours",
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her",
    "hers", "herself", "it", "its", "itself", "they", "them", "their",
    "theirs", "themselves", "about", "up", "down", "any", "it's", "don't",
    "doesn't", "didn't", "won't", "wouldn't", "can't", "couldn't",
    "shouldn't", "isn't", "aren't", "wasn't", "weren't", "haven't",
    "hasn't", "hadn't", "didn't", "i'm", "you're", "he's", "she's",
    "we're", "they're", "i've", "you've", "we've", "they've", "i'll",
    "you'll", "he'll", "she'll", "we'll", "they'll", "i'd", "you'd",
    "he'd", "she'd", "we'd", "they'd", "how's", "what's", "who's",
    "where's", "when's", "why's", "let's",
}


def tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]


def compute_idf(documents: list[str]) -> dict[str, float]:
    """Compute inverse document frequency across a corpus."""
    N = len(documents)
    if N == 0:
        return {}
    df = Counter()  # document frequency
    for doc in documents:
        tokens = set(tokenize(doc))
        for t in tokens:
            df[t] += 1
    return {t: math.log((N + 1) / (freq + 1)) + 1 for t, freq in df.items()}


def compute_bm25(query: str, document: str, avg_dl: float, k1: float = 1.5, b: float = 0.75) -> float:
    """Okapi BM25 scoring for a single query-document pair."""
    qt = tokenize(query)
    dt = tokenize(document)
    doc_len = len(dt)
    dt_freq = Counter(dt)
    score = 0.0
    for term in qt:
        freq = dt_freq.get(term, 0)
        # simplified IDF for single doc context
        idf = math.log(1.5 + freq / (1 + freq)) + 0.5
        num = freq * (k1 + 1)
        den = freq + k1 * (1 - b + b * doc_len / max(avg_dl, 1))
        score += idf * (num / den) if den else 0
    return score


def tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """Compute TF-IDF vector for token list."""
    tf = Counter(tokens)
    vec = {}
    for t, freq in tf.items():
        vec[t] = freq * idf.get(t, 0)
    return vec


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    dot = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in set(vec_a) | set(vec_b))
    norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def ngram_overlap(text_a: str, text_b: str, n: int = 2) -> float:
    """Character n-gram overlap ratio (Jaccard-like)."""
    def ngrams(s: str):
        s = s.lower()
        return set(s[i:i+n] for i in range(len(s) - n + 1)) if len(s) >= n else set()
    ng_a = ngrams(text_a)
    ng_b = ngrams(text_b)
    if not ng_a or not ng_b:
        return 0.0
    intersection = ng_a & ng_b
    union = ng_a | ng_b
    return len(intersection) / len(union) if union else 0.0


class RAGRetriever:
    """Advanced RAG retrieval with multiple scoring strategies."""

    def __init__(self, entries: dict, idf: Optional[dict] = None):
        """
        entries: dict of {id: {"title": str, "content": str, "tags": list, "intent": str, ...}}
        idf: pre-computed IDF dict (or computed from entries)
        """
        self.entries = entries
        self.corpus = [f"{e['title']} {e['content']} {' '.join(e.get('tags', []))}"
                       for e in self.entries.values()]
        self._idf = idf or compute_idf(self.corpus)
        self._precompute_tfidf()

    def _precompute_tfidf(self):
        """Pre-compute TF-IDF vectors for all entries."""
        self._entry_vecs = {}
        for eid, e in self.entries.items():
            tokens = tokenize(f"{e['title']} {e['content']} {' '.join(e.get('tags', []))}")
            self._entry_vecs[eid] = tfidf_vector(tokens, self._idf)

    def average_doc_length(self) -> float:
        lengths = [len(tokenize(f"{e['title']} {e['content']}"))
                   for e in self.entries.values()]
        return sum(lengths) / max(len(lengths), 1)

    def search(self, query: str, intent: str = "", entities: dict = None,
               top_k: int = 5, weights: dict = None) -> list[dict]:
        """
        Hybrid RAG retrieval combining:
          - BM25 ranking (40%)
          - TF-IDF cosine similarity (25%)
          - N-gram overlap (10%)
          - Intent match boost (15%)
          - Entity boost (10%)

        weights: optional dict to override default weights
          {"bm25": 0.4, "tfidf": 0.25, "ngram": 0.1, "intent": 0.15, "entity": 0.1}
        """
        if not query or not query.strip():
            return []

        w = weights or {"bm25": 0.4, "tfidf": 0.25, "ngram": 0.1, "intent": 0.15, "entity": 0.1}
        avg_dl = self.average_doc_length()
        qt = tokenize(query)
        query_vec = tfidf_vector(qt, self._idf)

        results = []
        for eid, e in self.entries.items():
            doc_text = f"{e['title']} {e['content']}"

            # BM25
            bm25_score = compute_bm25(query, doc_text, avg_dl)

            # TF-IDF cosine
            tfidf_score = cosine_similarity(query_vec, self._entry_vecs.get(eid, {}))

            # N-gram overlap
            ngram_score = ngram_overlap(query, doc_text, n=3)

            # Intent match
            intent_score = 1.0 if e.get("intent") == intent else (0.3 if intent else 0.0)

            # Entity match
            ent_score = 0.0
            if entities:
                matches = 0
                for k, v in entities.items():
                    vl = str(v).lower()
                    if vl in doc_text.lower():
                        matches += 1
                ent_score = matches / max(len(entities), 1)

            # Weighted combination (normalize to ~0-100 range)
            score = (w["bm25"] * bm25_score * 20
                     + w["tfidf"] * tfidf_score * 100
                     + w["ngram"] * ngram_score * 100
                     + w["intent"] * intent_score * 100
                     + w["entity"] * ent_score * 100)

            if score > 0:
                results.append({
                    **e,
                    "_score": round(score, 4),
                    "_bm25": round(bm25_score, 4),
                    "_tfidf": round(tfidf_score, 4),
                    "_ngram": round(ngram_score, 4),
                    "_intent_match": intent_score > 0,
                    "_entity_match": ent_score > 0,
                })

        return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]

    def search_with_recency(self, query: str, intent: str = "", entities: dict = None,
                             top_k: int = 5, quality_decay: float = 0.3) -> list[dict]:
        """
        RAG retrieval with recency/quality decay.
        Entries with lower quality scores are softly penalized.
        """
        results = self.search(query, intent, entities, top_k)
        for r in results:
            quality = r.get("quality", 1.0)
            # Gentle quality boost: good entries get slightly higher
            quality_boost = 1.0 + quality_decay * (quality - 0.5)
            r["_score"] = round(r["_score"] * quality_boost, 4)
        return sorted(results, key=lambda x: x["_score"], reverse=True)

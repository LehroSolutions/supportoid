"""
Agent 3: KnowledgeRetriever - RAG-style KB
==========================================
- Keyword + entity matching
- Intent-aware boosting
- Quality scoring from feedback
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("supportoid.kb")


class KnowledgeRetriever:
    def __init__(
        self,
        kb_dir: str,
        *,
        seed_dir: str | None = None,
        seed_if_empty: bool = False,
    ):
        self.kb_dir = kb_dir
        self.seed_dir = seed_dir or ""
        os.makedirs(kb_dir, exist_ok=True)
        self.entries: dict = {}
        self._load()
        if not self.entries and seed_if_empty and self.seed_dir:
            self._seed_from_directory()

    def _load(self):
        for fn in os.listdir(self.kb_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.kb_dir, fn), encoding="utf-8") as f:
                    data = json.load(f)
                entry_id = str(data.get("id") or "")
                if entry_id:
                    self.entries[entry_id] = data
            except Exception:
                logger.exception("Failed to load knowledge entry: %s", fn)

    def _seed_from_directory(self):
        seed_root = Path(self.seed_dir)
        if seed_root.name != "knowledge":
            seed_root = seed_root / "knowledge"
        if not seed_root.exists():
            logger.warning("Knowledge seed directory not found: %s", seed_root)
            return

        loaded = 0
        for source in sorted(seed_root.glob("*.json")):
            try:
                with source.open(encoding="utf-8") as f:
                    entry = json.load(f)
                entry_id = str(entry.get("id") or "")
                if not entry_id:
                    continue
                self.entries[entry_id] = entry
                self._save(entry)
                loaded += 1
            except Exception:
                logger.exception("Failed to seed knowledge entry: %s", source)
        if loaded:
            logger.info("Seeded %s knowledge entries from %s", loaded, seed_root)

    def _save(self, entry):
        path = os.path.join(self.kb_dir, f"{entry['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2)

    def search(self, query: str, intent: str, entities: dict = None, top_k: int = 3) -> list:
        if not query or not query.strip():
            return []
        ql = query.lower()
        qw = set(ql.split())
        results = []
        for entry in self.entries.values():
            score = 0.0
            title = entry["title"].lower()
            content = entry["content"].lower()
            if title == ql:
                score += 100
            elif title in ql:
                score += 30
            elif ql in title:
                score += 25
            for word in qw:
                if len(word) < 2:
                    continue
                if word in title:
                    score += 10
                elif word in content:
                    score += 2
            for tag in entry.get("tags", []):
                tag_lower = tag.lower()
                if tag_lower in ql:
                    score += 15
                elif any(word in tag_lower for word in qw):
                    score += 8
            if entry["intent"] == intent:
                score += 20
            if entities:
                for _, value in entities.items():
                    value_lower = str(value).lower()
                    if value_lower in content or value_lower in title:
                        score += 25
            score *= entry.get("quality", 1.0)
            if score > 0:
                results.append({**entry, "_score": score})
        return sorted(results, key=lambda item: item["_score"], reverse=True)[:top_k]

    def add_entry(self, title, content, intent, tags):
        entry_id = f"kb-auto-{len(self.entries) + 1:04d}"
        entry = {
            "id": entry_id,
            "title": title,
            "content": content,
            "intent": intent,
            "tags": tags,
            "quality": 1.0,
            "usage": 0,
        }
        self.entries[entry_id] = entry
        self._save(entry)
        return entry_id

    def record_feedback(self, entry_id: str, was_helpful: bool):
        if entry_id in self.entries:
            entry = self.entries[entry_id]
            entry["usage"] = entry.get("usage", 0) + 1
            delta = 0.05 if was_helpful else -0.05
            new_quality = entry.get("quality", 1.0) + delta
            entry["quality"] = min(1.05, max(0.2, new_quality))
            self._save(entry)

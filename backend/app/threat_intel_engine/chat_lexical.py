"""Lexical fingerprinting and synthetic chat detection."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def _char_ngrams(text: str, n: int = 4) -> Set[str]:
    t = text.lower().strip()
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass
class LexicalProfile:
    ngram_counts: Counter = field(default_factory=Counter)
    token_counts: Counter = field(default_factory=Counter)
    message_count: int = 0
    last_fingerprint: str = ""

    def update(self, message: str) -> str:
        self.message_count += 1
        for ng in _char_ngrams(message, 4):
            self.ngram_counts[ng] += 1
        for tok in _tokens(message):
            self.token_counts[tok] += 1
        top = self.ngram_counts.most_common(12)
        fp = "|".join(f"{k}:{v}" for k, v in top)
        self.last_fingerprint = fp
        return fp


class ChatLexicalAnalyzer:
    """Per-entity lexical fingerprints and spam/synthetic signals."""

    def __init__(self) -> None:
        self._profiles: Dict[str, LexicalProfile] = {}
        self._stream_recent: Dict[str, List[Tuple[str, str]]] = {}

    def _profile_key(self, stream_id: str, entity_key: str) -> str:
        return f"{stream_id}:{entity_key}"

    def analyze(
        self, stream_id: str, entity_key: str, message: str
    ) -> Dict[str, float | str | bool | List[str]]:
        pk = self._profile_key(stream_id, entity_key)
        prof = self._profiles.setdefault(pk, LexicalProfile())
        fp = prof.update(message)

        stream_key = stream_id
        recent = self._stream_recent.setdefault(stream_key, [])
        repetition_score = 0.0
        flags: List[str] = []

        msg_norm = message.strip().lower()
        for _, prev in recent[-40:]:
            if prev == msg_norm:
                repetition_score = 1.0
                flags.append("exact_repeat")
                break
            sim = jaccard(_char_ngrams(message, 4), _char_ngrams(prev, 4))
            if sim > 0.85:
                repetition_score = max(repetition_score, sim)
                flags.append("near_duplicate")

        recent.append((entity_key, msg_norm))
        self._stream_recent[stream_key] = recent[-200:]

        unique_tokens = len(prof.token_counts)
        diversity = unique_tokens / max(prof.message_count, 1)
        automated_phrase = self._detect_automated_phrase(message)
        if automated_phrase:
            flags.append("automated_phrase")
        if prof.message_count > 5 and diversity < 0.15:
            flags.append("low_lexical_diversity")
        if repetition_score > 0.7:
            flags.append("coordinated_spam_candidate")

        spam_p = min(
            1.0,
            repetition_score * 0.5
            + (0.3 if automated_phrase else 0)
            + (0.2 if diversity < 0.1 else 0),
        )
        synthetic_p = min(
            1.0,
            (1.0 - min(1.0, diversity * 3)) * 0.4 + spam_p * 0.6,
        )

        return {
            "lexical_fingerprint": fp,
            "repetition_score": round(repetition_score, 4),
            "lexical_diversity": round(diversity, 4),
            "spam_probability": round(spam_p, 4),
            "synthetic_chat_score": round(synthetic_p, 4),
            "automated_phrase": automated_phrase,
            "flags": flags,
        }

    def stream_lexical_diversity(self, stream_id: str) -> float:
        recent = self._stream_recent.get(stream_id, [])
        if len(recent) < 3:
            return 1.0
        texts = [t for _, t in recent[-50:]]
        all_ng: Set[str] = set()
        for t in texts:
            all_ng |= _char_ngrams(t, 4)
        return min(1.0, len(all_ng) / max(len(texts) * 3, 1))

    def _detect_automated_phrase(self, message: str) -> bool:
        m = message.strip().lower()
        if len(m) < 3:
            return False
        patterns = (
            r"^(gg|lol|lmao|nice|follow|sub|prime|free\s)",
            r"(bot|raid|viewbot|followbot)",
            r"^[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]+$",
        )
        for p in patterns:
            if re.search(p, m):
                return True
        if len(set(m)) <= 2 and len(m) > 8:
            return True
        return False

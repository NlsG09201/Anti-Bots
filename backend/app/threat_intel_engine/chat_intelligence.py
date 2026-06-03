"""Chat Intelligence System — Real-time chat analysis."""

from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json
import re
from difflib import SequenceMatcher

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis

logger = get_logger(__name__)
settings = get_settings()

# Message window for analysis
MESSAGE_WINDOW_SIZE = 500
MESSAGE_TIME_WINDOW = 300  # 5 minutes


class ChatIntelligenceEngine:
    """Real-time chat analysis for bot detection."""

    def __init__(self):
        self._cache = get_redis()
        self._message_windows: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=MESSAGE_WINDOW_SIZE)
        )
        self._user_messages: Dict[str, List[str]] = defaultdict(list)
        self._message_timestamps: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=500)
        )
        self._tfidf_vectorizer = TfidfVectorizer(
            max_features=100,
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
        )

    async def analyze_message(
        self,
        stream_id: str,
        user_id: str,
        username: str,
        message: str,
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Analyze a single chat message."""
        if timestamp is None:
            timestamp = int(__import__("time").time())

        message_data = {
            "user_id": user_id,
            "username": username,
            "message": message,
            "timestamp": timestamp,
        }

        self._message_windows[stream_id].append(message_data)
        self._message_timestamps[stream_id].append(timestamp)
        self._user_messages[f"{stream_id}:{user_id}"].append(message)

        # Run analyses
        analysis = {
            "repetition_score": await self._detect_message_repetition(stream_id, message),
            "automation_score": await self._detect_automation_patterns(message),
            "spam_score": await self._detect_spam_patterns(message),
            "coordinated_score": await self._detect_coordinated_patterns(
                stream_id, user_id, message, timestamp
            ),
            "lexical_fingerprint": await self._generate_lexical_fingerprint(message),
            "semantic_similarity": await self._check_semantic_similarity(
                stream_id, message
            ),
            "rate_anomaly": await self._detect_message_rate_anomaly(
                stream_id, user_id, timestamp
            ),
        }

        return analysis

    async def _detect_message_repetition(
        self, stream_id: str, message: str
    ) -> Dict[str, Any]:
        """Detect exact or similar message repetition."""
        messages = list(self._message_windows.get(stream_id, []))
        if len(messages) < 3:
            return {"repetition_detected": False, "confidence": 0, "match_count": 0}

        # Check last 20 messages
        recent = messages[-20:]
        recent_texts = [m["message"] for m in recent]

        # Exact matches
        exact_matches = sum(1 for m in recent_texts if m == message)

        # Similar matches (>80% similarity)
        similar_matches = sum(
            1
            for m in recent_texts
            if m != message and self._string_similarity(m, message) > 0.8
        )

        total_matches = exact_matches + similar_matches

        if total_matches >= 2:
            confidence = min(1.0, total_matches / 5.0)
        else:
            confidence = 0.0

        return {
            "repetition_detected": confidence > 0.5,
            "confidence": confidence,
            "match_count": total_matches,
            "exact_matches": exact_matches,
        }

    async def _detect_automation_patterns(self, message: str) -> Dict[str, Any]:
        """Detect automated message patterns."""
        score = 0.0

        # Check for common bot indicators
        bot_keywords = [
            r"\bfollow\b.*\bchannel\b",
            r"\bsubscribe\b.*\bchannel\b",
            r"\blogs?\b.*\bchannels?\b",
            r"\b\d+\s*[hl]",  # "5h", "10l", etc.
            r"\bhttp[s]?://\S+",  # URLs
            r"\b[A-Z]{2,}\s*[A-Z]{2,}\b",  # ALL CAPS words
            r"^[!@#$%]{2,}",  # Repeated symbols
        ]

        for pattern in bot_keywords:
            if re.search(pattern, message, re.IGNORECASE):
                score += 0.15

        # Check message structure
        if len(message) < 5:
            score += 0.1  # Very short messages

        if message.isupper() and len(message) > 3:
            score += 0.2  # All caps

        if message.count(" ") == 0 and len(message) > 3:
            score += 0.15  # No spaces

        # Check for emoji spam
        emoji_count = len([c for c in message if ord(c) > 0x1F300])
        if emoji_count > 3:
            score += 0.1

        return {
            "automation_detected": score > 0.3,
            "confidence": min(1.0, score),
            "indicators": self._extract_automation_indicators(message),
        }

    async def _detect_spam_patterns(self, message: str) -> Dict[str, Any]:
        """Detect spam message patterns."""
        score = 0.0

        # Common spam patterns
        spam_patterns = [
            r"([a-z])\1{2,}",  # Repeated letters (aaa, bbb)
            r"[\W_]{2,}",  # Multiple non-word characters
            r"\b(click|tap|visit|check|buy|sell|free|win|prize)\b",
            r"(?:https?://|\w+\.com|\w+\.co)",  # URLs/domains
            r"\d{2,}-\d{2,}-\d{2,}",  # Phone numbers
        ]

        for pattern in spam_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                score += 0.15

        # Check for excessive punctuation
        punct_count = sum(1 for c in message if c in "!?.,:;")
        if punct_count > len(message) / 3:
            score += 0.2

        return {
            "spam_detected": score > 0.3,
            "confidence": min(1.0, score),
            "spam_indicators": sum(1 for p in spam_patterns if re.search(p, message)),
        }

    async def _detect_coordinated_patterns(
        self, stream_id: str, user_id: str, message: str, timestamp: int
    ) -> Dict[str, Any]:
        """Detect coordinated/synchronized chat patterns."""
        messages = list(self._message_windows.get(stream_id, []))
        if len(messages) < 5:
            return {"coordinated_detected": False, "confidence": 0}

        # Get messages from last 10 seconds
        recent = [m for m in messages if timestamp - m["timestamp"] <= 10]

        # Find similar messages
        similar_count = sum(
            1
            for m in recent
            if m["user_id"] != user_id
            and self._string_similarity(m["message"], message) > 0.75
        )

        if similar_count >= 2:
            confidence = min(1.0, similar_count / 5.0)
        else:
            confidence = 0.0

        return {
            "coordinated_detected": confidence > 0.5,
            "confidence": confidence,
            "similar_messages": similar_count,
        }

    async def _generate_lexical_fingerprint(self, message: str) -> Dict[str, Any]:
        """Generate lexical fingerprint of message."""
        # Normalize message
        normalized = message.lower()
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)

        # Extract features
        words = normalized.split()
        char_distribution = {}
        for char in normalized:
            if char != " ":
                char_distribution[char] = char_distribution.get(char, 0) + 1

        # Top characteristics
        top_chars = sorted(char_distribution.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]

        return {
            "fingerprint": hash(normalized),
            "word_count": len(words),
            "unique_chars": len(set(normalized)),
            "top_chars": dict(top_chars),
            "avg_word_length": (
                sum(len(w) for w in words) / len(words) if words else 0
            ),
        }

    async def _check_semantic_similarity(
        self, stream_id: str, message: str
    ) -> Dict[str, Any]:
        """Check semantic similarity with recent messages."""
        messages = list(self._message_windows.get(stream_id, []))
        if len(messages) < 5:
            return {
                "semantic_similarity_score": 0,
                "most_similar_messages": 0,
            }

        recent = messages[-30:]
        recent_texts = [m["message"] for m in recent]

        # Check if we have enough diverse messages to analyze
        unique_messages = len(set(recent_texts))
        if unique_messages < 3:
            return {
                "semantic_similarity_score": 0.8,
                "most_similar_messages": len(recent) - unique_messages,
            }

        try:
            # Use TF-IDF for semantic similarity
            corpus = recent_texts + [message]
            tfidf_matrix = self._tfidf_vectorizer.fit_transform(corpus)
            similarities = cosine_similarity([tfidf_matrix[-1]], tfidf_matrix[:-1])[0]

            avg_similarity = np.mean(similarities)
            max_similarity = np.max(similarities)
            similar_count = sum(1 for s in similarities if s > 0.7)

            return {
                "semantic_similarity_score": float(avg_similarity),
                "max_similarity": float(max_similarity),
                "similar_messages": int(similar_count),
            }
        except Exception as exc:
            logger.debug("semantic_similarity_calculation_failed", error=str(exc))
            return {
                "semantic_similarity_score": 0,
                "similar_messages": 0,
            }

    async def _detect_message_rate_anomaly(
        self, stream_id: str, user_id: str, timestamp: int
    ) -> Dict[str, Any]:
        """Detect abnormal message rate for a user."""
        user_key = f"{stream_id}:{user_id}"
        user_timestamps = self._message_timestamps.get(user_key, deque())

        if len(user_timestamps) < 3:
            return {"rate_anomaly_detected": False, "confidence": 0}

        # Calculate message rate (messages per minute)
        time_window = 60
        recent_messages = sum(
            1 for ts in user_timestamps if timestamp - ts <= time_window
        )

        # Messages per minute
        rate = recent_messages

        # Typical human rate: 1-3 messages per minute
        # Bot rate: 5+ messages per minute
        if rate >= 10:
            confidence = 1.0
        elif rate >= 5:
            confidence = min(1.0, (rate - 5) / 5.0)
        else:
            confidence = 0.0

        return {
            "rate_anomaly_detected": confidence > 0.5,
            "confidence": confidence,
            "messages_per_minute": rate,
        }

    @staticmethod
    def _string_similarity(a: str, b: str) -> float:
        """Calculate string similarity using SequenceMatcher."""
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _extract_automation_indicators(message: str) -> List[str]:
        """Extract specific automation indicators from message."""
        indicators = []

        if re.search(r"\bfollow\b.*\bchannel\b", message, re.IGNORECASE):
            indicators.append("follow_request")
        if re.search(r"\bsubscribe\b", message, re.IGNORECASE):
            indicators.append("subscribe_request")
        if re.search(r"http[s]?://", message):
            indicators.append("url_link")
        if message.isupper():
            indicators.append("all_caps")
        if len(message) < 5:
            indicators.append("too_short")

        return indicators

    async def get_chat_risk_score(self, stream_id: str) -> float:
        """Calculate overall chat risk score."""
        messages = list(self._message_windows.get(stream_id, []))
        if len(messages) < 10:
            return 0.0

        # Analyze last 20 messages
        recent = messages[-20:]
        scores = []

        for msg in recent:
            analysis = await self.analyze_message(
                stream_id,
                msg["user_id"],
                msg["username"],
                msg["message"],
                msg["timestamp"],
            )
            avg_score = (
                analysis.get("repetition_score", {}).get("confidence", 0) * 0.2
                + analysis.get("automation_score", {}).get("confidence", 0) * 0.2
                + analysis.get("spam_score", {}).get("confidence", 0) * 0.2
                + analysis.get("coordinated_score", {}).get("confidence", 0) * 0.2
                + analysis.get("rate_anomaly", {}).get("confidence", 0) * 0.2
            )
            scores.append(avg_score)

        return sum(scores) / len(scores) if scores else 0.0

    async def clear_stream_data(self, stream_id: str) -> None:
        """Clear accumulated chat data."""
        self._message_windows.pop(stream_id, None)
        self._message_timestamps.pop(stream_id, None)

        # Also clear user message history
        keys_to_remove = [k for k in self._user_messages if k.startswith(stream_id)]
        for key in keys_to_remove:
            self._user_messages.pop(key, None)

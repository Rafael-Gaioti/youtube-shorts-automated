import re
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


class SubtitleAuditor:
    """
    Audits transcripts for hallucinations, gibberish, and repetitions.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.repetition_threshold = 0.3  # >30% repeated words is suspicious
        self.logprob_threshold = -1.0  # Lower is suspicious
        self.no_speech_threshold = 0.6  # Higher is suspicious
        self.min_segment_len = 5  # Ignore very short segments for some checks

    def check_repetitions(self, text: str) -> float:
        """
        Calculates a repetition score (0.0 to 1.0).
        High score indicates many repeated words or phrases.
        """
        words = re.findall(r"\w+", text.lower())
        if not words:
            return 0.0

        # Count individual word frequencies
        counts = Counter(words)
        repeat_count = sum(count - 1 for count in counts.values() if count > 1)

        # Word-level repetition score
        word_score = repeat_count / len(words)

        # Sequence-level repetition (e.g., "hello world hello world")
        # Simple check for repeating bigrams
        if len(words) > 4:
            bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
            bi_counts = Counter(bigrams)
            bi_repeat_count = sum(
                count - 1 for count in bi_counts.values() if count > 1
            )
            bi_score = bi_repeat_count / len(bigrams)
            return max(word_score, bi_score)

        return word_score

    def check_gibberish(self, text: str) -> float:
        """
        Checks for gibberish patterns (repeated letters, no vowels, etc.).
        """
        if not text:
            return 0.0

        # Long strings of same character (e.g., "aaaaaaaa")
        if re.search(r"(.)\1{5,}", text):
            return 1.0

        # Segments with very low vowel density
        vowels = len(re.findall(r"[aeiouáéíóúâêîôûãõ]", text.lower()))
        consonants = len(re.findall(r"[bcdfghjklmnpqrstvwxyz]", text.lower()))

        if consonants > 5 and vowels / (vowels + consonants) < 0.1:
            return 0.8

        return 0.0

    def audit_transcript(self, transcript_data: Dict) -> Dict:
        """
        Performs a full audit of the transcript.
        Returns a report with 'is_healthy' and 'issues'.
        """
        segments = transcript_data.get("segments", [])
        issues = []
        hallucinated_segments = 0
        total_chars = 0
        hallucinated_chars = 0

        for seg in segments:
            text = seg.get("text", "")
            avg_logprob = seg.get("avg_logprob", 0)
            no_speech_prob = seg.get("no_speech_prob", 0)

            total_chars += len(text)

            # Heuristic checks
            rep_score = self.check_repetitions(text)
            gib_score = self.check_gibberish(text)

            is_hallucinated = False
            reasons = []

            if avg_logprob < self.logprob_threshold:
                reasons.append(f"Low logprob: {avg_logprob:.2f}")
                is_hallucinated = True

            if no_speech_prob > self.no_speech_threshold and len(text) > 10:
                reasons.append(f"High no_speech_prob: {no_speech_prob:.2f}")
                is_hallucinated = True

            if rep_score > 0.5 and len(text) > 20:
                reasons.append(f"Repetitive text (score: {rep_score:.2f})")
                is_hallucinated = True

            if gib_score > 0.5:
                reasons.append(f"Gibberish detected (score: {gib_score:.2f})")
                is_hallucinated = True

            if is_hallucinated:
                hallucinated_segments += 1
                hallucinated_chars += len(text)
                issues.append(
                    {
                        "segment_id": seg.get("id"),
                        "text": text,
                        "reasons": reasons,
                        "start": seg.get("start"),
                        "end": seg.get("end"),
                    }
                )

        hallucination_ratio = hallucinated_chars / total_chars if total_chars > 0 else 0

        # Overall health check
        is_healthy = hallucination_ratio < 0.1 and len(issues) < (len(segments) * 0.2)

        report = {
            "is_healthy": is_healthy,
            "hallucination_ratio": hallucination_ratio,
            "total_segments": len(segments),
            "hallucinated_segments": hallucinated_segments,
            "issues": issues,
        }

        if not is_healthy:
            logger.warning(
                f"Transcript audit FAILED. Hallucination ratio: {hallucination_ratio:.2%}"
            )
        else:
            logger.info(
                f"Transcript audit PASSED. Hallucination ratio: {hallucination_ratio:.2%}"
            )

        return report

    def validate_with_llm(self, text_samples: List[str]) -> bool:
        """
        Future implementation: Use an LLM to verify if a set of suspicious segments
        are actually hallucinations or valid speech.
        """
        # TODO: Integrate with existing LLM tools
        return True


if __name__ == "__main__":
    # Test with a dummy transcript
    auditor = SubtitleAuditor()
    dummy_transcript = {
        "segments": [
            {
                "id": 1,
                "text": "Isso aqui é um teste normal.",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.01,
            },
            {
                "id": 2,
                "text": "Obrigado obrigado obrigado obrigado obrigado obrigado.",
                "avg_logprob": -1.2,
                "no_speech_prob": 0.4,
            },
            {
                "id": 3,
                "text": "Wait wait wait wait wait wait wait",
                "avg_logprob": -0.5,
                "no_speech_prob": 0.1,
            },
            {
                "id": 4,
                "text": "aaaaaaaaaaaaaaaaaaaaaa",
                "avg_logprob": -2.0,
                "no_speech_prob": 0.8,
            },
        ]
    }
    report = auditor.audit_transcript(dummy_transcript)
    print(json.dumps(report, indent=2))

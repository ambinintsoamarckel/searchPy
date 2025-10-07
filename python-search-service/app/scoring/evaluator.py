from typing import List, Dict
from .levenshtein import damerau_levenshtein

class Evaluator:
    """Compute a composite score combining levenshtein distance and simple heuristics."""
    def score(self, query: str, candidate: str) -> float:
        if not query:
            return 0.0
        d = damerau_levenshtein(query.lower(), candidate.lower())
        # simple normalization: shorter distance -> higher score
        max_len = max(len(query), len(candidate))
        score = max(0.0, (max_len - d) / max_len) * 10.0
        # small bonus for prefix match
        if candidate.lower().startswith(query.lower()):
            score += 1.5
        return round(score, 4)

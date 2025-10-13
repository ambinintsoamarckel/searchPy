# phonetic_scorer.py

import re
from typing import List, Dict, Any, Optional
from app.scoring.distance import string_distance
from app.models import QueryData # Pour l'annotation
class PhoneticScorer:
    """Scoreur phonétique pour le matching avancé."""

    def phonetic_tokens(self, s: str) -> List[str]:
        """Tokenisation phonétique d'une chaîne."""
        tokens = re.split(r'\s+', s.lower().strip())
        return [t for t in tokens if t and len(t) > 1]

    def match_phonetic_tokens(self, query_tokens: List[str], hit_tokens: List[str], tolerant: bool = False) -> Dict[str, Any]:
        """Effectue le matching phonétique entre les tokens."""
        used = {}
        matches = 0
        tolerant_used = False

        for query_token in query_tokens:
            best_idx = None
            is_tolerant = False

            for idx, hit_token in enumerate(hit_tokens):
                if used.get(idx, False):
                    continue

                if query_token == hit_token:
                    best_idx = idx
                    is_tolerant = False
                    break

                # Préfixe (si assez long)
                min_len = min(len(query_token), len(hit_token))
                if min_len >= 4 and (query_token.startswith(hit_token) or hit_token.startswith(query_token)):
                    best_idx = idx
                    is_tolerant = False
                    continue

                if tolerant and min_len >= 6 and string_distance.distance(query_token, hit_token, 1) <= 1:
                    best_idx = idx
                    is_tolerant = True

            if best_idx is not None:
                used[best_idx] = True
                matches += 1
                if is_tolerant:
                    tolerant_used = True

        return {'found': matches, 'tolerant_used': tolerant_used}

    def calculate_phonetic_score(self, hit: Dict[str, Any], query_data: QueryData) -> Optional[Dict[str, Any]]:
        """Calcule le score phonétique d'un hit."""
        q = query_data.soundex.strip()
        h = hit.get('name_soundex', '').strip()

        if not q or not h:
            return None

        q_tokens = self.phonetic_tokens(q)
        h_tokens = self.phonetic_tokens(h)

        if not q_tokens or not h_tokens:
            return None

        # Essai strict d'abord
        strict = self.match_phonetic_tokens(q_tokens, h_tokens, tolerant=False)
        ratio = strict['found'] / len(q_tokens)
        match_type = 'phonetic_strict'

        # Calcul du score
        score = 8 * ratio
        if ratio == 1.0:
            score = min(7.5, score)
        elif ratio >= 0.66:
            score = min(7.0, score)
        else:
            score = min(6.0, score)

        # Mode tolérant si score faible
        if score < 6.0:
            tolerant = self.match_phonetic_tokens(q_tokens, h_tokens, tolerant=True)
            ratio_tol = tolerant['found'] / len(q_tokens)

            if ratio_tol > ratio:
                ratio = ratio_tol
                match_type = 'phonetic_tolerant'
                score = 8 * ratio

                if ratio == 1.0:
                    score = min(7.5, score)
                elif ratio >= 0.66:
                    score = min(7.0, score)
                else:
                    score = min(6.0, score)

        return {
            'score': score,
            'ratio': ratio,
            'match_type': match_type,
            'query_soundex': q,
            'hit_soundex': h,
            'tokens': {'q': q_tokens, 'h': h_tokens}
        }

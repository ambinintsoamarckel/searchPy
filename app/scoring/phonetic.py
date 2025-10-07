"""Scoring phonétique."""
import re
from typing import List, Dict, Optional, Any
from app.scoring.distance import string_distance


class PhoneticScorer:
    """Scoreur phonétique pour le matching."""

    def phonetic_tokens(self, s: str) -> List[str]:
        """Extrait les tokens phonétiques d'une chaîne."""
        tokens = re.split(r'\s+', s.lower().strip())
        return [t for t in tokens if t and len(t) > 1]

    def match_phonetic_tokens(
        self,
        q_tokens: List[str],
        h_tokens: List[str],
        tolerant: bool = False
    ) -> Dict[str, Any]:
        """
        Match les tokens phonétiques entre query et hit.

        Args:
            q_tokens: Tokens de la query
            h_tokens: Tokens du hit
            tolerant: Si True, accepte des variations (Levenshtein <= 1)

        Returns:
            Dict avec 'found' (nombre de matches) et 'tolerant_used'
        """
        used = {}
        matches = 0
        tolerant_used = False

        for qt in q_tokens:
            best_idx = None
            is_tolerant = False

            for i, ct in enumerate(h_tokens):
                if used.get(i, False):
                    continue

                # Match exact
                if qt == ct:
                    best_idx = i
                    is_tolerant = False
                    break

                # Préfixe (si assez long)
                minlen = min(len(qt), len(ct))
                if minlen >= 4 and (qt.startswith(ct) or ct.startswith(qt)):
                    if best_idx is None:
                        best_idx = i
                        is_tolerant = False
                    continue

                # Mode tolérant
                if tolerant and minlen >= 6:
                    if string_distance.distance(qt, ct, 1) <= 1:
                        if best_idx is None:
                            best_idx = i
                            is_tolerant = True

            if best_idx is not None:
                used[best_idx] = True
                matches += 1
                if is_tolerant:
                    tolerant_used = True

        return {
            'found': matches,
            'tolerant_used': tolerant_used
        }

    def calculate_phonetic_score(self, hit: Dict[str, Any], query_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Calcule le score phonétique pour un hit.

        Args:
            hit: Le hit Meilisearch
            query_data: Les données de la query

        Returns:
            Dict avec score, ratio, match_type ou None si pas applicable
        """
        q = str(query_data.get('soundex', '')).strip()
        h = str(hit.get('name_soundex', '')).strip()

        if not q or not h:
            return None

        q_tokens = self.phonetic_tokens(q)
        h_tokens = self.phonetic_tokens(h)

        if not q_tokens or not h_tokens:
            return None

        # Essai strict
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

        # Si score faible, essai tolérant
        if score < 6.0:

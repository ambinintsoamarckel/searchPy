from typing import List, Dict

class Ranker:
    def rank(self, scored: List[Dict]) -> List[Dict]:
        return sorted(scored, key=lambda x: (-x['score'], x.get('distance', 0)))

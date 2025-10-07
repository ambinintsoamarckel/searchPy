from typing import List, Dict
from app.models import SearchResult
from app.scoring.evaluator import Evaluator
from app.scoring.ranking import Ranker

# Minimal "Meili-like" strategy that fakes hits for demo and scores them
class MeiliStrategy:
    def __init__(self):
        self.eval = Evaluator()
        self.ranker = Ranker()
        # small in-memory dataset for demo
        self._data = [
            {"id": "1", "name": "Le Petit Resto"},
            {"id": "2", "name": "La Grande Ferme"},
            {"id": "3", "name": "Cafe Central"},
        ]

    def search(self, query: str, location: str = None, limit: int = 50) -> List[SearchResult]:
        scored = []
        for doc in self._data:
            s = self.eval.score(query, doc['name'])
            scored.append({"id": doc['id'], "name": doc['name'], "score": s})
        ranked = self.ranker.rank(scored)
        results = [SearchResult(id=r['id'], name=r['name'], score=r['score']) for r in ranked[:limit]]
        return results

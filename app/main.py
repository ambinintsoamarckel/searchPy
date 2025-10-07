from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

from .models import SearchRequest, SearchResult
from .search.strategies import MeiliStrategy

app = FastAPI(title="SearchPy - Python Search Service")

strategy = MeiliStrategy()

@app.post('/search', response_model=List[SearchResult])
def search(req: SearchRequest):
    """Simple POST /search endpoint that delegates to a strategy."""
    results = strategy.search(req.query, req.location, limit=req.limit)
    return results

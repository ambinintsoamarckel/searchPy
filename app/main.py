from fastapi import FastAPI
from typing import List

from .models import SearchRequest, SearchResponse
from .search.search_service import SearchService

app = FastAPI(title="SearchPy - Python Search Service")

service = SearchService()


@app.post('/search', response_model=SearchResponse)
async def search(req: SearchRequest):
    """POST /search endpoint. Expects a preprocessed `QueryData` in the body and delegates the heavy work to the service."""
    resp = await service.search(req.index_name, req.query_data, req.options)
    return resp
@app.get("/")
def root():
    return {"status": "ok", "message": "SearchPy API is running 🚀"}

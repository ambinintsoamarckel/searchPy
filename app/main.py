from fastapi import FastAPI, HTTPException
import logging
from typing import List

from .models import SearchRequest, SearchResponse
from .search.search_service import SearchService

app = FastAPI(title="SearchPy - Python Search Service")
service = SearchService()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("search-api")

@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """POST /search endpoint avec logs pour debugging 422"""
    try:
        logger.info(f"Received request: {req.json()}")
        resp = await service.search(req.index_name, req.query_data, req.options)
        return resp
    except Exception as e:
        logger.exception("Error processing search request")
        raise HTTPException(status_code=500, detail={"error": str(e)})

@app.get("/")
def root():
    return {"status": "ok", "message": "SearchPy API is running 🚀"}

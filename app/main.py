from fastapi import FastAPI, HTTPException
import logging
from logging.handlers import RotatingFileHandler
from typing import List

from .models import SearchRequest, SearchResponse
from .search.search_service import SearchService

# Configure logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler for logs
log_file = 'search-api.log'
# 5 MB per file, 5 backup files
file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 5, backupCount=5)
file_handler.setFormatter(log_formatter)

# Get the logger and add the file handler
logger = logging.getLogger("search-api")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.propagate = False # Prevents logs from being propagated to the root logger

app = FastAPI(title="SearchPy - Python Search Service")
service = SearchService()


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

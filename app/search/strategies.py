import asyncio
from typing import Any
from .search_utils import SearchService


# Exported interface for the rest of the app
class SearchServiceWrapper:
    def __init__(self, meili_host: str | None = None, meili_key: str | None = None):
        self._svc = SearchService(meili_host, meili_key)

    async def search(self, index_name: str, query_data: Any, options: Any):
        return await self._svc.search(index_name, query_data, options)


# For tests or simple sync usage, provide a helper that runs the async search loop
def sync_search(index_name: str, query_data: Any, options: Any):
    svc = SearchService()
    return asyncio.get_event_loop().run_until_complete(svc.search(index_name, query_data, options))

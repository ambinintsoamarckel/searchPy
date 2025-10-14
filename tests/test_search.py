from fastapi.testclient import TestClient
from app import main
from app.models import QueryData, SearchOptions, SearchResponse
from .test_utils import print_test_name, print_test_result


class DummyService:
    async def search(self, index_name, qdata, options, user_id=None):
        # return a minimal valid SearchResponse
        return SearchResponse(
            hits=[{"id": "1", "name": "Le Petit Resto", "_score": 9.5, "_match_type": "near_perfect", "_match_priority": 2}],
            total=1,
            has_exact_results=False,
            exact_count=0,
            total_before_filter=1,
            query_time_ms=1.2,
            preprocessing=qdata,
        )


def test_search_basic():
    test_name = "test_search_basic"
    print_test_name(test_name)
    try:
        # patch the service used by the FastAPI app
        main.service = DummyService()
        client = TestClient(main.app)

        qdata = QueryData(
            original="Petit",
            cleaned="petit",
            no_space="petit",
            soundex="pt",
            original_length=5,
            cleaned_length=5,
            no_space_length=5,
            wordsCleaned=["petit"],
            wordsOriginal=["Petit"],
            wordsNoSpace=["petit"],
        )

        payload = {
            "index_name": "restaurants",
            "query_data": qdata.model_dump(),
            "options": {"limit": 10}
        }
        resp = client.post('/search', json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        assert body['total'] == 1
        assert isinstance(body['hits'], list)
        assert body['hits'][0]['name'] == 'Le Petit Resto'
        print_test_result(test_name, passed=True)
    except Exception as e:
        print_test_result(test_name, passed=False)
        raise e

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_search_basic():
    resp = client.post('/search', json={"query": "Petit"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert 'name' in body[0]

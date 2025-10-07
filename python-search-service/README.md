SearchPy - Python Search Service

This is a minimal FastAPI scaffold for the SearchPy project.

Quick start

1. Create a virtualenv and install deps:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate; pip install -r requirements.txt
```

2. Run development server:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

3. Run tests:

```powershell
pytest -q
```

Project layout

- `app/` - application package (main, models, scoring, search, utils)
- `tests/` - pytest tests

Contact

Tell me if you want extra endpoints, CI, or a GitHub Actions workflow.

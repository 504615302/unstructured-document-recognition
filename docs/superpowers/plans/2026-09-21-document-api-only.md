# Document API Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every non-`document_api` interface and its exclusive assets while keeping a runnable FastAPI service, startup script, and Docker file.

**Architecture:** Keep the existing package layout for the single route and its processor. Narrow shared files to the exact symbols consumed by that route, remove all unrelated modules and data, then validate imports and the generated OpenAPI document without contacting the external model.

**Tech Stack:** Python 3.10, FastAPI, Uvicorn, Pydantic, HTTPX, Loguru

**Spec:** `docs/superpowers/specs/2026-09-21-document-api-only-design.md`

## Global Constraints

- The only business route is `POST /documents/process`.
- Keep `start.sh` and `docker/Dockerfile`.
- Delete tests, logs, sample data, temporary files, backups, and other-interface code.
- Do not send a request to the configured external language model during verification.
- Preserve the existing explicit versions for FastAPI and Uvicorn; do not introduce dependency upgrades.

## Review Focus

- Importing `main` must not import a deleted router or utility.
- OpenAPI must contain no old business route.
- The retained Pydantic request and response schemas must still resolve.
- Model URL, key, and model name must remain configurable through environment variables.
- Starting the application must not recreate a persistent `logs/` directory.

---

### Task 1: Reduce the project to the document processing service

**Files:**
- Modify: `main.py`
- Modify: `requirements.txt`
- Modify: `app/config.py`
- Modify: `app/settings.py`
- Modify: `app/models/data_models.py`
- Delete: `app/routers/api.py`
- Delete: `app/routers/doc_api.py`
- Delete: `app/routers/llm_api.py`
- Delete: `app/tools/`
- Delete: all `app/utils/` files except `document_processor.py` and `__init__.py`
- Delete: `app/static/`
- Delete: `app/database/`
- Delete: `migrations/`
- Delete: `pakg/`
- Delete: `tests/`
- Delete: `logs/`

**Interfaces:**
- Consumes: `app.routers.document_api.router`, `DocumentProcessor.process(business_code: str, data: Any)` and the three document Pydantic models.
- Produces: importable `main.app` whose only business operation is `POST /documents/process`.

- [ ] **Step 1: Run the pre-change route check and observe failure**

```powershell
python -c "from main import app; assert set(app.openapi()['paths']) == {'/documents/process'}, set(app.openapi()['paths'])"
```

Expected: FAIL because `main.py` currently registers routes from `api` and `llm_api` in addition to `document_api`.

- [ ] **Step 2: Restrict the application entry point**

Replace the router import and registration in `main.py` with:

```python
from app.routers import document_api

app = FastAPI()
app.include_router(document_api.router)
```

Keep the existing command-line Uvicorn startup behavior.

- [ ] **Step 3: Narrow shared models, configuration, logging, and dependencies**

Make `app/models/data_models.py` contain only:

```python
from typing import Any, Dict, Optional

from pydantic import BaseModel


class UnstructuredDocumentRequest(BaseModel):
    business_code: str
    data: Any


class DocumentProcessData(BaseModel):
    business_code: str
    document_type: str
    type_name: str
    extracted_data: Dict[str, Any]


class UnstructuredDocumentResponse(BaseModel):
    success: bool
    data: Optional[DocumentProcessData] = None
    error: str = ""
```

Make `app/config.py` contain only environment-backed `MODEL_URL`, `MODEL_KEY`, and `DOCUMENT_MODEL_NAME`, retaining the current platform-specific defaults. Make `app/settings.py` export Loguru's default `logger` without creating a directory or file sink. Make `requirements.txt` contain only:

```text
fastapi==0.115.4
uvicorn==0.32.0
loguru
pydantic
httpx
```

- [ ] **Step 4: Delete confirmed unrelated files and directories**

Delete exactly the paths listed in this task's Files block. Preserve package `__init__.py` files needed by `app`, `app.models`, `app.routers`, and `app.utils`, as well as `start.sh`, `docker/Dockerfile`, the specification, and this plan.

- [ ] **Step 5: Verify the retained source compiles**

```powershell
python -m compileall -q main.py app
```

Expected: exit code 0.

- [ ] **Step 6: Verify imports, schema resolution, routes, configuration, and no log-directory side effect**

```powershell
python -c "import os; os.environ['MODEL_URL']='http://model.test/v1/chat/completions'; os.environ['MODEL_KEY']='test-key'; os.environ['DOCUMENT_MODEL_NAME']='test-model'; from app import config; from main import app; schema=app.openapi(); assert config.MODEL_URL=='http://model.test/v1/chat/completions'; assert config.MODEL_KEY=='test-key'; assert config.DOCUMENT_MODEL_NAME=='test-model'; assert set(schema['paths'])=={'/documents/process'}; assert set(schema['paths']['/documents/process'])=={'post'}; assert not os.path.isdir('logs')"
```

Expected: exit code 0 and no output.

- [ ] **Step 7: Verify the remaining file tree contains no removed modules or backup/sample artifacts**

```powershell
$forbidden = @('app/routers/api.py','app/routers/doc_api.py','app/routers/llm_api.py','app/tools','app/static','app/database','migrations','pakg','tests','logs')
$forbidden | ForEach-Object { if (Test-Path $_) { throw "Unexpected retained path: $_" } }
Get-ChildItem -Recurse -File | Where-Object { $_.Name -match '\.(bak|swp)$' } | ForEach-Object { throw "Unexpected artifact: $($_.FullName)" }
```

Expected: exit code 0 and no output.

- [ ] **Step 8: Commit the cleanup**

```powershell
git add -A
git commit -m "refactor: retain only document processing API"
```

Expected: one commit containing the implementation plan, source cleanup, and deletions.

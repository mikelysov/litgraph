## 1. Общий parse-модуль

- [x] 1.1 Создать `backend/src/pdf.py` с `parse_pdf_to_paper(file_path) -> Paper`: pypdf-извлечение, детект arXiv ID из имени, `fetch_paper_by_id`, fallback на имя файла
- [x] 1.2 Вынести существующую parse-логику из `mcp_server.ingest_pdf` в `pdf.py`, `ingest_pdf` зовёт её

## 2. URL-ветка в MCP-туле

- [x] 2.1 `ingest_pdf`: `url: str | None = None` + `file_path: str | None = None`, валидация «ровно один из них»
- [x] 2.2 Детект источника: http(s) / arXiv ID / `arxiv.org/abs/<id>` → целевой PDF-URL
- [x] 2.3 Скачать `httpx.stream("GET")` чанками в `INGEST_STAGING_DIR`
- [x] 2.4 Parse → POST `/ingest` → `finally: unlink` staging-файла
- [x] 2.5 Ошибки (404/таймаут/не-PDF) → сообщение + очистка, очередь не трогать

## 3. Upload-эндпоинт

- [x] 3.1 `POST /api/ingest/upload` (FastAPI `UploadFile`) в `api.py`
- [x] 3.2 Стрим чанками (~1MB) в staging, лимит 200MB счётчиком байтов, reject сверх лимита
- [x] 3.3 `parse_pdf_to_paper` + `enqueue_papers` напрямую (без HTTP-самозвонка)
- [x] 3.4 Вернуть `PaperState`-формат; `finally: unlink`
- [x] 3.5 Закрепить `python-multipart` в `pyproject.toml`

## 4. Staging и очистка

- [x] 4.1 Volume `litgraph_staging` (shared) в compose (`api`, `mcp`), env `INGEST_STAGING_DIR=/staging`
- [x] 4.2 TTL-свип осиротевших файлов (`STAGING_TTL`, дефолт 1h): lifespan API + перед ingest; shared volume — API-свип чистит и MCP-сирот, свип также при вызове MCP-тула

## 5. Приёмка

- [ ] 5.1 URL-ингест: staging чист, статус `queued`/`embedded`
- [ ] 5.2 Upload ≤200MB: `{id, status, in_graph}`, staging чист
- [ ] 5.3 Upload >200MB: reject, staging чист
- [ ] 5.4 arXiv ID / abs-ссылка: PDF + метаданные, как path-режим
- [ ] 5.5 Path-режим (`file_path`) не сломан
- [x] 5.6 `cd backend && uv run poe test` — зелёные
- [x] 5.7 `ingest_pdf` без `url`/`file_path` или с обоими → ошибка валидации

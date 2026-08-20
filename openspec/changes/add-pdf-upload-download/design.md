## Context

Сегодня `ingest_pdf` (MCP) — единственный вход для PDF, но читает только с диска сервера внутри `INGEST_PDF_ROOT=/docs`. `/docs` — bind-mount `../docs:/docs:ro`. Транспорт MCP — JSON-аргументы; файловых дескрипторов клиента сервер не видит. Отсюда тупик: «скачать с адреса на диске пользователя» невозможно — для URL сервер тянет сам, для локального файла байты должен толкнуть клиент.

Ограничения, которые не трогаем: worker-конвейер (Redis → эмбеддинги → граф), `paper_index.db`, ArcadeDB, `/ingest` (остаётся точкой входа очереди), существующий path-режим.

## Goals / Non-Goals

**Goals:**
- PDF по URL (интернет + arXiv) — сервер качает сам.
- PDF локальный — multipart-upload, стрим на диск, ≤200MB.
- Staging bounded: получил → обработал → удалил; сироты чистятся.
- Один общий parse-путь (PDF → Paper) для тула и upload-эндпоинта.

**Non-Goals:**
- Стриминг чанками поверх MCP (base64-в-аргументе) — отклонён.
- Обработка не-PDF (docx/epub).
- Авторизация/квоты мультиюзера (за рамками этого change).
- Изменение конвейера эмбеддингов/графа.

## Decisions

### D1: Два транспорта, один parse
```
URL / arXiv ID ──▶ ingest_pdf(url=...)   ──▶ httpx stream ──▶ staging
локальный файл ──▶ POST /api/ingest/upload ──▶ multipart stream ──▶ staging
                                        staging ──▶ parse_pdf_to_paper() ──▶ enqueue
                                        staging ──▶ delete (finally / TTL)
```
`parse_pdf_to_paper(file_path) -> (Paper, page_count, text_len)` — вынести из `mcp_server.py` в `src/pdf.py`: pypdf-извлечение текста, детект arXiv ID из имени/URL, `fetch_paper_by_id` для метаданных, fallback на имя файла. Оба входа зовут её — дубль логики не плодим.

### D2: URL-ветка в MCP-туле
Новый параметр `url: str | None = None`; `file_path` становится `str | None = None`. Валидация: **ровно один** из `url`/`file_path`, иначе ошибка (молчаливого приоритета нет). Детект источника:
- `^https?://` → прямая ссылка на PDF
- `^(\d{4}\.\d{4,5})(v\d+)?$` → arXiv ID → качать `https://arxiv.org/pdf/{id}`
- `arxiv.org/abs/<id>` → парсить ID → то же

Качаем `httpx.stream("GET")` чанками в staging-файл (не держим 200MB в RAM). Имя файла — из URL/ID. Затем `parse_pdf_to_paper` + POST `/ingest` (как сейчас). `finally` — удалить файл.

### D3: Upload-эндпоинт в API
`POST /api/ingest/upload`, `UploadFile` (FastAPI) + `python-multipart`. Стрим чанками в staging (размер чанка ~1MB), лимит 200MB — счётчик байтов при копировании (Content-Length при chunked multipart не гарантирован). После записи — `parse_pdf_to_paper` + `enqueue_papers` напрямую (не HTTP-самозвонок), возврат `{id, status, in_graph}` в формате `PaperState.model_dump()` (единичный объект, `/ingest` возвращает список). `finally` — удалить staging-файл.

Мультиюзер: на этом этапе без авторизации — просто надёжный приём и ограничение размера. Квоты — follow-up.

### D4: Staging-каталог и очистка
- Volume `litgraph_staging` — **один shared named volume**, монтируется в `api` и `mcp` (`/staging`), env `INGEST_STAGING_DIR=/staging`. Оба контейнера видят одни файлы — TTL-свип API чистит и MCP-сирот.
- Не `/docs` (ro и пользовательский) и не `/cache` (там `paper_index.db`).
- Очистка двухуровневая:
  1. `finally: unlink()` после успеха/ошибки ингеста.
  2. TTL-свип: файлы старше `STAGING_TTL` (дефолт 1h) удаляются — на lifespan API + перед каждым ingest. MCP-контейнер lifespan'а не имеет, его сирот кроет API-свип через shared volume + свип при вызове тула.

### D5: python-multipart в pyproject
Сейчас `python-multipart` только транзитивно (через mcp). Для `UploadFile`/`File(...)` FastAPI требует пакет в venv — закрепить в `pyproject.toml`.

## Risks / Trade-offs

- **200MB base64** — не используется; multipart стрим — RAM-безопасен.
- **pypdf на 200MB** — самое медленное место (весь файл читается), сеть не узкое горло. Абстракт всё равно режется до `[:15000]`/`[:10000]` — эмбеддинг по началу текста, как сейчас.
- **SSRF** (URL-ветка): сервер качает произвольные URL — блоклист приватных диапазонов **обязателен до мультиюзер-релиза**, в этом change — follow-up, не блокирует.
- **Гонка TTL-свипа** vs активный ingest: свип удаляет только файлы старше TTL; активная обработка короткая — риск минимален.

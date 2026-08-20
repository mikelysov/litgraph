## Why

Тул `ingest_pdf` (`backend/src/mcp_server.py:86`) умеет читать PDF только с диска сервера: путь резолвится внутри контейнера, жёстко ограничен `INGEST_PDF_ROOT=/docs` (bind-mount `../docs:/docs:ro`, `compose.yml:111`). Пользователь MCP не может передать файл: схема тула — только `file_path: str`, содержимого нет. Итог: сервис бесполезен для любого файла, который уже не лежит в `docs/` на хосте.

Нужно: `ingest_pdf` принимает URL (интернет) — сервер качает сам; локальный файл пользователя — сервер принимает через HTTP-upload. Файл: получил → обработал → данные в БД → файл удалил (хранение на диске не раздувать). Пользователей много.

## What Changes

- **`ingest_pdf` (MCP-тул)**: новый параметр `url` — http(s)-ссылка, arXiv ID или `arxiv.org/abs/<id>`; `file_path` становится опциональным, валидация «ровно один из `url`/`file_path`». Сервер качает PDF сам (httpx stream → staging), дальше существующий путь parse → `/ingest`.
- **Новый `POST /api/ingest/upload`** (multipart/form-data): принимает файл ≤200MB, пишет стримом на staging (не в RAM), парсит, ставит в очередь `/ingest`, **удаляет файл**, возвращает `{id, status, in_graph}` (единичный объект `PaperState`, в отличие от списка у `/ingest`). Локальные файлы пользователь шлёт HTTP-запросом на API (`:8889/api/ingest/upload`), не через MCP-тул.
- **Общая функция parse** `PDF → Paper` (pypdf + arXiv-метаданные) вынесена из `mcp_server.py` в отдельный модуль — используют и тул, и upload-эндпоинт.
- **Staging-каталог**: отдельный writable volume `litgraph_staging` (`INGEST_STAGING_DIR=/staging`) — не `/docs` (ro, пользовательский). Файл живёт только на время обработки.
- **Очистка**: process-then-delete (`finally`) + TTL-свип осиротевших файлов (упавший процесс) на старте и при каждом ingest.
- **base64-транспорт не вводим** (отклонено как лишнее: локальные файлы всегда через `/upload`).

## Capabilities

### New Capabilities

- `pdf-ingest`: приём PDF по URL (сервер качает сам) и через multipart-upload (клиент толкает файл), с bounded staging и удалением файла после индексации.

### Modified Capabilities

- `mcp-server` — тул `ingest_pdf` меняет сигнатуру: `url` добавлен, `file_path` стал опциональным. Main-спек в `openspec/specs/` отсутствует, дельта фиксируется новой capability `pdf-ingest`.

## Impact

- `backend/src/mcp_server.py` — параметр `url` в `ingest_pdf`, вынос parse-логики.
- `backend/src/api.py` — новый `POST /ingest/upload` (multipart).
- Новый модуль (parse PDF → Paper), имя — в design.md.
- `backend/pyproject.toml` — закрепить `python-multipart` (сейчас только транзитивно через mcp).
- `infra/compose.yml` — volume `litgraph_staging` в `api` и `mcp` сервисы, env `INGEST_STAGING_DIR`.
- `AGENTS.md` — раздел Stack/инг. Python (опционально).

## Acceptance Criteria

- [ ] `ingest_pdf(url="https://.../paper.pdf")` качает файл, индексирует, staging чист.
- [ ] `POST /api/ingest/upload` с файлом ≤200MB: принял → статус `queued`/`embedded` → файл на staging отсутствует.
- [ ] arXiv: `ingest_pdf(url="2203.13790")` или `arxiv.org/abs/...` тянет PDF + метаданные, как текущий path-режим.
- [ ] Упавший после скачивания процесс → осиротевший staging-файл удаляется TTL-свипом.
- [ ] Существующий path-режим (`file_path` под `/docs`) продолжает работать.
- [ ] `cd backend && uv run poe test` — существующие тесты зелёные.

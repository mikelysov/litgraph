# pdf-ingest

## ADDED Requirements

### Requirement: Приём PDF по URL — сервер качает сам
Тул `ingest_pdf` принимает параметр `url`: http(s)-ссылку на PDF, arXiv ID (`\d{4}\.\d{4,5}` с опциональным `vN`) или `arxiv.org/abs/<id>`. Сервер скачивает PDF стримом в staging-каталог, парсит, ставит в очередь индексирования и удаляет файл.

#### Scenario: Прямая ссылка на PDF
- **WHEN** клиент вызывает `ingest_pdf(url="https://example.com/paper.pdf")`
- **THEN** сервер скачивает файл в staging, парсит, возвращает подтверждение индексирования, staging-файл удалён

#### Scenario: arXiv ID
- **WHEN** клиент вызывает `ingest_pdf(url="2203.13790")`
- **THEN** сервер качает `https://arxiv.org/pdf/2203.13790`, тянет метаданные через `fetch_paper_by_id`, парсит, индексирует

#### Scenario: arXiv abs-ссылка
- **WHEN** клиент вызывает `ingest_pdf(url="https://arxiv.org/abs/2203.13790v2")`
- **THEN** ID извлекается из URL, PDF качается, версия нормализуется (суффикс `vN` убирается для стабильного ID)

#### Scenario: Недоступный URL
- **WHEN** URL не скачивается (404/таймаут/не-PDF)
- **THEN** тул возвращает сообщение об ошибке, staging-файл удалён, очередь не затронута

#### Scenario: Невалидный вызов (оба параметра или ни одного)
- **WHEN** клиент вызывает `ingest_pdf` без `url` и без `file_path`, либо с обоими сразу
- **THEN** тул возвращает ошибку валидации, ничего не качает, staging/очередь не затронуты

### Requirement: Приём локального файла через multipart-upload
`POST /api/ingest/upload` принимает `multipart/form-data` файл до 200MB, пишет стримом в staging (не загружая целиком в память), парсит, ставит в очередь и удаляет файл. Эндпоинт — HTTP, вызывается напрямую к API (`:8889/api/ingest/upload`), не через MCP-тул.

#### Scenario: Успешный upload
- **WHEN** клиент POST-ит PDF файл на `/api/ingest/upload`
- **THEN** возвращается `{id, status, in_graph}` (формат `PaperState`; `status` — `queued`, либо существующий `embedded` при повторной загрузке), файл на staging отсутствует

#### Scenario: ID из имени файла
- **WHEN** имя загруженного файла — arXiv ID или произвольное имя
- **THEN** paper-id берётся из имени файла с arXiv-детектом (как в path-режиме)

#### Scenario: Превышение лимита размера
- **WHEN** файл больше 200MB
- **THEN** запрос отклонён с 413/4xx, staging не содержит остатков файла

#### Scenario: Не-PDF файл
- **WHEN** загружен файл, из которого не извлекается текст
- **THEN** возвращается ошибка, staging-файл удалён

### Requirement: Bounded staging — файл живёт только на время обработки
Staging-каталог (`INGEST_STAGING_DIR`) — отдельный writable volume, не `/docs`. Файл удаляется после индексирования (успех или ошибка); осиротевшие файлы (упавший процесс) удаляются TTL-свипом.

#### Scenario: Файл удалён после обработки
- **WHEN** ингест завершён (успешно или с ошибкой)
- **THEN** staging-файл отсутствует

#### Scenario: Осиротевший файл
- **WHEN** файл на staging старше TTL (дефолт 1 час)
- **THEN** TTL-свип удаляет его при следующем запуске/ингесте

### Requirement: Обратная совместимость path-режима
Существующий вызов `ingest_pdf(file_path=...)` (путь под `INGEST_PDF_ROOT`) продолжает работать без изменений.

#### Scenario: Путь под /docs
- **WHEN** клиент вызывает `ingest_pdf(file_path="docs/name.pdf")`
- **THEN** поведение идентично текущему (parse + индексация)

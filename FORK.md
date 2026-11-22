# Форк Open WebUI с реестром провайдеров

Репозиторий содержит полную копию [Open WebUI](https://github.com/open-webui/open-webui) `0.13.4`
(лицензия — BSD-3, см. `LICENSE`) и два дополнения:

1. **Настройки → Провайдеры** — панель, где для каждого провайдера моделей задаются
   ссылка (base URL), ключ API / токен, тип авторизации, список моделей и
   дополнительные заголовки.
2. **Сборка в GitHub Actions** — CI (`Build`), публикация образов в GHCR (`Docker images`)
   и релизы из `CHANGELOG.md` (`Release`).

---

## 1. Панель «Провайдеры»

Открывается у администратора: **иконка профиля → Настройки → раздел Admin → «Провайдеры»**
(рядом с «Connections»). Для каждого провайдера поле за полем:

| Поле | Назначение |
| --- | --- |
| Название | любое имя, попадет в подпись модели |
| Тип API | `OpenAI compatible`, `Anthropic`, `Google Gemini`, `Ollama`, `Custom` |
| Базовый адрес API | ссылка вида `https://api.openai.com/v1` — **без** `/chat/completions` |
| Ключ API / токен | `sk-…`, `gsk_…` и т. п.; пустое поле = оставить сохранённый ключ |
| Способ авторизации | `Authorization: Bearer …`, «Свой заголовок» (`x-api-key`, `api-key`, …) или без авторизации |
| Разрешённые модели | по одному id в строке; пусто = все модели, которые вернул провайдер |
| Дополнительные заголовки | любые `Key: Value`, например `HTTP-Referer`, `X-Title` |
| Префикс id | `prefix_id`, чтобы модели разных провайдеров не пересекались |
| Переключатель | включает/выключает провайдера |

Кнопки карточки: **Save** (сохранить и применить), **Test** (проверить доступ и
получить число моделей + задержку), **Import model list** (загрузить список моделей
провайдера и сохранить его как allow-list), **Delete**.

Кнопка **Apply** сверху записывает включённых провайдеров в штатные настройки
Open WebUI — `openai.api_base_urls` / `openai.api_keys` / `openai.api_configs` и
`ollama.base_urls` / `ollama.api_configs`. Это ровно те же настройки, которые
редактирует «Admin Settings → Connections», поэтому чат, генерация картинок и
служебные задачи работают без каких-либо правок в конвейере запросов. Подключения,
добавленные вручную во вкладке Connections, не трогаются: принадлежат панели только
записи с `managed_by: "providers"`.

### Пресеты

Вверху панели есть чипы быстрых пресетов: OpenAI, Anthropic, Google Gemini, DeepSeek,
Mistral, Groq, OpenRouter, xAI, Together, Fireworks, Azure OpenAI, Ollama, LM Studio,
llama.cpp, vLLM и «Custom». Пресет заполняет ссылку и тип авторизации — остаётся
вставить ключ.

### Переменные окружения

```bash
# Провайдеры, которые подставятся при первом запуске (пока настройка не записана в БД)
PROVIDERS_JSON='[{"name":"OpenAI","base_url":"https://api.openai.com/v1","api_key":"sk-..."},
                 {"name":"Ollama","kind":"ollama","base_url":"http://ollama:11434"}]'
PROVIDERS_AUTO_APPLY=true   # сразу применить их к Connections (по умолчанию true)
```

### HTTP API

Все методы доступны администратору (`Authorization: Bearer <WEBUI_TOKEN>`):

| Метод | Путь | Описание |
| --- | --- | --- |
| `GET` | `/api/v1/providers/` | список провайдеров (ключ замаскирован, `?reveal=true` — полный) |
| `POST` | `/api/v1/providers/` | создать |
| `PUT` | `/api/v1/providers/{id}` | обновить (`api_key: null` = не менять ключ) |
| `DELETE` | `/api/v1/providers/{id}` | удалить и переприменить подключения |
| `POST` | `/api/v1/providers/{id}/test` | проверка доступности + число моделей |
| `POST` | `/api/v1/providers/{id}/models?save=true` | импорт списка моделей |
| `POST` | `/api/v1/providers/preview/test` | проверка несохранённой формы |
| `POST` | `/api/v1/providers/apply` | применить всех включённых провайдеров |
| `GET` | `/api/v1/providers/state` | когда и сколько подключений применено |

Пример:

```bash
curl -s -X POST http://localhost:3000/api/v1/providers/ \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"DeepSeek","kind":"openai","base_url":"https://api.deepseek.com/v1",
       "api_key":"sk-...","model_ids":["deepseek-chat"],"enabled":true}'
```

> Ключи хранятся в БД Open WebUI так же, как ключи, введённые во вкладке Connections
> (в открытом виде для администратора). Не коммитьте секреты в репозиторий — используйте
> переменные окружения или переменные/секреты репозитория GitHub.

---

## 2. Сборка

### Локально

```bash
npm ci                      # зависимости фронтенда
npm run dev                 # vite на :5173, проксирует /api на :8080
# в другом терминале:
cd backend && python -m uvicorn open_webui.main:app --port 8080 --reload
```

Сборка статического фронтенда без обращения к CDN Pyodide:

```bash
SKIP_PYODIDE_FETCH=true npm run build   # результат в build/
```

Docker-образ (multi-stage: `build` — Node 22, затем Python 3.11 slim):

```bash
docker build -t open-webui-fork .
docker run -d -p 3000:8080 -v open-webui:/app/backend/data open-webui-fork
# или:
docker compose -f docker-compose.providers.yaml up -d --build
```

Полезные build-аргументы: `USE_CUDA=true`, `USE_OLLAMA=true`, `USE_SLIM=true`.

### GitHub Actions

| Workflow | Файл | Когда | Что делает |
| --- | --- | --- | --- |
| `Build` | `.github/workflows/build.yml` | push в `main`/`dev`, PR, ручной запуск | `npm ci` → `crypto:verify` → юнит-тесты → `vite build` → артефакт `open-webui-frontend`; бэкенд: `compileall`, `ruff`, `pytest backend/tests`; smoke-сборка Docker-образа |
| `Docker images` | `.github/workflows/docker.yaml` | push в `main`/`dev`, тег `v*`, ручной запуск | сборка `main`/`slim`/`ollama`(+`cuda` на тегах) для `linux/amd64` и `linux/arm64`, публикация в `ghcr.io/<владелец>/<репозиторий>` c тегами `latest`, `<sha>`, `<version>` |
| `Release` | `.github/workflows/release.yml` | push в `main` с изменённым `package.json` | создаёт GitHub Release из `CHANGELOG.md` и запускает `docker.yaml` |

Что нужно включить в настройках репозитория:

- **Settings → Actions → General → Workflow permissions**: Read and write (для публикации пакетов).
- Secrets не обязательны: образы пушатся в GHCR под `GITHUB_TOKEN`.
- Если нужен образ на Docker Hub — добавьте job вручную, в форке он удалён вместе с
  upstream-автоматизацией (helm-charts, копирование на Docker Hub, ISSUE-боты).

Скачать собранный фронтенд: вкладка **Actions → последний прогон Build → артефакт
`open-webui-frontend`** (tar.gz каталога `build/`).

---

## 3. Что изменено в коде форка

```
backend/open_webui/routers/providers.py          # реестр провайдеров + проекция в Connections
backend/open_webui/main.py                       # регистрация /api/v1/providers
backend/tests/test_providers_registry.py         # юнит-тесты (без БД и сервера)
src/lib/apis/providers/index.ts                  # клиент API провайдеров
src/lib/components/admin/Settings/Providers.svelte
src/lib/components/admin/Settings/Providers/ProviderCard.svelte
src/lib/components/admin/Settings/Providers/presets.ts
src/lib/components/admin/Settings/AdminTabIcon.svelte
src/lib/components/chat/SettingsModal.svelte     # вкладка «Провайдеры»
src/lib/i18n/locales/en-US|ru-RU/translation.json
scripts/prepare-pyodide.js                       # SKIP_PYODIDE_FETCH для офлайн-сборок
.github/workflows/*                              # CI и публикация образов
.env.example, docker-compose.providers.yaml      # PROVIDERS_JSON
```

Обновление до нового релиза Open WebUI: слейте `upstream/main` — панель провайдеров
не правит файлы конвейера запросов, конфликты возможны только в
`main.py` (строка регистрации роутера) и `SettingsModal.svelte` (вкладка).

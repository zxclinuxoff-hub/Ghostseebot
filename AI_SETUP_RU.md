# GhostSee AI — настройка пяти провайдеров

Команда `.ai` использует один и тот же `AI_SYSTEM_PROMPT` для всех провайдеров. Сначала выполняется бесплатный веб-поиск DuckDuckGo, затем найденные сниппеты/тексты страниц передаются модели. Содержимое сайтов явно помечается как недоверенные данные.

## Подключаемые слоты

1. **Google Gemini** — отдельный ключ Google AI Studio. OpenAI-compatible endpoint: `https://generativelanguage.googleapis.com/v1beta/openai`. Модель по умолчанию: `gemini-3.8-flash`.
2. **Groq** — отдельный ключ GroqCloud. Endpoint: `https://api.groq.com/openai/v1`. Модель: `openai/gpt-oss-120b`.
3. **Cloudflare Workers AI** — отдельный Cloudflare API token и Account ID. OpenAI-compatible endpoint собирается автоматически. Модель по умолчанию: `@cf/zai-org/glm-4.7-flash`, которая доступна на Workers Free.
4. **OpenRouter** — использует `AI_OPENROUTER_API_KEY`, а если он пустой — прежний `AI_API_KEY`. По умолчанию `recursive/flint-v1.0:free`.
5. **Дополнительный API** — необязательный пятый слот для любого совместимого с OpenAI API сервиса: укажи его key, base URL и model.

## Переменные Render

Добавь в Render → GhostSee → Environment. Секретные ключи вставляй только в поля Value Render, не в GitHub и не в этот файл.

| Key | Value / назначение |
|---|---|
| `AI_API_KEY` | Твой существующий OpenRouter API key. Не удаляй: нужен для `.sound` и как резерв OpenRouter |
| `AI_BASE_URL` | `https://openrouter.ai/api/v1` |
| `AI_MODEL` | `recursive/flint-v1.0:free` |
| `AI_GEMINI_API_KEY` | Ключ Google AI Studio |
| `AI_GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `AI_GEMINI_MODEL` | `gemini-3.8-flash` |
| `AI_GROQ_API_KEY` | Ключ GroqCloud |
| `AI_GROQ_BASE_URL` | `https://api.groq.com/openai/v1` |
| `AI_GROQ_MODEL` | `openai/gpt-oss-120b` |
| `AI_CLOUDFLARE_API_KEY` | Cloudflare API Token с разрешением Workers AI |
| `AI_CLOUDFLARE_ACCOUNT_ID` | Account ID из панели Cloudflare |
| `AI_CLOUDFLARE_MODEL` | `@cf/zai-org/glm-4.7-flash` |
| `AI_OPENROUTER_API_KEY` | Можно не добавлять: будет использован `AI_API_KEY` |
| `AI_OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` |
| `AI_OPENROUTER_MODEL` | `recursive/flint-v1.0:free` |
| `AI_EXTRA_NAME` | Название пятого API (опционально) |
| `AI_EXTRA_API_KEY` | Ключ пятого API (опционально) |
| `AI_EXTRA_BASE_URL` | Base URL пятого API без `/chat/completions` (опционально) |
| `AI_EXTRA_MODEL` | ID модели пятого API (опционально) |
| `AI_PROVIDER_ORDER` | `gemini,groq,cloudflare,openrouter,extra` |
| `AI_SYSTEM_PROMPT` | Общий промпт, одинаковый для всех моделей |
| `AI_MAX_OUTPUT_TOKENS` | `1200` |
| `AI_TIMEOUT_SECONDS` | `35` |
| `AI_TTS_MODEL` | `heygen/heygen-voice-1-turbo:free` |
| `AI_TTS_VOICE` | `nadine` |
| `AI_TTS_FORMAT` | `mp3` |

Остальные переменные бота не меняй: `BOT_TOKEN`, `ADMIN_IDS`, `SUPABASE_URL`, `SUPABASE_KEY`, `CHANNEL`, `BOT_USERNAME`, `WEBHOOK_SECRET` и другие существующие значения.

## Как работает переключение

Провайдеры, для которых указан API-ключ, включаются автоматически. Начальный провайдер выбирается по round-robin, чтобы не отправлять каждый запрос только в одну сеть. Если провайдер вернул ошибку, 429, пустой ответ или timeout, бот пробует остальные настроенные провайдеры. Все получают одинаковые system prompt и web context. В рамках одного процесса это распределяет нагрузку; при нескольких Render instances счётчик ротации у каждого процесса отдельный.

## Важные ограничения

- Пять подключений не означают гарантированные пять одинаковых бесплатных квот: лимиты, доступные модели и условия бесплатного доступа задаёт каждый провайдер и они меняются.
- Gemini лимитирует по проекту, а не по числу API-ключей внутри проекта. Groq, Cloudflare Workers AI и OpenRouter имеют собственные отдельные лимиты. Cloudflare Workers AI предоставляет 10 000 Neurons в сутки бесплатно; после исчерпания дневной квоты запросы будут отклоняться на бесплатном плане.
- OpenRouter free tier отдельно ограничен; не считай его единственным запасом мощности.
- Бесплатные тарифы не дают гарантии обслуживания для 1000 одновременных активных пользователей. Для стабильной нагрузки потребуется платный тариф/резерв или локальная инфраструктура.
- Если не заполнен ключ провайдера, он пропускается. Пятый слот — дополнительный, а не обязательный.
- `.sound` по-прежнему использует `AI_API_KEY` и OpenRouter TTS; новые текстовые ключи не заменяют его.

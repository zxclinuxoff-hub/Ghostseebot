# GhostSeeBot (aiogram 3) — Telegram Business бот

Единая подписка «Всё включено»: удалённые и изменённые сообщения, временные фото («сии»), команды.
Тариф: 7 дней бесплатно → 1 мес — 40⭐, 3 мес — 100⭐, 1 год — 360⭐. Рефералы, рулетка, партнёрка, админ-панель, логи.

## Структура
```
main.py                  вход: webhook-сервер (aiohttp) или long polling, обработчик ошибок → админу
schema.sql               таблицы Supabase (префикс gs_)
assets/                  твои баннеры: banner_start.jpg (инструкция), banner_main.png (главное меню)
bot/config.py            настройки, тарифы
bot/db.py                клиент Supabase
bot/keyboards.py         inline-клавиатуры
bot/texts.py             справка по командам
bot/services/            users · billing · referrals · roulette · scheduler · biz (Business API) · logs
bot/handlers/            start (меню, кабинет, рефералы, рулетка, настройки) · payments · admin · business
bot/commands/            engine (реестр) · tools (все .команды)
```

## Установка
1. **Supabase** → SQL Editor → вставь `schema.sql` → Run.
2. **GitHub**: залей проект (с сохранением папок).
3. **Render** → New → Web Service → репозиторий. Build: `pip install -r requirements.txt`, Start: `python main.py` (или Blueprint из `render.yaml`).
4. **Environment** (см. `.env.example`): `BOT_TOKEN`, `ADMIN_IDS`, `SUPABASE_URL`, `SUPABASE_KEY` (secret-ключ), `WEBHOOK_BASE_URL` (адрес сервиса на Render), `WEBHOOK_SECRET`, `CHANNEL`, `BOT_USERNAME`.
5. **Канал**: добавь бота **админом** в @ghostsee_channel — иначе проверка подписки для рефералов не работает.
6. **cron-job.org**: GET `https://ТВОЙ-СЕРВИС.onrender.com/health` каждые 10 минут (на бесплатном Render сервис засыпает, пинг его будит и держит фоновые задачи).
7. @BotFather → Bot Settings → **Business Mode** включить. Потом в Telegram: Настройки → Автоматизация чатов → ввести @ghostseebot → Добавить (права: читать, отвечать, удалять, менять имя).

Локально без вебхука: оставь `WEBHOOK_BASE_URL` пустым — запустится long polling.

## Админ-панель (`/admin`, только ADMIN_IDS)
`/give @user 7d|3m|1y` · `/take @user [30d]` · `/ban` `/unban` · `/user` · `/stats` · `/logs [level] [N]` · `/broadcast` (текст/фото + кнопки, предпросмотр) ·
`/partner_add ID процент [код]` · `/partners` · `/payout код звёзды` · `/refund USER_ID CHARGE_ID`

## Рефералы
2 друга → +3 дня · 5 друзей → +8 дней всего (ещё +5) · далее +1 день за каждого. Засчитывается, только если друг запустил бота по ссылке и подписан на канал.

## Рулетка (раз в 24 ч)
+1 день 70% · +2 дня 10% · +3 дня 5% · скидка до 50% на год 7% · скидка до 20% на 3 месяца 8%.

## Партнёрка
`/partner_add` создаёт ссылку `?start=p_КОД`. С каждой покупки Stars привлечённых пользователей партнёру начисляется процент; выплата вручную (`/payout`).

## Чего нет и почему
- **Трекер прочтений** — Telegram не присылает ботам события «собеседник прочитал», технически невозможно.
- **`.pinf`, `.spinf`, `.plink`, `.clonep`** — слежка за профилями и фишинговые ссылки, не реализовано.

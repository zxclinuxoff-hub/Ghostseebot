TRACKER_MODULE = """🖥️ <b>Модуль: Трекер сообщений</b>

Следит за всеми личными переписками — даже когда Telegram закрыт.

• <b>Удаление и редактирование:</b> бот пришлёт тебе оригинал.
• <b>Одноразовые медиа:</b> ответь любым текстом на такое сообщение — бот сохранит его тебе.

⚙️ <b>Настройки:</b> в настройках бота можно включить «тихий режим» — он полностью отключает эти уведомления. Либо можно настроить под себя отдельные типы оповещений."""

from .config import cfg

SUPPORT_BOT = "ghostseeHelper_robot"

# ---------------- Туториал (3 экрана) ----------------
TUTORIAL = [
    f"""📖 <b>Туториал</b> · шаг 1 из 3
<b>🔌 Подключение бота</b>
━━━━━━━━━━━━━━

1️⃣ Открой <b>Настройки</b> Telegram
2️⃣ Зайди в <b>Автоматизация чатов</b>
3️⃣ В поиске введи <code>@{cfg.bot_username}</code> и нажми <b>Добавить</b>
4️⃣ Выдай права: <b>читать</b>, <b>отвечать</b>, <b>удалять</b> сообщения (и «менять имя» — для <code>.time</code>)
5️⃣ Чаты: лучше «Все личные чаты, кроме…»

✅ Бот напишет «Подключён» — готово!

⚠️ Нужна подписка на канал {cfg.channel}, иначе бот не работает.""",

    f"""📖 <b>Туториал</b> · шаг 2 из 3
<b>👁 Что бот делает сам</b>
━━━━━━━━━━━━━━

🗑 <b>Удалённые</b> — собеседник удалил сообщение? Бот пришлёт его тебе в личку (текст и медиа).

✏️ <b>Изменённые</b> — покажу, что было и что стало.

👁 <b>Исчезающие фото, видео, кружки</b> — ответь (reply) на такое сообщение:
 • ответ <b>сии</b> — бот достанет медиа, твой ответ удалится
 • ответ <b>любым другим текстом</b> — бот достанет медиа, твой ответ остаётся
Медиа придёт сюда, в чат с ботом.

🔔 Что присылать — настраивается в ⚙️ Настройках.
ℹ️ Бот видит только то, что написали после подключения.""",

    f"""📖 <b>Туториал</b> · шаг 3 из 3
<b>⌨️ Команды и бонусы</b>
━━━━━━━━━━━━━━

В любом личном чате пиши команду с точкой (или «/»):
<code>.afk ушёл ужинать</code> — режим AFK
<code>.mute</code> — заглушить собеседника (восстановление ≤5 раз подряд)
<code>.tl en привет</code> — перевод
<code>.remind 10m позвонить</code> — напоминание
<code>.dox</code> — шуточный «пробив» 😈

Полный список с примерами — в разделе <b>🛠 Команды</b>.

🎁 <b>Как получить больше</b>
 • 7 дней бесплатно при старте
 • 👥 приглашай друзей — бонусные дни
 • 🎰 рулетка раз в сутки

Вопросы — в 💬 Поддержку. Приятного пользования! 👻""",
]

# ---------------- Команды по категориям ----------------
CMD_CATEGORIES = {
    "foe": ("🔇 Собеседник", """<b>🔇 Команды для собеседника</b>
Пиши прямо в чате с человеком (префикс <code>.</code> или <code>/</code>)

<code>.mute</code> — заглушить: все его сообщения сразу удаляются. Сообщение восстанавливается не больше 5 раз подряд: если его удаляют снова и снова, у собеседника, скорее всего, жёсткий мут.
⚠️ С подключённым юзерботом мут нельзя обойти через <code>.nomute</code> даже другими ботами.
<code>.unmute</code> — снять мут
<code>.nomute</code> — обход чужого мута: если сообщение удалили сразу — бот отправит ещё раз (лимит 5 восстановлений подряд). Повторно <code>.nomute</code> — выключить. С юзерботом у собеседника обход не сработает.
<code>.warn [причина]</code> — предупреждение, на 3-м автомут
<code>.wsag</code> — вкл/выкл удаление его стикеров и гифок
<code>.wbl</code> — вкл/выкл удаление его мата
<code>.bw слово слово</code> — удалять сообщения с этими словами · <code>.bw off</code> — очистить
<code>.clone</code> — эхо: повторяю его сообщения
<code>.troll</code> — агрессивный троллинг: отвечаю на каждое сообщение едкой фразой · повторно — выкл
<code>.spam 5 текст</code> — повторить сообщение (до 35)
<code>.spamg слово слово</code> — каждое слово отдельным сообщением (до 100)
<code>.haha 10</code> — смех «ХВХАХАХ» (до 35)
<code>.imit typing|voice|video|photo|file|round [сек]</code> — имитация «печатает…»
<code>.dox</code> — шуточный «пробив» с анимацией (ответом на его сообщение). Ничего не ищет — просто розыгрыш 😈"""),

    "auto": ("🌙 AFK и автоматика", """<b>🌙 AFK и автоматика</b>

<code>.afk [текст]</code> — режим AFK: собеседникам отвечаю с таймером «Прошло: X мин.»
<code>.unafk</code> — выключить AFK
<code>.afk_ex</code> — не отправлять AFK этому собеседнику · <code>.afk_unex</code> — вернуть
<code>.burn 30 текст</code> — самоудаляющееся сообщение (30 сек, можно 1m)
<code>.bchat 10m</code> — мои сообщения в чате удаляются через 10 мин · <code>.bchat off</code>
<code>.remind 10m текст</code> — напомню тебе в личку
<code>.remindf 10m текст</code> — напомню прямо в чат
<code>.time on [Europe/Moscow]</code> — время в имени профиля · <code>.time off</code>
<code>.del [N]</code> — удалить последние N моих сообщений в чате

<i>Время: s — сек, m — мин, h — час, d — день (или с, м, ч, д).</i>"""),

    "text": ("✍️ Текст и оформление", """<b>✍️ Текст и оформление</b>
Пиши команду и текст — или ответь командой на сообщение.
Режим: <code>.bold</code> без текста включит жирный для каждого твоего нового сообщения в этом чате, <code>.unbold</code> выключит. Так же работают <code>.italic</code>, <code>.mono</code>, <code>.line</code>, <code>.crossed</code>, <code>.hidden</code>, <code>.quote</code>, <code>.code</code> (выключение — <code>.un…</code>).

<code>.bold</code> <b>жирный</b> · <code>.italic</code> <i>курсив</i> · <code>.mono</code> <code>моно</code>
<code>.line</code> <u>подчёркнутый</u> · <code>.crossed</code> <s>зачёркнутый</s>
<code>.hidden</code> — скрытый текст (спойлер) · <code>.quote</code> — цитата · <code>.code</code> — блок кода
<code>.morse</code> — шифр Морзе туда-обратно (<code>.morse en</code> — латиница)
<code>.sw</code> — исправить раскладку (ghbdtn → привет)
<code>.anim</code> — текст «набирается» посимвольно
<code>.type</code> — печатает по словам
<code>.love</code> ❤️ · <code>.fire</code> 🔥 · <code>.snow</code> ❄️ · <code>.boom</code> 💥 · <code>.cum</code> 🥵 — анимации"""),

    "tools": ("🧰 Утилиты", """<b>🧰 Утилиты</b>

<code>.canary [название]</code> — прозрачная ссылка-маячок (только факт/время клика)
<code>.canary_stats</code> — статистика кликов по последним ссылкам
<code>.fake_react ❤️</code> — макет реакции в личке владельца (не реальная реакция)
<code>.exif</code> — ответом на фото: EXIF и GPS (если сохранились; отчёт владельцу в личку)
<code>.ai вопрос</code> — спросить ИИ
<code>.tl [en] текст</code> — перевод (по умолчанию на русский; работает и ответом на сообщение)
<code>.rates</code> — курсы валют · <code>.rates 100 usd rub</code> — конвертер
<code>.short ссылка</code> — сократить · <code>.unshort ссылка</code> — раскрыть
<code>.link текст | url</code> — ссылка с текстом
<code>.qr текст</code> — QR-код
<code>.geo 55.75 37.61</code> — отправить точку на карте
<code>.info</code> — ID и данные собеседника (ответом на его сообщение)
<code>.help</code> — краткая справка"""),

    "fun": ("🎲 Игры", """<b>🎲 Игры и приколы</b>

<code>.flip</code> — орёл или решка
<code>.roll</code> — случайное число (<code>.roll 1 100</code>)
<code>.ball вопрос</code> — магический шар
<code>.rps</code> — камень-ножницы-бумага
<code>.revo</code> — русская рулетка
<code>.duel</code> — дуэль на револьверах
<code>.haha 10</code> — смех · <code>.dox</code> — шуточный «пробив»"""),

    "media": ("👁 Временные фото", """<b>👁 Исчезающие фото, видео и кружки</b>

Ответь (reply) на такое сообщение одним из слов:
 • ответ <b>сии</b> — бот достанет медиа, твой ответ удалится
 • ответ <b>любым другим текстом</b> — бот достанет медиа, твой ответ остаётся

Медиа приходит в чат с ботом. Звук уведомления можно отключить в ⚙️ Настройках.

<b>🗑 Удалённые и ✏️ изменённые</b> сообщения собеседников бот присылает сам."""),

    "new": ("🆕 Новые функции", """<b>🆕 Новые функции</b>

<code>.antispam</code> — включить антиспам (удаляет сообщения с множеством ссылок, капсом и повторами) · <code>.unantispam</code> — выключить
<code>.autoreply фраза1 | фраза2</code> — автоответчик со случайной фразой · <code>.unautoreply</code> — выключить
<code>.react</code> — автореакция ❤️ на каждое сообщение собеседника · <code>.unreact</code> — выключить
<code>.voice</code> — перевод голосовых в текст (отправляется в личку) · <code>.unvoice</code> — выключить
<code>.translate</code> — автоперевод иностранных сообщений на русский · <code>.untranslate</code> — выключить
<code>.cold</code> — режим «холод»: ледяные ответы на каждое сообщение · <code>.uncold</code> — выключить"""),
}

# краткий список (его же показывает команда .help)
HELP_CMDS = """<b>🛠 Команды</b> (префикс <code>.</code> или <code>/</code>)

🔇 <b>Собеседник:</b> .mute .unmute .nomute .warn .wsag .wbl .bw .clone .troll .spam .haha .spamg .imit .dox
🌙 <b>Автоматика:</b> .afk .unafk .burn .bchat .remind .remindf .time .del
✍️ <b>Текст:</b> .bold/.unbold .italic/.unitalic .mono .line .crossed .hidden .quote .code .morse .sw .anim .type .love .fire .snow .boom .cum
🧰 <b>Утилиты:</b> .ai .tl .rates .short .unshort .link .qr .geo .info
🎲 <b>Игры:</b> .flip .roll .ball .rps .revo .duel
👁 <b>Временные фото:</b> ответь на фото любым сообщением. «сии» — одноразовое, твой ответ удалится
🆕 <b>Новое:</b> .antispam .autoreply .react .voice .translate .cold (и их un- версии)

Подробно с примерами: /start → 🛠 Функционал"""


CMD_INFO = {
    'fake_react': '<code>.fake_react ❤️</code> — макет реакции\n\n<blockquote>Показывает в личке, как выглядела бы реакция на сообщение. Настоящую реакцию собеседник не видит.\n\nФормат ввода:\n<code>.fake_react ❤️</code> ответом на сообщение</blockquote>',
    'afk_ex': '<code>.afk_ex</code> — исключить этого собеседника из AFK\n\n<blockquote>Пиши в диалоге с нужным человеком. После этого ему не будет уходить AFK-ответ.\n\nФормат ввода:\n<code>.afk_ex</code></blockquote>',
    'afk_unex': '<code>.afk_unex</code> — вернуть AFK-ответ этому собеседнику\n\n<blockquote>Убирает человека из исключений .afk.\n\nФормат ввода:\n<code>.afk_unex</code></blockquote>',
    'unafk': '<code>.unafk</code> — выключить AFK\n\n<blockquote>Режим AFK выключается для всех собеседников. Исключения сохраняются.\n\nФормат ввода:\n<code>.unafk</code></blockquote>',
    'unantispam': '<code>.unantispam</code> — выключить антиспам\n\n<blockquote>Отключает фильтр, который удаляет спам в чате.\n\nФормат ввода:\n<code>.unantispam</code></blockquote>',
    'unautoreply': '<code>.unautoreply</code> — выключить автореплай\n\n<blockquote>Останавливает случайные фразы-ответы в этом чате.\n\nФормат ввода:\n<code>.unautoreply</code></blockquote>',
    'unbchat': '<code>.unbchat</code> — выключить автоудаление сообщений\n\n<blockquote>Свои сообщения в этом чате перестают удаляться по таймеру.\n\nФормат ввода:\n<code>.unbchat</code></blockquote>',
    'unclone': '<code>.unclone</code> — выключить клон\n\n<blockquote>Перестаёт повторять сообщения собеседника в этом чате.\n\nФормат ввода:\n<code>.unclone</code></blockquote>',
    'uncold': '<code>.uncold</code> — выключить холодные ответы\n\n<blockquote>Бот перестаёт отвечать короткими фразами на каждое сообщение.\n\nФормат ввода:\n<code>.uncold</code></blockquote>',
    'unnomute': '<code>.unnomute</code> — выключить обход мута\n\n<blockquote>Повторная отправка удалённых сообщений прекращается.\n\nФормат ввода:\n<code>.unnomute</code></blockquote>',
    'unreact': '<code>.unreact</code> — выключить автореакцию\n\n<blockquote>Бот перестаёт ставить ❤️ на сообщения собеседника.\n\nФормат ввода:\n<code>.unreact</code></blockquote>',
    'unshort': '<code>.unshort</code> — выключить сокращение ссылок\n\n<blockquote>Ссылки в этом чате больше не сокращаются.\n\nФормат ввода:\n<code>.unshort</code></blockquote>',
    'untranslate': '<code>.untranslate</code> — выключить перевод\n\n<blockquote>Перевод иностранных сообщений собеседника выключается.\n\nФормат ввода:\n<code>.untranslate</code></blockquote>',
    'untroll': '<code>.untroll</code> — выключить троллинг\n\n<blockquote>Бот перестаёт отвечать троллящими фразами.\n\nФормат ввода:\n<code>.untroll</code></blockquote>',
    'unwbl': '<code>.unwbl</code> — выключить чёрный список слов\n\n<blockquote>Сообщения с запрещёнными словами перестают удаляться.\n\nФормат ввода:\n<code>.unwbl</code></blockquote>',
    'unwsag': '<code>.unwsag</code> — выключить фильтр стикеров и гифок\n\n<blockquote>Стикеры и гифки собеседника перестают удаляться.\n\nФормат ввода:\n<code>.unwsag</code></blockquote>',
    'decrypt': '<code>.decrypt</code> — расшифровка\n\n<blockquote>Обратная операция к <code>.encrypt</code>: сдвигает латинские буквы назад на 3.\n\nФормат ввода:\n<code>.decrypt текст</code> или ответом на сообщение</blockquote>',
    'emoji': '<code>.emoji</code> — эмодзи-строка\n\n<blockquote>Повторяет переданный символ или текст в виде строки. Без аргумента — 👻.\n\nФормат ввода:\n<code>.emoji 🔥</code></blockquote>',
    'help': '<code>.help</code> — справка по командам\n\n<blockquote>Полный список команд приходит одним сообщением в личку.\n\nФормат ввода:\n<code>.help</code></blockquote>',
    'cmds': '<code>.cmds</code> — то же, что <code>.help</code>\n\n<blockquote>Полный список команд приходит в личку.\n\nФормат ввода:\n<code>.cmds</code></blockquote>',
    'afk': '<code>.afk</code> — AFK\n\n<blockquote>Автоответ, пока тебя нет. Если ты в сети (писал или нажимал что-то в Telegram за последние 5 минут), автоответ не отправляется.\n\nФормат ввода:\n<code>.afk отошёл</code>\nснять: <code>.unafk</code></blockquote>',
    'ai': '<code>.ai</code> — нейросеть\n\n<blockquote>Запрос к ИИ (если включён ключ на сервере).\n\nФормат ввода:\n<code>.ai вопрос</code></blockquote>',
    'anim': '<code>.anim</code> — анимация\n\n<blockquote>Показывает короткую emoji-анимацию в чате.\n\nФормат ввода:\n<code>.anim</code></blockquote>',
    'antispam': '<code>.antispam</code> — антиспам\n\n<blockquote>Режет спам-сообщения в чате.\n\nФормат ввода:\n<code>.antispam</code> / <code>.unantispam</code></blockquote>',
    'autoreply': '<code>.autoreply</code> — автореплай\n\n<blockquote>Синоним автоответа.\n\nФормат ввода:\n<code>.autoreply текст</code></blockquote>',
    'ball': '<code>.ball</code> — шар судьбы\n\n<blockquote>Ответ на вопрос да/нет.\n\nФормат ввода:\n<code>.ball повезёт?</code></blockquote>',
    'bchat': '<code>.bchat</code> — таймер чата\n\n<blockquote>Все твои сообщения в чате удаляются через N сек.\n\nФормат ввода:\n<code>.bchat 30</code>\nвыкл: <code>.unbchat</code></blockquote>',
    'bomb': '<code>.bomb</code> — бомба\n\n<blockquote>Сообщение с таймером самоудаления.\n\nФормат ввода:\n<code>.bomb 15 текст</code></blockquote>',
    'boom': '<code>.boom</code> — взрыв\n\n<blockquote>Анимация взрыва.\n\nФормат ввода:\n<code>.boom</code></blockquote>',
    'burn': '<code>.burn</code> — самоудаление\n\n<blockquote>Сообщение удалится через N сек.\n\nФормат ввода:\n<code>.burn 10 секрет</code></blockquote>',
    'bw': '<code>.bw</code> — чёрный список слов\n\n<blockquote>Удаляет сообщения со словами из списка.\n\nФормат ввода:\n<code>.bw слово1 слово2</code>\nочистить: <code>.bw off</code></blockquote>',
    'calc': '<code>.calc</code> — калькулятор\n\n<blockquote>Считает выражение.\n\nФормат ввода:\n<code>.calc 2+2*3</code></blockquote>',
    'canary': '<code>.canary</code> — ссылка-маяк\n\n<blockquote>Прозрачная ссылка: узнаешь, когда её откроют (без IP).\n\nФормат ввода:\n<code>.canary метка</code></blockquote>',
    'canary_stats': '<code>.canary_stats</code> — статистика маяков\n\n<blockquote>Клики по твоим canary-ссылкам.\n\nФормат ввода:\n<code>.canary_stats</code></blockquote>',
    'check': '<code>.check</code> — проверка\n\n<blockquote>Быстрая проверка @user или ссылки.\n\nФормат ввода:\n<code>.check @user</code></blockquote>',
    'clone': '<code>.clone</code> — клон\n\n<blockquote>Повторяет сообщения собеседника от твоего имени (осторожно).\n\nФормат ввода:\n<code>.clone</code> / <code>.unclone</code></blockquote>',
    'cold': '<code>.cold</code> — холод\n\n<blockquote>Короткие сухие ответы собеседнику.\n\nФормат ввода:\n<code>.cold</code> / <code>.uncold</code></blockquote>',
    'core': '<code>.core</code> — core-статус\n\n<blockquote>Служебный статус чата (mute/afk/warns).\n\nФормат ввода:\n<code>.core</code></blockquote>',
    'cum': '<code>.cum</code> — спец-эффект\n\n<blockquote>Шуточная анимация/эффект в чате.\n\nФормат ввода:\n<code>.cum</code></blockquote>',
    'date': '<code>.date</code> — дата\n\n<blockquote>Текущая дата и время.\n\nФормат ввода:\n<code>.date</code></blockquote>',
    'del': '<code>.del</code> — удалить\n\n<blockquote>Удаляет сообщение (reply) или своё.\n\nФормат ввода:\nreply + <code>.del</code></blockquote>',
    'dox': '<code>.dox</code> — «докс»-шутка\n\n<blockquote>Шуточный «скан» собеседника. Не реальный докс.\n\nФормат ввода:\nreply + <code>.dox</code></blockquote>',
    'duel': '<code>.duel</code> — дуэль\n\n<blockquote>Дуэль на револьверах (мини-игра).\n\nФормат ввода:\n<code>.duel</code></blockquote>',
    'echo': '<code>.echo</code> — эхо\n\n<blockquote>Повторяет текст.\n\nФормат ввода:\n<code>.echo текст</code> или reply</blockquote>',
    'emojis': '<code>.emojis</code> — эмодзи\n\n<blockquote>Размножает эмодзи из текста.\n\nФормат ввода:\n<code>.emojis 👻</code></blockquote>',
    'encrypt': '<code>.encrypt</code> — шифр\n\n<blockquote>Простой шифр Цезаря (+3). Расшифровка: <code>.decrypt</code>.\n\nФормат ввода:\n<code>.encrypt секрет</code></blockquote>',
    'ex': '<code>.exif</code> — EXIF\n\n<blockquote>Метаданные фото (если есть).\n\nФормат ввода:\nreply на фото + <code>.exif</code></blockquote>',
    'exif': '<code>.exif</code> — EXIF\n\n<blockquote>Метаданные фото (если есть).\n\nФормат ввода:\nreply на фото + <code>.exif</code></blockquote>',
    'fake': '<code>.fake</code> — fake react\n\n<blockquote>Демо/макет реакции.\n\nФормат ввода:\n<code>.fake</code></blockquote>',
    'fire': '<code>.fire</code> — огонь\n\n<blockquote>Анимация огня.\n\nФормат ввода:\n<code>.fire</code></blockquote>',
    'flip': '<code>.flip</code> — монетка\n\n<blockquote>Орёл или решка.\n\nФормат ввода:\n<code>.flip</code></blockquote>',
    'freeze': '<code>.freeze</code> — заморозка бота\n\n<blockquote>Полный стоп на N дней: нет команд, удаляшек, сии. Подписка на паузе. Снять — кнопкой в личке.\n\nФормат ввода:\n<code>.freeze 7</code>\nснять: кнопка «Разморозить»</blockquote>',
    'geo': '<code>.geo</code> — гео\n\n<blockquote>Инфо по IP/гео (если доступно).\n\nФормат ввода:\n<code>.geo</code></blockquote>',
    'guess': '<code>.guess</code> — ход Wordle\n\n<blockquote>После <code>.wordle</code> — слово из 5 букв.\n\nФормат ввода:\n<code>.guess crane</code></blockquote>',
    'haha': '<code>.haha</code> — спам смехом\n\n<blockquote>Шлёт пачки «ХАХА/ХВХА».\n\nФормат ввода:\n<code>.haha 10</code></blockquote>',
    'imit': '<code>.imit</code> — имитация статуса\n\n<blockquote>Показывает «печатает / записывает голосовое» и т.п.\n\nФормат ввода:\n<code>.imit typing</code>\n<code>.imit voice</code></blockquote>',
    'info': '<code>.info</code> — инфо о человеке\n\n<blockquote>ID, username собеседника.\n\nФормат ввода:\nreply + <code>.info</code></blockquote>',
    'last': '<code>.last</code> — последнее удалённое\n\n<blockquote>Показывает последнее сохранённое удалённое в этом чате.\n\nФормат ввода:\n<code>.last</code></blockquote>',
    'link': '<code>.link</code> — разбор ссылки\n\n<blockquote>Показывает, куда ведёт ссылка.\n\nФормат ввода:\n<code>.link url</code></blockquote>',
    'links': '<code>.links</code> — вытащить ссылки\n\n<blockquote>Достаёт все URL из текста/reply.\n\nФормат ввода:\nreply + <code>.links</code></blockquote>',
    'love': '<code>.love</code> — сердечки\n\n<blockquote>Анимация из сердечек.\n\nФормат ввода:\n<code>.love</code></blockquote>',
    'mb': '<code>.ball</code> — шар судьбы\n\n<blockquote>Ответ на вопрос да/нет.\n\nФормат ввода:\n<code>.ball повезёт?</code></blockquote>',
    'meta': '<code>.exif</code> — EXIF\n\n<blockquote>Метаданные фото (если есть).\n\nФормат ввода:\nreply на фото + <code>.exif</code></blockquote>',
    'morse': '<code>.morse</code> — азбука Морзе\n\n<blockquote>Кодирует или декодирует текст в Морзе.\n\nФормат ввода:\n<code>.morse привет</code></blockquote>',
    'ms': '<code>.ms</code> — сапёр\n\n<blockquote>Поле 5×5. Открыть клетку: буква+цифра.\n\nФормат ввода:\n<code>.ms</code> · <code>.ms B3</code></blockquote>',
    'mute': '<code>.mute</code> — мутит собеседника\n\n<blockquote>Удаляет все сообщения собеседника, пока мут не снять. Восстановление «чужим» ботом — не больше 5 раз подряд.\n\nФормат ввода:\n<code>.mute</code>\nотключить: <code>.unmute</code></blockquote>',
    'nomute': '<code>.nomute</code> — обход чужого мута\n\n<blockquote>Если твоё сообщение сразу удалили — бот отправит его ещё раз (до 5 раз). С юзерботом у собеседника может не сработать.\n\nФормат ввода:\n<code>.nomute</code>\nвыключить: снова <code>.nomute</code> или кнопка</blockquote>',
    'promo': '<code>.promo</code> — промокод\n\n<blockquote>Активирует промокод (дни подписки).\n\nФормат ввода:\n<code>.promo КОД</code>\nили /start promo_КОД</blockquote>',
    'qr': '<code>.qr</code> — QR-код\n\n<blockquote>Генерирует QR из текста/ссылки.\n\nФормат ввода:\n<code>.qr https://t.me/ghostseebot</code></blockquote>',
    'rates': '<code>.rates</code> — курсы\n\n<blockquote>Курсы валют (если источник доступен).\n\nФормат ввода:\n<code>.rates USD</code></blockquote>',
    'rd': '<code>.roll</code> — кубик\n\n<blockquote>Случайное число.\n\nФормат ввода:\n<code>.roll</code> · <code>.roll 100</code></blockquote>',
    'react': '<code>.react</code> — автореакция\n\n<blockquote>Ставит реакцию на сообщения собеседника.\n\nФормат ввода:\n<code>.react ❤️</code> / <code>.unreact</code></blockquote>',
    'remind': '<code>.remind</code> — напоминание\n\n<blockquote>Напомнит в этом чате через время.\n\nФормат ввода:\n<code>.remind 10m текст</code></blockquote>',
    'remindf': '<code>.remindf</code> — напоминание себе\n\n<blockquote>Напомнит тебе в личку с ботом.\n\nФормат ввода:\n<code>.remindf 1h купить молоко</code></blockquote>',
    'revo': '<code>.revo</code> — русская рулетка\n\n<blockquote>1 из 6 — «Bang».\n\nФормат ввода:\n<code>.revo</code></blockquote>',
    'roll': '<code>.roll</code> — кубик\n\n<blockquote>Случайное число.\n\nФормат ввода:\n<code>.roll</code> · <code>.roll 100</code></blockquote>',
    'rp': '<code>.rp</code> — RP-действие\n\n<blockquote>Пишет действие от твоего имени.\n\nФормат ввода:\n<code>.rp обнял</code></blockquote>',
    'rps': '<code>.rps</code> — КНБ\n\n<blockquote>Камень-ножницы-бумага против бота.\n\nФормат ввода:\n<code>.rps камень</code></blockquote>',
    'rul': '<code>.revo</code> — русская рулетка\n\n<blockquote>1 из 6 — «Bang».\n\nФормат ввода:\n<code>.revo</code></blockquote>',
    'safety': '<code>.safety</code> — проверка ссылки\n\n<blockquote>Грубая проверка на фишинг/сокращатели.\n\nФормат ввода:\n<code>.safety url</code></blockquote>',
    'save': '<code>.save</code> — сохранить себе\n\n<blockquote>Пересылает reply тебе в бота.\n\nФормат ввода:\nreply + <code>.save</code></blockquote>',
    'short': '<code>.short</code> — сократить ссылку\n\n<blockquote>Короткая ссылка.\n\nФормат ввода:\n<code>.short https://...</code></blockquote>',
    'snow': '<code>.snow</code> — снег\n\n<blockquote>Анимация снега.\n\nФормат ввода:\n<code>.snow</code></blockquote>',
    'spam': '<code>.spam</code> — спам текстом\n\n<blockquote>Отправляет текст несколько раз (лимит пачек).\n\nФормат ввода:\n<code>.spam 5 привет</code></blockquote>',
    'spamg': '<code>.spamg</code> — спам гифками/стикерами\n\n<blockquote>Спам медиа из reply.\n\nФормат ввода:\nreply + <code>.spamg 5</code></blockquote>',
    'stats': '<code>.stats</code> — стата чата\n\n<blockquote>Мут, варны, bw, nomute в этом чате.\n\nФормат ввода:\n<code>.stats</code></blockquote>',
    'sw': '<code>.sw</code> — переворот текста\n\n<blockquote>Переворачивает слова или буквы в тексте (ответом на сообщение или из аргумента).\n\nФормат ввода:\n<code>.sw текст</code>\nили reply + <code>.sw</code></blockquote>',
    'time': '<code>.time</code> — время в имени\n\n<blockquote>Подставляет время в имя бизнес-аккаунта (нужны права).\n\nФормат ввода:\n<code>.time</code></blockquote>',
    'timer': '<code>.timer</code> — таймер\n\n<blockquote>Через N секунд пришлёт сообщение.\n\nФормат ввода:\n<code>.timer 30 готово</code></blockquote>',
    'tl': '<code>.tl</code> / <code>.tr</code> — перевод\n\n<blockquote>Переводит текст.\n\nФормат ввода:\n<code>.tl en привет</code>\nили reply + <code>.tl en</code></blockquote>',
    'tr': '<code>.tl</code> / <code>.tr</code> — перевод\n\n<blockquote>Переводит текст.\n\nФормат ввода:\n<code>.tl en привет</code>\nили reply + <code>.tl en</code></blockquote>',
    'translate': '<code>.translate</code> — автоперевод\n\n<blockquote>Автоперевод входящих.\n\nФормат ввода:\n<code>.translate en</code> / <code>.untranslate</code></blockquote>',
    'troll': '<code>.troll</code> — тролль-режим\n\n<blockquote>На каждое сообщение собеседника — язвительный ответ.\n\nФормат ввода:\n<code>.troll</code> / <code>.untroll</code></blockquote>',
    'ttt': '<code>.ttt</code> — крестики-нолики\n\n<blockquote>Игра против бота, клетки 1–9.\n\nФормат ввода:\n<code>.ttt</code> · <code>.ttt 5</code></blockquote>',
    'type': '<code>.type</code> — печать\n\n<blockquote>Печатает текст с эффектом набора по символам.\n\nФормат ввода:\n<code>.type привет мир</code></blockquote>',
    'typing': '<code>.typing</code> — «печатает»\n\n<blockquote>Имитация набора N секунд.\n\nФормат ввода:\n<code>.typing 5</code></blockquote>',
    'unfreeze': '<code>.unfreeze</code> — разморозка\n\n<blockquote>Снимает freeze (в чате во время freeze не работает — только кнопка в боте).\n\nФормат ввода:\nкнопка в личке / <code>.unfreeze</code> если уже не заморожен</blockquote>',
    'unmute': '<code>.unmute</code> — снять мут\n\n<blockquote>Снимает мут с собеседника в этом чате.\n\nФормат ввода:\n<code>.unmute</code></blockquote>',
    'warn': '<code>.warn</code> — предупреждение\n\n<blockquote>Выдаёт варн собеседнику. После лимита — действие по настройке чата.\n\nФормат ввода:\n<code>.warn</code> · reply</blockquote>',
    'wbl': '<code>.wbl</code> — мат-фильтр\n\n<blockquote>Удаляет сообщения с матом.\n\nФормат ввода:\n<code>.wbl</code> / <code>.unwbl</code></blockquote>',
    'wordle': '<code>.wordle</code> — Wordle\n\n<blockquote>Слово из 5 букв, 6 попыток.\n\nФормат ввода:\n<code>.wordle</code>\nход: <code>.guess слово</code></blockquote>',
    'wsag': '<code>.wsag</code> — без стикеров/гифок\n\n<blockquote>Удаляет стикеры и анимации собеседника.\n\nФормат ввода:\n<code>.wsag</code> / <code>.unwsag</code></blockquote>',
    'wth': '<code>.wth</code> — что это\n\n<blockquote>Разбор reply: id, тип, автор.\n\nФормат ввода:\nreply + <code>.wth</code></blockquote>',
}

from __future__ import annotations

import asyncio
import html
import io
import random
import re
import time
from types import SimpleNamespace

import httpx
from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, BusinessConnection, BusinessMessagesDeleted, CallbackQuery, Message, ReactionTypeEmoji

from ..commands import engine
from ..commands import tools  # noqa: F401  (регистрирует команды)
from ..keyboards import buy_shortcut, channel_kb
from ..services import biz, gate
from ..services import users as U
from ..services.logs import audit, bg
from ..services.forum_logs import log_business_message, log_deleted

router = Router(name="business")
esc = html.escape

MAT = re.compile(r"(хуй|хуе|хуё|хуя|пизд|ебан|ёбан|ебат|ебал|ебну|заеб|сука|сучк|бляд|блят|мудак|мудил|залуп|пидор|пидар|пидр)", re.I)
SII_RE = re.compile(r"(сии|сий|сиии|sii)[.!]*", re.I)
LATER_RE = re.compile(r"(попозже|не грузит(ся)?)[.!…]*", re.I)

# Новый список троллинга
TROLL = [
    "Твой рот лучше открывать когда туда суют член, уебище.",
    "Соси.",
    "Твой рот нужен исключительно для того, чтобы принимать в него чужие биологические жидкости, пока ты стоишь на коленях посреди грязного коридора, мразь ебаная.",
    "Заткнись.",
    "Твоя тупость превосходит все мыслимые границы человеческого понимания, заставляя каждого нормального человека испытывать физическое отвращение от одного твоего присутствия рядом.",
    "Ты кусок дерьма.",
    "Каждый раз, когда ты открываешь свою пасть, из нее начинает нести такой лютой помойкой и безнадежной тупостью, что хочется надеть противогаз и сжечь этот чат вместе с тобой.",
    "Иди нахуй.",
    "Твой отец горько сожалеет, что в тот злосчастный вечер не прокончил мимо твоей матери, потому что мир получил абсолютное биомусорное недоразумение без единого признака мозгов.",
    "Сдохни.",
    "Ты выглядишь так, будто по твоей дурной башке регулярно прыгал табуном дикий скот, пока у тебя окончательно не вытекли последние остатки серого вещества.",
    "Мразь.",
    "Твое законное место — подрасти на панели, обслуживая дальнобойщиков за пачку дешевых сухариков, потому что на большее твоя никчемная дырявая тушка физически не способна.",
    "Тварь.",
    "У тебя в голове не извилины, а сплошной заброшенный склад протухшего дерьма, в котором копошатся голодные черви твоих убогих и никому не нужных фантазий.",
    "Пошел вон.",
    "Твоя мать по ночам плачет в подушку, вспоминая девять месяцев вынашивания этого ходячего аборта, который теперь сидит в интернете и позорит ее седые волосы.",
    "Конченый.",
    "Твой уровень интеллекта находится где-то на дне выгребной ямы, куда тебя поспешили спустить сразу после рождения, но даже там ты умудрился всплыть и завонять.",
    "Шлюха.",
    "Закрой свой отвратительный рот, от которого разит за версту протухшей селедкой и чужими членами, потому что слушать твой бред выше человеческих сил.",
    "Ублюдок.",
    "Тебя в детстве роняли головой об бетонный пол, причем делали это регулярно, с особым энтузиазмом и до тех пор, пока череп не принял форму твоего убогого характера.",
    "Чмо.",
    "Твои пальцы дрожащими судорогами набирают этот бессмысленный высер только потому, что в реальной жизни тебе давным-давно сломали бы челюсть за такие слова.",
    "Ничтожество.",
    "Посмотри на себя в зеркало и осознай, что ты — биологический тупик, ошибка природы и ходячее доказательство того, что презервативы иногда рвутся не зря.",
    "Свинья.",
    "Твое мнение ценится ровно столько же, сколько использованная туалетная бумага, валяющаяся возле общественного туалета на вокзале.",
    "Идиот.",
    "Каждая секунда твоего существования в этом мире — это чистое оскорбление для всех окружающих живых существ, включая дворовых бродячих собак.",
    "Днище.",
    "Ты даже не представляешь, насколько глубоко всем наплевать на твои высеры, потому что ты — пустое место с ником, кусок биомассы без лица и имени.",
    "Пидорас.",
    "Убирайся нахуй отсюда, пока тебе не разорвали пасть за излишнюю разговорчивость и полное отсутствие хотя бы зачатков мозговой активности.",
    "Мразь тупорылая.",
    "Твоя жизнь — это унылая череда унижений, побоев за гаражами и попыток хоть как-то самоутвердиться в интернете, потому что в реальности ты обычная половая тряпка.",
    "Закрой хайло, биомусор.",
    "Ты выродок больного сифилисом бомжа.",
    "Твоя рожа просит кирпича.",
    "Сгинь, недобитый аборт.",
    "Твое мнение спросить забыли, кусок мяса.",
    "Пасть порву, моргалы выколю.",
    "Иди поплачь в углу, омежка.",
    "Твой батя зря потратил на тебя презерватив.",
    "Ты ошибка эволюции.",
    "Глаза б мои тебя не видели, мразь.",
    "Завали ебало, от тебя смердит.",
    "Твоя голова забита калом.",
    "Уебывай отсюда пока живой.",
    "Ты ходячий парадокс: мозг размером с горошину, а самомнения на целый завод.",
    "Твои тексты вызывают кровотечение из глаз и непреодолимое желание проблеваться.",
    "Слышь, ослиное ты копыто, захлопни свою мусорку.",
    "Каждый раз, когда ты открываешь рот, в мире умирает один дельфин от стыда за человечество.",
    "Твоя мамаша знала, кого рожает — будущую половую тряпку всего района.",
    "Иди в будку, пёс шелудивый.",
    "Твой интеллектуальный багаж умещается в спичечный коробок, да и тот наполовину пустой.",
    "От тебя толку меньше, чем от мертвого грузчика на разгрузке вагонов с ватой.",
    "Тебе впору не в чатах сидеть, а бутылки собирать по теплотрассам, утырок.",
    "Твое присутствие здесь — чистой воды вредительство экологии планеты.",
    "Заткнись, животное бессловесное.",
    "Твоя харизма равна нулю, а дебильность стремится к бесконечности.",
    "Иди учебники отнеси обратно в школу, хотя тебе и десять классов не помогут.",
    "Ты выглядишь как жертва неудачного эксперимента по клонированию свиней.",
    "Твой рот — общая парковка для чужих органов.",
    "Кончай нести этот бред шизофреника, тошно смотреть.",
    "Твое погоняло в зоне будет «Швабра», не сомневайся.",
    "Идиот кусок, тебя учили думать или только жрать и сереть?",
    "Твоя тупость фонит так сильно, что дозиметр зашкаливает.",
    "Завали хлебало, выкидыш.",
    "Твой мозг ссохся до размеров грецкого ореха от бесконечного просмотра помоек.",
    "Мразь конченая, вали в закат.",
    "Твой ковыряющийся в носу пацанчик-сосед умнее тебя в три раза.",
    "Иди проспись, алкаш недобитый.",
    "Твое лицо излучает такую концентрацию дебилизма, что впору диссертации писать.",
    "Забейся под плинтус и не отсвечивай, урод.",
    "Твои пальцы пишут то, за что твоя жопа будет горько отвечать.",
    "Сдохни от зависти, моллюск безмозглый.",
    "Твой словесный поток — это диагноз для психиатра высшей категории.",
    "Иди на хутор бабочек ловить, долбоеб.",
    "Твое мнение никому не уперлось, кроме твоих воображаемых друзей.",
    "Заглоти и сиди тихо, убогий.",
    "Твой уровень развития застрял на стадии инфузории-туфельки.",
    "Мразь поганая, чтоб ты захлебнулся собственной желчью.",
    "Твой батя плачет водопадом, глядя на это недоразумение.",
    "Иди подмойся, от тебя разит за километр.",
    "Твое существование — оскорбление для всех здравомыслящих людей.",
    "Закрой варежку, олень.",
    "Твой мозг заплыл жиром и тупостью окончательно.",
    "Свободен, петушок комнатный.",
    "Твоя мать должна была сделать вакуум еще на первой неделе.",
    "Иди мусор вынеси, может за умного сойдешь.",
    "Твое словесное недержание лечится только лоботомией ржавой лопатой.",
    "Заткнись нахуй, жертва ЕГЭ.",
    "Твой уровень IQ ниже комнатной температуры в антарктическом морге.",
    "Мразь тупоголовая, сгинь с глаз долой.",
    "Твой рот — не помойка, но ты упорно продолжаешь в него сереть словами.",
    "Иди лечись, шизоид ебаный.",
    "Твое лицо — прямое доказательство того, что обезьяны эволюционировали обратно.",
    "Завали едало, уебок.",
    "Твой котелок не варит вообще никак, пусто там.",
    "Сдохни в канаве, биомусор.",
    "Твоя глупость оскорбляет законы физики.",
    "Иди нахуй, долбоящер.",
    "Твое мнение — плевок в вечность, который никому не интересен.",
    "Заткни пасть, шавка помойная.",
    "Твой мозг работает со скрипом ржавой телеги.",
    "Мразь портовая, вали отсюда.",
    "Твой батя — сапожник, а ты — сапог тупой.",
    "Иди сдохни под забором, ничтожество.",
    "Твое присутствие здесь токсичнее чернобыльского реактора.",
    "Заглоти язык, выблядок.",
    "Твой уровень аргументации держится на честном слове и соплях.",
    "Свободен, ничтожный клоун.",
    "Твоя жизнь — сплошной баг матрицы.",
    "Иди в пень, дурак кусок.",
    "Твое лицо просит кирпича без регистрации.",
    "Завали будку, псина.",
    "Твой разум покинул чат навсегда.",
    "Мразь сутулая, исчезни.",
    "Твой словесный понос утомил планету.",
    "Иди проспись, синяк.",
    "Твое мнение отправлено в унитаз.",
    "Заткнись, убогий.",
    "Твой мозг пропил еще твой дед.",
    "Сдохни молча, шваль.",
    "Твоя тупость легендарна в узких кругах дебилов.",
    "Иди нахер, утырок.",
    "Твое лицо — боль пластического хирурга.",
    "Завали хлебало, чучело.",
    "Твой уровень жизни — дно выгребной ямы.",
    "Мразь уличная, василек.",
    "Твой батя разочарован.",
    "Иди лесом, дятел.",
    "Твое существование бессмысленно.",
    "Заткнись нахрен.",
    "Твой мозг — пустота.",
    "Свободен нахуй."
]

SEND = {"photo": "send_photo", "video": "send_video", "video_note": "send_video_note", "voice": "send_voice",
        "audio": "send_audio", "animation": "send_animation", "document": "send_document", "sticker": "send_sticker"}
EXPIRED = "⏸ Подписка закончилась, бот на паузе. Продли — и всё продолжит работать."


def media_of(m: Message):
    if m.photo:
        p = m.photo[-1]
        return {"type": "photo", "file_id": p.file_id, "uid": p.file_unique_id}
    for t in ("video", "video_note", "voice", "audio", "animation", "document", "sticker"):
        obj = getattr(m, t, None)
        if obj:
            return {"type": t, "file_id": obj.file_id, "uid": getattr(obj, "file_unique_id", None)}
    return None


def name_of(u) -> str:
    if not u:
        return "—"
    n = " ".join(x for x in (u.first_name, getattr(u, "last_name", None)) if x) or "—"
    return esc(n + (f" (@{u.username})" if getattr(u, "username", None) else ""))


async def send_media(bot: Bot, chat_id: int, media: dict, silent: bool = False):
    meth = getattr(bot, SEND[media["type"]])
    try:
        return await meth(chat_id, media["file_id"], disable_notification=silent)
    except Exception:
        f = await bot.get_file(media["file_id"])
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
        return await meth(chat_id, BufferedInputFile(buf.getvalue(), filename=f.file_path.split("/")[-1]), disable_notification=silent)


async def owner_user(conn: dict):
    u = await U.get_user(conn["owner_id"])
    if u:
        return u
    u, _ = await U.ensure_user(SimpleNamespace(id=conn["owner_id"], first_name=conn.get("first_name") or "", username=conn.get("username")))
    return u


async def upsell(bot: Bot, u: dict, conn: dict, text: str, member: bool = True):
    last = U.parse(u.get("last_notice"))
    if last and (U.now() - last).total_seconds() < 86400:
        return
    await U.patch_user(u["tg_id"], last_notice=U.iso(U.now()))
    if member:
        await bot.send_message(conn["user_chat_id"], text, reply_markup=buy_shortcut())
    else:  # не подписан на канал
        await bot.send_message(conn["user_chat_id"], gate.GATE_SHORT, reply_markup=channel_kb())


# ---------------- подключение ----------------
@router.business_connection()
async def on_connection(c: BusinessConnection, bot: Bot):
    await biz.save_conn({"id": c.id, "owner_id": c.user.id, "user_chat_id": c.user_chat_id, "enabled": c.is_enabled,
                         "first_name": c.user.first_name or "", "last_name": c.user.last_name or "", "username": c.user.username})
    if c.is_enabled:
        u, _ = await U.ensure_user(c.user)
        await audit("info", "connect", c.user.id)
        st = f"✅ Подписка до {U.fmt_dt(u['sub_until'])}" if U.is_active(u) else EXPIRED
        await bot.send_message(c.user_chat_id, f"✅ <b>Бот подключён к аккаунту.</b>\n{st}\n\n"
                                               "Команды: <code>.help</code> · исчезающее фото: ответь «сии», «попозже» или «не грузит».")
    else:
        await audit("info", "disconnect", c.user.id)


# ---------------- сообщения ----------------
@router.business_message()
async def on_message(m: Message, bot: Bot):
    bc = m.business_connection_id
    conn = await biz.get_conn(bc)
    if not conn or not m.from_user:
        return
    # Форум-лог независим от подписки: не теряем сообщения во время паузы.
    await log_business_message(bot, m, conn, "message")
    u = await owner_user(conn)
    if u.get("banned"):
        return
    member = await gate.allowed(bot, conn["owner_id"])
    active = member and U.is_active(u)
    chat = m.chat.id
    owner = m.from_user.id == conn["owner_id"]
    text = (m.text or "").strip()
    snap = {"name": name_of(m.from_user), "text": m.text, "caption": m.caption, "media": media_of(m), "out": owner, "ts": time.time()}

    if owner:
        # ---- достать исчезающее медиа: «сии» (удаляется) / «попозже», «не грузит» (остаются) ----
        kind = None
        if m.reply_to_message:
            if SII_RE.fullmatch(text):
                kind = "sii"
            elif LATER_RE.fullmatch(text) and media_of(m.reply_to_message):  # без медиа это обычная фраза — не трогаем
                kind = "later"
        if kind:
            if not active:
                return await upsell(bot, u, conn, EXPIRED, member)
            media = media_of(m.reply_to_message)
            if not media:
                return await bot.send_message(conn["user_chat_id"], "⚠️ В сообщении, на которое ты ответил, нет медиа (или Telegram его не отдал боту).")
            silent = U.setting(u, "silent", False)
            await bot.send_message(conn["user_chat_id"], f"👁 <b>Временное медиа</b> от {name_of(m.reply_to_message.from_user)}", disable_notification=silent)
            try:
                await send_media(bot, conn["user_chat_id"], media, silent)
                await audit("info", "timer_reveal", conn["owner_id"], type=media["type"], via=kind)
            except Exception as e:
                await audit("error", "timer_fail", conn["owner_id"], err=str(e)[:200])
                await bot.send_message(conn["user_chat_id"], "⚠️ Не удалось получить медиа: " + str(e)[:200])
            if kind == "sii":
                try:
                    await biz.delete(bc, [m.message_id])
                except Exception:
                    pass
            return
        if not active:
            if text.startswith("."):
                await upsell(bot, u, conn, EXPIRED, member)
            return
        bg(biz.cache_msg(bc, chat, m.message_id, conn["owner_id"], snap))
        sec = (await biz.chat_get(bc, chat)).get("bchat")
        if sec:
            await biz.schedule("del", sec, bc=bc, ids=[m.message_id])
        if text.startswith((".", "/")):
            ran = await engine.run(bot, m, conn, u)
            if ran:
                await audit("info", "cmd", conn["owner_id"], cmd=ran)
        return

    # ---- входящее от собеседника ----
    if not active:
        return
    bg(biz.cache_msg(bc, chat, m.message_id, conn["owner_id"], snap))  # в фоне — не тормозит ответ
    st = await biz.chat_get(bc, chat)
    body = (m.text or m.caption or "")
    bw = st.get("bw") or []
    if (st.get("muted") or (st.get("wsag") and (m.sticker or m.animation))
            or (st.get("wbl") and MAT.search(body)) or any(w in body.lower() for w in bw)):
        try:
            await biz.delete(bc, [m.message_id])
        except Exception as e:
            await audit("warn", "delete_failed", conn["owner_id"], err=str(e)[:150])
        return
    if m.from_user.is_bot:
        return

    if st.get("troll"):  # отвечаем на каждое сообщение, без задержек
        return await biz.send(bc, chat, random.choice(TROLL), reply_to=m.message_id)
    
    if st.get("cold"):
        cold_phrases = ["Принято.", "Ясно.", "Понятно.", "Хорошо.", "Отмечено.", "Засчитано."]
        return await biz.send(bc, chat, random.choice(cold_phrases), reply_to=m.message_id)
    
    if st.get("antispam"):
        # Простая проверка на спам: больше 3 ссылок, капс или повторяющиеся символы
        if (len(re.findall(r'https?://', body)) > 3 or
            (len(body) > 20 and body.isupper()) or
            re.search(r'(.)\1{4,}', body)):
            try:
                await biz.delete(bc, [m.message_id])
                return
            except Exception:
                pass
    
    if st.get("autoreply") and time.time() - st.get("last_autoreply", 0) > 60:
        await biz.chat_set(bc, chat, last_autoreply=time.time())
        phrases = st["autoreply"]
        if phrases:
            return await biz.send(bc, chat, random.choice(phrases))
    
    if st.get("react"):
        try:
            await bot.set_message_reaction(chat_id=chat, message_id=m.message_id, reaction=[ReactionTypeEmoji(emoji="❤️")])
        except Exception:
            pass
    
    if st.get("voice") and m.voice:
        # Скачиваем и распознаём голосовое (в реальности нужен API, здесь заглушка)
        await bot.send_message(conn["user_chat_id"], f"🎤 <b>Голосовое от {name_of(m.from_user)}</b>\n<i>Распознавание пока не реализовано (нужен API).</i>")
        return
    
    if st.get("translate") and body and not re.search(r'[а-яё]', body, re.I):
        try:
            async with httpx.AsyncClient(timeout=10) as h:
                r = await h.get("https://translate.googleapis.com/translate_a/single",
                                params={"client": "gtx", "sl": "auto", "tl": "ru", "dt": "t", "q": body[:1000]})
                translated = "".join(x[0] for x in r.json()[0])
            await bot.send_message(conn["user_chat_id"], f"🌐 <b>Перевод от {name_of(m.from_user)}</b>\n{esc(translated)}")
        except Exception:
            pass
        return

    now = time.time()
    if st.get("clone") and m.text and now - st.get("last_clone", 0) > 1:
        await biz.chat_set(bc, chat, last_clone=now)
        return await biz.send(bc, chat, esc(m.text))
    afk = (u.get("settings") or {}).get("afk")
    if st.get("auto") and now - st.get("last_auto", 0) > 60:
        await biz.chat_set(bc, chat, last_auto=now)
        return await biz.send(bc, chat, esc(st["auto"]))
    if afk and now - st.get("last_afk", 0) > 180:
        await biz.chat_set(bc, chat, last_afk=now)
        await biz.send(bc, chat, f"🌙 <b>AFK:</b> {esc(afk['text'])}\n⏱ Прошло: {U.elapsed(afk['since'])}")


@router.edited_business_message()
async def on_edited(m: Message, bot: Bot):
    bc = m.business_connection_id
    conn = await biz.get_conn(bc)
    if not conn or not m.from_user:
        return
    if m.location and not (m.text or m.caption):  # обновление live-локации — не обрабатываем вовсе
        return
    await log_business_message(bot, m, conn, "edited")
    u = await owner_user(conn)
    if u.get("banned") or not U.is_active(u) or not await gate.allowed(bot, conn["owner_id"]):
        return
    owner = m.from_user.id == conn["owner_id"]
    old = await biz.get_msg(bc, m.chat.id, m.message_id)
    new_text = m.text or m.caption or ""
    nm = media_of(m)
    if not owner and old and U.setting(u, "tracker", True) and U.setting(u, "notify_edited", True):
        was = old.get("text") or old.get("caption") or ""
        # уведомляем ТОЛЬКО если изменился текст/подпись. События без смены текста (открыли исчезающее фото,
        # обновился превью, реакция и т.п.) — молча пропускаем, иначе получался спам «(пусто) → (пусто)».
        if was != new_text and (was or new_text):
            silent = U.setting(u, "silent", False)
            await bot.send_message(
                conn["user_chat_id"],
                (f"✏️ <b>Изменено</b> • {name_of(m.from_user)}\n\n<b>Было:</b>\n{esc(was) or '<i>(пусто)</i>'}"
                 f"\n\n<b>Стало:</b>\n{esc(new_text) or '<i>(пусто)</i>'}")[:4000],
                disable_notification=silent)
            await audit("info", "edited_fwd", conn["owner_id"])
    bg(biz.cache_msg(bc, m.chat.id, m.message_id, conn["owner_id"],
                     {"name": name_of(m.from_user), "text": m.text, "caption": m.caption, "media": nm, "out": owner, "ts": time.time()}))


@router.deleted_business_messages()
async def on_deleted(d: BusinessMessagesDeleted, bot: Bot):
    bc = d.business_connection_id
    conn = await biz.get_conn(bc)
    if not conn:
        return
    u = await owner_user(conn)
    if u.get("banned"):
        return
    # Telegram присылает только ID удалённых сообщений. Логируем событие даже
    # если подписка на паузе или текст уже исчез из кэша.
    records = {mid: await biz.get_msg(bc, d.chat.id, mid) for mid in d.message_ids}
    for deleted_mid in d.message_ids:
        await log_deleted(bot, conn, d.chat.id, deleted_mid, records[deleted_mid])
    member = await gate.allowed(bot, conn["owner_id"])
    if not (member and U.is_active(u)):
        return await upsell(bot, u, conn, "⏸ Тебе удалили сообщение, но бот на паузе (подписка закончилась).", member)
    notify = U.setting(u, "tracker", True) and U.setting(u, "notify_deleted", True)
    silent = U.setting(u, "silent", False)
    st = None
    n = 0
    for mid in d.message_ids:
        rec = records.get(mid)
        if not rec:
            continue
        bg(biz.drop_msg(bc, d.chat.id, mid))
        if rec.get("out"):
            # .nomute: моё сообщение удалили сразу после отправки (чужой мут) — отправляем ещё раз (один раз)
            if rec.get("text") and time.time() - (rec.get("ts") or 0) < 4:
                st = st or await biz.chat_get(bc, d.chat.id)
                if st.get("nomute"):
                    ncount = int(st.get("nomute_count") or 0)
                    if ncount >= 5:
                        await biz.chat_set(bc, d.chat.id, nomute=False, nomute_count=0)
                        await audit("info", "nomute_limit", conn["owner_id"])
                    else:
                        await biz.chat_set(bc, d.chat.id, nomute_count=ncount + 1)
                        # Обфускация текста, чтобы обойти ботов
                        obfuscated = rec["text"].replace(" ", "\u200b ").replace("о", "o").replace("а", "a")
                        await biz.send(bc, d.chat.id, esc(obfuscated))
                        await audit("info", "nomute_resend", conn["owner_id"])
            continue
        if not notify:
            continue
        body = rec.get("text") or rec.get("caption") or ""
        await bot.send_message(conn["user_chat_id"], (f"🗑 <b>Удалено</b> • {rec['name']}\n\n"
                                                      + (esc(body) or ("<i>(медиа ниже)</i>" if rec.get("media") else "<i>(пусто)</i>")))[:4000],
                               disable_notification=silent)
        if rec.get("media"):
            try:
                await send_media(bot, conn["user_chat_id"], rec["media"], silent)
            except Exception as e:
                await audit("warn", "deleted_media_failed", conn["owner_id"], err=str(e)[:150])
        n += 1
    if n:
        await audit("info", "deleted_fwd", conn["owner_id"], count=n)


# ---------------- кнопка «Размутить» ----------------
@router.callback_query(F.data.startswith("unmute:"))
async def cb_unmute(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), muted=False, warns=0)
    await cb.answer("😃 Мут снят")
    try:
        await biz.edit(bc, int(chat), cb.message.message_id, "😃 Мут снят")
    except Exception:
        pass


# ---------------- обработчики кнопок отключения ----------------
@router.callback_query(F.data.startswith("untroll:"))
async def cb_untroll(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), troll=False)
    await cb.answer("🧌 Режим троллинга отключен")
    try:
        await cb.message.edit_text("🧌 Режим троллинга отключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unwsag:"))
async def cb_unwsag(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), wsag=False)
    await cb.answer("🧽 Стикеры и гифки снова разрешены")
    try:
        await cb.message.edit_text("🧽 Стикеры и гифки снова разрешены")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unwbl:"))
async def cb_unwbl(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), wbl=False)
    await cb.answer("🧼 Фильтр мата выключен")
    try:
        await cb.message.edit_text("🧼 Фильтр мата выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unclone:"))
async def cb_unclone(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), clone=False)
    await cb.answer("🪞 Эхо выключено")
    try:
        await cb.message.edit_text("🪞 Эхо выключено")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unnomute:"))
async def cb_unnomute(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), nomute=False)
    await cb.answer("🔓 Обход мута выключен")
    try:
        await cb.message.edit_text("🔓 Обход мута выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unauto:"))
async def cb_unauto(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), auto=None)
    await cb.answer("🤖 Автоответчик выключен")
    try:
        await cb.message.edit_text("🤖 Автоответчик выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unbchat:"))
async def cb_unbchat(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), bchat=0)
    await cb.answer("🧹 Автоудаление выключено")
    try:
        await cb.message.edit_text("🧹 Автоудаление выключено")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unantispam:"))
async def cb_unantispam(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), antispam=False)
    await cb.answer("🛡 Антиспам выключен")
    try:
        await cb.message.edit_text("🛡 Антиспам выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unautoreply:"))
async def cb_unautoreply(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), autoreply=None)
    await cb.answer("🤖 Автоответчик выключен")
    try:
        await cb.message.edit_text("🤖 Автоответчик выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unreact:"))
async def cb_unreact(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), react=False)
    await cb.answer("❤️ Автореакция выключена")
    try:
        await cb.message.edit_text("❤️ Автореакция выключена")
    except Exception:
        pass


@router.callback_query(F.data.startswith("unvoice:"))
async def cb_unvoice(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), voice=False)
    await cb.answer("🎤 Перевод голосовых выключен")
    try:
        await cb.message.edit_text("🎤 Перевод голосовых выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("untranslate:"))
async def cb_untranslate(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), translate=False)
    await cb.answer("🌐 Автоперевод выключен")
    try:
        await cb.message.edit_text("🌐 Автоперевод выключен")
    except Exception:
        pass


@router.callback_query(F.data.startswith("uncold:"))
async def cb_uncold(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), cold=False)
    await cb.answer("🧊 Режим «холод» выключен")
    try:
        await cb.message.edit_text("🧊 Режим «холод» выключен")
    except Exception:
        pass

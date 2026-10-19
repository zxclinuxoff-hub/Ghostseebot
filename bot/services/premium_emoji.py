"""Замена обычных эмодзи на премиум (custom emoji) перед отправкой.

Карта «символ → custom_emoji_id» лежит в bot/data/premium_emoji_map.json.
Пока карта пустая — текст отправляется без изменений.

В тексте (parse_mode HTML) символ заменяется на <tg-emoji emoji-id="ID">символ</tg-emoji>,
символ внутри тега остаётся как запасной вариант для тех, у кого нет Premium.
В кнопках текст не может содержать премиум-эмодзи, поэтому используется icon_custom_emoji_id.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "premium_emoji_map.json"
_VS = "\uFE0F"


def _load() -> dict[str, str]:
    try:
        raw = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k.replace(_VS, ""): str(v) for k, v in raw.items() if v and not str(k).startswith("_")}


MAP: dict[str, str] = _load()

_pattern = None


def reload_map() -> None:
    global MAP, _pattern
    MAP = _load()
    _pattern = None



def _norm(glyph: str) -> str:
    return glyph.replace(_VS, "")


def _get_pattern():
    """Ключи — последовательности символов. Между символами и после них допускается U+FE0F
    (например, «⚙» и «⚙️», «1⃣» и «1️⃣»)."""
    global _pattern
    if _pattern is None and MAP:
        keys = sorted(MAP, key=len, reverse=True)
        alts = ["\uFE0F?".join(re.escape(c) for c in k) for k in keys]
        _pattern = re.compile("(" + "|".join(alts) + ")" + _VS + "?")
    return _pattern


def _tag(m: re.Match) -> str:
    glyph = m.group(0)  # вместе с U+FE0F — он нужен в запасном символе
    return f'<tg-emoji emoji-id="{MAP[_norm(glyph)]}">{glyph}</tg-emoji>'


def to_html(text: str) -> str:
    """Заменяет символы в HTML-тексте, не трогая сами теги и их атрибуты."""
    pat = _get_pattern()
    if not pat or not text:
        return text
    parts = re.split(r"(<[^>]+>)", text)  # чётные — текст, нечётные — теги
    for i in range(0, len(parts), 2):
        parts[i] = pat.sub(_tag, parts[i])
    return "".join(parts)


def _button(btn: dict) -> dict:
    text = btn.get("text") or ""
    if not text or "icon_custom_emoji_id" in btn:
        return btn
    pat = _get_pattern()
    if not pat:
        return btn
    m = pat.match(text)
    if m:
        btn = dict(btn)
        btn["icon_custom_emoji_id"] = MAP[_norm(m.group(1))]
        btn["text"] = text[m.end():].lstrip()
    return btn


def transform_markup(markup):
    """Меняет reply_markup (dict в формате Bot API): иконки у кнопок."""
    if not isinstance(markup, dict) or "inline_keyboard" not in markup or not MAP:
        return markup
    rows = []
    for row in markup["inline_keyboard"]:
        rows.append([_button(b) if isinstance(b, dict) else b for b in row])
    return {**markup, "inline_keyboard": rows}


def transform_params(params: dict) -> dict:
    """Применяется к параметрам запроса sendMessage / editMessageText / sendPhoto и т.п."""
    if not MAP or not isinstance(params, dict):
        return params
    out = dict(params)
    if (out.get("parse_mode") or "").upper() == "HTML":
        for key in ("text", "caption"):
            if isinstance(out.get(key), str):
                out[key] = to_html(out[key])
    if "reply_markup" in out:
        out["reply_markup"] = transform_markup(out["reply_markup"])
    return out


# ---- aiogram: подмена в самом объекте метода перед отправкой ----
def _is_html(pm) -> bool:
    return pm is None or str(getattr(pm, "value", pm)).upper() == "HTML"


def prepare_method(method):
    """Меняет текст, подпись и кнопки у метода aiogram (sendMessage, editMessageText, sendPhoto и т.д.).
    Вызывается из Bot.__call__ — через неё проходят все запросы бота."""
    if not MAP or not hasattr(method, "__api_method__"):
        return method
    if _is_html(getattr(method, "parse_mode", None)):
        for key in ("text", "caption"):
            val = getattr(method, key, None)
            if isinstance(val, str) and "<tg-emoji" not in val:
                setattr(method, key, to_html(val))
    markup = getattr(method, "reply_markup", None)
    if markup is not None and hasattr(markup, "inline_keyboard"):
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        rows = [[InlineKeyboardButton(**_button(b.model_dump(exclude_none=True))) for b in row]
                for row in markup.inline_keyboard]
        setattr(method, "reply_markup", InlineKeyboardMarkup(inline_keyboard=rows))
    return method

"""Offline text correction for .fix: keyboard layout (EN↔RU), caps-lock, stretched letters, typos
(neighbour keys, missing/extra/swapped letters via frequency dictionaries) and spacing. Ambiguous
corrections are reported, never applied silently."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~"
RU = "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ"
EN2RU = str.maketrans(EN, RU)
RU2EN = str.maketrans(RU, EN)
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё\[\];',.`{}:\"<>~]+")
_CYR_WORD = re.compile(r"^[А-Яа-яЁё-]+$")
_LAT_WORD = re.compile(r"^[A-Za-z'-]+$")

COMMON_RU = set("""и в не на я что он с как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему
теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть
надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом
один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про
всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между
привет пока спасибо пожалуйста здравствуйте как дела хорошо понял ладно давай завтра сегодня вчера сейчас скоро позвоню напиши ответь
работа дом время день ночь утро вечер друг брат сестра мама папа""".split())
COMMON_EN = set("""the be to of and a in that have i it for not on with he as you do at this but his by from they we say her she or an will my one
all would there their what so up out if about who get which go me when make can like time no just him know take people into year your good
some could them see other than then now look only come its over think also back after use two how our work first well way even new want
because any these give day most us hello hi thanks please ok yes how are you""".split())


@dataclass
class FixResult:
    text: str
    changes: list[tuple[str, str, str]] = field(default_factory=list)   # (kind, before, after)
    ambiguous: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


@lru_cache(maxsize=2)
def _checker(lang: str):
    try:
        from spellchecker import SpellChecker
        return SpellChecker(language=lang, distance=2)
    except Exception:  # dictionary not installed
        return None


def known(word: str, lang: str) -> bool:
    w = word.lower()
    if (lang == "ru" and w in COMMON_RU) or (lang == "en" and w in COMMON_EN):
        return True
    sp = _checker(lang)
    return bool(sp and w in sp)


def freq(word: str, lang: str) -> int:
    sp = _checker(lang)
    return int(sp.word_usage_frequency(word.lower()) * 1e9) if sp else 0


def _match_case(src: str, dst: str) -> str:
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def fix_layout_word(word: str) -> str | None:
    """Return converted word if it was typed in the wrong keyboard layout."""
    core = word.strip(".,!?;:")
    if len(core) < 2:
        return None
    if re.fullmatch(r"[A-Za-z\[\];',.`{}:\"<>~]+", core) and not known(core, "en"):
        conv = core.translate(EN2RU)
        if _CYR_WORD.match(conv) and known(conv, "ru"):
            return word.replace(core, conv)
    if _CYR_WORD.match(core) and not known(core, "ru"):
        conv = core.translate(RU2EN)
        if _LAT_WORD.match(conv) and known(conv, "en") and len(conv) > 2:
            return word.replace(core, conv)
    return None


def fix_caps(word: str) -> str | None:
    letters = [c for c in word if c.isalpha()]
    if len(letters) >= 3 and letters[0].islower() and all(c.isupper() for c in letters[1:]):
        return word.swapcase()
    return None


def fix_stretch(word: str, lang: str) -> str | None:
    if not re.search(r"(\w)\1{2,}", word):
        return None
    collapsed = re.sub(r"(\w)\1{2,}", r"\1", word)
    if known(collapsed, lang):
        return collapsed
    double = re.sub(r"(\w)\1{2,}", r"\1\1", word)
    return double if known(double, lang) else None


def spell(word: str, lang: str) -> tuple[str | None, list[str]]:
    """(confident correction | None, ambiguous candidate list)."""
    sp = _checker(lang)
    w = word.lower()
    if sp is None or len(w) < 3 or known(w, lang) or not w.isalpha():
        return None, []
    cands = sorted(sp.candidates(w) or [], key=lambda c: -freq(c, lang))
    cands = [c for c in cands if c != w][:5]
    if not cands:
        return None, []
    if len(cands) == 1:
        return _match_case(word, cands[0]), []
    f0, f1 = freq(cands[0], lang), freq(cands[1], lang)
    if f0 >= max(1, f1) * 4:
        return _match_case(word, cands[0]), []
    return None, [_match_case(word, c) for c in cands[:3]]


def fix_text(text: str) -> FixResult:
    res = FixResult(text)
    words = text.split(" ")
    # whole-message layout detection first (more reliable than per-word)
    latin_words = [w for w in words if re.fullmatch(r"[A-Za-z\[\];',.`{}:\"<>~]+[.,!?]*", w)]
    if latin_words and len(latin_words) == len([w for w in words if w]):
        converted = text.translate(EN2RU)
        ru_known = sum(1 for w in re.findall(r"[А-Яа-яЁё]+", converted) if known(w, "ru"))
        en_known = sum(1 for w in re.findall(r"[A-Za-z]+", text) if known(w, "en"))
        if ru_known > en_known and ru_known >= max(1, len(latin_words) // 2):
            res.changes.append(("layout", text, converted))
            res.text = converted
            words = converted.split(" ")
    cyr_words = [w for w in words if re.fullmatch(r"[А-Яа-яЁё]+[.,!?]*", w)]
    if not res.changes and cyr_words and len(cyr_words) == len([w for w in words if w]):
        converted = text.translate(RU2EN)
        en_known = sum(1 for w in re.findall(r"[A-Za-z]+", converted) if known(w, "en"))
        ru_known = sum(1 for w in re.findall(r"[А-Яа-яЁё]+", text) if known(w, "ru"))
        if en_known > ru_known and en_known >= max(1, len(cyr_words) // 2 + 1):
            res.changes.append(("layout", text, converted))
            res.text = converted
            words = converted.split(" ")
    out = []
    for w in words:
        if not w:
            out.append(w)
            continue
        new = w
        lead = re.match(r"^\W*", new).group(0)
        trail = re.search(r"\W*$", new).group(0)
        core = new[len(lead):len(new) - len(trail)] if trail else new[len(lead):]
        if not core:
            out.append(w)
            continue
        lang = "ru" if re.search(r"[А-Яа-яЁё]", core) else "en"
        for kind, fn in (("layout", lambda c: fix_layout_word(c)), ("caps", fix_caps), ("stretch", lambda c: fix_stretch(c, lang))):
            r = fn(core)
            if r and r != core:
                res.changes.append((kind, core, r))
                core = r
                lang = "ru" if re.search(r"[А-Яа-яЁё]", core) else "en"
        if core.isalpha():
            fixed, amb = spell(core, lang)
            if fixed and fixed != core:
                res.changes.append(("typo", core, fixed))
                core = fixed
            elif amb:
                res.ambiguous.append((core, amb))
        out.append(lead + core + trail)
    t = " ".join(out)
    t2 = re.sub(r" {2,}", " ", t)
    t2 = re.sub(r"\s+([,.!?;:])", r"\1", t2)
    t2 = re.sub(r"([,!?;:])(?=[A-Za-zА-Яа-яЁё])", r"\1 ", t2)
    if t2 != t:
        res.changes.append(("spacing", "", ""))
    res.text = t2
    return res


def apply_choice(text: str, word: str, choice: str) -> str:
    return re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", choice, text, count=1)

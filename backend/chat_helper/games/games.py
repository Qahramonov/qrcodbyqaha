"""Mini games (entertainment only, no bets): duel, revo, ttt, rps, quiz, guess, mathgame, wordgame,
reaction, dice, slot, coin, rd, challenge."""
from __future__ import annotations

import asyncio
import random
import re
import time
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import CommandSpec, registry
from ..keyboards import kb
from ..security.sanitize import esc
from .engine import BOT_PLAYER, Game, GameEngine, Session

router = Router(name="games")
rng = random.SystemRandom()
GAME = dict(rate=(10, 60))


def _btn(s: Session, action: str, arg: str = "") -> str:
    return f"g:{s.id}:{action}:{arg}"


# ================================================================================================
# Duel — reaction duel with false start detection
# ================================================================================================

class Duel(Game):
    id = "duel"
    ttl = 180

    async def start(self, eng, s, args):
        a = list(s.players)[0]
        if s.vs_bot:
            s.status = "active"
            await eng.send(s, eng.t(s, "⚔️ <b>Дуэль на реакцию</b> с Chat helper!\nКогда загорится 🟢 — жми кнопку. Раньше времени — фальстарт.",
                                    "⚔️ <b>Reaksiya dueli</b> Chat helper bilan!\n🟢 yonganda tugmani bosing. Erta bossangiz — fal'start."),
                           kb([[(eng.t(s, "🎯 Готов!", "🎯 Tayyorman!"), _btn(s, "ready"))]]))
            return
        await eng.send(s, eng.t(s, "⚔️ <b>{a}</b> вызывает <b>{b}</b> на дуэль на реакцию!\nКогда загорится 🟢 — жмите «Огонь». Фальстарт = поражение.",
                                "⚔️ <b>{a}</b> <b>{b}</b>ni reaksiya dueliga chorlaydi!\n🟢 yonganda «Olov»ni bosing. Fal'start = mag'lubiyat.",
                                a=s.name(a), b=esc(s.state["invitee_name"])),
                       kb([[(eng.t(s, "✅ Принять", "✅ Qabul"), _btn(s, "accept")), (eng.t(s, "❌ Отказ", "❌ Rad"), _btn(s, "decline"))]]))

    async def _arm(self, eng: GameEngine, s: Session) -> None:
        s.status = "active"
        s.state["phase"] = "wait"
        eng.touch(s, 60)
        await eng.edit(s, eng.t(s, "🔴 <b>Приготовьтесь…</b>\nНе нажимайте, пока не загорится 🟢!", "🔴 <b>Tayyorlaning…</b>\n🟢 yonmaguncha bosmang!"),
                       kb([[("🔴 …", _btn(s, "fire"))]]))
        st = await eng.app.settings.all(s.owner_id)
        delay = rng.uniform(st.get("duel_min_delay", 2), max(st.get("duel_min_delay", 2) + 0.5, st.get("duel_max_delay", 6)))
        eng.schedule(s, delay, lambda: self._green(eng, s))

    async def _green(self, eng: GameEngine, s: Session) -> None:
        if s.state.get("phase") != "wait":
            return
        s.state["phase"] = "green"
        await eng.edit(s, eng.t(s, "🟢 <b>ОГОНЬ!</b>", "🟢 <b>OLOV!</b>"), kb([[("🔫 " + eng.t(s, "ОГОНЬ!", "OLOV!"), _btn(s, "fire"))]]))
        s.state["green_at"] = time.monotonic()
        if s.vs_bot:
            bot_ms = rng.randint(260, 520)
            s.state["bot_ms"] = bot_ms
            eng.schedule(s, bot_ms / 1000, lambda: self._bot_fires(eng, s))
        else:
            eng.schedule(s, 10, lambda: self._no_shot(eng, s))

    async def _bot_fires(self, eng: GameEngine, s: Session) -> None:
        if s.state.get("phase") == "green":
            human = next(p for p in s.players if p != BOT_PLAYER)
            await self._win(eng, s, BOT_PLAYER, human, s.state["bot_ms"])

    async def _no_shot(self, eng: GameEngine, s: Session) -> None:
        if s.state.get("phase") == "green":
            await eng.edit(s, eng.t(s, "😴 Никто не выстрелил — ничья.", "😴 Hech kim otmadi — durang."), self._again(eng, s))
            await eng.finish(s, None, None, draw=True, score={"reason": "no_shot"})

    def _again(self, eng: GameEngine, s: Session):
        return kb([[(eng.t(s, "🔁 Реванш", "🔁 Revansh"), f"gr:duel:{s.chat_id}:{s.conn_id or ''}"[:64])]])

    async def _win(self, eng: GameEngine, s: Session, winner: int, loser: int, ms: int | None, false_start: bool = False) -> None:
        s.state["phase"] = "done"
        if false_start:
            text = eng.t(s, "💥 <b>Фальстарт!</b> {l} нажал(а) слишком рано.\n🏆 Победитель: <b>{w}</b>",
                         "💥 <b>Fal'start!</b> {l} juda erta bosdi.\n🏆 G'olib: <b>{w}</b>", l=s.name(loser), w=s.name(winner))
        else:
            text = eng.t(s, "🏆 Победитель: <b>{w}</b>\n⚡️ Реакция: <b>{ms} мс</b>", "🏆 G'olib: <b>{w}</b>\n⚡️ Reaksiya: <b>{ms} ms</b>",
                         w=s.name(winner), ms=ms)
        await eng.edit(s, "⚔️ " + text, self._again(eng, s))
        await eng.finish(s, winner, loser, score={"ms": ms, "false_start": false_start},
                         best_ms={winner: ms} if ms and winner != BOT_PLAYER else None)

    async def callback(self, eng, s, uid, action, arg):
        if action == "decline" and s.status == "pending":
            await eng.edit(s, eng.t(s, "🏳️ Вызов отклонён.", "🏳️ Chaqiruv rad etildi."), None)
            await eng.finish(s, None, None, draw=True, score={"reason": "declined"})
            return "🏳️"
        if action == "accept" and s.status == "pending":
            if uid != s.state["invitee"]:
                return eng.t(s, "Принять может только соперник", "Faqat raqib qabul qila oladi")
            s.players[uid] = s.state["invitee_name"]
            await eng.app.db.execute("INSERT OR IGNORE INTO game_players(session_id, player_id, name, joined_at) VALUES (?,?,?,?)",
                                     (s.id, uid, s.state["invitee_name"][:64], int(time.time())))
            await self._arm(eng, s)
            return "⚔️"
        if action == "ready" and s.vs_bot and s.status == "active" and "phase" not in s.state:
            await self._arm(eng, s)
            return "🎯"
        if action == "fire" and s.status == "active":
            phase = s.state.get("phase")
            if phase == "wait":
                await self._win(eng, s, s.other(uid), uid, None, false_start=True)
                return "💥"
            if phase == "green":
                ms = int((time.monotonic() - s.state["green_at"]) * 1000)
                await self._win(eng, s, uid, s.other(uid), ms)
                return f"⚡️ {ms} ms"
        return None


# ================================================================================================
# Revo — virtual Russian roulette (6 chambers, 1 virtual cartridge)
# ================================================================================================

class Revo(Game):
    id = "revo"
    ttl = 300

    def _kb(self, eng, s):
        return kb([[("🔫 " + eng.t(s, "Нажать на курок", "Tepkini bosish"), _btn(s, "pull"))]])

    async def start(self, eng, s, args):
        s.state.update({"bullet": rng.randrange(6), "pos": 0, "turn": list(s.players)[0], "log": []})
        if not s.vs_bot:
            await eng.send(s, eng.t(s, "🎰 <b>{a}</b> предлагает <b>{b}</b> сыграть в виртуальную рулетку (6 камер, 1 «патрон»).",
                                    "🎰 <b>{a}</b> <b>{b}</b>ga virtual ruletka o'ynashni taklif qiladi (6 kamera, 1 «o'q»).",
                                    a=s.name(list(s.players)[0]), b=esc(s.state["invitee_name"])),
                           kb([[(eng.t(s, "✅ Играть", "✅ O'ynash"), _btn(s, "accept")), (eng.t(s, "❌ Нет", "❌ Yo'q"), _btn(s, "decline"))]]))
            return
        s.status = "active"
        await eng.send(s, await self._render(eng, s, eng.t(s, "🔄 Барабан раскручен!", "🔄 Baraban aylantirildi!")), self._kb(eng, s))

    async def _render(self, eng, s, head: str) -> str:
        chambers = "".join("⚪️" if i < s.state["pos"] else "⚫️" for i in range(6))
        lines = [f"🎰 <b>{eng.t(s, 'Виртуальная рулетка', 'Virtual ruletka')}</b>", head, chambers]
        lines += s.state["log"][-4:]
        lines.append(eng.t(s, "Ход: <b>{p}</b>", "Navbat: <b>{p}</b>", p=s.name(s.state["turn"])))
        return "\n".join(lines)

    async def _pull(self, eng, s, uid) -> str:
        pos = s.state["pos"]
        await eng.edit(s, await self._render(eng, s, eng.t(s, "😰 {p} медленно нажимает на курок…", "😰 {p} sekin tepkini bosmoqda…", p=s.name(uid))), None)
        await asyncio.sleep(1.2)
        if pos == s.state["bullet"]:
            winner = s.other(uid)
            s.state["pos"] = pos + 1
            rendered = await self._render(eng, s, eng.t(s, "💥 <b>БАХ!</b> {p} выбывает (виртуально 😉)\n🏆 Победитель: <b>{w}</b>",
                                                        "💥 <b>BAH!</b> {p} chiqib ketdi (virtual 😉)\n🏆 G'olib: <b>{w}</b>",
                                                        p=s.name(uid), w=s.name(winner)))
            await eng.edit(s, rendered.rsplit("\n", 1)[0], None)
            await eng.finish(s, winner, uid, score={"shot": pos + 1})
            return "💥"
        s.state["pos"] = pos + 1
        s.state["log"].append(eng.t(s, "😅 *щёлк* — {p} повезло", "😅 *chiq* — {p}ga omad kuldi", p=s.name(uid)))
        s.state["turn"] = s.other(uid)
        eng.touch(s, 120)
        await eng.edit(s, await self._render(eng, s, eng.t(s, "Камера {n} пуста.", "{n}-kamera bo'sh.", n=pos + 1)), self._kb(eng, s))
        return "😅"

    async def callback(self, eng, s, uid, action, arg):
        if action == "decline" and s.status == "pending":
            await eng.edit(s, eng.t(s, "🏳️ Отказ от игры.", "🏳️ O'yindan voz kechildi."), None)
            await eng.finish(s, None, None, draw=True, score={"reason": "declined"})
            return "🏳️"
        if action == "accept" and s.status == "pending" and uid == s.state.get("invitee"):
            s.players[uid] = s.state["invitee_name"]
            s.status = "active"
            await eng.edit(s, await self._render(eng, s, eng.t(s, "🔄 Барабан раскручен!", "🔄 Baraban aylantirildi!")), self._kb(eng, s))
            return "🎰"
        if action == "pull" and s.status == "active":
            if uid != s.state["turn"]:
                return eng.t(s, "Сейчас не ваш ход", "Hozir sizning navbatingiz emas")
            res = await self._pull(eng, s, uid)
            if s.status == "active" and s.vs_bot and s.state["turn"] == BOT_PLAYER:
                await asyncio.sleep(0.8)
                await self._pull(eng, s, BOT_PLAYER)
            await eng.save(s)
            return res
        return None


# ================================================================================================
# Tic-tac-toe
# ================================================================================================

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def ttt_winner(b: list[str]) -> str | None:
    for x, y, z in LINES:
        if b[x] != " " and b[x] == b[y] == b[z]:
            return b[x]
    return "draw" if " " not in b else None


def ttt_best(b: list[str], me: str) -> int:
    other = "O" if me == "X" else "X"

    def score(board, player):
        w = ttt_winner(board)
        if w == me:
            return 1
        if w == other:
            return -1
        if w == "draw":
            return 0
        vals = []
        for i in range(9):
            if board[i] == " ":
                board[i] = player
                vals.append(score(board, other if player == me else me))
                board[i] = " "
        return max(vals) if player == me else min(vals)
    best, best_val = -1, -2
    for i in range(9):
        if b[i] == " ":
            b[i] = me
            v = score(b, other)
            b[i] = " "
            if v > best_val:
                best, best_val = i, v
    return best


class TTT(Game):
    id = "ttt"
    ttl = 600

    def _board(self, s: Session):
        b = s.state["b"]
        sym = {"X": "❌", "O": "⭕️", " ": "▫️"}
        rows = []
        for r in range(3):
            rows.append([(sym[b[r * 3 + c]], _btn(s, "m", str(r * 3 + c))) for c in range(3)])
        return kb(rows)

    def _head(self, eng, s, extra=""):
        x, o = s.state["X"], s.state["O"]
        return eng.t(s, "❌ {x}  vs  ⭕️ {o}\n{e}", "❌ {x}  vs  ⭕️ {o}\n{e}", x=s.name(x), o=s.name(o), e=extra)

    async def start(self, eng, s, args):
        first = list(s.players)[0]
        s.state.update({"b": [" "] * 9, "X": first, "O": s.state.get("invitee", BOT_PLAYER), "turn": "X"})
        if s.vs_bot:
            s.state["O"] = BOT_PLAYER
            s.status = "active"
            await eng.send(s, "🎮 <b>Tic-tac-toe</b>\n" + self._head(eng, s, eng.t(s, "Ваш ход ❌", "Sizning yurishingiz ❌")), self._board(s))
            return
        head = eng.t(s, "❌ {x}  vs  ⭕️ {o}\nЖдём соперника…", "❌ {x}  vs  ⭕️ {o}\nRaqib kutilmoqda…",
                     x=s.name(first), o=esc(s.state["invitee_name"]))
        await eng.send(s, "🎮 <b>Tic-tac-toe</b>\n" + head, kb([[(eng.t(s, "✅ Играть ⭕️", "✅ O'ynash ⭕️"), _btn(s, "accept"))]]))

    async def callback(self, eng, s, uid, action, arg):
        if action == "accept" and s.status == "pending" and uid == s.state.get("invitee"):
            s.players[uid] = s.state["invitee_name"]
            s.status = "active"
            await eng.edit(s, "🎮 <b>Tic-tac-toe</b>\n" + self._head(eng, s, eng.t(s, "Ход: ❌ {p}", "Navbat: ❌ {p}", p=s.name(s.state["X"]))), self._board(s))
            return "⭕️"
        if action != "m" or s.status != "active" or not arg.isdigit():
            return None
        sym = s.state["turn"]
        if s.state[sym] != uid:
            return eng.t(s, "Сейчас не ваш ход", "Hozir sizning navbatingiz emas")
        i = int(arg)
        b = s.state["b"]
        if not 0 <= i < 9 or b[i] != " ":
            return eng.t(s, "Клетка занята", "Katak band")
        b[i] = sym
        if await self._check(eng, s):
            return sym
        s.state["turn"] = "O" if sym == "X" else "X"
        if s.vs_bot and s.state["turn"] == "O":
            move = ttt_best(b, "O") if rng.random() > 0.25 else rng.choice([k for k in range(9) if b[k] == " "])
            b[move] = "O"
            if await self._check(eng, s):
                return "🤖"
            s.state["turn"] = "X"
        eng.touch(s, 300)
        nxt = s.state[s.state["turn"]]
        await eng.edit(s, "🎮 <b>Tic-tac-toe</b>\n" + self._head(eng, s, eng.t(s, "Ход: {sym} {p}", "Navbat: {sym} {p}",
                                                                              sym="❌" if s.state["turn"] == "X" else "⭕️", p=s.name(nxt))), self._board(s))
        await eng.save(s)
        return sym

    async def _check(self, eng, s) -> bool:
        w = ttt_winner(s.state["b"])
        if w is None:
            return False
        if w == "draw":
            await eng.edit(s, "🎮 <b>Tic-tac-toe</b>\n" + self._head(eng, s, eng.t(s, "🤝 Ничья!", "🤝 Durang!")), self._board(s))
            await eng.finish(s, None, None, draw=True)
        else:
            winner = s.state[w]
            loser = s.state["O" if w == "X" else "X"]
            await eng.edit(s, "🎮 <b>Tic-tac-toe</b>\n" + self._head(eng, s, eng.t(s, "🏆 Победа: {p}", "🏆 G'alaba: {p}", p=s.name(winner))), self._board(s))
            await eng.finish(s, winner, loser)
        return True


# ================================================================================================
# Rock-paper-scissors (hidden choices)
# ================================================================================================

RPS = {"r": "🪨", "p": "📄", "s": "✂️"}
BEATS = {"r": "s", "p": "r", "s": "p"}


class Rps(Game):
    id = "rps"
    ttl = 180

    def _kb(self, s):
        return kb([[(e, _btn(s, "c", k)) for k, e in RPS.items()]])

    async def start(self, eng, s, args):
        s.state["choices"] = {}
        s.status = "active"
        if not s.vs_bot:
            s.players[s.state["invitee"]] = s.state["invitee_name"]
        names = " vs ".join(s.name(p) for p in s.players)
        await eng.send(s, eng.t(s, "✊ <b>Камень-ножницы-бумага</b>\n{n}\nВыберите тайно — результат покажу, когда выберут оба.",
                                "✊ <b>Tosh-qaychi-qog'oz</b>\n{n}\nYashirin tanlang — ikkalangiz tanlaganda natijani ko'rsataman.", n=names), self._kb(s))

    async def callback(self, eng, s, uid, action, arg):
        if action != "c" or arg not in RPS or s.status != "active":
            return None
        ch = s.state["choices"]
        if str(uid) in ch:
            return eng.t(s, "Вы уже выбрали", "Siz allaqachon tanladingiz")
        ch[str(uid)] = arg
        if s.vs_bot:
            ch[str(BOT_PLAYER)] = rng.choice(list(RPS))
        if len(ch) < 2:
            await eng.edit(s, s.state["last_text"].split("\n✅")[0] + "\n✅ " + eng.t(s, "{p} сделал(а) выбор", "{p} tanladi", p=s.name(uid)), self._kb(s))
            await eng.save(s)
            return "✅ " + RPS[arg]
        a, b = list(s.players)
        ca, cb_ = ch[str(a)], ch[str(b)]
        line = f"{s.name(a)} {RPS[ca]}  —  {RPS[cb_]} {s.name(b)}"
        if ca == cb_:
            await eng.edit(s, "✊ " + line + "\n" + eng.t(s, "🤝 Ничья!", "🤝 Durang!"), None)
            await eng.finish(s, None, None, draw=True, score=ch)
        else:
            win, lose = (a, b) if BEATS[ca] == cb_ else (b, a)
            await eng.edit(s, "✊ " + line + "\n" + eng.t(s, "🏆 Победа: {p}", "🏆 G'alaba: {p}", p=s.name(win)), None)
            await eng.finish(s, win, lose, score=ch)
        return RPS[arg]


# ================================================================================================
# Quiz
# ================================================================================================

QUIZ: list[tuple[str, str, list[str], int]] = [
    ("Столица Узбекистана?", "O'zbekiston poytaxti?", ["Самарканд|Samarqand", "Ташкент|Toshkent", "Бухара|Buxoro", "Хива|Xiva"], 1),
    ("Сколько планет в Солнечной системе?", "Quyosh tizimida nechta sayyora bor?", ["7", "8", "9", "10"], 1),
    ("Самая длинная река в мире?", "Dunyodagi eng uzun daryo?", ["Амазонка|Amazonka", "Нил|Nil", "Янцзы|Yanszi", "Миссисипи|Missisipi"], 1),
    ("Сколько секунд в часе?", "Bir soatda necha soniya bor?", ["360", "3600", "6000", "60000"], 1),
    ("Химический символ золота?", "Oltinning kimyoviy belgisi?", ["Ag", "Au", "Gd", "Go"], 1),
    ("Кто написал «Войну и мир»?", "«Urush va tinchlik»ni kim yozgan?", ["Достоевский|Dostoyevskiy", "Толстой|Tolstoy", "Чехов|Chexov", "Пушкин|Pushkin"], 1),
    ("Самый большой океан?", "Eng katta okean?", ["Атлантический|Atlantika", "Индийский|Hind", "Тихий|Tinch", "Северный Ледовитый|Shimoliy Muz"], 2),
    ("Сколько будет 12 × 12?", "12 × 12 nechaga teng?", ["124", "144", "132", "154"], 1),
    ("Какой газ мы вдыхаем для дыхания?", "Nafas olish uchun qaysi gaz kerak?", ["Азот|Azot", "Кислород|Kislorod", "Гелий|Geliy", "CO₂"], 1),
    ("Автор «Минувших дней» (O'tkan kunlar)?", "«O'tkan kunlar» muallifi?", ["Абдулла Кадыри|Abdulla Qodiriy", "Чолпон|Cho'lpon", "Навои|Navoiy", "Ойбек|Oybek"], 0),
    ("Сколько сторон у шестиугольника?", "Oltiburchakning nechta tomoni bor?", ["5", "6", "7", "8"], 1),
    ("Какой язык программирования создал Гвидо ван Россум?", "Gvido van Rossum qaysi dasturlash tilini yaratgan?", ["Java", "Python", "C++", "Ruby"], 1),
    ("Самая высокая гора мира?", "Dunyodagi eng baland tog'?", ["К2|K2", "Эверест|Everest", "Эльбрус|Elbrus", "Монблан|Monblan"], 1),
    ("Сколько дней в високосном году?", "Kabisa yilida necha kun bor?", ["364", "365", "366", "367"], 2),
    ("Кто нарисовал «Мону Лизу»?", "«Mona Liza»ni kim chizgan?", ["Микеланджело|Mikelanjelo", "Леонардо да Винчи|Leonardo da Vinchi", "Рафаэль|Rafael", "Ван Гог|Van Gog"], 1),
    ("Скорость света ≈ … км/с", "Yorug'lik tezligi ≈ … km/s", ["30 000", "300 000", "3 000 000", "3 000"], 1),
    ("Какая планета называется «красной»?", "Qaysi sayyora «qizil» deb ataladi?", ["Венера|Venera", "Марс|Mars", "Юпитер|Yupiter", "Сатурн|Saturn"], 1),
    ("Сколько игроков в футбольной команде на поле?", "Futbol jamoasida maydonda nechta o'yinchi?", ["9", "10", "11", "12"], 2),
    ("Валюта Японии?", "Yaponiya valyutasi?", ["Юань|Yuan", "Вона|Von", "Иена|Iyena", "Рупия|Rupiya"], 2),
    ("Великий учёный-астроном из Самарканда?", "Samarqandlik buyuk astronom olim?", ["Улугбек|Ulug'bek", "Ибн Сина|Ibn Sino", "Беруни|Beruniy", "Хорезми|Xorazmiy"], 0),
    ("Что тяжелее: 1 кг железа или 1 кг ваты?", "Nima og'irroq: 1 kg temir yoki 1 kg paxta?", ["Железо|Temir", "Вата|Paxta", "Одинаково|Bir xil", "Зависит|Bog'liq"], 2),
    ("Сколько байт в килобайте (двоичный)?", "Kilobaytda necha bayt (ikkilik)?", ["1000", "1024", "512", "2048"], 1),
]


class Quiz(Game):
    id = "quiz"
    ttl = 90

    def _opt(self, s, o: str) -> str:
        parts = o.split("|")
        return parts[1] if s.lang == "uz" and len(parts) > 1 else parts[0]

    async def start(self, eng, s, args):
        q = rng.choice(QUIZ)
        s.state.update({"q": QUIZ.index(q), "out": []})
        s.status = "active"
        if not s.vs_bot:
            s.players[s.state["invitee"]] = s.state["invitee_name"]
        else:
            s.players.pop(BOT_PLAYER, None)
        s.state["t0"] = time.monotonic()
        question = q[1] if s.lang == "uz" else q[0]
        await eng.send(s, f"❓ <b>{esc(question)}</b>\n" + eng.t(s, "Кто первым ответит правильно?", "Kim birinchi to'g'ri javob beradi?"),
                       kb([[(self._opt(s, o), _btn(s, "a", str(i)))] for i, o in enumerate(q[2])]))
        eng.schedule(s, 60, lambda: self.timeout(eng, s))

    async def callback(self, eng, s, uid, action, arg):
        if action != "a" or s.status != "active" or not arg.isdigit():
            return None
        if uid in s.state["out"]:
            return eng.t(s, "Вы уже ответили неверно", "Siz allaqachon noto'g'ri javob berdingiz")
        q = QUIZ[s.state["q"]]
        correct = q[2][q[3]]
        if int(arg) == q[3]:
            ms = int((time.monotonic() - s.state["t0"]) * 1000)
            others = [p for p in s.players if p != uid]
            await eng.edit(s, s.state["last_text"].split("\n")[0] + "\n" + eng.t(s, "✅ {a}\n🏆 {p} — за {t} с", "✅ {a}\n🏆 {p} — {t} s da",
                                                                                a=esc(self._opt(s, correct)), p=s.name(uid), t=round(ms / 1000, 1)), None)
            await eng.finish(s, uid, others[0] if others else None, score={"ms": ms})
            return "✅"
        s.state["out"].append(uid)
        if all(p in s.state["out"] for p in s.players):
            await eng.edit(s, s.state["last_text"].split("\n")[0] + "\n" + eng.t(s, "❌ Никто не угадал. Ответ: {a}", "❌ Hech kim topmadi. Javob: {a}",
                                                                                a=esc(self._opt(s, correct))), None)
            await eng.finish(s, None, None, draw=True)
        await eng.save(s)
        return "❌"

    async def timeout(self, eng, s):
        q = QUIZ[s.state["q"]]
        await eng.edit(s, s.state["last_text"].split("\n")[0] + "\n⌛ " + eng.t(s, "Время вышло. Ответ: {a}", "Vaqt tugadi. Javob: {a}",
                                                                               a=esc(self._opt(s, q[2][q[3]]))), None)
        await eng.finish(s, None, None, draw=True, score={"reason": "timeout"})


# ================================================================================================
# Text games: guess, mathgame, wordgame
# ================================================================================================

class Guess(Game):
    id = "guess"
    text_input = True
    ttl = 240

    async def start(self, eng, s, args):
        hi = 100
        if args and args[0].isdigit() and 10 <= int(args[0]) <= 1000:
            hi = int(args[0])
        s.state.update({"n": rng.randint(1, hi), "hi": hi, "tries": 0, "log": []})
        s.status = "active"
        if not s.vs_bot:
            s.players[s.state["invitee"]] = s.state["invitee_name"]
        else:
            s.players.pop(BOT_PLAYER, None)
        await eng.send(s, eng.t(s, "🔢 <b>Угадай число</b> от 1 до {h}! Пишите числа в чат.", "🔢 <b>Sonni top</b> 1 dan {h} gacha! Chatga son yozing.", h=hi), None)

    async def text(self, eng, s, uid, text):
        if not re.fullmatch(r"\d{1,4}", text):
            return False
        g = int(text)
        s.state["tries"] += 1
        n = s.state["n"]
        if g == n:
            others = [p for p in s.players if p != uid]
            await eng.edit(s, eng.t(s, "🔢 Число <b>{n}</b> угадал(а) <b>{p}</b> за {t} попыток! 🎉", "🔢 <b>{n}</b> sonini <b>{p}</b> {t} urinishda topdi! 🎉",
                                    n=n, p=s.name(uid), t=s.state["tries"]), None)
            await eng.finish(s, uid, others[0] if others else None, score={"tries": s.state["tries"]})
            return True
        hint = eng.t(s, "больше ⬆️", "kattaroq ⬆️") if g < n else eng.t(s, "меньше ⬇️", "kichikroq ⬇️")
        s.state["log"].append(f"{s.name(uid)}: {g} → {hint}")
        eng.touch(s, 180)
        await eng.edit(s, eng.t(s, "🔢 <b>Угадай число</b> 1–{h}\n", "🔢 <b>Sonni top</b> 1–{h}\n", h=s.state["hi"]) + "\n".join(s.state["log"][-6:]), None)
        await eng.save(s)
        return True


class MathGame(Game):
    id = "mathgame"
    text_input = True
    ttl = 60

    async def start(self, eng, s, args):
        op = rng.choice(["+", "-", "×"])
        if op == "×":
            a, b = rng.randint(3, 19), rng.randint(3, 19)
            ans = a * b
        else:
            a, b = rng.randint(10, 199), rng.randint(10, 199)
            ans = a + b if op == "+" else a - b
        s.state.update({"ans": ans, "t0": time.monotonic(), "q": f"{a} {op} {b}"})
        s.status = "active"
        if not s.vs_bot:
            s.players[s.state["invitee"]] = s.state["invitee_name"]
        else:
            s.players.pop(BOT_PLAYER, None)
        await eng.send(s, eng.t(s, "🧮 Кто быстрее? <b>{q} = ?</b>", "🧮 Kim tezroq? <b>{q} = ?</b>", q=s.state["q"]), None)
        eng.schedule(s, 45, lambda: self.timeout(eng, s))

    async def text(self, eng, s, uid, text):
        if not re.fullmatch(r"-?\d{1,6}", text):
            return False
        if int(text) != s.state["ans"]:
            return True
        ms = int((time.monotonic() - s.state["t0"]) * 1000)
        others = [p for p in s.players if p != uid]
        await eng.edit(s, eng.t(s, "🧮 {q} = <b>{a}</b>\n🏆 {p} — {t} с", "🧮 {q} = <b>{a}</b>\n🏆 {p} — {t} s", q=s.state["q"], a=s.state["ans"],
                                p=s.name(uid), t=round(ms / 1000, 2)), None)
        await eng.finish(s, uid, others[0] if others else None, score={"ms": ms}, best_ms={uid: ms})
        return True

    async def timeout(self, eng, s):
        await eng.edit(s, eng.t(s, "🧮 {q} = <b>{a}</b>\n⌛ Никто не успел.", "🧮 {q} = <b>{a}</b>\n⌛ Hech kim ulgurmadi.", q=s.state["q"], a=s.state["ans"]), None)
        await eng.finish(s, None, None, draw=True, score={"reason": "timeout"})


def last_letter(word: str) -> str:
    letters = [c for c in word.lower() if c.isalpha()]
    while letters and letters[-1] in "ьъы":
        letters.pop()
    return letters[-1] if letters else ""


class WordGame(Game):
    id = "wordgame"
    text_input = True
    ttl = 90

    async def start(self, eng, s, args):
        s.status = "active"
        if not s.vs_bot:
            s.players[s.state["invitee"]] = s.state["invitee_name"]
        else:
            s.players.pop(BOT_PLAYER, None)
        start_word = rng.choice(["яблоко", "машина", "телефон", "дерево", "кошка", "olma", "kitob", "daryo"] if s.lang == "uz"
                                else ["яблоко", "машина", "телефон", "дерево", "кошка", "река", "город", "звезда"])
        s.state.update({"used": [start_word], "need": last_letter(start_word), "turn": None, "scores": {}})
        await eng.send(s, self._text(eng, s, eng.t(s, "Первое слово: <b>{w}</b>", "Birinchi so'z: <b>{w}</b>", w=start_word)), None)
        eng.schedule(s, 60, lambda: self.timeout(eng, s))

    def _text(self, eng, s, head):
        sc = s.state["scores"]
        board = " · ".join(f"{s.name(int(k))}: {v}" for k, v in sc.items()) or "—"
        return (eng.t(s, "🔤 <b>Игра в слова</b>\n", "🔤 <b>So'z o'yini</b>\n") + head + "\n" +
                eng.t(s, "Следующее слово на букву <b>«{l}»</b> · 60 с на ход", "Keyingi so'z <b>«{l}»</b> harfiga · har yurishga 60 s",
                      l=s.state["need"].upper()) + "\n🏅 " + board)

    async def text(self, eng, s, uid, text):
        word = text.strip().lower()
        if not re.fullmatch(r"[a-zа-яёўқғҳ'ʻ-]{2,30}", word):
            return False
        if s.state["turn"] is not None and s.state["turn"] == uid:
            return True
        if not word.startswith(s.state["need"]) or word in s.state["used"]:
            return True
        s.state["used"].append(word)
        s.state["need"] = last_letter(word)
        s.state["turn"] = uid
        s.state["scores"][str(uid)] = s.state["scores"].get(str(uid), 0) + 1
        eng.touch(s, 90)
        await eng.edit(s, self._text(eng, s, f"✅ {s.name(uid)}: <b>{esc(word)}</b>"), None)
        await eng.save(s)
        eng.schedule(s, 60, lambda: self.timeout(eng, s))
        return True

    async def timeout(self, eng, s):
        sc = s.state["scores"]
        if not sc:
            await eng.edit(s, eng.t(s, "🔤 Игра в слова завершена — слов не было.", "🔤 So'z o'yini yakunlandi — so'zlar bo'lmadi."), None)
            await eng.finish(s, None, None, draw=True)
            return
        last = s.state["turn"]
        waiting = [p for p in s.players if p != last]
        loser = waiting[0] if waiting else None
        winner = last
        await eng.edit(s, eng.t(s, "🔤 Время вышло! Слов: {n}\n🏆 Победа: {p}", "🔤 Vaqt tugadi! So'zlar: {n}\n🏆 G'alaba: {p}",
                                n=len(s.state["used"]) - 1, p=s.name(winner)), None)
        await eng.finish(s, winner, loser, score=sc)


# ================================================================================================
# Reaction test (both players measured)
# ================================================================================================

class Reaction(Game):
    id = "reaction"
    ttl = 60

    async def start(self, eng, s, args):
        s.status = "active"
        if not s.vs_bot:
            s.players[s.state["invitee"]] = s.state["invitee_name"]
        else:
            s.players.pop(BOT_PLAYER, None)
        s.state.update({"phase": "wait", "times": {}})
        await eng.send(s, eng.t(s, "⚡️ <b>Тест реакции</b>: жмите, когда станет 🟢", "⚡️ <b>Reaksiya testi</b>: 🟢 bo'lganda bosing"),
                       kb([[("🔴 …", _btn(s, "tap"))]]))
        eng.schedule(s, rng.uniform(2, 5), lambda: self._green(eng, s))

    async def _green(self, eng, s):
        s.state["phase"] = "green"
        await eng.edit(s, "🟢 <b>" + eng.t(s, "ЖМИ!", "BOS!") + "</b>", kb([[("⚡️ TAP", _btn(s, "tap"))]]))
        s.state["t0"] = time.monotonic()
        eng.schedule(s, 6, lambda: self._results(eng, s))

    async def _results(self, eng, s):
        t = s.state["times"]
        lines = [eng.t(s, "⚡️ <b>Результаты реакции</b>", "⚡️ <b>Reaksiya natijalari</b>")]
        for pid in s.players:
            v = t.get(str(pid))
            lines.append(f"{s.name(pid)}: " + (eng.t(s, "фальстарт", "fal'start") if v == -1 else (f"{v} ms" if v else "—")))
        valid = {int(k): v for k, v in t.items() if v and v > 0}
        if valid:
            win = min(valid, key=valid.get)
            others = [p for p in s.players if p != win]
            lines.append("🏆 " + s.name(win))
            await eng.edit(s, "\n".join(lines), None)
            await eng.finish(s, win, others[0] if others else None, score=t, best_ms={win: valid[win]})
        else:
            await eng.edit(s, "\n".join(lines), None)
            await eng.finish(s, None, None, draw=True, score=t)

    async def callback(self, eng, s, uid, action, arg):
        if action != "tap" or s.status != "active":
            return None
        t = s.state["times"]
        if str(uid) in t:
            return "✔️"
        if s.state["phase"] == "wait":
            t[str(uid)] = -1
            return eng.t(s, "Фальстарт!", "Fal'start!")
        t[str(uid)] = int((time.monotonic() - s.state["t0"]) * 1000)
        if all(str(p) in t for p in s.players):
            await self._results(eng, s)
        return f"{t[str(uid)]} ms"


# ================================================================================================
# registration + commands
# ================================================================================================

GAME_CLASSES = [Duel(), Revo(), TTT(), Rps(), Quiz(), Guess(), MathGame(), WordGame(), Reaction()]


def register_games(engine: GameEngine) -> None:
    for g in GAME_CLASSES:
        engine.register(g)


async def start_game(ctx: CommandContext, game: str, args: list[str] | None = None) -> None:
    eng: GameEngine = ctx.app.games
    owner_name = ctx.message.from_user.full_name if ctx.message and ctx.message.from_user else "Player"
    players = {ctx.user_id: owner_name}
    state: dict[str, Any] = {}
    if ctx.is_business:
        chat = ctx.message.chat
        if chat.id == ctx.user_id:
            raise CommandError(ctx.t("Игры работают в чате с собеседником.", "O'yinlar suhbatdosh bilan chatda ishlaydi."))
        state["invitee"] = chat.id
        state["invitee_name"] = chat.full_name or chat.username or str(chat.id)
        conn_id = ctx.conn.id if ctx.conn else None
    elif ctx.source == "private":
        players[BOT_PLAYER] = "Chat helper"
        conn_id = None
    else:
        raise CommandError(ctx.t("Игры нельзя запускать в тестовом режиме.", "O'yinlarni test rejimida ishga tushirib bo'lmaydi."))
    active = [s for s in eng.sessions.values() if s.chat_id == ctx.chat_id and s.conn_id == conn_id]
    if len(active) >= 2:
        raise CommandError(ctx.t("В этом чате уже идут игры. Завершите их или подождите.", "Bu chatda o'yinlar davom etmoqda."))
    s = await eng.create(game, owner_id=ctx.user_id, conn_id=conn_id, chat_id=ctx.chat_id, lang=ctx.lang, players=players, state=state,
                         ttl=ctx.settings.get("game_timeout_sec", 120) if game in ("duel", "revo") else None)
    await eng.games[game].start(eng, s, args or [])
    await ctx.cleanup_command(fallback_text="🎮")


def _game_cmd(gid: str, aliases: list[str], ru: str, uz: str, example: str):
    async def handler(ctx: CommandContext) -> None:
        await start_game(ctx, gid, ctx.args)
    registry.add(CommandSpec(
        id=gid, category="games", handler=handler, aliases=aliases, ru=ru, uz=uz, syntax=f".{gid}", examples=[example],
        rights=["can_reply"], **GAME))


_game_cmd("duel", ["дуэль", "duel_"], "Дуэль на реакцию: приглашение, фальстарт, время реакции, рейтинг",
          "Reaksiya dueli: taklif, fal'start, reaksiya vaqti, reyting", ".duel")
_game_cmd("revo", ["рулетка", "ruletka"], "Виртуальная русская рулетка: 6 камер, пошагово, без ставок",
          "Virtual rus ruletkasi: 6 kamera, navbat bilan, garovsiz", ".revo")
_game_cmd("ttt", ["крестики", "xo", "tictactoe"], "Крестики-нолики (с собеседником или с ботом)", "X-O (suhbatdosh yoki bot bilan)", ".ttt")
_game_cmd("rps", ["кнб", "камень", "tqq"], "Камень-ножницы-бумага с тайным выбором", "Tosh-qaychi-qog'oz yashirin tanlov bilan", ".rps")
_game_cmd("quiz", ["викторина", "viktorina"], "Викторина: кто первым ответит правильно", "Viktorina: kim birinchi to'g'ri javob beradi", ".quiz")
_game_cmd("guess", ["угадай", "top"], "Угадай число (подсказки больше/меньше)", "Sonni top (kattaroq/kichikroq maslahatlari)", ".guess 100")
_game_cmd("mathgame", ["математика", "matematika"], "Кто быстрее решит пример", "Kim misolni tezroq yechadi", ".mathgame")
_game_cmd("wordgame", ["слова", "so'zlar"], "Игра в слова: на последнюю букву", "So'z o'yini: oxirgi harfga", ".wordgame")
_game_cmd("reaction", ["реакция", "reaksiya"], "Тест реакции для обоих игроков", "Ikkala o'yinchi uchun reaksiya testi", ".reaction")


@registry.command("dice", "games", aliases=["кубик", "кости", "zar"], ru="Бросить кубик Telegram (🎲 🎯 🏀 ⚽ 🎳)", uz="Telegram zarini tashlash (🎲 🎯 🏀 ⚽ 🎳)",
                  syntax=".dice [🎲|🎯|🏀|⚽|🎳]", examples=[".dice", ".dice 🎯"], rights=["can_reply"], **GAME)
async def cmd_dice(ctx: CommandContext) -> None:
    emoji = ctx.args[0] if ctx.args and ctx.args[0] in ("🎲", "🎯", "🏀", "⚽", "🎳") else "🎲"
    if ctx.source == "sandbox":
        await ctx.answer(f"{emoji} {rng.randint(1, 6)}")
        return
    res = await ctx.app.sender.send_dice(ctx.chat_id, emoji, bc_id=ctx.bc_id)
    if not res.ok:
        raise CommandError(ctx.t("Не удалось отправить кубик ({k}).", "Zarni yuborib bo'lmadi ({k}).", k=res.kind))
    await ctx.cleanup_command(fallback_text=emoji)
    await ctx.app.metrics.incr("games_played", ctx.user_id)


SLOT = ["BAR", "🍇", "🍋", "7️⃣"]


def slot_combo(value: int) -> list[str]:
    v = value - 1
    return [SLOT[v % 4], SLOT[(v // 4) % 4], SLOT[(v // 16) % 4]]


@registry.command("slot", "games", aliases=["слот", "казино"], ru="Слот-машина Telegram 🎰 (без ставок)", uz="Telegram slot-mashinasi 🎰 (garovsiz)",
                  syntax=".slot", examples=[".slot"], rights=["can_reply"], **GAME)
async def cmd_slot(ctx: CommandContext) -> None:
    if ctx.source == "sandbox":
        await ctx.answer("🎰 " + " ".join(slot_combo(rng.randint(1, 64))))
        return
    res = await ctx.app.sender.send_dice(ctx.chat_id, "🎰", bc_id=ctx.bc_id)
    if not res.ok:
        raise CommandError(ctx.t("Не удалось отправить слот ({k}).", "Slotni yuborib bo'lmadi ({k}).", k=res.kind))
    await ctx.cleanup_command(fallback_text="🎰")
    value = res.message.dice.value if res.message is not None and res.message.dice else None
    if value:
        await asyncio.sleep(2.2)
        combo = slot_combo(value)
        jackpot = len(set(combo)) == 1
        txt = "🎰 " + " | ".join(combo) + ("\n🎉 " + ctx.t("ДЖЕКПОТ!", "JEKPOT!") if jackpot else "")
        await ctx.app.sender.send_text(ctx.chat_id, txt, bc_id=ctx.bc_id, reply_to=res.message_id)
    await ctx.app.metrics.incr("games_played", ctx.user_id)


@registry.command("coin", "games", aliases=["монетка", "монета", "tanga"], ru="Подбросить монетку", uz="Tanga tashlash",
                  syntax=".coin", examples=[".coin"], sandbox_safe=True, **GAME)
async def cmd_coin(ctx: CommandContext) -> None:
    await ctx.status("🪙 " + ctx.t("Подбрасываю…", "Tashlayapman…"))
    if ctx.source != "sandbox":
        await asyncio.sleep(1.0)
    side = rng.choice([ctx.t("🦅 Орёл", "🦅 Gerb"), ctx.t("🔢 Решка", "🔢 Raqam")])
    await ctx.answer("🪙 " + side)


@registry.command("rd", "games", aliases=["рандом", "random_choice", "tasodif"], ru="Случайное число или выбор: .rd, .rd 50, .rd 10 20, .rd чай | кофе",
                  uz="Tasodifiy son yoki tanlov: .rd, .rd 50, .rd 10 20, .rd choy | qahva", syntax=".rd [макс | мин макс | вариант | вариант]",
                  examples=[".rd", ".rd 1 6", ".rd пицца | суши | бургер"], sandbox_safe=True, **GAME)
async def cmd_rd(ctx: CommandContext) -> None:
    raw = ctx.raw.strip()
    if "|" in raw:
        opts = [o.strip() for o in raw.split("|") if o.strip()]
        if len(opts) < 2:
            raise UsageError()
        await ctx.answer(ctx.t("🎲 Выбор: <b>{x}</b>", "🎲 Tanlov: <b>{x}</b>", x=esc(rng.choice(opts))))
        return
    nums = ctx.args
    try:
        if not nums:
            lo, hi = 1, 100
        elif len(nums) == 1:
            lo, hi = 1, int(nums[0])
        else:
            lo, hi = int(nums[0]), int(nums[1])
    except ValueError:
        raise UsageError() from None
    if lo > hi or hi - lo > 10 ** 12:
        raise UsageError()
    await ctx.answer(f"🎲 {lo}–{hi}: <b>{rng.randint(lo, hi)}</b>")


@registry.command("challenge", "games", aliases=["вызов", "chaqiruv"], ru="Случайный вызов: бот выбирает игру за вас", uz="Tasodifiy chaqiruv: bot o'yinni tanlaydi",
                  syntax=".challenge", examples=[".challenge"], rights=["can_reply"], **GAME)
async def cmd_challenge(ctx: CommandContext) -> None:
    game = rng.choice(["duel", "ttt", "rps", "quiz", "mathgame", "revo", "reaction"])
    await start_game(ctx, game)


@router.callback_query(F.data.startswith("g:"))
async def cb_game(cb: CallbackQuery, app: Any) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3:
        await cb.answer()
        return
    sid, action = parts[1], parts[2]
    arg = parts[3] if len(parts) > 3 else ""
    try:
        res = await app.games.handle_callback(sid, cb.from_user.id, action, arg)
    except Exception:
        res = "⚠️"
        import logging
        logging.getLogger(__name__).exception("game callback failed")
    await cb.answer(res or "")


@router.callback_query(F.data.startswith("gr:"))
async def cb_rematch(cb: CallbackQuery, app: Any) -> None:
    """Rematch button: starts a new duel in the same chat (works in DM and in business chats)."""
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer()
        return
    game, chat_id, conn_id = parts[1], parts[2], parts[3] or None
    if game not in app.games.games or not chat_id.lstrip("-").isdigit():
        await cb.answer()
        return
    chat_id_i = int(chat_id)
    eng: GameEngine = app.games
    if conn_id:
        conn = await app.connections.get(conn_id)
        if conn is None or cb.from_user.id not in (conn.user_id, chat_id_i):
            await cb.answer("—")
            return
        owner, opponent = conn.user_id, chat_id_i
        owner_row = await app.users.get(owner) or {}
        chat_row = await app.chats.get(owner, chat_id_i) or {}
        players = {owner: owner_row.get("first_name") or "Owner"}
        state = {"invitee": opponent, "invitee_name": chat_row.get("title") or str(opponent)}
        if cb.from_user.id == opponent:  # the contact asked for a rematch → invite the owner
            players = {opponent: state["invitee_name"]}
            state = {"invitee": owner, "invitee_name": owner_row.get("first_name") or "Owner"}
    else:
        if cb.from_user.id != chat_id_i:
            await cb.answer("—")
            return
        owner = chat_id_i
        players = {owner: cb.from_user.full_name, BOT_PLAYER: "Chat helper"}
        state = {}
    s = await eng.create(game, owner_id=owner, conn_id=conn_id, chat_id=chat_id_i, lang=(await app.settings.all(owner))["lang"],
                         players=players, state=state)
    await eng.games[game].start(eng, s, [])
    await cb.answer("🔁")

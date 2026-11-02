"""Game engine: sessions (SQLite + memory), per-session locks, button ownership checks, timeouts,
results, Elo ratings and leaderboards. Works in business chats (owner vs contact) and in the bot DM (user vs bot)."""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardMarkup, Message

from ..database.db import dumps, loads
from ..localization import tr
from ..security.sanitize import esc

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)
BOT_PLAYER = 0


@dataclass
class Session:
    id: str
    game: str
    owner_id: int
    conn_id: str | None
    chat_id: int
    lang: str
    players: dict[int, str] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    message_id: int | None = None
    created: float = field(default_factory=time.time)
    expires: float = 0.0

    def name(self, uid: int) -> str:
        return esc(self.players.get(uid, str(uid)))

    def other(self, uid: int) -> int:
        for p in self.players:
            if p != uid:
                return p
        return uid

    @property
    def vs_bot(self) -> bool:
        return BOT_PLAYER in self.players


class Game:
    id = "base"
    text_input = False
    ttl = 300

    async def start(self, eng: "GameEngine", s: Session, args: list[str]) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    async def callback(self, eng: "GameEngine", s: Session, uid: int, action: str, arg: str) -> str | None:
        return None

    async def text(self, eng: "GameEngine", s: Session, uid: int, text: str) -> bool:
        return False

    async def timeout(self, eng: "GameEngine", s: Session) -> None:
        await eng.edit(s, s.state.get("last_text", "") + "\n\n⌛ " + eng.t(s, "engine.vremya_vyshlo_igra_zavershena"), None)
        await eng.finish(s, None, None, draw=True, score={"reason": "timeout"})


class GameEngine:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self.games: dict[str, Game] = {}
        self.sessions: dict[str, Session] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self._timers: dict[str, asyncio.Task] = {}

    def register(self, game: Game) -> None:
        self.games[game.id] = game

    @staticmethod
    def t(s: Session, key: str, **kw: Any) -> str:
        return tr(s.lang, key, **kw)

    # ---- lifecycle ---------------------------------------------------------------------
    async def create(self, game: str, *, owner_id: int, conn_id: str | None, chat_id: int, lang: str,
                     players: dict[int, str], state: dict[str, Any] | None = None, ttl: int | None = None) -> Session:
        g = self.games[game]
        s = Session(id=secrets.token_hex(4), game=game, owner_id=owner_id, conn_id=conn_id, chat_id=chat_id, lang=lang,
                    players=players, state=state or {}, expires=time.time() + (ttl or g.ttl))
        now = int(time.time())
        async with self.app.db.transaction() as tx:
            await tx.execute("INSERT INTO game_sessions(id, owner_id, connection_id, chat_id, game, state_json, status, created_at, "
                             "updated_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (s.id, owner_id, conn_id, chat_id, game, dumps(s.state), s.status, now, now, int(s.expires)))
            for pid, name in players.items():
                await tx.execute("INSERT OR IGNORE INTO game_players(session_id, player_id, name, joined_at) VALUES (?,?,?,?)",
                                 (s.id, pid, name[:64], now))
        self.sessions[s.id] = s
        self.locks[s.id] = asyncio.Lock()
        await self.app.metrics.incr("games_played", owner_id)
        await self.app.metrics.incr(f"game:{game}")
        self.app.events.emit("game", user_id=owner_id, game=game, status="started")
        return s

    async def save(self, s: Session) -> None:
        await self.app.db.execute("UPDATE game_sessions SET state_json=?, status=?, message_id=?, updated_at=?, expires_at=? WHERE id=?",
                                  (dumps(s.state), s.status, s.message_id, int(time.time()), int(s.expires), s.id))

    def touch(self, s: Session, seconds: int) -> None:
        s.expires = time.time() + seconds

    async def finish(self, s: Session, winner: int | None, loser: int | None, *, draw: bool = False,
                     score: dict[str, Any] | None = None, best_ms: dict[int, int] | None = None) -> None:
        if s.status == "finished":
            return
        s.status = "finished"
        await self.save(s)
        await self.app.db.execute("INSERT INTO game_results(session_id, owner_id, game, winner_id, loser_id, draw, score_json, created_at) "
                                  "VALUES (?,?,?,?,?,?,?,?)", (s.id, s.owner_id, s.game, winner, loser, 1 if draw else 0,
                                                               dumps(score or {}), int(time.time())))
        if s.players:
            await self._update_ratings(s, winner, loser, draw, best_ms or {})
        self.sessions.pop(s.id, None)
        self.locks.pop(s.id, None)
        t = self._timers.pop(s.id, None)
        if t and not t.done() and t is not asyncio.current_task():
            t.cancel()
        self.app.events.emit("game", user_id=s.owner_id, game=s.game, status="finished", winner=winner)

    async def _update_ratings(self, s: Session, winner: int | None, loser: int | None, draw: bool, best: dict[int, int]) -> None:
        now = int(time.time())
        ratings: dict[int, int] = {}
        for pid, name in s.players.items():
            row = await self.app.db.fetchone("SELECT rating FROM game_ratings WHERE owner_id=? AND player_id=? AND game=?", (s.owner_id, pid, s.game))
            ratings[pid] = row["rating"] if row else 1000
            await self.app.db.execute("INSERT OR IGNORE INTO game_ratings(owner_id, player_id, game, name, updated_at) VALUES (?,?,?,?,?)",
                                      (s.owner_id, pid, s.game, name[:64], now))
        if len(ratings) == 2 and (draw or (winner is not None and loser is not None)):
            a, b = list(ratings)
            ea = 1 / (1 + 10 ** ((ratings[b] - ratings[a]) / 400))
            sa = 0.5 if draw else (1.0 if winner == a else 0.0)
            delta = round(32 * (sa - ea))
            ratings[a] += delta
            ratings[b] -= delta
        for pid in s.players:
            res_col = "draws" if draw else ("wins" if pid == winner else "losses" if pid == loser else None)
            sets = ["rating=?", "updated_at=?", "name=?"]
            params: list[Any] = [ratings[pid], now, s.players[pid][:64]]
            if res_col:
                sets.append(f"{res_col}={res_col}+1")
            if pid in best:
                sets.append("best_ms=CASE WHEN best_ms IS NULL OR best_ms > ? THEN ? ELSE best_ms END")
                params += [best[pid], best[pid]]
            await self.app.db.execute(f"UPDATE game_ratings SET {', '.join(sets)} WHERE owner_id=? AND player_id=? AND game=?",
                                      params + [s.owner_id, pid, s.game])

    # ---- I/O ---------------------------------------------------------------------------
    async def send(self, s: Session, text: str, markup: InlineKeyboardMarkup | None, reply_to: int | None = None) -> int | None:
        s.state["last_text"] = text
        res = await self.app.sender.send_text(s.chat_id, text, bc_id=s.conn_id, markup=markup, reply_to=reply_to)
        if res.ok:
            s.message_id = res.message_id
            await self.save(s)
            return res.message_id
        if s.conn_id:
            await self.app.sender.send_text(s.owner_id, self.t(s, "engine.udalos_nachat_igru_chate", k=res.kind))
        await self.finish(s, None, None, draw=True, score={"reason": "send_failed"})
        return None

    async def edit(self, s: Session, text: str, markup: InlineKeyboardMarkup | None) -> bool:
        s.state["last_text"] = text
        if s.message_id is None:
            return False
        res = await self.app.sender.edit_text(s.chat_id, s.message_id, text, bc_id=s.conn_id, markup=markup)
        return res.ok

    async def send_dice(self, s: Session, emoji: str) -> int | None:
        res = await self.app.sender.send_dice(s.chat_id, emoji, bc_id=s.conn_id)
        if res.ok and res.message is not None and res.message.dice is not None:
            return res.message.dice.value
        return None

    def schedule(self, s: Session, delay: float, coro_fn) -> None:
        old = self._timers.pop(s.id, None)
        if old and not old.done():
            old.cancel()

        async def runner():
            try:
                await asyncio.sleep(delay)
                lock = self.locks.get(s.id)
                if lock is None:
                    return
                async with lock:
                    if s.status != "finished":
                        await coro_fn()
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("game timer failed")
        self._timers[s.id] = asyncio.create_task(runner())

    # ---- dispatch ----------------------------------------------------------------------
    async def handle_callback(self, sid: str, uid: int, action: str, arg: str) -> str | None:
        s = self.sessions.get(sid)
        if s is None or s.status == "finished":
            return "⌛"
        if time.time() > s.expires:
            async with self.locks[sid]:
                await self.games[s.game].timeout(self, s)
            return "⌛"
        game = self.games[s.game]
        allowed = uid in s.players or (action in ("accept", "decline") and uid == s.state.get("invitee"))
        if not allowed:
            return self.t(s, "engine.vasha_igra")
        async with self.locks[sid]:
            return await game.callback(self, s, uid, action, arg)

    async def on_chat_message(self, conn: Any, message: Message) -> bool:
        """Route plain text in a business chat to an active text game (guess, mathgame, wordgame, quiz)."""
        if not message.text or message.text.startswith((".", "/")):
            return False
        uid = message.from_user.id if message.from_user else None
        for s in list(self.sessions.values()):
            if s.conn_id == conn.id and s.chat_id == message.chat.id and s.status == "active" and self.games[s.game].text_input:
                if uid in s.players:
                    async with self.locks[s.id]:
                        return await self.games[s.game].text(self, s, uid, message.text.strip())
        return False

    async def on_private_text(self, user_id: int, text: str) -> bool:
        for s in list(self.sessions.values()):
            if s.conn_id is None and s.chat_id == user_id and s.status == "active" and self.games[s.game].text_input:
                async with self.locks[s.id]:
                    return await self.games[s.game].text(self, s, user_id, text.strip())
        return False

    # ---- queries -------------------------------------------------------------------------
    async def leaderboard(self, owner_id: int, game: str | None, limit: int = 10) -> list[dict[str, Any]]:
        if game:
            return await self.app.db.fetchall("SELECT * FROM game_ratings WHERE owner_id=? AND game=? AND player_id != 0 "
                                              "ORDER BY rating DESC, wins DESC LIMIT ?", (owner_id, game, limit))
        return await self.app.db.fetchall(
            "SELECT player_id, MAX(name) AS name, SUM(wins) AS wins, SUM(losses) AS losses, SUM(draws) AS draws, "
            "CAST(AVG(rating) AS INTEGER) AS rating, MIN(best_ms) AS best_ms FROM game_ratings WHERE owner_id=? AND player_id != 0 "
            "GROUP BY player_id ORDER BY wins DESC, rating DESC LIMIT ?", (owner_id, limit))

    async def history(self, owner_id: int, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT * FROM game_results WHERE owner_id=? ORDER BY id DESC LIMIT ?", (owner_id, limit))
        for r in rows:
            r["score"] = loads(r.pop("score_json"), {})
        return rows

    def active(self, owner_id: int | None = None) -> list[dict[str, Any]]:
        return [{"id": s.id, "game": s.game, "owner_id": s.owner_id, "chat_id": s.chat_id, "status": s.status,
                 "players": list(s.players.values()), "created": int(s.created), "expires": int(s.expires)}
                for s in self.sessions.values() if owner_id is None or s.owner_id == owner_id]

    async def end(self, sid: str, owner_id: int | None = None) -> bool:
        s = self.sessions.get(sid)
        if s is None:
            n = await self.app.db.rowcount("UPDATE game_sessions SET status='finished' WHERE id=? AND status!='finished'" +
                                           ("" if owner_id is None else " AND owner_id=?"), (sid,) if owner_id is None else (sid, owner_id))
            return n > 0
        if owner_id is not None and s.owner_id != owner_id:
            return False
        await self.edit(s, s.state.get("last_text", "") + "\n\n🛑 " + self.t(s, "engine.igra_ostanovlena"), None)
        await self.finish(s, None, None, draw=True, score={"reason": "ended"})
        return True

    async def expire_due(self) -> int:
        n = 0
        for s in list(self.sessions.values()):
            if time.time() > s.expires and s.status != "finished":
                async with self.locks[s.id]:
                    try:
                        await self.games[s.game].timeout(self, s)
                    except Exception:
                        await self.finish(s, None, None, draw=True, score={"reason": "timeout"})
                n += 1
        await self.app.db.execute("UPDATE game_sessions SET status='finished' WHERE status!='finished' AND expires_at < ?", (int(time.time()) - 60,))
        return n

    async def clear_history(self, owner_id: int) -> int:
        n = await self.app.db.rowcount("DELETE FROM game_results WHERE owner_id=?", (owner_id,))
        n += await self.app.db.rowcount("DELETE FROM game_ratings WHERE owner_id=?", (owner_id,))
        return n

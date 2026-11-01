"""Analytics: DAU/WAU/MAU, new users, retention, churn, usage, costs, revenue + CSV/JSON/PDF export.
Every number is computed from stored events — nothing is invented; empty data stays empty."""
from __future__ import annotations

import csv
import datetime as dt
import io
import time
from typing import TYPE_CHECKING, Any

from ..core.timeutil import today

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

METRICS = ("messages_in", "messages_out", "auto_replies", "commands", "ai_requests", "ai_tokens", "ai_cost_usd", "media_jobs",
           "errors", "games_played", "automation_runs", "revenue_stars", "payments", "connections_new", "connections_lost")


def _days(start: dt.date, end: dt.date) -> list[str]:
    return [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


class AnalyticsService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._seen_today: set[tuple[int, str]] = set()

    async def touch(self, user_id: int) -> None:
        d = today()
        key = (user_id, d)
        if key in self._seen_today:
            return
        self._seen_today.add(key)
        if len(self._seen_today) > 50000:
            self._seen_today = {k for k in self._seen_today if k[1] == d}
        await self.app.db.execute("INSERT INTO user_activity(user_id, day, events) VALUES (?,?,1) ON CONFLICT(user_id, day) DO UPDATE SET events=events+1",
                                  (user_id, d))

    @staticmethod
    def range(date_from: str | None, date_to: str | None, default_days: int = 30) -> tuple[dt.date, dt.date]:
        end = dt.date.fromisoformat(date_to) if date_to else dt.datetime.now(dt.timezone.utc).date()
        start = dt.date.fromisoformat(date_from) if date_from else end - dt.timedelta(days=default_days - 1)
        if start > end:
            start, end = end, start
        if (end - start).days > 366:
            start = end - dt.timedelta(days=366)
        return start, end

    async def series(self, metric: str, start: dt.date, end: dt.date, user_id: int = 0) -> list[dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT day, value FROM daily_metrics WHERE metric=? AND user_id=? AND day BETWEEN ? AND ?",
                                          (metric, user_id, start.isoformat(), end.isoformat()))
        m = {r["day"]: r["value"] for r in rows}
        return [{"day": d, "value": m.get(d, 0)} for d in _days(start, end)]

    async def active_series(self, start: dt.date, end: dt.date) -> dict[str, list[dict[str, Any]]]:
        db = self.app.db
        dau, wau, mau = [], [], []
        for d in _days(start, end):
            day = dt.date.fromisoformat(d)
            dau.append({"day": d, "value": await db.fetchval("SELECT COUNT(*) FROM user_activity WHERE day=?", (d,), 0)})
            wau.append({"day": d, "value": await db.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE day BETWEEN ? AND ?",
                                                             ((day - dt.timedelta(days=6)).isoformat(), d), 0)})
            mau.append({"day": d, "value": await db.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE day BETWEEN ? AND ?",
                                                             ((day - dt.timedelta(days=29)).isoformat(), d), 0)})
        return {"dau": dau, "wau": wau, "mau": mau}

    async def new_users(self, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
        t0 = int(dt.datetime.combine(start, dt.time.min, dt.timezone.utc).timestamp())
        t1 = int(dt.datetime.combine(end, dt.time.max, dt.timezone.utc).timestamp())
        rows = await self.app.db.fetchall("SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS n FROM users WHERE created_at BETWEEN ? AND ? GROUP BY day",
                                          (t0, t1))
        m = {r["day"]: r["n"] for r in rows}
        return [{"day": d, "value": m.get(d, 0)} for d in _days(start, end)]

    async def retention(self, start: dt.date, end: dt.date) -> dict[str, Any]:
        """Classic D1/D7 retention over users who joined in the range."""
        db = self.app.db
        t0 = int(dt.datetime.combine(start, dt.time.min, dt.timezone.utc).timestamp())
        t1 = int(dt.datetime.combine(end, dt.time.max, dt.timezone.utc).timestamp())
        cohort = await db.fetchall("SELECT id, date(created_at, 'unixepoch') AS d FROM users WHERE created_at BETWEEN ? AND ?", (t0, t1))
        if not cohort:
            return {"cohort": 0, "d1": None, "d7": None}
        d1 = d7 = 0
        elig1 = elig7 = 0
        today_d = dt.datetime.now(dt.timezone.utc).date()
        for u in cohort:
            base = dt.date.fromisoformat(u["d"])
            if base + dt.timedelta(days=1) <= today_d:
                elig1 += 1
                if await db.fetchval("SELECT 1 FROM user_activity WHERE user_id=? AND day=?", (u["id"], (base + dt.timedelta(days=1)).isoformat())):
                    d1 += 1
            if base + dt.timedelta(days=7) <= today_d:
                elig7 += 1
                if await db.fetchval("SELECT 1 FROM user_activity WHERE user_id=? AND day BETWEEN ? AND ?",
                                     (u["id"], (base + dt.timedelta(days=7)).isoformat(), (base + dt.timedelta(days=13)).isoformat())):
                    d7 += 1
        return {"cohort": len(cohort), "d1": round(d1 / elig1, 3) if elig1 else None, "d7": round(d7 / elig7, 3) if elig7 else None}

    async def churn(self) -> dict[str, Any]:
        db = self.app.db
        now = dt.datetime.now(dt.timezone.utc).date()
        prev = await db.fetchall("SELECT DISTINCT user_id FROM user_activity WHERE day BETWEEN ? AND ?",
                                 ((now - dt.timedelta(days=59)).isoformat(), (now - dt.timedelta(days=30)).isoformat()))
        if not prev:
            return {"previous_active": 0, "churned": 0, "rate": None}
        cur = {r["user_id"] for r in await db.fetchall("SELECT DISTINCT user_id FROM user_activity WHERE day > ?",
                                                        ((now - dt.timedelta(days=30)).isoformat(),))}
        churned = sum(1 for r in prev if r["user_id"] not in cur)
        return {"previous_active": len(prev), "churned": churned, "rate": round(churned / len(prev), 3)}

    async def overview(self, date_from: str | None = None, date_to: str | None = None, user_id: int | None = None) -> dict[str, Any]:
        start, end = self.range(date_from, date_to)
        uid = user_id or 0
        series = {m: await self.series(m, start, end, uid) for m in METRICS}
        totals = {m: round(sum(p["value"] for p in s), 4) for m, s in series.items()}
        out: dict[str, Any] = {"from": start.isoformat(), "to": end.isoformat(), "scope": "user" if user_id else "global",
                               "series": series, "totals": totals}
        if not user_id:
            out["active"] = await self.active_series(start, end)
            out["new_users"] = await self.new_users(start, end)
            out["retention"] = await self.retention(start, end)
            out["churn"] = await self.churn()
            out["subscriptions"] = await self.app.subs.stats()
            out["connections"] = await self.app.connections.counts()
            out["module_usage"] = await self.module_usage(start, end)
        return out

    async def module_usage(self, start: dt.date, end: dt.date) -> dict[str, float]:
        rows = await self.app.db.fetchall("SELECT metric, SUM(value) AS v FROM daily_metrics WHERE user_id=0 AND day BETWEEN ? AND ? AND "
                                          "(metric LIKE 'cmd:%' OR metric LIKE 'media:%' OR metric LIKE 'game:%' OR metric LIKE 'auto:%') "
                                          "GROUP BY metric ORDER BY v DESC LIMIT 40", (start.isoformat(), end.isoformat()))
        return {r["metric"]: r["v"] for r in rows}

    # ---- export ------------------------------------------------------------------------------
    async def export_csv(self, data: dict[str, Any]) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        metrics = list(data["series"])
        extra = ["dau", "wau", "mau"] if "active" in data else []
        w.writerow(["day", *metrics, *extra, *(["new_users"] if "new_users" in data else [])])
        days = [p["day"] for p in data["series"][metrics[0]]]
        for i, d in enumerate(days):
            row = [d] + [data["series"][m][i]["value"] for m in metrics]
            row += [data["active"][k][i]["value"] for k in extra]
            if "new_users" in data:
                row.append(data["new_users"][i]["value"])
            w.writerow(row)
        return buf.getvalue().encode("utf-8")

    async def export_pdf(self, data: dict[str, Any]) -> bytes:
        """Renders a compact report with charts using Pillow (no extra PDF dependency)."""
        from PIL import Image, ImageDraw

        from ..media.image import font
        W, H = 1240, 1754
        page = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(page)
        d.text((60, 50), "Chat helper — Analytics report", font=font(44), fill=(17, 24, 39))
        d.text((60, 110), f"{data['from']} — {data['to']} · generated {time.strftime('%Y-%m-%d %H:%M')}", font=font(24, weight="Regular"),
               fill=(90, 90, 110))
        y = 170
        charts = [("messages_in", "Incoming messages"), ("commands", "Commands"), ("ai_requests", "AI requests"),
                  ("media_jobs", "Media jobs"), ("errors", "Errors")]
        if "active" in data:
            charts.insert(0, ("__dau", "Daily active users"))
        for key, title in charts:
            pts = data["active"]["dau"] if key == "__dau" else data["series"][key]
            vals = [p["value"] for p in pts]
            d.text((60, y), f"{title}: total {round(sum(vals), 2)}", font=font(26), fill=(30, 30, 50))
            x0, y0, x1, y1 = 60, y + 40, W - 60, y + 220
            d.rectangle((x0, y0, x1, y1), outline=(225, 228, 235), width=2)
            mx = max(vals) if vals and max(vals) > 0 else 1
            n = max(1, len(vals))
            bw = (x1 - x0) / n
            for i, v in enumerate(vals):
                h = (y1 - y0 - 10) * (v / mx)
                if h < 2:
                    continue
                d.rectangle((x0 + i * bw + 2, y1 - h, x0 + (i + 1) * bw - 2, y1 - 1), fill=(108, 92, 231))
            y += 260
            if y > H - 260:
                break
        totals = data["totals"]
        d.text((60, y), "Totals: " + ", ".join(f"{k}={v}" for k, v in list(totals.items())[:8]), font=font(20, weight="Regular"), fill=(50, 50, 60))
        buf = io.BytesIO()
        page.save(buf, "PDF", resolution=150)
        return buf.getvalue()

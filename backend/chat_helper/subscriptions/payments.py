"""Telegram Stars payments (currency XTR) for digital subscriptions. Disabled until PAYMENTS_ENABLED=true.
Never simulates success: subscriptions are granted only from Telegram's successful_payment update,
idempotently keyed by telegram_payment_charge_id."""
from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery

from ..localization import tr

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)
router = Router(name="payments")


class PaymentService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app

    @property
    def enabled(self) -> bool:
        return bool(self.app.config.payments_enabled) and not self.app.runtime.is_module_paused("payments")

    async def send_invoice(self, uid: int, plan_id: str, lang: str = "ru") -> int:
        if not self.enabled:
            raise ValueError("payments are disabled")
        plan = self.app.subs.plan(plan_id)
        if plan is None or not plan["is_active"] or plan["price_stars"] <= 0:
            raise ValueError("plan is not purchasable")
        payload = f"sub:{plan_id}:{uid}:{secrets.token_hex(6)}"
        pid = await self.app.db.execute("INSERT INTO payments(user_id, plan_id, amount, currency, payload, status, created_at) VALUES (?,?,?,?,?,?,?)",
                                        (uid, plan_id, plan["price_stars"], "XTR", payload, "pending", int(time.time())))
        await self.app.bot.send_invoice(
            chat_id=uid, title=f"Chat helper {plan['name']}",
            description=tr(lang, "Подписка {n} на {d} дн. Цифровая услуга внутри Chat helper.", "{n} obunasi {d} kunga. Chat helper ichidagi raqamli xizmat.",
                           n=plan["name"], d=plan["duration_days"]),
            payload=payload, currency="XTR", prices=[LabeledPrice(label=plan["name"], amount=plan["price_stars"])])
        return pid

    async def validate_checkout(self, q: PreCheckoutQuery) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "Payments are temporarily disabled"
        row = await self.app.db.fetchone("SELECT * FROM payments WHERE payload=?", (q.invoice_payload,))
        if row is None or row["status"] != "pending":
            return False, "Invoice expired, request a new one"
        if row["user_id"] != q.from_user.id or row["amount"] != q.total_amount or q.currency != "XTR":
            return False, "Invoice data mismatch"
        plan = self.app.subs.plan(row["plan_id"])
        if plan is None or not plan["is_active"]:
            return False, "Plan unavailable"
        return True, None

    async def on_success(self, message: Message) -> dict[str, Any] | None:
        sp = message.successful_payment
        if sp is None:
            return None
        charge = sp.telegram_payment_charge_id
        async with self.app.db.transaction() as tx:
            dup = await tx.fetchval("SELECT 1 FROM payments WHERE telegram_charge_id=?", (charge,))
            if dup:
                return None  # idempotency: never grant twice
            row = await tx.fetchone("SELECT * FROM payments WHERE payload=?", (sp.invoice_payload,))
            if row is None or row["user_id"] != message.from_user.id or row["amount"] != sp.total_amount:
                log.warning("successful_payment with unknown/mismatched payload")
                await tx.execute("INSERT INTO payments(user_id, plan_id, amount, currency, payload, telegram_charge_id, provider_charge_id, status, created_at) "
                                 "VALUES (?,?,?,?,?,?,?,?,?)", (message.from_user.id, None, sp.total_amount, sp.currency, sp.invoice_payload, charge,
                                                                sp.provider_payment_charge_id, "orphan", int(time.time())))
                return None
            await tx.execute("UPDATE payments SET status='paid', telegram_charge_id=?, provider_charge_id=? WHERE id=? AND status='pending'",
                             (charge, sp.provider_payment_charge_id, row["id"]))
        plan = self.app.subs.plan(row["plan_id"])
        sub = await self.app.subs.grant(row["user_id"], row["plan_id"], plan["duration_days"] if plan else 30, source="payment", payment_id=row["id"])
        await self.app.metrics.incr("revenue_stars", row["user_id"], row["amount"])
        await self.app.metrics.incr("payments", row["user_id"])
        await self.app.audit.log("payment.paid", actor_id=row["user_id"], actor_type="telegram", target_type="payment", target_id=row["id"],
                                 amount=row["amount"], plan=row["plan_id"])
        await self.app.notifications.notify(self.app.config.super_admin_id, "payment", "⭐️ Payment", f"user {row['user_id']}: {row['amount']} XTR ({row['plan_id']})")
        return sub

    async def refund(self, payment_id: int, by: int) -> bool:
        row = await self.app.db.fetchone("SELECT * FROM payments WHERE id=?", (payment_id,))
        if row is None or row["status"] != "paid" or not row["telegram_charge_id"]:
            return False
        await self.app.bot.refund_star_payment(user_id=row["user_id"], telegram_payment_charge_id=row["telegram_charge_id"])
        await self.app.db.execute("UPDATE payments SET status='refunded', refunded_at=? WHERE id=?", (int(time.time()), payment_id))
        await self.app.db.execute("UPDATE subscriptions SET status='refunded' WHERE payment_id=?", (payment_id,))
        self.app.subs.invalidate(row["user_id"])
        await self.app.audit.log("payment.refund", actor_id=by, target_type="payment", target_id=payment_id)
        return True

    async def list(self, user_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if user_id is None:
            return await self.app.db.fetchall("SELECT * FROM payments ORDER BY id DESC LIMIT ?", (limit,))
        return await self.app.db.fetchall("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))


@router.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery, app: "AppContext") -> None:
    ok, err = await app.payments.validate_checkout(q)
    await q.answer(ok=ok, error_message=err)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, app: "AppContext") -> None:
    sub = await app.payments.on_success(message)
    s = await app.settings.all(message.from_user.id)
    if sub:
        await message.answer(tr(s["lang"], "🎉 Оплата получена! Тариф {p} активен.", "🎉 To'lov qabul qilindi! {p} tarifi faol.", p=sub["plan_id"].upper()))

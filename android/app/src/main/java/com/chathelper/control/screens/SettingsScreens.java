package com.chathelper.control.screens;

import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chathelper.control.core.ApiError;
import com.chathelper.control.core.Fmt;
import com.chathelper.control.core.L;
import com.chathelper.control.ui.Theme;
import com.chathelper.control.ui.UI;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Settings hub: account, Theme Studio, language, server, bot behaviour, devices, privacy, diagnostics, support. */
public final class SettingsScreens {
    private SettingsScreens() {}

    public static final String VERSION = "1.0.0";

    // =====================================================================================================
    public static final class Hub extends Screen {
        @Override
        public String title() { return L.t("Настройки", "Sozlamalar", "Settings"); }

        @Override
        public void load() {
            loading();
            api.get("/settings", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    render(res.optJSONObject("values"));
                }

                @Override
                public void fail(ApiError err) {
                    render(null); // appearance & server settings work offline
                }
            });
        }

        private void set(String key, Object v) {
            api.patch("/settings", put(new JSONObject(), "values", put(new JSONObject(), key, v)), new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    toast(L.t("Сохранено", "Saqlandi", "Saved"));
                }
            });
        }

        private void render(final JSONObject s) {
            body.removeAllViews();
            JSONObject me = act.me();
            JSONObject user = me.optJSONObject("user");
            LinearLayout acc = UI.tinted(c, Theme.accent);
            LinearLayout ar = UI.row(c);
            ar.addView(UI.iconBubble(c, "user", Theme.accent));
            LinearLayout at = UI.col(c);
            at.setPadding(Theme.dp(12), 0, 0, 0);
            at.addView(UI.h3(c, user == null ? "—" : (user.optString("first_name", "") + (user.isNull("username") ? "" : "  @" + user.optString("username")))));
            at.addView(UI.caption(c, me.optString("role") + " · " + me.optString("plan").toUpperCase() + (user == null ? "" : " · ID " + user.optLong("id"))));
            ar.addView(at, UI.weight(1));
            acc.addView(ar);
            body.addView(acc);

            // ---- Theme Studio ---------------------------------------------------------------------------
            body.addView(UI.section(c, "Theme Studio"));
            LinearLayout ts = UI.card(c);
            final String[] modes = {Theme.SYSTEM, Theme.DARK, Theme.LIGHT, Theme.AMOLED};
            String[] modeNames = {L.t("Система", "Tizim", "System"), L.t("Тёмная", "Qorong'i", "Dark"), L.t("Светлая", "Yorug'", "Light"), "AMOLED"};
            int mi = 0;
            for (int i = 0; i < modes.length; i++) if (modes[i].equals(Theme.mode)) mi = i;
            ts.addView(UI.caption(c, L.t("Тема", "Mavzu", "Theme")));
            ts.addView(UI.mt(UI.chips(c, modeNames, mi, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    Theme.mode = modes[v];
                    act.store().put("theme", modes[v]);
                    act.applyAppearance();
                }
            }), 6));
            ts.addView(UI.mt(UI.caption(c, L.t("Акцентный цвет", "Asosiy rang", "Accent color")), 12));
            LinearLayout sw = UI.row(c);
            UI.mt(sw, 8);
            for (int i = 0; i < Theme.ACCENTS.length; i++) {
                final int color = Theme.ACCENTS[i];
                View dot = new View(c);
                GradientDrawable g = new GradientDrawable();
                g.setShape(GradientDrawable.OVAL);
                g.setColor(color);
                if (color == Theme.accent) g.setStroke(Theme.dp(3), Theme.text);
                dot.setBackground(g);
                dot.setContentDescription(Theme.ACCENT_NAMES[i]);
                LinearLayout.LayoutParams p = UI.lp(Theme.dp(32), Theme.dp(32));
                p.rightMargin = Theme.dp(8);
                dot.setLayoutParams(p);
                UI.onClick(dot, new Runnable() {
                    @Override
                    public void run() {
                        Theme.accent = color;
                        act.store().put("accent", String.valueOf(color));
                        act.applyAppearance();
                    }
                });
                sw.addView(dot);
            }
            android.widget.HorizontalScrollView hs = new android.widget.HorizontalScrollView(c);
            hs.setHorizontalScrollBarEnabled(false);
            hs.addView(sw);
            ts.addView(hs);
            final String[] motion = {"0", "0.5", "1", "1.5"};
            String[] motionNames = {L.t("Без анимаций", "Animatsiyasiz", "Off"), L.t("Меньше", "Kamroq", "Reduced"), L.t("Обычно", "Odatiy", "Normal"),
                    L.t("Насыщенно", "Boy", "Rich")};
            int mo = 2;
            for (int i = 0; i < motion.length; i++) if (Float.parseFloat(motion[i]) == Theme.motion) mo = i;
            ts.addView(UI.mt(UI.caption(c, L.t("Интенсивность анимаций", "Animatsiya intensivligi", "Animation intensity")
                    + (Theme.systemReducedMotion ? L.t(" (система: анимации выключены)", " (tizim: animatsiyalar o'chirilgan)", " (system: animations off)") : "")), 12));
            ts.addView(UI.mt(UI.chips(c, motionNames, mo, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    Theme.motion = Float.parseFloat(motion[v]);
                    act.store().put("motion", motion[v]);
                    act.applyAppearance();
                }
            }), 6));
            body.addView(ts);

            // ---- language & server -----------------------------------------------------------------------
            body.addView(UI.section(c, L.t("Язык приложения", "Ilova tili", "App language")));
            final String[] langs = {L.RU, L.UZ, L.EN};
            int li = 0;
            for (int i = 0; i < langs.length; i++) if (langs[i].equals(L.lang())) li = i;
            body.addView(UI.chips(c, new String[]{"Русский", "O'zbekcha", "English"}, li, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    L.set(langs[v]);
                    act.store().put("lang", langs[v]);
                    act.applyAppearance();
                }
            }));
            body.addView(UI.section(c, L.t("Сервер", "Server", "Server")));
            LinearLayout sv = UI.card(c);
            sv.addView(UI.keyValue(c, L.t("Адрес", "Manzil", "Address"), act.store().server()));
            long okAt = api.lastOkAt;
            sv.addView(UI.keyValue(c, L.t("Связь", "Aloqa", "Connection"), okAt > 0 ? "● " + L.t("онлайн", "onlayn", "online") + " · " + Fmt.time(okAt / 1000) : "—"));
            sv.addView(UI.listRow(c, "server", Theme.INFO, L.t("Диагностика", "Diagnostika", "Diagnostics"), null, null, new Runnable() {
                @Override
                public void run() {
                    push(new Diagnostics());
                }
            }));
            body.addView(sv);

            if (s != null) {
                // ---- bot behaviour -------------------------------------------------------------------------
                body.addView(UI.section(c, L.t("Бот в Telegram", "Telegram'dagi bot", "Bot in Telegram")));
                LinearLayout bot = UI.card(c);
                final String[] blangs = {"ru", "uz"};
                bot.addView(UI.caption(c, L.t("Язык сообщений бота", "Bot xabarlari tili", "Bot message language")));
                bot.addView(UI.mt(UI.chips(c, new String[]{"RU", "UZ"}, "uz".equals(s.optString("lang")) ? 1 : 0, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        set("lang", blangs[v]);
                    }
                }), 6));
                final String[] prefixes = {".", "!", "-", ","};
                int pi = 0;
                for (int i = 0; i < prefixes.length; i++) if (prefixes[i].equals(s.optString("prefix"))) pi = i;
                bot.addView(UI.mt(UI.caption(c, L.t("Префикс команд", "Buyruq prefiksi", "Command prefix")), 10));
                bot.addView(UI.mt(UI.chips(c, prefixes, pi, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        set("prefix", prefixes[v]);
                    }
                }), 6));
                final String[] tzs = {"Asia/Tashkent", "Asia/Samarkand", "Europe/Moscow", "Asia/Almaty", "Asia/Dubai", "Europe/Istanbul", "UTC"};
                int ti = 0;
                for (int i = 0; i < tzs.length; i++) if (tzs[i].equals(s.optString("timezone"))) ti = i;
                bot.addView(UI.mt(UI.caption(c, L.t("Часовой пояс", "Vaqt mintaqasi", "Time zone")), 10));
                bot.addView(UI.mt(UI.chips(c, tzs, ti, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        set("timezone", tzs[v]);
                    }
                }), 6));
                bot.addView(UI.slider(c, L.t("Пауза автоответов после вашего сообщения, мин", "Xabaringizdan keyin pauza, daq", "Pause automation after you reply, min"),
                        0, 120, s.optInt("owner_pause_minutes"), "", new UI.IntCallback() {
                            @Override
                            public void on(int v) {
                                set("owner_pause_minutes", v);
                            }
                        }));
                bot.addView(UI.toggleRow(c, L.t("Удалять команды из чата", "Buyruqlarni chatdan o'chirish", "Delete commands from chats"), null, s.optBoolean("delete_commands"), b("delete_commands")));
                bot.addView(UI.toggleRow(c, L.t("Уведомлять о важных сообщениях", "Muhim xabarlar haqida xabar berish", "Notify about important messages"), null, s.optBoolean("notify_important"), b("notify_important")));
                bot.addView(UI.toggleRow(c, L.t("Уведомлять о новых чатах", "Yangi chatlar haqida", "Notify about new chats"), null, s.optBoolean("notify_new_chats"), b("notify_new_chats")));
                bot.addView(UI.toggleRow(c, L.t("Уведомлять об отключении бота", "Bot uzilishi haqida", "Notify when bot is disconnected"), null, s.optBoolean("notify_disconnect"), b("notify_disconnect")));
                bot.addView(UI.toggleRow(c, L.t("Сохранять превью сообщений", "Xabar ko'rinishlarini saqlash", "Store message previews"),
                        L.t("Для Smart Inbox, удаляются через 7 дней", "Smart Inbox uchun, 7 kundan keyin o'chiriladi", "For Smart Inbox, deleted after 7 days"), s.optBoolean("store_previews"), b("store_previews")));
                body.addView(bot);
            }

            // ---- account & privacy -------------------------------------------------------------------------
            body.addView(UI.section(c, L.t("Аккаунт и приватность", "Akkaunt va maxfiylik", "Account & privacy")));
            LinearLayout pv = UI.card(c);
            pv.addView(UI.listRow(c, "phone", Theme.accent, L.t("Устройства и сессии", "Qurilmalar va sessiyalar", "Devices & sessions"), null, null, new Runnable() {
                @Override
                public void run() {
                    push(new AdminScreens.Security());
                }
            }));
            pv.addView(UI.listRow(c, "download", Theme.accent, L.t("Экспорт моих данных (JSON)", "Ma'lumotlarimni eksport (JSON)", "Export my data (JSON)"), null, null, new Runnable() {
                @Override
                public void run() {
                    api.download("/export", new com.chathelper.control.core.Api.BytesCallback() {
                        @Override
                        public void ok(byte[] data, String ct) {
                            String w = AdminScreens.Files.save(act, "chat_helper_export_" + System.currentTimeMillis() / 1000 + ".json", "application/json", data);
                            toast(w == null ? "⚠️" : L.t("Сохранено: ", "Saqlandi: ", "Saved: ") + w);
                        }

                        @Override
                        public void fail(ApiError err) {
                            toast(err.human());
                        }
                    });
                }
            }));
            pv.addView(UI.listRow(c, "crown", Theme.WARNING, L.t("Подписка", "Obuna", "Subscription"), null, null, new Runnable() {
                @Override
                public void run() {
                    push(new AdminScreens.Subscriptions());
                }
            }));
            pv.addView(UI.listRow(c, "help", Theme.INFO, L.t("Поддержка и FAQ", "Yordam va FAQ", "Support & FAQ"), null, null, new Runnable() {
                @Override
                public void run() {
                    push(new Support());
                }
            }));
            pv.addView(UI.listRow(c, "info", Theme.INFO, L.t("Что нового", "Yangiliklar", "What's new"), null, null, new Runnable() {
                @Override
                public void run() {
                    push(new Changelog());
                }
            }));
            body.addView(pv);
            body.addView(UI.dangerButton(c, L.t("Выйти из приложения", "Ilovadan chiqish", "Sign out"), new Runnable() {
                @Override
                public void run() {
                    UI.confirm(c, L.t("Выйти?", "Chiqilsinmi?", "Sign out?"), L.t("Сессия будет отозвана. Для входа понадобится новый код из Telegram.",
                            "Sessiya bekor qilinadi. Kirish uchun Telegram'dan yangi kod kerak bo'ladi.", "The session will be revoked. You will need a new code from Telegram."),
                            L.t("Выйти", "Chiqish", "Sign out"), new Runnable() {
                                @Override
                                public void run() {
                                    act.logout();
                                }
                            });
                }
            }));
            TextView ver = UI.caption(c, "Chat helper Control v" + VERSION + " · Android " + Build.VERSION.RELEASE + " · API " + Build.VERSION.SDK_INT);
            ver.setPadding(Theme.dp(4), Theme.dp(16), 0, 0);
            body.addView(ver);
        }

        private UI.BoolCallback b(final String key) {
            return new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    set(key, v);
                }
            };
        }
    }

    // =====================================================================================================
    public static final class Diagnostics extends Screen {
        @Override
        public String title() { return L.t("Диагностика", "Diagnostika", "Diagnostics"); }

        @Override
        public void load() {
            loading();
            final long t0 = System.currentTimeMillis();
            api.health(act.store().server(), new Cb() {
                @Override
                public void ok(JSONObject h) {
                    long ms = System.currentTimeMillis() - t0;
                    body.removeAllViews();
                    LinearLayout card = UI.card(c);
                    card.addView(UI.listRow(c, "check", Theme.SUCCESS, L.t("Backend доступен", "Backend mavjud", "Backend reachable"), act.store().server() + " · " + ms + " ms", null, null));
                    card.addView(UI.listRow(c, h.optBoolean("bot_polling") ? "check" : "warning", h.optBoolean("bot_polling") ? Theme.SUCCESS : Theme.WARNING,
                            L.t("Опрос Telegram", "Telegram so'rovi", "Telegram polling"), h.optBoolean("bot_polling") ? "OK" : L.t("не активен — проверьте BOT_TOKEN и сеть", "faol emas — BOT_TOKEN va tarmoqni tekshiring",
                                    "inactive — check BOT_TOKEN and network"), null, null));
                    card.addView(UI.listRow(c, "info", Theme.INFO, L.t("Версия backend", "Backend versiyasi", "Backend version"), h.optString("version"), null, null));
                    card.addView(UI.listRow(c, act.store().loggedIn() ? "check" : "warning", act.store().loggedIn() ? Theme.SUCCESS : Theme.WARNING,
                            L.t("Сессия", "Sessiya", "Session"), act.store().loggedIn() ? L.t("активна, токены в Android Keystore", "faol, tokenlar Android Keystore'da", "active, tokens in Android Keystore") : "—", null, null));
                    if (api.lastError != null) card.addView(UI.listRow(c, "warning", Theme.WARNING, L.t("Последняя ошибка", "Oxirgi xato", "Last error"), api.lastError.toString(), null, null));
                    body.addView(card);
                    if (act.isAdmin()) body.addView(UI.button(c, L.t("Полная проверка системы", "To'liq tizim tekshiruvi", "Full system check"), true, new Runnable() {
                        @Override
                        public void run() {
                            push(new AdminScreens.SystemControl());
                        }
                    }));
                    body.addView(UI.section(c, L.t("Если не подключается", "Ulanmasa", "If it can't connect")));
                    LinearLayout tips = UI.card(c);
                    String[] t = {
                            L.t("Termux: cd ~/Chat_helper && ./scripts/status.sh", "Termux: cd ~/Chat_helper && ./scripts/status.sh", "Termux: cd ~/Chat_helper && ./scripts/status.sh"),
                            L.t("Отключите оптимизацию батареи для Termux и выполните termux-wake-lock", "Termux uchun batareya optimizatsiyasini o'chiring va termux-wake-lock bajaring",
                                    "Disable battery optimisation for Termux and run termux-wake-lock"),
                            L.t("Адрес по умолчанию http://127.0.0.1:8787 (API_PORT в .env)", "Standart manzil http://127.0.0.1:8787 (.env dagi API_PORT)", "Default address http://127.0.0.1:8787 (API_PORT in .env)"),
                            L.t("Для другого телефона нужен https:// и API_REMOTE_ENABLED=true (см. docs/SECURITY.md)", "Boshqa telefon uchun https:// va API_REMOTE_ENABLED=true kerak",
                                    "Another phone needs https:// and API_REMOTE_ENABLED=true (see docs/SECURITY.md)"),
                    };
                    for (String s : t) tips.addView(UI.listRow(c, "info", Theme.INFO, s, null, null, null));
                    body.addView(tips);
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Support extends Screen {
        @Override
        public String title() { return L.t("Поддержка", "Yordam", "Support"); }

        @Override
        public boolean refreshable() { return false; }

        @Override
        public void load() {
            body.removeAllViews();
            body.addView(UI.button(c, L.t("Написать администратору", "Administratorga yozish", "Message the administrator"), true, new Runnable() {
                @Override
                public void run() {
                    UI.prompt(c, L.t("Ваш вопрос", "Savolingiz", "Your question"), "", "", true, new UI.TextCallback() {
                        @Override
                        public void on(String v) {
                            if (v.trim().length() < 3) return;
                            api.post("/support", obj("message", v.trim()), new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    toast(L.t("Отправлено", "Yuborildi", "Sent"));
                                }
                            });
                        }
                    });
                }
            }));
            body.addView(UI.section(c, "FAQ"));
            String[][] faq = {
                    {L.t("Почему бот не отвечает собеседнику?", "Nega bot suhbatdoshga javob bermayapti?", "Why doesn't the bot reply to a contact?"),
                            L.t("Telegram разрешает боту писать только если собеседник писал за последние 24 часа. Проверьте режим (Автоматика), право «Отвечать на сообщения» и что чат не в чёрном списке.",
                                    "Telegram botga faqat suhbatdosh so'nggi 24 soatda yozgan bo'lsa yozishga ruxsat beradi. Rejim, huquq va qora ro'yxatni tekshiring.",
                                    "Telegram lets the bot write only if the contact wrote within 24 hours. Check the mode, the reply right and that the chat isn't blacklisted.")},
                    {L.t("Команда с точкой не срабатывает", "Nuqtali buyruq ishlamayapti", "A dot command doesn't work"),
                            L.t("Команды выполняет только владелец аккаунта. Проверьте префикс (Настройки), что команда включена (Команды) и есть нужные права (Inspector).",
                                    "Buyruqlarni faqat akkaunt egasi bajaradi. Prefiks, buyruq yoqilganligi va huquqlarni tekshiring.",
                                    "Only the account owner can run commands. Check the prefix, that the command is enabled and the required rights (Inspector).")},
                    {L.t("Можно ли сделать статус «онлайн»?", "«Onlayn» holatini qilish mumkinmi?", "Can I fake the online status?"),
                            L.t("Нет: Bot API этого не позволяет, и мы не используем пользовательские сессии.", "Yo'q: Bot API bunga ruxsat bermaydi.", "No: the Bot API doesn't allow it and we never use user sessions.")},
                    {L.t("Backend остановился", "Backend to'xtadi", "The backend stopped"),
                            L.t("Android может выгрузить Termux. Используйте termux-wake-lock, отключите оптимизацию батареи и запускайте через ./scripts/start.sh (tmux).",
                                    "Android Termux'ni yopishi mumkin. termux-wake-lock va batareya optimizatsiyasini o'chiring.",
                                    "Android may kill Termux. Use termux-wake-lock, disable battery optimisation and start via ./scripts/start.sh (tmux).")},
            };
            for (String[] f : faq) {
                LinearLayout card = UI.card(c);
                card.addView(UI.h3(c, f[0]));
                card.addView(UI.mt(UI.body2(c, f[1]), 6));
                body.addView(card);
            }
        }
    }

    public static final class Changelog extends Screen {
        @Override
        public String title() { return L.t("Что нового", "Yangiliklar", "What's new"); }

        @Override
        public void load() {
            loading();
            api.get("/changelog", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    JSONArray items = res.optJSONArray("items");
                    for (int i = 0; items != null && i < items.length(); i++) {
                        JSONObject v = items.optJSONObject(i);
                        LinearLayout card = UI.card(c);
                        card.addView(UI.h3(c, "v" + v.optString("version") + " · " + v.optString("date")));
                        JSONArray lines = v.optJSONArray("items");
                        for (int j = 0; lines != null && j < lines.length(); j++) card.addView(UI.mt(UI.body2(c, "• " + lines.optString(j)), 4));
                        body.addView(card);
                    }
                    LinearLayout app = UI.card(c);
                    app.addView(UI.h3(c, "Chat helper Control v" + VERSION));
                    List<String> notes = new ArrayList<String>();
                    notes.add(L.t("Aurora Glass дизайн, темы и акценты", "Aurora Glass dizayni, mavzular va ranglar", "Aurora Glass design, themes and accents"));
                    notes.add(L.t("Безопасный вход по одноразовому коду", "Bir martalik kod bilan xavfsiz kirish", "Secure one-time-code sign-in"));
                    notes.add(L.t("Полное управление ботом, AI и автоматизацией", "Bot, AI va avtomatlashtirishni to'liq boshqarish", "Full control of bot, AI and automation"));
                    for (String n : notes) app.addView(UI.mt(UI.body2(c, "• " + n), 4));
                    body.addView(app);
                }
            });
        }
    }
}

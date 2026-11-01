package com.chathelper.control.screens;

import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chathelper.control.core.Fmt;
import com.chathelper.control.core.L;
import com.chathelper.control.ui.Theme;
import com.chathelper.control.ui.UI;
import com.chathelper.control.ui.widget.Chart;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Dashboard, sections hub, chats, connections + permission inspector, notifications, live monitor. */
public final class HomeScreens {
    private HomeScreens() {}

    static long now() { return System.currentTimeMillis() / 1000L; }

    // =====================================================================================================
    public static final class Dashboard extends Screen {
        @Override
        public String title() { return L.t("Главная", "Asosiy", "Home"); }

        @Override
        public void load() {
            if (body.getChildCount() == 0) loading();
            api.get("/dashboard", new Cb() {
                @Override
                public void ok(JSONObject d) {
                    render(d);
                }
            });
        }

        private void render(JSONObject d) {
            body.removeAllViews();
            JSONObject bot = d.optJSONObject("bot");
            JSONObject today = d.optJSONObject("today");
            boolean global = "global".equals(d.optString("scope"));
            JSONObject user = act.me().optJSONObject("user");
            String name = user != null ? user.optString("first_name", "") : "";
            body.addView(UI.caption(c, L.f("Привет, %s 👋", "Salom, %s 👋", "Hi, %s 👋", name.isEmpty() ? "👤" : name)));

            // hero status card
            boolean polling = bot != null && bot.optBoolean("polling");
            boolean emergency = bot != null && bot.optBoolean("emergency_stop");
            LinearLayout hero = UI.tinted(c, emergency ? Theme.DANGER : (polling ? Theme.accent : Theme.WARNING));
            LinearLayout hr = UI.row(c);
            hr.addView(UI.iconBubble(c, emergency ? "warning" : "pulse", emergency ? Theme.DANGER : Theme.SUCCESS));
            LinearLayout ht = UI.col(c);
            ht.setPadding(Theme.dp(12), 0, 0, 0);
            ht.addView(UI.h3(c, emergency ? L.t("Аварийная остановка", "Favqulodda to'xtatish", "Emergency stop")
                    : polling ? L.t("Chat helper работает", "Chat helper ishlayapti", "Chat helper is running")
                    : L.t("Бот не опрашивает Telegram", "Bot Telegram'ni so'ramayapti", "Bot is not polling Telegram")));
            JSONObject backend = d.optJSONObject("backend");
            String botName = bot != null && !bot.isNull("username") ? "@" + bot.optString("username") + " · " : "";
            ht.addView(UI.caption(c, botName + L.t("аптайм ", "ishlash ", "uptime ") + Fmt.duration(backend != null ? backend.optLong("uptime_sec") : 0)
                    + " · v" + d.optString("version")));
            hr.addView(ht, UI.weight(1));
            hero.addView(hr);
            if (!global) {
                JSONObject meInfo = d.optJSONObject("me");
                JSONObject conns = d.optJSONObject("connections");
                if (meInfo != null) {
                    LinearLayout chips = UI.row(c);
                    chips.setPadding(0, Theme.dp(12), 0, 0);
                    chips.addView(UI.badge(c, L.t("режим: ", "rejim: ", "mode: ") + meInfo.optString("mode"), Theme.accent));
                    chips.addView(UI.space(c, 0), UI.lp(Theme.dp(6), 1));
                    chips.addView(UI.badge(c, meInfo.optBoolean("afk") ? "AFK ●" : "AFK ○", meInfo.optBoolean("afk") ? Theme.WARNING : Theme.text3));
                    chips.addView(UI.space(c, 0), UI.lp(Theme.dp(6), 1));
                    chips.addView(UI.badge(c, meInfo.optString("plan").toUpperCase(), Theme.INFO));
                    if (conns != null) {
                        chips.addView(UI.space(c, 0), UI.lp(Theme.dp(6), 1));
                        chips.addView(UI.badge(c, conns.optString("status"), conns.optInt("active") > 0 ? Theme.SUCCESS : Theme.DANGER));
                    }
                    hero.addView(chips);
                }
            }
            body.addView(hero);

            // quick actions
            LinearLayout qa = UI.row(c);
            qa.addView(quick("moon", L.t("AFK", "AFK", "AFK"), new Runnable() {
                @Override
                public void run() {
                    toggleAfk();
                }
            }), UI.weight(1));
            qa.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
            qa.addView(quick("link", L.t("Подключения", "Ulanishlar", "Connections"), new Runnable() {
                @Override
                public void run() {
                    push(new Connections());
                }
            }), UI.weight(1));
            qa.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
            qa.addView(quick("pulse", L.t("Live", "Live", "Live"), new Runnable() {
                @Override
                public void run() {
                    push(new LiveMonitor());
                }
            }), UI.weight(1));
            body.addView(qa);

            // stat tiles
            body.addView(UI.section(c, L.t("Сегодня", "Bugun", "Today")));
            List<View> tiles = new ArrayList<View>();
            if (global) {
                JSONObject users = d.optJSONObject("users");
                JSONObject conns = d.optJSONObject("connections");
                tiles.add(UI.statTile(c, "users", Theme.accent, L.t("Пользователи", "Foydalanuvchilar", "Users"), users == null ? "—" : Fmt.number(users.optInt("total"))));
                tiles.add(UI.statTile(c, "link", Theme.SUCCESS, L.t("Подключения", "Ulanishlar", "Connections"), conns == null ? "—" : Fmt.number(conns.optInt("active"))));
            }
            tiles.add(UI.statTile(c, "chat", Theme.INFO, L.t("Входящие", "Kiruvchi", "Incoming"), Fmt.number(today.optDouble("messages_in"))));
            tiles.add(UI.statTile(c, "bolt", Theme.accent, L.t("Автоответы", "Avtojavoblar", "Auto replies"), Fmt.number(today.optDouble("auto_replies"))));
            tiles.add(UI.statTile(c, "sparkle", Theme.accent2(), L.t("AI-запросы", "AI so'rovlar", "AI requests"), Fmt.number(today.optDouble("ai_requests"))));
            tiles.add(UI.statTile(c, "star", Theme.WARNING, L.t("Расход AI", "AI xarajat", "AI cost"), Fmt.money(today.optDouble("ai_cost_usd"))));
            tiles.add(UI.statTile(c, "film", Theme.INFO, L.t("Медиа", "Media", "Media"), Fmt.number(today.optDouble("media_jobs"))));
            tiles.add(UI.statTile(c, "warning", Theme.DANGER, L.t("Ошибки", "Xatolar", "Errors"), Fmt.number(today.optDouble("errors"))));
            tiles.add(UI.statTile(c, "terminal", Theme.SUCCESS, L.t("Команды", "Buyruqlar", "Commands"), Fmt.number(today.optDouble("commands"))));
            tiles.add(UI.statTile(c, "game", Theme.accent, L.t("Игры", "O'yinlar", "Games"), Fmt.number(today.optDouble("games"))));
            if (global) {
                JSONObject subs = d.optJSONObject("subscriptions");
                tiles.add(UI.statTile(c, "crown", Theme.WARNING, L.t("Выручка ⭐", "Daromad ⭐", "Revenue ⭐"), subs == null ? "—" : Fmt.number(subs.optDouble("revenue_stars"))));
                JSONObject qd = d.optJSONObject("media_queue");
                tiles.add(UI.statTile(c, "server", Theme.INFO, L.t("Очередь медиа", "Media navbati", "Media queue"), qd == null ? "—" : String.valueOf(qd.optInt("queued") + qd.optInt("active"))));
            } else {
                tiles.add(UI.statTile(c, "chat", Theme.WARNING, L.t("Ждут ответа", "Javob kutmoqda", "Unanswered"), String.valueOf(d.optInt("unanswered"))));
            }
            body.addView(UI.grid(c, tiles, 2));

            // charts
            JSONObject charts = d.optJSONObject("charts");
            if (charts != null) {
                body.addView(UI.section(c, L.t("Активность за 14 дней", "14 kunlik faollik", "Activity · 14 days")));
                if (global && charts.optJSONArray("active_users") != null)
                    body.addView(chartCard(L.t("Активные пользователи", "Faol foydalanuvchilar", "Active users"), charts.optJSONArray("active_users"), Chart.LINE, Theme.SUCCESS));
                body.addView(chartCard(L.t("Сообщения", "Xabarlar", "Messages"), charts.optJSONArray("messages"), Chart.LINE, Theme.accent));
                body.addView(chartCard(L.t("AI-запросы", "AI so'rovlar", "AI requests"), charts.optJSONArray("ai_requests"), Chart.BAR, Theme.accent2()));
                body.addView(chartCard(L.t("Расход AI, $", "AI xarajati, $", "AI cost, $"), charts.optJSONArray("ai_cost"), Chart.LINE, Theme.WARNING));
                body.addView(chartCard(L.t("Ошибки", "Xatolar", "Errors"), charts.optJSONArray("errors"), Chart.BAR, Theme.DANGER));
            }
            JSONObject modules = d.optJSONObject("module_usage");
            if (modules != null && modules.length() > 0) {
                body.addView(UI.section(c, L.t("Использование модулей", "Modullardan foydalanish", "Module usage")));
                LinearLayout card = UI.card(c);
                JSONArray names = modules.names();
                double max = 1;
                for (int i = 0; i < names.length(); i++) max = Math.max(max, modules.optDouble(names.optString(i)));
                for (int i = 0; i < Math.min(8, names.length()); i++) {
                    String k = names.optString(i);
                    card.addView(bar(k, modules.optDouble(k), max));
                }
                body.addView(card);
            }
            JSONObject res = d.optJSONObject("resources");
            if (res != null) {
                body.addView(UI.section(c, L.t("Ресурсы устройства", "Qurilma resurslari", "Device resources")));
                LinearLayout card = UI.card(c);
                card.addView(UI.keyValue(c, "RAM (backend)", res.isNull("process_rss_mb") ? "—" : res.optDouble("process_rss_mb") + " MB"));
                card.addView(UI.keyValue(c, "CPU", res.isNull("cpu_percent") ? L.t("собирается…", "yig'ilmoqda…", "sampling…") : res.optDouble("cpu_percent") + "%"));
                JSONObject disk = res.optJSONObject("disk");
                if (disk != null) card.addView(UI.keyValue(c, L.t("Свободно", "Bo'sh joy", "Free disk"), disk.optLong("free_mb") + " MB"));
                card.addView(UI.keyValue(c, L.t("Временные файлы", "Vaqtinchalik fayllar", "Temp files"), res.optDouble("tmp_mb") + " MB"));
                body.addView(card);
            }
            JSONArray ev = d.optJSONArray("recent_events");
            body.addView(UI.section(c, L.t("Последняя активность", "So'nggi faollik", "Recent activity")));
            LinearLayout evCard = UI.card(c);
            if (ev == null || ev.length() == 0) {
                evCard.addView(UI.empty(c, "pulse", L.t("Пока тихо", "Hozircha jim", "All quiet"),
                        L.t("События появятся, когда бот получит сообщения.", "Bot xabar olganda hodisalar paydo bo'ladi.", "Events appear when the bot receives messages.")));
            } else {
                for (int i = ev.length() - 1; i >= Math.max(0, ev.length() - 8); i--) evCard.addView(eventRow(c, ev.optJSONObject(i)));
            }
            body.addView(evCard);
            body.addView(UI.section(c, L.t("Все разделы", "Barcha bo'limlar", "All sections")));
            body.addView(Sections.grid(this));
        }

        private View quick(String icon, String label, Runnable r) {
            LinearLayout card = UI.card(c);
            card.setGravity(android.view.Gravity.CENTER);
            card.setPadding(Theme.dp(8), Theme.dp(12), Theme.dp(8), Theme.dp(12));
            card.addView(UI.icon(c, icon, Theme.accent, 22));
            TextView t = UI.caption(c, label);
            t.setGravity(android.view.Gravity.CENTER);
            t.setPadding(0, Theme.dp(4), 0, 0);
            card.addView(t);
            UI.pressable(card);
            UI.onClick(card, r);
            return card;
        }

        private void toggleAfk() {
            api.get("/afk", new Cb(false) {
                @Override
                public void ok(JSONObject res) {
                    if (res.isNull("active")) {
                        UI.prompt(c, L.t("Включить AFK", "AFK'ni yoqish", "Enable AFK"), L.t("Причина (необязательно)", "Sabab (ixtiyoriy)", "Reason (optional)"), "", false, new UI.TextCallback() {
                            @Override
                            public void on(String v) {
                                api.post("/afk/enable", obj("reason", v.trim().isEmpty() ? null : v.trim()), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        toast("💤 AFK ✓");
                                        load();
                                    }
                                });
                            }
                        });
                    } else {
                        api.post("/afk/disable", null, new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast(L.t("AFK выключен", "AFK o'chirildi", "AFK disabled"));
                                load();
                            }
                        });
                    }
                }
            });
        }

        private View chartCard(String title, JSONArray series, int type, int color) {
            LinearLayout card = UI.card(c);
            LinearLayout head = UI.row(c);
            head.addView(UI.h3(c, title), UI.weight(1));
            double total = 0;
            double[] v = values(series);
            for (double x : v) total += x;
            head.addView(UI.caption(c, "Σ " + Fmt.number(total)));
            card.addView(head);
            Chart ch = new Chart(c, type, color);
            ch.setData(v, days(series));
            card.addView(UI.mt(ch, 8));
            if (ch.isEmpty()) card.addView(UI.caption(c, L.t("Нет данных за период", "Davr uchun ma'lumot yo'q", "No data for this period")));
            return card;
        }

        private View bar(String label, double value, double max) {
            LinearLayout l = UI.col(c);
            l.setPadding(0, Theme.dp(4), 0, Theme.dp(4));
            l.addView(UI.keyValue(c, label, Fmt.number(value)));
            View track = new View(c);
            android.graphics.drawable.GradientDrawable g = new android.graphics.drawable.GradientDrawable(
                    android.graphics.drawable.GradientDrawable.Orientation.LEFT_RIGHT, new int[]{Theme.accent, Theme.accent2()});
            g.setCornerRadius(Theme.dp(4));
            track.setBackground(g);
            LinearLayout wrap = UI.row(c);
            wrap.addView(track, new LinearLayout.LayoutParams(0, Theme.dp(6), (float) Math.max(0.02, value / max)));
            wrap.addView(new View(c), new LinearLayout.LayoutParams(0, Theme.dp(6), (float) Math.max(0, 1 - value / max)));
            l.addView(wrap);
            return l;
        }
    }

    static View eventRow(android.content.Context c, JSONObject e) {
        if (e == null) return new View(c);
        String kind = e.optString("kind");
        String icon = kind.startsWith("ai") ? "sparkle" : kind.startsWith("media") ? "film" : kind.startsWith("game") ? "game"
                : kind.startsWith("command") ? "terminal" : kind.startsWith("afk") ? "moon" : kind.startsWith("business") ? "link"
                : kind.startsWith("message") ? "chat" : kind.startsWith("auto") ? "bolt" : "pulse";
        String level = e.optString("level");
        int color = "warning".equals(level) ? Theme.WARNING : "error".equals(level) ? Theme.DANGER : Theme.accent;
        JSONObject data = e.optJSONObject("data");
        String detail = data == null ? "" : data.toString().replace("\"", "").replace("{", "").replace("}", "").replace(",", " · ");
        if (detail.length() > 120) detail = detail.substring(0, 120) + "…";
        return UI.listRow(c, icon, color, kind, detail, Fmt.time(e.optLong("ts")), null);
    }

    // =====================================================================================================
    /** All sections, gated by capabilities. */
    public static final class Sections {
        private Sections() {}

        public static View grid(final Screen s) {
            String[][] items = {
                    {"link", L.t("Подключения", "Ulanishlar", "Connections"), "connections", ""},
                    {"chat", L.t("Чаты", "Chatlar", "Chats"), "chats", ""},
                    {"terminal", L.t("Команды", "Buyruqlar", "Commands"), "commands", ""},
                    {"film", "Media Studio", "media", ""},
                    {"game", L.t("Игры", "O'yinlar", "Games"), "games", ""},
                    {"crown", L.t("Подписка", "Obuna", "Subscription"), "subscription", ""},
                    {"chart", L.t("Аналитика", "Analitika", "Analytics"), "analytics_self", ""},
                    {"shield", L.t("Безопасность", "Xavfsizlik", "Security"), "security_self", ""},
                    {"bell", L.t("Уведомления", "Bildirishnomalar", "Notifications"), "notifications", ""},
                    {"pulse", "Live Monitor", "dashboard", ""},
                    {"megaphone", L.t("Рассылки", "Tarqatmalar", "Broadcasts"), "broadcast_view", ""},
                    {"server", L.t("Система", "Tizim", "System"), "system", ""},
                    {"flag", "Feature Flags", "flags", ""},
                    {"help", L.t("Поддержка", "Yordam", "Support"), "dashboard", ""},
            };
            List<View> views = new ArrayList<View>();
            for (final String[] it : items) {
                if (!s.act.can(it[2])) continue;
                LinearLayout card = UI.card(s.c);
                card.setGravity(android.view.Gravity.CENTER_HORIZONTAL);
                card.setPadding(Theme.dp(6), Theme.dp(14), Theme.dp(6), Theme.dp(12));
                card.addView(UI.iconBubble(s.c, it[0], Theme.accent));
                TextView t = UI.caption(s.c, it[1]);
                t.setGravity(android.view.Gravity.CENTER);
                t.setTextColor(Theme.text2);
                t.setPadding(0, Theme.dp(6), 0, 0);
                card.addView(t);
                UI.pressable(card);
                UI.onClick(card, new Runnable() {
                    @Override
                    public void run() {
                        s.push(open(it[2], it[0]));
                    }
                });
                views.add(card);
            }
            return UI.grid(s.c, views, 3);
        }

        static Screen open(String key, String icon) {
            if ("connections".equals(key)) return new Connections();
            if ("chats".equals(key)) return new Chats();
            if ("commands".equals(key)) return new AutomationScreens.Commands();
            if ("media".equals(key)) return new AutomationScreens.Media();
            if ("games".equals(key)) return new AutomationScreens.Games();
            if ("subscription".equals(key)) return new AdminScreens.Subscriptions();
            if ("analytics_self".equals(key)) return new AdminScreens.Analytics();
            if ("security_self".equals(key)) return new AdminScreens.Security();
            if ("notifications".equals(key)) return new Notifications();
            if ("broadcast_view".equals(key)) return new AdminScreens.Broadcasts();
            if ("system".equals(key)) return new AdminScreens.SystemControl();
            if ("flags".equals(key)) return new AdminScreens.Flags();
            if ("help".equals(icon)) return new SettingsScreens.Support();
            return new LiveMonitor();
        }
    }

    // =====================================================================================================
    public static final class Chats extends Screen {
        private String query = "";
        private boolean unanswered;

        @Override
        public String title() { return L.t("Чаты", "Chatlar", "Chats"); }

        @Override
        public void load() {
            if (body.getChildCount() == 0) loading();
            String q = "/chats?page_size=100" + (unanswered ? "&unanswered=true" : "") + (query.isEmpty() ? "" : "&q=" + android.net.Uri.encode(query));
            api.get(q, new Cb() {
                @Override
                public void ok(JSONObject res) {
                    render(res);
                }
            });
        }

        private void render(JSONObject res) {
            body.removeAllViews();
            final EditText search = UI.input(c, L.t("Поиск по имени или @username", "Ism yoki @username bo'yicha qidirish", "Search by name or @username"), query, false);
            search.setOnEditorActionListener(new TextView.OnEditorActionListener() {
                @Override
                public boolean onEditorAction(TextView v, int actionId, android.view.KeyEvent event) {
                    query = search.getText().toString().trim();
                    load();
                    return true;
                }
            });
            body.addView(search);
            body.addView(UI.mt(UI.chips(c, new String[]{L.t("Все", "Hammasi", "All"), L.t("Ждут ответа", "Javob kutmoqda", "Unanswered")}, unanswered ? 1 : 0,
                    new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            unanswered = v == 1;
                            load();
                        }
                    }), 10));
            JSONArray items = res.optJSONArray("items");
            body.addView(UI.section(c, L.f("Чатов: %d", "Chatlar: %d", "Chats: %d", res.optInt("total"))));
            if (items == null || items.length() == 0) {
                body.addView(UI.empty(c, "chat", L.t("Чатов пока нет", "Hozircha chatlar yo'q", "No chats yet"),
                        L.t("Чаты появятся, когда вам напишут в подключённом бизнес-аккаунте. Мы показываем только данные, доступные через Bot API.",
                                "Ulangan biznes akkauntga yozishganda chatlar paydo bo'ladi. Faqat Bot API orqali mavjud ma'lumotlar ko'rsatiladi.",
                                "Chats appear when someone writes to your connected business account. Only data available via the Bot API is shown.")));
                return;
            }
            LinearLayout card = UI.card(c);
            for (int i = 0; i < items.length(); i++) {
                final JSONObject ch = items.optJSONObject(i);
                String title = ch.optString("title", String.valueOf(ch.optLong("chat_id")));
                String sub = (ch.isNull("last_preview") ? "" : ch.optString("last_preview"));
                String trail = ch.optInt("unanswered") > 0 ? "● " + ch.optInt("unanswered") : Fmt.ago(ch.optLong("last_incoming_at"), now());
                int color = ch.optInt("ignored") == 1 ? Theme.text3 : (ch.optInt("priority_score") >= 5 ? Theme.DANGER : Theme.accent);
                card.addView(UI.listRow(c, "user", color, title, sub, trail, new Runnable() {
                    @Override
                    public void run() {
                        push(new ChatDetail(ch.optLong("chat_id"), ch.optString("title")));
                    }
                }));
            }
            body.addView(card);
        }
    }

    public static final class ChatDetail extends Screen {
        private final long chatId;
        private final String name;

        ChatDetail(long chatId, String name) {
            this.chatId = chatId;
            this.name = name;
        }

        @Override
        public String title() { return name == null || name.isEmpty() ? String.valueOf(chatId) : name; }

        @Override
        public void load() {
            loading();
            api.get("/chats/" + chatId, new Cb() {
                @Override
                public void ok(JSONObject ch) {
                    render(ch);
                }
            });
        }

        private void patch(String key, Object value) {
            api.patch("/chats/" + chatId, put(new JSONObject(), key, value), new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    toast(L.t("Сохранено", "Saqlandi", "Saved"));
                }
            });
        }

        private View tri(String title, final String key, JSONObject ch) {
            int state = ch.isNull(key) ? 0 : (ch.optInt(key) == 1 ? 1 : 2);
            LinearLayout l = UI.col(c);
            l.setPadding(Theme.dp(4), Theme.dp(8), Theme.dp(4), Theme.dp(8));
            l.addView(UI.body(c, title));
            l.addView(UI.mt(UI.chips(c, new String[]{L.t("Как в настройках", "Sozlamadagidek", "Default"), L.t("Вкл", "Yoq", "On"), L.t("Выкл", "O'ch", "Off")}, state,
                    new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            patch(key, v == 0 ? JSONObject.NULL : (Object) (v == 1));
                            load();
                        }
                    }), 6));
            return l;
        }

        private void render(final JSONObject ch) {
            body.removeAllViews();
            LinearLayout info = UI.card(c);
            info.addView(UI.keyValue(c, "ID", String.valueOf(chatId)));
            if (!ch.isNull("username")) info.addView(UI.keyValue(c, "Username", "@" + ch.optString("username")));
            info.addView(UI.keyValue(c, L.t("Последнее входящее", "Oxirgi kiruvchi", "Last incoming"), Fmt.dateTime(ch.optLong("last_incoming_at"))));
            info.addView(UI.keyValue(c, L.t("Ждут ответа", "Javob kutmoqda", "Unanswered"), String.valueOf(ch.optInt("unanswered"))));
            info.addView(UI.keyValue(c, L.t("Автоответов сегодня", "Bugungi avtojavoblar", "Auto replies today"), String.valueOf(ch.optInt("auto_replies_today"))));
            JSONObject ctx = ch.optJSONObject("ai_context");
            if (ctx != null) info.addView(UI.keyValue(c, L.t("AI-контекст", "AI kontekst", "AI context"), ctx.optInt("messages") + " msg · " + ctx.optInt("facts") + " facts"));
            body.addView(info);
            body.addView(UI.section(c, L.t("Автоматизация в этом чате", "Bu chatda avtomatlashtirish", "Automation in this chat")));
            LinearLayout card = UI.card(c);
            card.addView(tri("🧠 AI", "ai_enabled", ch));
            card.addView(tri("💤 AFK", "afk_enabled", ch));
            card.addView(tri(L.t("💬 Автоответы", "💬 Avtojavoblar", "💬 Auto replies"), "autoreply_enabled", ch));
            card.addView(tri(L.t("✍️ Ручное подтверждение AI", "✍️ AI'ni qo'lda tasdiqlash", "✍️ Manual AI confirmation"), "manual_confirm", ch));
            card.addView(UI.toggleRow(c, L.t("Чёрный список", "Qora ro'yxat", "Blacklist"), L.t("Никаких автоответов", "Avtojavoblarsiz", "No automation"),
                    ch.optInt("ignored") == 1, new UI.BoolCallback() {
                        @Override
                        public void on(boolean v) {
                            patch("ignored", v);
                        }
                    }));
            card.addView(UI.toggleRow(c, L.t("Белый список", "Oq ro'yxat", "Whitelist"), null, ch.optInt("whitelisted") == 1, new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    patch("whitelisted", v);
                }
            }));
            body.addView(card);
            LinearLayout prefs = UI.card(c);
            final String[] langs = {"auto", "ru", "uz", "en"};
            int li = 0;
            for (int i = 0; i < langs.length; i++) if (langs[i].equals(ch.optString("language", "auto"))) li = i;
            prefs.addView(UI.caption(c, L.t("Язык ответов", "Javob tili", "Reply language")));
            prefs.addView(UI.mt(UI.chips(c, langs, li, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    patch("language", v == 0 ? JSONObject.NULL : langs[v]);
                    load();
                }
            }), 6));
            final String[] styles = {"—", "friendly", "professional", "funny", "smart", "short", "creative"};
            int si = 0;
            for (int i = 0; i < styles.length; i++) if (styles[i].equals(ch.optString("style"))) si = i;
            prefs.addView(UI.mt(UI.caption(c, L.t("Стиль AI", "AI uslubi", "AI style")), 12));
            prefs.addView(UI.mt(UI.chips(c, styles, si, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    patch("style", v == 0 ? JSONObject.NULL : styles[v]);
                    load();
                }
            }), 6));
            prefs.addView(UI.slider(c, L.t("Приоритет", "Ustuvorlik", "Priority"), -5, 5, ch.optInt("priority"), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    patch("priority", v);
                }
            }));
            prefs.addView(UI.slider(c, L.t("Лимит автоответов в день", "Kunlik avtojavob limiti", "Daily auto-reply limit"), 0, 100,
                    ch.isNull("reply_limit") ? 20 : ch.optInt("reply_limit"), "", new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            patch("reply_limit", v == 0 ? JSONObject.NULL : (Object) v);
                        }
                    }));
            body.addView(prefs);
            body.addView(UI.button(c, L.t("Заглушить на 8 часов", "8 soatga o'chirish", "Mute for 8 hours"), false, new Runnable() {
                @Override
                public void run() {
                    patch("muted_until", now() + 8 * 3600);
                }
            }));
            body.addView(UI.space(c, 10));
            body.addView(UI.button(c, L.t("Очистить AI-историю", "AI tarixini tozalash", "Clear AI history"), false, new Runnable() {
                @Override
                public void run() {
                    api.delete("/chats/" + chatId + "/history", new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast(L.f("Удалено: %d", "O'chirildi: %d", "Deleted: %d", r.optInt("deleted")));
                        }
                    });
                }
            }));
            body.addView(UI.space(c, 10));
            body.addView(UI.dangerButton(c, L.t("Удалить все данные чата", "Chatning barcha ma'lumotlarini o'chirish", "Delete all chat data"), new Runnable() {
                @Override
                public void run() {
                    UI.confirm(c, L.t("Удалить данные чата?", "Chat ma'lumotlari o'chirilsinmi?", "Delete chat data?"),
                            L.t("Настройки, AI-память и черновики этого чата будут удалены.", "Bu chat sozlamalari, AI xotirasi va qoralamalari o'chiriladi.",
                                    "Settings, AI memory and drafts of this chat will be deleted."), L.t("Удалить", "O'chirish", "Delete"), new Runnable() {
                                @Override
                                public void run() {
                                    api.delete("/chats/" + chatId + "/data", new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            toast(L.t("Удалено", "O'chirildi", "Deleted"));
                                            act.back();
                                        }
                                    });
                                }
                            });
                }
            }));
        }
    }

    // =====================================================================================================
    public static final class Connections extends Screen {
        @Override
        public String title() { return L.t("Бизнес-подключения", "Biznes ulanishlar", "Business connections"); }

        @Override
        public void load() {
            loading();
            api.get("/connections" + (act.isAdmin() ? "?all=true" : ""), new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "link", L.t("Нет подключений", "Ulanishlar yo'q", "No connections"),
                                L.t("Telegram → Настройки → Telegram для бизнеса → Чат-боты → выберите Chat helper.",
                                        "Telegram → Sozlamalar → Telegram Business → Chat-botlar → Chat helper'ni tanlang.",
                                        "Telegram → Settings → Telegram Business → Chatbots → choose Chat helper.")));
                        return;
                    }
                    for (int i = 0; i < items.length(); i++) {
                        final JSONObject cn = items.optJSONObject(i);
                        String st = cn.optString("status");
                        int color = "connected".equals(st) ? Theme.SUCCESS : "disabled".equals(st) ? Theme.text3 : "limited".equals(st) ? Theme.WARNING : Theme.DANGER;
                        LinearLayout card = UI.tinted(c, color);
                        LinearLayout head = UI.row(c);
                        head.addView(UI.iconBubble(c, "link", color));
                        LinearLayout t = UI.col(c);
                        t.setPadding(Theme.dp(12), 0, 0, 0);
                        t.addView(UI.h3(c, cn.optString("status_title")));
                        t.addView(UI.caption(c, "ID " + cn.optLong("user_id") + (cn.isNull("username") ? "" : " · @" + cn.optString("username"))));
                        head.addView(t, UI.weight(1));
                        card.addView(head);
                        card.addView(UI.mt(UI.keyValue(c, L.t("Подключено", "Ulangan", "Connected"), Fmt.dateTime(cn.optLong("connected_at"))), 8));
                        card.addView(UI.keyValue(c, L.t("Последнее событие", "Oxirgi hodisa", "Last event"), Fmt.dateTime(cn.optLong("last_event_at"))));
                        card.addView(UI.keyValue(c, L.t("Доступно модулей", "Mavjud modullar", "Modules available"), cn.optInt("available_modules") + " / " + cn.optInt("total_modules")));
                        card.addView(UI.keyValue(c, L.t("Пауза", "Pauza", "Paused"), cn.optBoolean("paused") ? "✓" : "—"));
                        LinearLayout btns = UI.row(c);
                        UI.mt(btns, 10);
                        btns.addView(UI.smallButton(c, L.t("Inspector", "Tekshiruv", "Inspector"), new Runnable() {
                            @Override
                            public void run() {
                                push(new Inspector(cn.optString("id")));
                            }
                        }));
                        btns.addView(UI.space(c, 0), UI.lp(Theme.dp(8), 1));
                        btns.addView(UI.smallButton(c, cn.optBoolean("paused") ? L.t("Продолжить", "Davom", "Resume") : L.t("Пауза", "Pauza", "Pause"), new Runnable() {
                            @Override
                            public void run() {
                                api.post("/connections/" + cn.optString("id") + (cn.optBoolean("paused") ? "/resume" : "/pause"), null, new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        load();
                                    }
                                });
                            }
                        }));
                        btns.addView(UI.space(c, 0), UI.lp(Theme.dp(8), 1));
                        btns.addView(UI.smallButton(c, L.t("Обновить", "Yangilash", "Refresh"), new Runnable() {
                            @Override
                            public void run() {
                                api.post("/connections/" + cn.optString("id") + "/refresh", null, new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        toast(L.t("Права обновлены из Telegram", "Huquqlar Telegram'dan yangilandi", "Rights refreshed from Telegram"));
                                        load();
                                    }
                                });
                            }
                        }));
                        card.addView(btns);
                        body.addView(card);
                    }
                }
            });
        }
    }

    public static final class Inspector extends Screen {
        private final String id;

        Inspector(String id) { this.id = id; }

        @Override
        public String title() { return "Permission Inspector"; }

        @Override
        public void load() {
            loading();
            api.get("/connections/" + id + "/inspector", new Cb() {
                @Override
                public void ok(JSONObject r) {
                    body.removeAllViews();
                    body.addView(UI.h2(c, r.optString("status_title")));
                    body.addView(UI.section(c, L.t("Возможности", "Imkoniyatlar", "Capabilities")));
                    LinearLayout caps = UI.card(c);
                    JSONArray arr = r.optJSONArray("capabilities");
                    for (int i = 0; arr != null && i < arr.length(); i++) {
                        JSONObject cap = arr.optJSONObject(i);
                        boolean ok = cap.optBoolean("available");
                        JSONArray miss = cap.optJSONArray("missing_titles");
                        String sub = ok ? null : L.t("Нужно: ", "Kerak: ", "Requires: ") + (miss == null ? "" : miss.toString().replace("[", "").replace("]", "").replace("\"", ""));
                        caps.addView(UI.listRow(c, ok ? "check" : "close", ok ? Theme.SUCCESS : Theme.DANGER, cap.optString("description"), sub, null, null));
                    }
                    body.addView(caps);
                    body.addView(UI.section(c, L.t("Права бизнес-бота", "Biznes-bot huquqlari", "Business bot rights")));
                    LinearLayout rights = UI.card(c);
                    JSONObject rs = r.optJSONObject("rights");
                    JSONObject titles = r.optJSONObject("rights_titles");
                    if (rs != null) {
                        JSONArray names = rs.names();
                        for (int i = 0; names != null && i < names.length(); i++) {
                            String k = names.optString(i);
                            rights.addView(UI.keyValue(c, titles != null ? titles.optString(k, k) : k, rs.optBoolean(k) ? "✅" : "—"));
                        }
                    }
                    body.addView(rights);
                    JSONArray blocked = r.optJSONArray("commands_blocked");
                    if (blocked != null && blocked.length() > 0) {
                        body.addView(UI.section(c, L.f("Недоступные команды (%d)", "Mavjud bo'lmagan buyruqlar (%d)", "Blocked commands (%d)", blocked.length())));
                        LinearLayout bl = UI.card(c);
                        StringBuilder sb = new StringBuilder();
                        for (int i = 0; i < blocked.length(); i++) sb.append('.').append(blocked.optJSONObject(i).optString("command")).append("  ");
                        bl.addView(UI.mono(c, sb.toString()));
                        body.addView(bl);
                    }
                    body.addView(UI.section(c, L.t("Как исправить", "Qanday tuzatish", "How to fix")));
                    LinearLayout adv = UI.card(c);
                    JSONArray advice = r.optJSONArray("advice");
                    for (int i = 0; advice != null && i < advice.length(); i++) adv.addView(UI.listRow(c, "info", Theme.INFO, advice.optString(i), null, null, null));
                    body.addView(adv);
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Notifications extends Screen {
        @Override
        public String title() { return L.t("Уведомления", "Bildirishnomalar", "Notifications"); }

        @Override
        public void load() {
            loading();
            api.get("/notifications", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    body.addView(UI.button(c, L.t("Отметить всё прочитанным", "Hammasini o'qilgan deb belgilash", "Mark all as read"), false, new Runnable() {
                        @Override
                        public void run() {
                            api.post("/notifications/read", null, new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    load();
                                }
                            });
                        }
                    }));
                    body.addView(UI.space(c, 12));
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "bell", L.t("Уведомлений нет", "Bildirishnomalar yo'q", "No notifications"),
                                L.t("Здесь появятся важные события: подключения, ошибки, лимиты, безопасность.", "Bu yerda muhim hodisalar paydo bo'ladi.",
                                        "Important events appear here: connections, errors, limits, security.")));
                        return;
                    }
                    LinearLayout card = UI.card(c);
                    for (int i = 0; i < items.length(); i++) {
                        JSONObject n = items.optJSONObject(i);
                        String lvl = n.optString("level");
                        int color = "error".equals(lvl) ? Theme.DANGER : "warning".equals(lvl) ? Theme.WARNING : Theme.accent;
                        String title = (n.isNull("read_at") ? "● " : "") + n.optString("title");
                        card.addView(UI.listRow(c, "bell", color, title, n.optString("body"), Fmt.dateTime(n.optLong("created_at")), null));
                    }
                    body.addView(card);
                }
            });
        }
    }

    // =====================================================================================================
    public static final class LiveMonitor extends Screen {
        private final Handler h = new Handler(Looper.getMainLooper());
        private long lastId;
        private boolean paused;
        private LinearLayout list;
        private final Runnable tick = new Runnable() {
            @Override
            public void run() {
                poll();
                h.postDelayed(this, 2500);
            }
        };

        @Override
        public String title() { return "Live Monitor"; }

        @Override
        protected void build() {
            final TextView state = UI.caption(c, "● LIVE");
            state.setTextColor(Theme.SUCCESS);
            body.addView(state);
            body.addView(UI.mt(UI.button(c, L.t("Пауза / продолжить", "Pauza / davom", "Pause / resume"), false, new Runnable() {
                @Override
                public void run() {
                    paused = !paused;
                    state.setText(paused ? "❚❚ PAUSED" : "● LIVE");
                    state.setTextColor(paused ? Theme.WARNING : Theme.SUCCESS);
                }
            }), 8));
            list = UI.card(c);
            UI.mt(list, 12);
            list.addView(UI.caption(c, L.t("Ожидание событий… (опрос каждые 2.5 с)", "Hodisalar kutilmoqda… (har 2.5 s)", "Waiting for events… (polling every 2.5 s)")));
            body.addView(list);
        }

        @Override
        public void onShow() {
            super.onShow();
            h.removeCallbacks(tick);
            h.post(tick);
        }

        @Override
        public void onHide() {
            super.onHide();
            h.removeCallbacks(tick);
        }

        @Override
        public void load() {}

        private void poll() {
            if (paused || !visible()) return;
            api.get("/events?after_id=" + lastId, new Cb(false) {
                @Override
                public void ok(JSONObject res) {
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) return;
                    if (lastId == 0) list.removeAllViews();
                    for (int i = 0; i < items.length(); i++) {
                        JSONObject e = items.optJSONObject(i);
                        lastId = Math.max(lastId, e.optLong("id"));
                        list.addView(eventRow(c, e), 0);
                    }
                    while (list.getChildCount() > 120) list.removeViewAt(list.getChildCount() - 1);
                }
            });
        }
    }
}

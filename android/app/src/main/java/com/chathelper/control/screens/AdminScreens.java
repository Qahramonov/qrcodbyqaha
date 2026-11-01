package com.chathelper.control.screens;

import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chathelper.control.core.ApiError;
import com.chathelper.control.core.Api;
import com.chathelper.control.core.Fmt;
import com.chathelper.control.core.L;
import com.chathelper.control.ui.Theme;
import com.chathelper.control.ui.UI;
import com.chathelper.control.ui.widget.Chart;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/** Users, subscriptions, broadcasts, analytics, security, system control, feature flags. */
public final class AdminScreens {
    private AdminScreens() {}

    static long now() { return System.currentTimeMillis() / 1000L; }

    // =====================================================================================================
    public static final class Users extends Screen {
        private String q = "";
        private int filter;
        private int sort;
        private int page = 1;
        private final String[] sorts = {"last_seen", "created", "name"};

        @Override
        public String title() { return L.t("Пользователи", "Foydalanuvchilar", "Users"); }

        @Override
        public void load() {
            if (body.getChildCount() == 0) loading();
            StringBuilder path = new StringBuilder("/users?page_size=50&page=").append(page).append("&sort=").append(sorts[sort]);
            if (!q.isEmpty()) path.append("&q=").append(Uri.encode(q));
            if (filter == 1) path.append("&active_days=7");
            if (filter == 2) path.append("&connected=true");
            if (filter == 3) path.append("&connected=false");
            if (filter == 4) path.append("&plan=pro");
            if (filter == 5) path.append("&plan=vip");
            if (filter == 6) path.append("&status=restricted");
            api.get(path.toString(), new Cb() {
                @Override
                public void ok(JSONObject res) {
                    render(res);
                }
            });
        }

        private void render(JSONObject res) {
            body.removeAllViews();
            final EditText search = UI.input(c, L.t("Поиск: имя, @username или ID", "Qidiruv: ism, @username yoki ID", "Search: name, @username or ID"), q, false);
            search.setOnEditorActionListener(new TextView.OnEditorActionListener() {
                @Override
                public boolean onEditorAction(TextView v, int a, android.view.KeyEvent e) {
                    q = search.getText().toString().trim();
                    page = 1;
                    load();
                    return true;
                }
            });
            body.addView(search);
            body.addView(UI.mt(UI.chips(c, new String[]{L.t("Все", "Hammasi", "All"), L.t("Активные 7д", "Faol 7k", "Active 7d"), L.t("Подключены", "Ulangan", "Connected"),
                    L.t("Без подключения", "Ulanmagan", "Not connected"), "PRO", "VIP", L.t("Ограничены", "Cheklangan", "Restricted")}, filter, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    filter = v;
                    page = 1;
                    load();
                }
            }), 10));
            body.addView(UI.mt(UI.chips(c, new String[]{L.t("По активности", "Faollik", "Last seen"), L.t("Новые", "Yangilar", "Newest"), L.t("По имени", "Ism", "Name")},
                    sort, new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            sort = v;
                            load();
                        }
                    }), 8));
            int total = res.optInt("total");
            body.addView(UI.section(c, L.f("Найдено: %d", "Topildi: %d", "Found: %d", total)));
            JSONArray items = res.optJSONArray("items");
            if (items == null || items.length() == 0) {
                body.addView(UI.empty(c, "users", L.t("Никого не найдено", "Hech kim topilmadi", "Nobody found"), null));
                return;
            }
            LinearLayout card = UI.card(c);
            for (int i = 0; i < items.length(); i++) {
                final JSONObject u = items.optJSONObject(i);
                String name = (u.optString("first_name", "") + " " + (u.isNull("last_name") ? "" : u.optString("last_name"))).trim();
                if (name.isEmpty()) name = String.valueOf(u.optLong("id"));
                String sub = (u.isNull("username") ? "" : "@" + u.optString("username") + " · ") + u.optString("plan").toUpperCase()
                        + " · " + (u.optInt("active_connections") > 0 ? "🔗" : "—") + ("restricted".equals(u.optString("status")) ? " · ⛔" : "");
                card.addView(UI.listRow(c, "user", u.optInt("active_connections") > 0 ? Theme.SUCCESS : Theme.text3, name, sub,
                        Fmt.ago(u.optLong("last_seen_at"), now()), new Runnable() {
                            @Override
                            public void run() {
                                push(new UserDetail(u.optLong("id")));
                            }
                        }));
            }
            body.addView(card);
            LinearLayout pager = UI.row(c);
            if (page > 1) pager.addView(UI.smallButton(c, "◀", new Runnable() {
                @Override
                public void run() {
                    page--;
                    load();
                }
            }));
            pager.addView(UI.caption(c, "  " + page + "  "));
            if (page * 50 < total) pager.addView(UI.smallButton(c, "▶", new Runnable() {
                @Override
                public void run() {
                    page++;
                    load();
                }
            }));
            body.addView(pager);
        }
    }

    public static final class UserDetail extends Screen {
        private final long uid;

        UserDetail(long uid) { this.uid = uid; }

        @Override
        public String title() { return "ID " + uid; }

        @Override
        public void load() {
            loading();
            api.get("/users/" + uid, new Cb() {
                @Override
                public void ok(JSONObject r) {
                    render(r);
                }
            });
        }

        private void render(final JSONObject r) {
            body.removeAllViews();
            JSONObject u = r.optJSONObject("user");
            LinearLayout card = UI.card(c);
            card.addView(UI.h2(c, (u.optString("first_name", "") + " " + (u.isNull("last_name") ? "" : u.optString("last_name"))).trim()));
            card.addView(UI.caption(c, (u.isNull("username") ? "" : "@" + u.optString("username") + " · ") + "ID " + uid));
            card.addView(UI.divider(c));
            card.addView(UI.keyValue(c, L.t("Роль", "Rol", "Role"), r.optString("role")));
            card.addView(UI.keyValue(c, L.t("Тариф", "Tarif", "Plan"), r.optString("plan").toUpperCase()));
            card.addView(UI.keyValue(c, L.t("Статус", "Holat", "Status"), u.optString("status") + (u.isNull("restricted_reason") ? "" : " (" + u.optString("restricted_reason") + ")")));
            card.addView(UI.keyValue(c, L.t("Регистрация", "Ro'yxatdan o'tgan", "Registered"), Fmt.dateTime(u.optLong("created_at"))));
            card.addView(UI.keyValue(c, L.t("Активность", "Faollik", "Last seen"), Fmt.dateTime(u.optLong("last_seen_at"))));
            card.addView(UI.keyValue(c, L.t("Язык", "Til", "Language"), u.optString("language")));
            body.addView(card);
            JSONObject usage = r.optJSONObject("usage");
            if (usage != null) {
                body.addView(UI.section(c, L.t("Использование", "Foydalanish", "Usage")));
                LinearLayout uc = UI.card(c);
                uc.addView(UI.keyValue(c, L.t("AI-запросов всего", "Jami AI so'rovlar", "AI requests total"), String.valueOf(usage.optInt("ai_requests_total"))));
                uc.addView(UI.keyValue(c, L.t("Расход AI всего", "Jami AI xarajati", "AI cost total"), Fmt.money(usage.optDouble("ai_cost_total"))));
                uc.addView(UI.keyValue(c, L.t("AI сегодня", "AI bugun", "AI today"), String.valueOf(usage.optInt("ai_today"))));
                uc.addView(UI.keyValue(c, L.t("Медиа сегодня", "Media bugun", "Media today"), String.valueOf(usage.optInt("media_today"))));
                uc.addView(UI.keyValue(c, L.t("Команд всего", "Jami buyruqlar", "Commands total"), String.valueOf(usage.optInt("commands_total"))));
                body.addView(uc);
            }
            JSONObject limits = r.optJSONObject("limits");
            if (limits != null) {
                body.addView(UI.section(c, L.t("Лимиты", "Limitlar", "Limits")));
                LinearLayout lc = UI.card(c);
                JSONArray names = limits.names();
                for (int i = 0; names != null && i < names.length(); i++) {
                    String k = names.optString(i);
                    int v = limits.optInt(k);
                    lc.addView(UI.keyValue(c, k, v == -1 ? "∞" : String.valueOf(v)));
                }
                body.addView(lc);
            }
            JSONArray conns = r.optJSONArray("connections");
            body.addView(UI.section(c, L.t("Подключения", "Ulanishlar", "Connections")));
            LinearLayout cc = UI.card(c);
            if (conns == null || conns.length() == 0) cc.addView(UI.caption(c, L.t("Нет бизнес-подключений", "Biznes ulanishlar yo'q", "No business connections")));
            for (int i = 0; conns != null && i < conns.length(); i++) {
                JSONObject cn = conns.optJSONObject(i);
                cc.addView(UI.listRow(c, "link", "connected".equals(cn.optString("status")) ? Theme.SUCCESS : Theme.WARNING, cn.optString("status"),
                        Fmt.dateTime(cn.optLong("connected_at")), null, null));
            }
            body.addView(cc);
            TextView note = UI.caption(c, "🔒 " + r.optString("note"));
            note.setPadding(Theme.dp(4), 0, Theme.dp(4), Theme.dp(8));
            body.addView(note);
            body.addView(UI.section(c, L.t("Действия", "Amallar", "Actions")));
            if (act.isSuper()) {
                body.addView(UI.button(c, L.t("Выдать подписку", "Obuna berish", "Grant subscription"), true, new Runnable() {
                    @Override
                    public void run() {
                        final String[] plans = {"plus", "pro", "vip"};
                        UI.choose(c, L.t("Тариф", "Tarif", "Plan"), new String[]{"Plus", "Pro", "VIP"}, new UI.IntCallback() {
                            @Override
                            public void on(final int p) {
                                UI.prompt(c, L.t("Сколько дней?", "Necha kun?", "How many days?"), "30", "30", false, new UI.TextCallback() {
                                    @Override
                                    public void on(String v) {
                                        int days;
                                        try {
                                            days = Integer.parseInt(v.trim());
                                        } catch (Exception e) {
                                            toast(L.t("Нужно число", "Raqam kerak", "Number required"));
                                            return;
                                        }
                                        api.post("/users/" + uid + "/subscription", put(put(new JSONObject(), "plan_id", plans[p]), "days", days), new Cb(false) {
                                            @Override
                                            public void ok(JSONObject res) {
                                                toast("💎 ✓");
                                                load();
                                            }
                                        });
                                    }
                                });
                            }
                        });
                    }
                }));
                body.addView(UI.space(c, 10));
                body.addView(UI.button(c, L.t("Отозвать подписку", "Obunani bekor qilish", "Revoke subscription"), false, new Runnable() {
                    @Override
                    public void run() {
                        api.delete("/users/" + uid + "/subscription", new Cb(false) {
                            @Override
                            public void ok(JSONObject res) {
                                toast(L.t("Отозвано", "Bekor qilindi", "Revoked"));
                                load();
                            }
                        });
                    }
                }));
                body.addView(UI.space(c, 10));
                final boolean mod = "moderator".equals(r.optString("role"));
                if (!"super_admin".equals(r.optString("role"))) {
                    body.addView(UI.button(c, mod ? L.t("Снять модератора", "Moderatorlikni olib tashlash", "Remove moderator") : L.t("Назначить модератором", "Moderator qilish", "Make moderator"), false, new Runnable() {
                        @Override
                        public void run() {
                            api.put("/users/" + uid + "/role", obj("role", mod ? "user" : "moderator"), new Cb(false) {
                                @Override
                                public void ok(JSONObject res) {
                                    load();
                                }
                            });
                        }
                    }));
                    body.addView(UI.space(c, 10));
                }
            }
            final boolean restricted = "restricted".equals(u.optString("status"));
            if (!"super_admin".equals(r.optString("role"))) {
                body.addView(restricted ? UI.button(c, L.t("Восстановить доступ", "Kirishni tiklash", "Restore access"), false, new Runnable() {
                    @Override
                    public void run() {
                        api.post("/users/" + uid + "/restore", null, new Cb(false) {
                            @Override
                            public void ok(JSONObject res) {
                                load();
                            }
                        });
                    }
                }) : UI.dangerButton(c, L.t("Ограничить доступ", "Kirishni cheklash", "Restrict access"), new Runnable() {
                    @Override
                    public void run() {
                        UI.prompt(c, L.t("Причина ограничения", "Cheklash sababi", "Restriction reason"), "", "", false, new UI.TextCallback() {
                            @Override
                            public void on(String v) {
                                if (v.trim().length() < 2) return;
                                api.post("/users/" + uid + "/restrict", obj("reason", v.trim()), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject res) {
                                        toast("⛔ ✓");
                                        load();
                                    }
                                });
                            }
                        });
                    }
                }));
            }
            body.addView(UI.space(c, 10));
            body.addView(UI.button(c, L.t("История действий", "Amallar tarixi", "Admin history"), false, new Runnable() {
                @Override
                public void run() {
                    push(new AuditList("/users/" + uid + "/audit", L.t("История действий", "Amallar tarixi", "Admin history")));
                }
            }));
        }
    }

    public static final class AuditList extends Screen {
        private final String path, name;

        AuditList(String path, String name) {
            this.path = path;
            this.name = name;
        }

        @Override
        public String title() { return name; }

        @Override
        public void load() {
            loading();
            api.get(path, new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "shield", L.t("Записей нет", "Yozuvlar yo'q", "No records"), null));
                        return;
                    }
                    LinearLayout card = UI.card(c);
                    for (int i = 0; i < items.length(); i++) {
                        JSONObject a = items.optJSONObject(i);
                        JSONObject det = a.optJSONObject("details");
                        String sub = (a.isNull("actor_id") ? a.optString("actor_type") : "by " + a.optLong("actor_id")) + (det != null && det.length() > 0 ? " · " + det : "");
                        card.addView(UI.listRow(c, "shield", Theme.accent, a.optString("action"), sub, Fmt.dateTime(a.optLong("created_at")), null));
                    }
                    body.addView(card);
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Subscriptions extends Screen {
        @Override
        public String title() { return L.t("Подписки", "Obunalar", "Subscriptions"); }

        @Override
        public void load() {
            loading();
            api.get("/subscriptions/me", new Cb() {
                @Override
                public void ok(final JSONObject mine) {
                    api.get("/subscriptions/plans", new Cb() {
                        @Override
                        public void ok(JSONObject plans) {
                            render(mine, plans);
                        }
                    });
                }
            });
        }

        private void render(JSONObject mine, JSONObject plans) {
            body.removeAllViews();
            LinearLayout my = UI.tinted(c, Theme.accent);
            my.addView(UI.caption(c, L.t("Ваш тариф", "Tarifingiz", "Your plan")));
            my.addView(UI.h1(c, mine.optString("plan").toUpperCase()));
            JSONObject sub = mine.optJSONObject("subscription");
            if (sub != null && !sub.isNull("expires_at")) my.addView(UI.caption(c, L.t("до ", "gacha ", "until ") + Fmt.dateTime(sub.optLong("expires_at"))));
            body.addView(my);
            LinearLayout act2 = UI.row(c);
            act2.addView(UI.button(c, L.t("Пробный период", "Sinov muddati", "Free trial"), false, new Runnable() {
                @Override
                public void run() {
                    api.post("/subscriptions/trial", null, new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast("🆓 Plus ✓");
                            load();
                        }
                    });
                }
            }), UI.weight(1));
            act2.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
            act2.addView(UI.button(c, L.t("Промокод", "Promokod", "Promo code"), false, new Runnable() {
                @Override
                public void run() {
                    UI.prompt(c, L.t("Промокод", "Promokod", "Promo code"), "CH-XXXX", "", false, new UI.TextCallback() {
                        @Override
                        public void on(String v) {
                            api.post("/subscriptions/redeem", obj("code", v.trim()), new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    toast("🎉 " + r.optString("plan_id").toUpperCase());
                                    load();
                                }
                            });
                        }
                    });
                }
            }), UI.weight(1));
            body.addView(act2);
            body.addView(UI.section(c, L.t("Тарифы", "Tariflar", "Plans")));
            JSONArray items = plans.optJSONArray("items");
            for (int i = 0; items != null && i < items.length(); i++) {
                final JSONObject p = items.optJSONObject(i);
                LinearLayout card = UI.card(c);
                LinearLayout head = UI.row(c);
                head.addView(UI.h3(c, p.optString("name")), UI.weight(1));
                head.addView(UI.badge(c, p.optInt("price_stars") + " ⭐ / " + p.optInt("duration_days") + L.t("д", "k", "d"), Theme.WARNING));
                card.addView(head);
                card.addView(UI.caption(c, p.optString("description")));
                JSONObject lim = p.optJSONObject("limits");
                if (lim != null) card.addView(UI.mt(UI.caption(c, "AI " + lim.optInt("ai_requests_day") + "/" + L.t("день", "kun", "day") + " · Media " + lim.optInt("media_jobs_day")
                        + " · " + L.t("правил ", "qoidalar ", "rules ") + (lim.optInt("autoreply_rules") == -1 ? "∞" : String.valueOf(lim.optInt("autoreply_rules")))), 6));
                if (act.isSuper()) {
                    card.addView(UI.mt(UI.smallButton(c, L.t("Изменить цену/срок", "Narx/muddatni o'zgartirish", "Edit price/duration"), new Runnable() {
                        @Override
                        public void run() {
                            UI.prompt(c, p.optString("name") + ": " + L.t("цена в Stars и дни через пробел", "Stars narxi va kunlar", "price in Stars and days"),
                                    "150 30", p.optInt("price_stars") + " " + p.optInt("duration_days"), false, new UI.TextCallback() {
                                        @Override
                                        public void on(String v) {
                                            String[] parts = v.trim().split("\\s+");
                                            try {
                                                JSONObject b = new JSONObject();
                                                b.put("name", p.optString("name"));
                                                b.put("price_stars", Integer.parseInt(parts[0]));
                                                b.put("duration_days", Integer.parseInt(parts.length > 1 ? parts[1] : "30"));
                                                b.put("description", p.optString("description"));
                                                b.put("sort", p.optInt("sort"));
                                                api.put("/subscriptions/plans/" + p.optString("id"), b, new Cb(false) {
                                                    @Override
                                                    public void ok(JSONObject r) {
                                                        toast("✓");
                                                        load();
                                                    }
                                                });
                                            } catch (Exception e) {
                                                toast(L.t("Формат: 150 30", "Format: 150 30", "Format: 150 30"));
                                            }
                                        }
                                    });
                        }
                    }), 10));
                }
                body.addView(card);
            }
            if (!plans.optBoolean("payments_enabled")) {
                body.addView(UI.caption(c, L.t("ℹ️ Оплата Telegram Stars выключена (PAYMENTS_ENABLED=false). Подписку выдаёт администратор или промокод.",
                        "ℹ️ Telegram Stars to'lovi o'chirilgan. Obunani administrator yoki promokod beradi.",
                        "ℹ️ Telegram Stars payments are disabled. Subscriptions come from the admin or promo codes.")));
            }
            if (act.isSuper()) {
                body.addView(UI.section(c, L.t("Промокоды", "Promokodlar", "Promo codes")));
                body.addView(UI.button(c, L.t("Создать промокод", "Promokod yaratish", "Create promo code"), true, new Runnable() {
                    @Override
                    public void run() {
                        UI.prompt(c, L.t("Тариф дни использований", "Tarif kunlar foydalanishlar", "Plan days uses"), "pro 30 10", "plus 7 1", false, new UI.TextCallback() {
                            @Override
                            public void on(String v) {
                                String[] parts = v.trim().split("\\s+");
                                try {
                                    JSONObject b = new JSONObject();
                                    b.put("plan_id", parts[0]);
                                    b.put("days", Integer.parseInt(parts[1]));
                                    b.put("max_uses", parts.length > 2 ? Integer.parseInt(parts[2]) : 1);
                                    api.post("/subscriptions/promo", b, new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            UI.info(c, L.t("Промокод создан", "Promokod yaratildi", "Promo code created"), r.optString("code"));
                                            load();
                                        }
                                    });
                                } catch (Exception e) {
                                    toast(L.t("Формат: plus 7 1", "Format: plus 7 1", "Format: plus 7 1"));
                                }
                            }
                        });
                    }
                }));
                final LinearLayout promoCard = UI.card(c);
                UI.mt(promoCard, 10);
                promoCard.addView(UI.caption(c, "…"));
                body.addView(promoCard);
                api.get("/subscriptions/promo", new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        promoCard.removeAllViews();
                        JSONArray ps = r.optJSONArray("items");
                        if (ps == null || ps.length() == 0) promoCard.addView(UI.caption(c, L.t("Промокодов нет", "Promokodlar yo'q", "No promo codes")));
                        for (int i = 0; ps != null && i < ps.length(); i++) {
                            final JSONObject p = ps.optJSONObject(i);
                            promoCard.addView(UI.listRow(c, "key", p.optInt("is_active") == 1 ? Theme.SUCCESS : Theme.text3, p.optString("code"),
                                    p.optString("plan_id") + " · " + p.optInt("days") + "d · " + p.optInt("used_count") + "/" + p.optInt("max_uses"),
                                    p.optInt("is_active") == 1 ? "✕" : "", p.optInt("is_active") == 1 ? new Runnable() {
                                        @Override
                                        public void run() {
                                            api.delete("/subscriptions/promo/" + p.optString("code"), new Cb(false) {
                                                @Override
                                                public void ok(JSONObject x) {
                                                    load();
                                                }
                                            });
                                        }
                                    } : null));
                        }
                    }
                });
                body.addView(UI.section(c, L.t("Статистика", "Statistika", "Statistics")));
                final LinearLayout st = UI.card(c);
                body.addView(st);
                api.get("/subscriptions/stats", new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        JSONObject byPlan = r.optJSONObject("active_by_plan");
                        JSONArray n = byPlan == null ? null : byPlan.names();
                        for (int i = 0; n != null && i < n.length(); i++) st.addView(UI.keyValue(c, n.optString(i).toUpperCase(), String.valueOf(byPlan.optInt(n.optString(i)))));
                        st.addView(UI.keyValue(c, L.t("Выручка", "Daromad", "Revenue"), r.optInt("revenue_stars") + " ⭐"));
                        st.addView(UI.keyValue(c, L.t("Истекают за 3 дня", "3 kunda tugaydi", "Expiring in 3 days"), String.valueOf(r.optInt("expiring_3d"))));
                    }
                });
            }
        }
    }

    // =====================================================================================================
    public static final class Broadcasts extends Screen {
        private final Handler h = new Handler(Looper.getMainLooper());
        private final Runnable poll = new Runnable() {
            @Override
            public void run() {
                if (visible()) load();
            }
        };

        @Override
        public String title() { return L.t("Рассылки", "Tarqatmalar", "Broadcasts"); }

        @Override
        public void onHide() {
            super.onHide();
            h.removeCallbacks(poll);
        }

        @Override
        public void load() {
            if (body.getChildCount() == 0) loading();
            api.get("/broadcasts", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    TextView note = UI.caption(c, L.t("Рассылки отправляются только пользователям бота, которые не запретили контакт. Бизнес-подключения для рассылок не используются.",
                            "Tarqatmalar faqat bot foydalanuvchilariga yuboriladi. Biznes ulanishlar ishlatilmaydi.",
                            "Broadcasts go only to bot users who allowed contact. Business connections are never used for mass messages."));
                    note.setPadding(Theme.dp(4), 0, Theme.dp(4), Theme.dp(12));
                    body.addView(note);
                    if (act.isSuper()) body.addView(UI.button(c, L.t("Новая рассылка", "Yangi tarqatma", "New broadcast"), true, new Runnable() {
                        @Override
                        public void run() {
                            compose();
                        }
                    }));
                    JSONArray items = res.optJSONArray("items");
                    boolean running = false;
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "megaphone", L.t("Рассылок ещё не было", "Hali tarqatmalar bo'lmagan", "No broadcasts yet"), null));
                    } else {
                        LinearLayout card = UI.card(c);
                        UI.mt(card, 12);
                        for (int i = 0; i < items.length(); i++) {
                            final JSONObject b = items.optJSONObject(i);
                            String st = b.optString("status");
                            running |= "running".equals(st);
                            String sub = st + " · " + b.optInt("sent") + "/" + b.optInt("total") + (b.optInt("failed") > 0 ? " · ✕" + b.optInt("failed") : "");
                            card.addView(UI.listRow(c, "megaphone", "done".equals(st) ? Theme.SUCCESS : "running".equals(st) ? Theme.INFO : Theme.text3,
                                    "#" + b.optInt("id") + " " + b.optString("text", "").replace("\n", " "), sub, Fmt.dateTime(b.optLong("created_at")), new Runnable() {
                                        @Override
                                        public void run() {
                                            manage(b);
                                        }
                                    }));
                        }
                        body.addView(card);
                    }
                    h.removeCallbacks(poll);
                    if (running) h.postDelayed(poll, 3000);
                }
            });
        }

        private void compose() {
            UI.prompt(c, L.t("Текст рассылки (HTML)", "Tarqatma matni (HTML)", "Broadcast text (HTML)"), "", "", true, new UI.TextCallback() {
                @Override
                public void on(final String text) {
                    if (text.trim().isEmpty()) return;
                    final String[] segs = {L.t("Все", "Hammasi", "Everyone"), L.t("Активные 7 дней", "7 kun faol", "Active 7 days"), L.t("С подключением", "Ulanganlar", "Connected"), "RU", "UZ"};
                    UI.choose(c, L.t("Сегмент", "Segment", "Segment"), segs, new UI.IntCallback() {
                        @Override
                        public void on(int s) {
                            JSONObject seg = new JSONObject();
                            if (s == 1) put(seg, "active_days", 7);
                            if (s == 2) put(seg, "connected", true);
                            if (s == 3) put(seg, "lang", "ru");
                            if (s == 4) put(seg, "lang", "uz");
                            JSONObject b = put(put(new JSONObject(), "text", text.trim()), "segment", seg);
                            api.post("/broadcasts", b, new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    toast(L.f("Черновик #%d · получателей: %d", "Qoralama #%d · qabul qiluvchilar: %d", "Draft #%d · recipients: %d",
                                            r.optInt("id"), r.optInt("recipients")));
                                    load();
                                }
                            });
                        }
                    });
                }
            });
        }

        private void manage(final JSONObject b) {
            if (!act.isSuper()) return;
            final int id = b.optInt("id");
            UI.choose(c, "#" + id, new String[]{L.t("Предпросмотр мне в Telegram", "Telegram'da menga ko'rish", "Preview to me in Telegram"),
                    L.t("Запустить", "Ishga tushirish", "Start"), L.t("Отменить", "Bekor qilish", "Cancel")}, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    if (v == 0) api.post("/broadcasts/" + id + "/preview", null, new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast(r.optBoolean("ok") ? "👁 ✓" : "⚠️");
                        }
                    });
                    if (v == 1) UI.confirm(c, L.t("Запустить рассылку?", "Tarqatma boshlansinmi?", "Start broadcast?"),
                            L.t("Сообщение получат все пользователи сегмента. Скорость ограничена лимитами Telegram.", "Xabarni segmentdagi barcha foydalanuvchilar oladi.",
                                    "All users of the segment will receive it. Speed respects Telegram limits."), L.t("Запустить", "Boshlash", "Start"), new Runnable() {
                                @Override
                                public void run() {
                                    api.post("/broadcasts/" + id + "/start", put(new JSONObject(), "confirm", true), new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            toast("🚀 " + r.optInt("total"));
                                            load();
                                        }
                                    });
                                }
                            });
                    if (v == 2) api.post("/broadcasts/" + id + "/cancel", null, new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            load();
                        }
                    });
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Analytics extends Screen {
        private int range = 1;
        private final int[] days = {7, 30, 90};

        @Override
        public String title() { return L.t("Аналитика", "Analitika", "Analytics"); }

        private String query() {
            long to = now();
            long from = to - (days[range] - 1) * 86400L;
            java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US);
            f.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
            return "from=" + f.format(new java.util.Date(from * 1000)) + "&to=" + f.format(new java.util.Date(to * 1000));
        }

        @Override
        public void load() {
            loading();
            api.get("/analytics/overview?" + query(), new Cb() {
                @Override
                public void ok(JSONObject d) {
                    render(d);
                }
            });
        }

        private void render(JSONObject d) {
            body.removeAllViews();
            body.addView(UI.chips(c, new String[]{"7d", "30d", "90d"}, range, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    range = v;
                    load();
                }
            }));
            body.addView(UI.caption(c, d.optString("from") + " — " + d.optString("to") + " · " + d.optString("scope")));
            JSONObject totals = d.optJSONObject("totals");
            List<View> tiles = new ArrayList<View>();
            if (d.optJSONObject("active") != null) {
                JSONArray dau = d.optJSONObject("active").optJSONArray("dau");
                JSONArray wau = d.optJSONObject("active").optJSONArray("wau");
                JSONArray mau = d.optJSONObject("active").optJSONArray("mau");
                tiles.add(UI.statTile(c, "users", Theme.accent, "DAU", last(dau)));
                tiles.add(UI.statTile(c, "users", Theme.INFO, "WAU", last(wau)));
                tiles.add(UI.statTile(c, "users", Theme.SUCCESS, "MAU", last(mau)));
                JSONObject ret = d.optJSONObject("retention");
                tiles.add(UI.statTile(c, "refresh", Theme.WARNING, "Retention D1/D7", ret == null ? "—" : pct(ret, "d1") + " / " + pct(ret, "d7")));
                JSONObject churn = d.optJSONObject("churn");
                tiles.add(UI.statTile(c, "logout", Theme.DANGER, "Churn 30d", churn == null || churn.isNull("rate") ? "—" : Fmt.percent(churn.optDouble("rate"))));
            }
            if (totals != null) {
                tiles.add(UI.statTile(c, "terminal", Theme.accent, L.t("Команды", "Buyruqlar", "Commands"), Fmt.number(totals.optDouble("commands"))));
                tiles.add(UI.statTile(c, "sparkle", Theme.accent2(), "AI", Fmt.number(totals.optDouble("ai_requests"))));
                tiles.add(UI.statTile(c, "star", Theme.WARNING, L.t("Расход AI", "AI xarajati", "AI cost"), Fmt.money(totals.optDouble("ai_cost_usd"))));
                tiles.add(UI.statTile(c, "crown", Theme.WARNING, L.t("Выручка", "Daromad", "Revenue"), Fmt.number(totals.optDouble("revenue_stars")) + " ⭐"));
            }
            body.addView(UI.mt(UI.grid(c, tiles, 2), 10));
            JSONObject series = d.optJSONObject("series");
            if (d.optJSONObject("active") != null) body.addView(chart("DAU", d.optJSONObject("active").optJSONArray("dau"), Chart.LINE, Theme.accent));
            if (d.optJSONArray("new_users") != null) body.addView(chart(L.t("Новые пользователи", "Yangi foydalanuvchilar", "New users"), d.optJSONArray("new_users"), Chart.BAR, Theme.SUCCESS));
            if (series != null) {
                body.addView(chart(L.t("Входящие сообщения", "Kiruvchi xabarlar", "Incoming messages"), series.optJSONArray("messages_in"), Chart.LINE, Theme.INFO));
                body.addView(chart(L.t("Команды", "Buyruqlar", "Commands"), series.optJSONArray("commands"), Chart.BAR, Theme.accent));
                body.addView(chart("AI", series.optJSONArray("ai_requests"), Chart.BAR, Theme.accent2()));
                body.addView(chart(L.t("Токены", "Tokenlar", "Tokens"), series.optJSONArray("ai_tokens"), Chart.LINE, Theme.accent2()));
                body.addView(chart(L.t("Расход API, $", "API xarajati, $", "API cost, $"), series.optJSONArray("ai_cost_usd"), Chart.LINE, Theme.WARNING));
                body.addView(chart(L.t("Медиа-задачи", "Media vazifalar", "Media jobs"), series.optJSONArray("media_jobs"), Chart.BAR, Theme.INFO));
                body.addView(chart(L.t("Ошибки", "Xatolar", "Errors"), series.optJSONArray("errors"), Chart.BAR, Theme.DANGER));
                body.addView(chart(L.t("Выручка ⭐", "Daromad ⭐", "Revenue ⭐"), series.optJSONArray("revenue_stars"), Chart.BAR, Theme.WARNING));
            }
            body.addView(UI.section(c, L.t("Экспорт отчёта", "Hisobotni eksport", "Export report")));
            LinearLayout ex = UI.row(c);
            for (final String fmt : new String[]{"csv", "json", "pdf"}) {
                ex.addView(UI.button(c, fmt.toUpperCase(), false, new Runnable() {
                    @Override
                    public void run() {
                        export(fmt);
                    }
                }), UI.weight(1));
                if (!"pdf".equals(fmt)) ex.addView(UI.space(c, 0), UI.lp(Theme.dp(8), 1));
            }
            body.addView(ex);
        }

        private static String last(JSONArray a) {
            return a == null || a.length() == 0 ? "—" : Fmt.number(a.optJSONObject(a.length() - 1).optDouble("value"));
        }

        private static String pct(JSONObject o, String k) { return o.isNull(k) ? "—" : Fmt.percent(o.optDouble(k)); }

        private View chart(String title, JSONArray s, int type, int color) {
            LinearLayout card = UI.card(c);
            card.addView(UI.h3(c, title));
            Chart ch = new Chart(c, type, color);
            ch.setData(values(s), days(s));
            card.addView(UI.mt(ch, 8));
            if (ch.isEmpty()) card.addView(UI.caption(c, L.t("Нет данных", "Ma'lumot yo'q", "No data")));
            return card;
        }

        private void export(final String fmt) {
            toast(L.t("Готовлю отчёт…", "Hisobot tayyorlanmoqda…", "Preparing report…"));
            api.download("/analytics/export?format=" + fmt + "&" + query(), new Api.BytesCallback() {
                @Override
                public void ok(byte[] data, String contentType) {
                    String name = "chat_helper_analytics_" + now() + "." + fmt;
                    String where = Files.save(act, name, contentType, data);
                    toast(where == null ? "⚠️" : L.t("Сохранено: ", "Saqlandi: ", "Saved: ") + where);
                }

                @Override
                public void fail(ApiError err) {
                    toast(err.human());
                }
            });
        }
    }

    /** Saves exported files to Downloads (API 29+) or the app's external files dir. */
    public static final class Files {
        private Files() {}

        public static String save(android.app.Activity a, String name, String mime, byte[] data) {
            try {
                if (Build.VERSION.SDK_INT >= 29) {
                    ContentValues v = new ContentValues();
                    v.put(MediaStore.Downloads.DISPLAY_NAME, name);
                    v.put(MediaStore.Downloads.MIME_TYPE, mime == null ? "application/octet-stream" : mime.split(";")[0]);
                    v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/ChatHelper");
                    Uri uri = a.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                    if (uri == null) return null;
                    OutputStream os = a.getContentResolver().openOutputStream(uri);
                    os.write(data);
                    os.close();
                    return "Download/ChatHelper/" + name;
                }
                File dir = a.getExternalFilesDir(null);
                File f = new File(dir, name);
                FileOutputStream fos = new FileOutputStream(f);
                fos.write(data);
                fos.close();
                return f.getAbsolutePath();
            } catch (Exception e) {
                return null;
            }
        }

        public static void share(android.app.Activity a, String text) {
            Intent i = new Intent(Intent.ACTION_SEND);
            i.setType("text/plain");
            i.putExtra(Intent.EXTRA_TEXT, text);
            a.startActivity(Intent.createChooser(i, "Chat helper"));
        }
    }

    // =====================================================================================================
    public static final class Security extends Screen {
        @Override
        public String title() { return L.t("Безопасность", "Xavfsizlik", "Security"); }

        @Override
        public void load() {
            loading();
            api.get("/security/sessions", new Cb() {
                @Override
                public void ok(final JSONObject sessions) {
                    api.get("/security/logins", new Cb() {
                        @Override
                        public void ok(JSONObject logins) {
                            render(sessions, logins);
                        }
                    });
                }
            });
        }

        private void render(JSONObject sessions, JSONObject logins) {
            body.removeAllViews();
            if (act.isSuper()) {
                LinearLayout es = UI.tinted(c, Theme.DANGER);
                es.addView(UI.h3(c, "🛑 Emergency Stop"));
                es.addView(UI.caption(c, L.t("Мгновенно останавливает все автоответы, AI и действия в бизнес-чатах для всех пользователей.",
                        "Barcha foydalanuvchilar uchun avtojavob, AI va biznes chatlardagi amallarni darhol to'xtatadi.",
                        "Instantly stops all auto replies, AI and business-chat actions for every user.")));
                LinearLayout row = UI.row(c);
                UI.mt(row, 10);
                row.addView(UI.dangerButton(c, L.t("Остановить", "To'xtatish", "Stop"), new Runnable() {
                    @Override
                    public void run() {
                        emergency(true);
                    }
                }), UI.weight(1));
                row.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
                row.addView(UI.button(c, L.t("Возобновить", "Davom ettirish", "Resume"), false, new Runnable() {
                    @Override
                    public void run() {
                        emergency(false);
                    }
                }), UI.weight(1));
                es.addView(row);
                body.addView(es);
            }
            body.addView(UI.section(c, L.t("Сессии приложения", "Ilova sessiyalari", "App sessions")));
            LinearLayout sc = UI.card(c);
            JSONArray items = sessions.optJSONArray("items");
            for (int i = 0; items != null && i < items.length(); i++) {
                final JSONObject s = items.optJSONObject(i);
                sc.addView(UI.listRow(c, "phone", Theme.accent, s.optString("device_name", s.optString("device_id")),
                        "user " + s.optLong("user_id") + " · " + s.optString("last_ip", "") + " · " + Fmt.dateTime(s.optLong("last_used_at")),
                        L.t("отозвать", "bekor", "revoke"), new Runnable() {
                            @Override
                            public void run() {
                                UI.confirm(c, L.t("Отозвать сессию?", "Sessiya bekor qilinsinmi?", "Revoke session?"), s.optString("device_name", ""),
                                        L.t("Отозвать", "Bekor qilish", "Revoke"), new Runnable() {
                                            @Override
                                            public void run() {
                                                api.delete("/security/sessions/" + s.optInt("id"), new Cb(false) {
                                                    @Override
                                                    public void ok(JSONObject r) {
                                                        load();
                                                    }
                                                });
                                            }
                                        });
                            }
                        }));
            }
            body.addView(sc);
            body.addView(UI.button(c, L.t("Выйти на всех других устройствах", "Boshqa barcha qurilmalardan chiqish", "Sign out all other devices"), false, new Runnable() {
                @Override
                public void run() {
                    api.post("/security/revoke-all", null, new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast(L.f("Отозвано: %d", "Bekor qilindi: %d", "Revoked: %d", r.optInt("revoked")));
                            load();
                        }
                    });
                }
            }));
            body.addView(UI.section(c, L.t("Журнал входов", "Kirishlar jurnali", "Login log")));
            LinearLayout lc = UI.card(c);
            JSONArray li = logins.optJSONArray("items");
            if (li == null || li.length() == 0) lc.addView(UI.caption(c, "—"));
            for (int i = 0; li != null && i < Math.min(30, li.length()); i++) {
                JSONObject e = li.optJSONObject(i);
                boolean ok = e.optInt("success") == 1;
                lc.addView(UI.listRow(c, ok ? "check" : "close", ok ? Theme.SUCCESS : Theme.DANGER, (ok ? "✓ " : "✕ ") + e.optString("reason"),
                        e.optString("ip", "") + " · " + e.optString("device_name", ""), Fmt.dateTime(e.optLong("created_at")), null));
            }
            body.addView(lc);
            body.addView(UI.button(c, L.t("Журнал действий (аудит)", "Amallar jurnali (audit)", "Audit log"), false, new Runnable() {
                @Override
                public void run() {
                    push(new AuditList("/security/audit", L.t("Аудит", "Audit", "Audit")));
                }
            }));
            if (act.isAdmin()) {
                body.addView(UI.space(c, 10));
                final LinearLayout sus = UI.card(c);
                sus.addView(UI.h3(c, L.t("Подозрительная активность", "Shubhali faollik", "Suspicious activity")));
                body.addView(sus);
                api.get("/security/suspicious", new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        JSONArray ips = r.optJSONArray("failed_by_ip");
                        sus.addView(UI.keyValue(c, L.t("Блокировка входа", "Kirish bloki", "Pairing lockout"), r.optBoolean("lockout_active") ? "⚠️ ON" : "—"));
                        sus.addView(UI.keyValue(c, L.t("Заблокировано лимитером", "Limiter blokladi", "Rate-limited requests"), String.valueOf(r.optInt("rate_limiter_blocked"))));
                        JSONObject lg = r.optJSONObject("loop_guard");
                        if (lg != null) sus.addView(UI.keyValue(c, L.t("Остановленные циклы", "To'xtatilgan sikllar", "Stopped reply loops"), String.valueOf(lg.optInt("tripped_chats"))));
                        for (int i = 0; ips != null && i < ips.length(); i++)
                            sus.addView(UI.keyValue(c, ips.optJSONObject(i).optString("ip"), ips.optJSONObject(i).optInt("failures") + " ✕"));
                    }
                });
            }
        }

        private void emergency(final boolean enable) {
            final String word = enable ? "STOP" : "RESUME";
            UI.typedConfirm(c, enable ? "Emergency Stop" : "Resume", L.t("Подтвердите действие вводом слова.", "So'zni kiritib tasdiqlang.", "Confirm by typing the word."), word, new UI.TextCallback() {
                @Override
                public void on(String v) {
                    JSONObject b = put(put(new JSONObject(), "enabled", enable), "confirm", v);
                    api.post("/security/emergency-stop", b, new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast(r.optBoolean("emergency_stop") ? "🛑 STOP" : "▶️ RESUMED");
                        }
                    });
                }
            });
        }
    }

    // =====================================================================================================
    public static final class SystemControl extends Screen {
        @Override
        public String title() { return L.t("Система", "Tizim", "System"); }

        @Override
        public void load() {
            loading();
            api.get("/system/checks?remote=true", new Cb() {
                @Override
                public void ok(final JSONObject checks) {
                    api.get("/system/status", new Cb() {
                        @Override
                        public void ok(JSONObject status) {
                            render(checks, status);
                        }
                    });
                }
            });
        }

        private void render(JSONObject checks, final JSONObject status) {
            body.removeAllViews();
            boolean ok = checks.optBoolean("ok");
            LinearLayout hero = UI.tinted(c, ok ? Theme.SUCCESS : Theme.WARNING);
            hero.addView(UI.h3(c, ok ? L.t("Все системы в норме", "Barcha tizimlar me'yorida", "All systems operational")
                    : L.t("Есть проблемы", "Muammolar bor", "Issues detected")));
            body.addView(hero);
            body.addView(UI.section(c, "Health Check"));
            LinearLayout hc = UI.card(c);
            JSONObject ch = checks.optJSONObject("checks");
            JSONArray names = ch == null ? null : ch.names();
            for (int i = 0; names != null && i < names.length(); i++) {
                String k = names.optString(i);
                JSONObject v = ch.optJSONObject(k);
                boolean good = v != null && v.optBoolean("ok", true);
                String detail = v == null ? "" : v.toString();
                if (detail.length() > 140) detail = detail.substring(0, 140) + "…";
                hc.addView(UI.listRow(c, good ? "check" : "warning", good ? Theme.SUCCESS : Theme.DANGER, k, detail, null, null));
            }
            body.addView(hc);
            JSONObject runtime = status.optJSONObject("runtime");
            body.addView(UI.section(c, L.t("Управление", "Boshqaruv", "Control")));
            LinearLayout ctl = UI.card(c);
            if (runtime != null) {
                ctl.addView(UI.toggleRow(c, L.t("Режим обслуживания", "Texnik xizmat rejimi", "Maintenance mode"), L.t("Обычные пользователи получат сообщение о работах",
                        "Oddiy foydalanuvchilar ishlar haqida xabar oladi", "Regular users get a maintenance notice"), runtime.optBoolean("maintenance"), new UI.BoolCallback() {
                    @Override
                    public void on(boolean v) {
                        api.post("/system/maintenance", put(new JSONObject(), "enabled", v), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast("🛠 " + (r.optBoolean("maintenance") ? "ON" : "OFF"));
                            }
                        });
                    }
                }));
                ctl.addView(UI.caption(c, L.t("Приостановленные модули:", "To'xtatilgan modullar:", "Paused modules:")));
                final JSONArray modules = runtime.optJSONArray("modules");
                final JSONArray paused = runtime.optJSONArray("paused_modules");
                final List<String> pausedList = new ArrayList<String>();
                for (int i = 0; paused != null && i < paused.length(); i++) pausedList.add(paused.optString(i));
                LinearLayout mods = UI.col(c);
                for (int i = 0; modules != null && i < modules.length(); i++) {
                    final String m = modules.optString(i);
                    mods.addView(UI.toggleRow(c, m, null, !pausedList.contains(m), new UI.BoolCallback() {
                        @Override
                        public void on(boolean on) {
                            if (on) pausedList.remove(m);
                            else if (!pausedList.contains(m)) pausedList.add(m);
                            api.put("/system/modules", put(new JSONObject(), "paused", new JSONArray(pausedList)), new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    toast("✓");
                                }
                            });
                        }
                    }));
                }
                ctl.addView(mods);
            }
            body.addView(ctl);
            LinearLayout ops = UI.col(c);
            String[][] actions = {
                    {L.t("Журнал логов", "Loglar", "Logs"), "logs"},
                    {L.t("Очистить временные файлы", "Vaqtinchalik fayllarni tozalash", "Clean temp files"), "cleanup"},
                    {L.t("Создать резервную копию", "Zaxira nusxa yaratish", "Create backup"), "backup"},
                    {L.t("Проверка целостности БД", "Baza yaxlitligini tekshirish", "Database integrity"), "integrity"},
                    {L.t("Перезапуск очереди медиа", "Media navbatini qayta ishga tushirish", "Restart media queue"), "restart:media_queue"},
                    {L.t("Перезапуск планировщика", "Rejalashtiruvchini qayta ishga tushirish", "Restart scheduler"), "restart:scheduler"},
                    {L.t("Управление процессом в Termux", "Termux jarayonini boshqarish", "Process control in Termux"), "termux"},
            };
            for (final String[] a : actions) {
                ops.addView(UI.mt(UI.button(c, a[0], false, new Runnable() {
                    @Override
                    public void run() {
                        action(a[1]);
                    }
                }), 8));
            }
            body.addView(ops);
            body.addView(UI.section(c, L.t("Конфигурация (без секретов)", "Konfiguratsiya (sirsiz)", "Configuration (no secrets)")));
            LinearLayout cfg = UI.card(c);
            JSONObject conf = status.optJSONObject("config");
            cfg.addView(UI.mono(c, conf == null ? "—" : conf.toString().replace(",\"", ",\n\"")));
            body.addView(cfg);
        }

        private void action(String a) {
            if ("logs".equals(a)) {
                push(new Logs());
            } else if ("cleanup".equals(a)) {
                api.post("/system/cleanup", null, new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        toast(L.f("Удалено: %d · освобождено %s", "O'chirildi: %d · bo'shatildi %s", "Removed: %d · freed %s", r.optInt("tmp_removed"), Fmt.bytes(r.optLong("freed_bytes"))));
                    }
                });
            } else if ("backup".equals(a)) {
                UI.confirm(c, L.t("Создать резервную копию?", "Zaxira nusxa yaratilsinmi?", "Create backup?"), L.t("Копия базы сохранится в backend/data/backups.",
                        "Nusxa backend/data/backups da saqlanadi.", "A copy is stored in backend/data/backups."), "OK", new Runnable() {
                    @Override
                    public void run() {
                        api.post("/system/backup", put(new JSONObject(), "confirm", true), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast("🗄 " + r.optString("name") + " · " + Fmt.bytes(r.optLong("size")));
                            }
                        });
                    }
                });
            } else if ("integrity".equals(a)) {
                api.get("/system/db-integrity", new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        UI.info(c, r.optBoolean("ok") ? "✅ OK" : "⚠️", "schema v" + r.optInt("schema_version") + "\n" + Fmt.bytes(r.optLong("bytes")) + "\n" + r.optString("integrity"));
                    }
                });
            } else if (a.startsWith("restart:")) {
                api.post("/system/" + a.replace(":", "/"), null, new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        toast("♻️ " + r.optString("component"));
                    }
                });
            } else if ("termux".equals(a)) {
                UI.info(c, "Termux", L.t("API не может безопасно перезапустить собственный Python-процесс. Используйте скрипты в Termux:\n\n",
                        "API o'z Python jarayonini xavfsiz qayta ishga tushira olmaydi. Termux'dagi skriptlardan foydalaning:\n\n",
                        "The API cannot safely restart its own Python process. Use the Termux scripts:\n\n")
                        + "cd ~/Chat_helper\n./scripts/status.sh\n./scripts/restart.sh\n./scripts/stop.sh\n./scripts/start.sh\n\ntermux-wake-lock");
            }
        }
    }

    public static final class Logs extends Screen {
        private int level = 1;
        private final String[] levels = {"DEBUG", "INFO", "WARNING", "ERROR"};

        @Override
        public String title() { return L.t("Логи", "Loglar", "Logs"); }

        @Override
        public void load() {
            loading();
            api.get("/system/logs?limit=300&level=" + levels[level], new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    body.addView(UI.chips(c, levels, level, new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            level = v;
                            load();
                        }
                    }));
                    LinearLayout card = UI.card(c);
                    UI.mt(card, 10);
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) card.addView(UI.caption(c, L.t("Записей нет", "Yozuvlar yo'q", "No entries")));
                    StringBuilder sb = new StringBuilder();
                    for (int i = 0; items != null && i < items.length(); i++) {
                        JSONObject e = items.optJSONObject(i);
                        sb.append(Fmt.time(e.optLong("ts"))).append(' ').append(e.optString("level").charAt(0)).append(' ')
                                .append(e.optString("logger")).append(": ").append(e.optString("message")).append('\n');
                    }
                    if (sb.length() > 0) card.addView(UI.mono(c, sb.toString()));
                    body.addView(card);
                    body.addView(UI.button(c, L.t("Экспорт лог-файла", "Log faylni eksport", "Export log file"), false, new Runnable() {
                        @Override
                        public void run() {
                            api.download("/system/logs/export", new Api.BytesCallback() {
                                @Override
                                public void ok(byte[] data, String ct) {
                                    String w = Files.save(act, "chat_helper_" + now() + ".log", "text/plain", data);
                                    toast(w == null ? "⚠️" : w);
                                }

                                @Override
                                public void fail(ApiError err) {
                                    toast(err.human());
                                }
                            });
                        }
                    }));
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Flags extends Screen {
        @Override
        public String title() { return "Feature Flags"; }

        @Override
        public void load() {
            loading();
            api.get("/flags", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    if (act.isSuper()) body.addView(UI.button(c, L.t("Новый флаг", "Yangi bayroq", "New flag"), true, new Runnable() {
                        @Override
                        public void run() {
                            UI.prompt(c, L.t("Ключ флага (латиница)", "Bayroq kaliti", "Flag key"), "beta_inbox", "", false, new UI.TextCallback() {
                                @Override
                                public void on(String v) {
                                    save(v.trim(), false, "");
                                }
                            });
                        }
                    }));
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "flag", L.t("Флагов нет", "Bayroqlar yo'q", "No flags"),
                                L.t("Флаги включают экспериментальные функции для выбранных пользователей.", "Bayroqlar tajribaviy funksiyalarni yoqadi.",
                                        "Flags enable experimental features for selected users.")));
                        return;
                    }
                    LinearLayout card = UI.card(c);
                    UI.mt(card, 12);
                    for (int i = 0; i < items.length(); i++) {
                        final JSONObject f = items.optJSONObject(i);
                        card.addView(UI.toggleRow(c, f.optString("key"), f.optString("description", ""), f.optBoolean("enabled", f.optBoolean("active_for_me")), new UI.BoolCallback() {
                            @Override
                            public void on(boolean v) {
                                save(f.optString("key"), v, f.optString("description", ""));
                            }
                        }));
                    }
                    body.addView(card);
                }
            });
        }

        private void save(String key, boolean enabled, String desc) {
            JSONObject b = put(put(new JSONObject(), "enabled", enabled), "description", desc);
            api.put("/flags/" + key, b, new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    load();
                }
            });
        }
    }
}

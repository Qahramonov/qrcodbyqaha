package com.chathelper.control.screens;

import android.graphics.BitmapFactory;
import android.media.MediaPlayer;
import android.net.Uri;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.VideoView;

import com.chathelper.control.core.Api;
import com.chathelper.control.core.ApiError;
import com.chathelper.control.core.Fmt;
import com.chathelper.control.core.L;
import com.chathelper.control.ui.Theme;
import com.chathelper.control.ui.UI;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;

/** Automation hub (modes, AFK, rules, scenarios, templates), rule editor, commands, media, games. */
public final class AutomationScreens {
    private AutomationScreens() {}

    static final String[] MODES = {"manual", "auto", "ai", "afk", "silent", "business", "hybrid"};

    static String modeTitle(String m) {
        if ("manual".equals(m)) return L.t("✋ Ручной", "✋ Qo'lda", "✋ Manual");
        if ("auto".equals(m)) return L.t("⚡ Авто", "⚡ Avto", "⚡ Auto");
        if ("ai".equals(m)) return "🧠 AI";
        if ("afk".equals(m)) return "💤 AFK";
        if ("silent".equals(m)) return L.t("🔕 Тихий", "🔕 Tinch", "🔕 Silent");
        if ("business".equals(m)) return L.t("💼 Бизнес", "💼 Biznes", "💼 Business");
        return L.t("🔀 Гибрид", "🔀 Gibrid", "🔀 Hybrid");
    }

    // =====================================================================================================
    public static final class Hub extends Screen {
        private int tab;

        @Override
        public String title() { return L.t("Автоматизация", "Avtomatlashtirish", "Automation"); }

        @Override
        public void load() {
            loading();
            api.get("/settings", new Cb() {
                @Override
                public void ok(final JSONObject settings) {
                    if (tab == 0) {
                        api.get("/afk", new Cb() {
                            @Override
                            public void ok(JSONObject afk) {
                                renderMode(settings.optJSONObject("values"), afk);
                            }
                        });
                    } else if (tab == 1) {
                        api.get("/autoreply/rules", new Cb() {
                            @Override
                            public void ok(JSONObject rules) {
                                renderRules(rules);
                            }
                        });
                    } else {
                        api.get("/automation/rules", new Cb() {
                            @Override
                            public void ok(JSONObject rules) {
                                renderScenarios(rules);
                            }
                        });
                    }
                }
            });
        }

        private void header() {
            body.removeAllViews();
            body.addView(UI.chips(c, new String[]{L.t("Режим и AFK", "Rejim va AFK", "Mode & AFK"), L.t("Автоответы", "Avtojavoblar", "Auto replies"),
                    L.t("Сценарии", "Ssenariylar", "Scenarios")}, tab, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    tab = v;
                    load();
                }
            }));
            body.addView(UI.space(c, 8));
        }

        private void setSetting(String key, Object value) {
            JSONObject vals = put(new JSONObject(), key, value);
            api.patch("/settings", put(new JSONObject(), "values", vals), new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    toast(L.t("Сохранено", "Saqlandi", "Saved"));
                }
            });
        }

        private void renderMode(final JSONObject s, JSONObject afk) {
            header();
            body.addView(UI.section(c, L.t("Режим автоответчика", "Avtojavob rejimi", "Auto-reply mode")));
            List<View> cards = new ArrayList<View>();
            for (final String m : MODES) {
                boolean on = m.equals(s.optString("mode"));
                LinearLayout card = on ? UI.tinted(c, Theme.accent) : UI.card(c);
                card.setPadding(Theme.dp(12), Theme.dp(14), Theme.dp(12), Theme.dp(14));
                TextView t = UI.body(c, modeTitle(m));
                t.setTextColor(on ? Theme.text : Theme.text2);
                card.addView(t);
                UI.pressable(card);
                UI.onClick(card, new Runnable() {
                    @Override
                    public void run() {
                        api.put("/autoreply/mode", obj("mode", m), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                load();
                            }
                        });
                    }
                });
                cards.add(card);
            }
            body.addView(UI.grid(c, cards, 2));
            TextView expl = UI.caption(c, L.t("Ручной — только команды. Авто — правила. AI — ответы ассистента. Бизнес — рабочие часы. Гибрид — правила, затем AI. Тихий — без автоответов.",
                    "Qo'lda — faqat buyruqlar. Avto — qoidalar. AI — yordamchi javoblari. Biznes — ish vaqti. Gibrid — qoidalar, so'ng AI. Tinch — avtojavobsiz.",
                    "Manual — commands only. Auto — rules. AI — assistant replies. Business — working hours. Hybrid — rules then AI. Silent — no automation."));
            body.addView(expl);
            body.addView(UI.section(c, "AFK"));
            LinearLayout ac = UI.card(c);
            final JSONObject sess = afk.optJSONObject("active");
            if (sess != null) {
                ac.addView(UI.h3(c, "💤 " + L.t("Включён", "Yoqilgan", "Active") + " · " + Fmt.duration(HomeScreens.now() - sess.optLong("started_at"))));
                if (!sess.isNull("reason")) ac.addView(UI.body2(c, sess.optString("reason")));
                ac.addView(UI.caption(c, L.f("Сообщений: %d · ответов: %d", "Xabarlar: %d · javoblar: %d", "Messages: %d · replies: %d",
                        sess.optInt("messages_received"), sess.optInt("replies_sent"))));
                ac.addView(UI.mt(UI.button(c, L.t("Выключить AFK", "AFK'ni o'chirish", "Disable AFK"), true, new Runnable() {
                    @Override
                    public void run() {
                        api.post("/afk/disable", null, new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                load();
                            }
                        });
                    }
                }), 10));
            } else {
                ac.addView(UI.body2(c, L.t("AFK выключен", "AFK o'chirilgan", "AFK is off")));
                LinearLayout row = UI.row(c);
                UI.mt(row, 10);
                final int[] mins = {0, 30, 60, 180};
                final String[] labels = {L.t("Без таймера", "Taymersiz", "No timer"), "30m", "1h", "3h"};
                for (int i = 0; i < mins.length; i++) {
                    final int mm = mins[i];
                    row.addView(UI.chip(c, labels[i], false, new Runnable() {
                        @Override
                        public void run() {
                            UI.prompt(c, L.t("Причина", "Sabab", "Reason"), L.t("Занят делами", "Bandman", "Busy"), "", false, new UI.TextCallback() {
                                @Override
                                public void on(String v) {
                                    JSONObject b = new JSONObject();
                                    if (!v.trim().isEmpty()) put(b, "reason", v.trim());
                                    if (mm > 0) put(b, "minutes", mm);
                                    api.post("/afk/enable", b, new Cb(false) {
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
                ac.addView(row);
            }
            body.addView(ac);
            LinearLayout afkSet = UI.card(c);
            final String[] themes = {"classic", "minimal", "fancy", "emoji"};
            int ti = 0;
            for (int i = 0; i < themes.length; i++) if (themes[i].equals(s.optString("msg_theme"))) ti = i;
            afkSet.addView(UI.caption(c, L.t("Дизайн AFK-сообщения", "AFK xabari dizayni", "AFK message design")));
            afkSet.addView(UI.mt(UI.chips(c, themes, ti, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    setSetting("msg_theme", themes[v]);
                    preview(themes[v]);
                }
            }), 6));
            afkSet.addView(UI.toggleRow(c, L.t("Выключать при моём сообщении", "Xabar yozsam o'chirish", "Turn off when I write"), null, s.optBoolean("afk_auto_off"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    setSetting("afk_auto_off", v);
                }
            }));
            afkSet.addView(UI.toggleRow(c, L.t("AI-ответы в AFK", "AFK'da AI javoblari", "AI replies while AFK"), null, s.optBoolean("afk_ai"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    setSetting("afk_ai", v);
                }
            }));
            afkSet.addView(UI.toggleRow(c, L.t("Сводка после возвращения", "Qaytgandan keyin xulosa", "Summary when back"), null, s.optBoolean("afk_notify_summary"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    setSetting("afk_notify_summary", v);
                }
            }));
            afkSet.addView(UI.slider(c, L.t("Повтор не чаще (мин)", "Takrorlash (daq)", "Repeat at most every (min)"), 1, 240, s.optInt("afk_cooldown_min", 30), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    setSetting("afk_cooldown_min", v);
                }
            }));
            for (final String part : new String[]{"morning", "day", "evening", "night"}) {
                final String key = "afk_text_" + part;
                afkSet.addView(UI.listRow(c, "moon", Theme.accent, L.t("Свой текст: ", "O'z matni: ", "Custom text: ") + part,
                        s.optString(key).isEmpty() ? L.t("по умолчанию", "standart", "default") : s.optString(key), null, new Runnable() {
                            @Override
                            public void run() {
                                UI.prompt(c, part + " — {name} {reason} {duration} {until}", "", s.optString(key), true, new UI.TextCallback() {
                                    @Override
                                    public void on(String v) {
                                        setSetting(key, v);
                                        load();
                                    }
                                });
                            }
                        }));
            }
            body.addView(afkSet);
            body.addView(UI.section(c, L.t("Бизнес-часы и приветствие", "Ish vaqti va salomlashish", "Business hours & welcome")));
            LinearLayout bh = UI.card(c);
            bh.addView(UI.listRow(c, "clock", Theme.INFO, L.t("Рабочие часы", "Ish vaqti", "Working hours"), s.optString("work_start") + " — " + s.optString("work_end"), null, new Runnable() {
                @Override
                public void run() {
                    UI.prompt(c, L.t("Часы работы", "Ish vaqti", "Working hours"), "09:00-18:00", s.optString("work_start") + "-" + s.optString("work_end"), false, new UI.TextCallback() {
                        @Override
                        public void on(String v) {
                            String[] p = v.split("-");
                            if (p.length != 2) return;
                            JSONObject vals = put(put(new JSONObject(), "work_start", p[0].trim()), "work_end", p[1].trim());
                            api.patch("/settings", put(new JSONObject(), "values", vals), new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    load();
                                }
                            });
                        }
                    });
                }
            }));
            bh.addView(UI.listRow(c, "chat", Theme.INFO, L.t("Текст вне рабочего времени", "Ish vaqtidan tashqari matn", "Off-hours text"), s.optString("offhours_text"), null, new Runnable() {
                @Override
                public void run() {
                    UI.prompt(c, L.t("Текст вне рабочего времени", "Ish vaqtidan tashqari matn", "Off-hours text"), "", s.optString("offhours_text"), true, new UI.TextCallback() {
                        @Override
                        public void on(String v) {
                            setSetting("offhours_text", v);
                            load();
                        }
                    });
                }
            }));
            bh.addView(UI.toggleRow(c, L.t("Приветствие новых собеседников", "Yangi suhbatdoshlarni salomlash", "Greet new contacts"), s.optString("welcome_text"), s.optBoolean("welcome_enabled"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    if (v && s.optString("welcome_text").isEmpty()) {
                        UI.prompt(c, L.t("Текст приветствия", "Salomlashish matni", "Welcome text"), "{name}, {owner}, {time}", "", true, new UI.TextCallback() {
                            @Override
                            public void on(String t) {
                                JSONObject vals = put(put(new JSONObject(), "welcome_text", t), "welcome_enabled", true);
                                api.patch("/settings", put(new JSONObject(), "values", vals), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        load();
                                    }
                                });
                            }
                        });
                    } else {
                        setSetting("welcome_enabled", v);
                    }
                }
            }));
            bh.addView(UI.toggleRow(c, L.t("Пауза всей автоматики", "Barcha avtomatikani to'xtatish", "Pause all automation"), null, s.optBoolean("automation_paused"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    setSetting("automation_paused", v);
                }
            }));
            body.addView(bh);
        }

        private void preview(String theme) {
            api.get("/afk/preview?theme=" + theme, new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    UI.info(c, L.t("Так увидят собеседники", "Suhbatdoshlar shunday ko'radi", "What contacts will see"),
                            android.text.Html.fromHtml(r.optString("html")).toString());
                }
            });
        }

        private void renderRules(JSONObject res) {
            header();
            body.addView(UI.button(c, L.t("Новое правило", "Yangi qoida", "New rule"), true, new Runnable() {
                @Override
                public void run() {
                    UI.prompt(c, L.t("Ключевые слова через запятую", "Kalit so'zlar vergul bilan", "Keywords, comma separated"), "цена, прайс", "", false, new UI.TextCallback() {
                        @Override
                        public void on(final String kw) {
                            if (kw.trim().isEmpty()) return;
                            UI.prompt(c, L.t("Ответ", "Javob", "Reply"), "{name}, {owner}, {time}", "", true, new UI.TextCallback() {
                                @Override
                                public void on(String resp) {
                                    JSONObject b = put(put(put(new JSONObject(), "trigger_type", "keyword"), "pattern", kw.trim()), "response", resp);
                                    api.post("/autoreply/rules", b, new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            load();
                                        }
                                    });
                                }
                            });
                        }
                    });
                }
            }));
            JSONArray items = res.optJSONArray("items");
            if (items == null || items.length() == 0) {
                body.addView(UI.empty(c, "chat", L.t("Правил пока нет", "Qoidalar yo'q", "No rules yet"),
                        L.t("Правила работают в режимах Авто, Бизнес и Гибрид.", "Qoidalar Avto, Biznes va Gibrid rejimlarida ishlaydi.", "Rules work in Auto, Business and Hybrid modes.")));
                return;
            }
            LinearLayout card = UI.card(c);
            UI.mt(card, 12);
            for (int i = 0; i < items.length(); i++) {
                final JSONObject r = items.optJSONObject(i);
                LinearLayout row = UI.toggleRow(c, "#" + r.optInt("id") + " · " + r.optString("pattern", r.optString("trigger_type")),
                        "→ " + r.optString("response") + " · " + r.optInt("hits") + "×", r.optInt("enabled") == 1, new UI.BoolCallback() {
                            @Override
                            public void on(boolean v) {
                                api.patch("/autoreply/rules/" + r.optInt("id"), put(new JSONObject(), "enabled", v), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject x) {}
                                });
                            }
                        });
                row.setOnLongClickListener(new View.OnLongClickListener() {
                    @Override
                    public boolean onLongClick(View v) {
                        UI.confirm(c, L.t("Удалить правило?", "Qoida o'chirilsinmi?", "Delete rule?"), r.optString("pattern"), L.t("Удалить", "O'chirish", "Delete"), new Runnable() {
                            @Override
                            public void run() {
                                api.delete("/autoreply/rules/" + r.optInt("id"), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject x) {
                                        load();
                                    }
                                });
                            }
                        });
                        return true;
                    }
                });
                card.addView(row);
            }
            body.addView(card);
            body.addView(UI.caption(c, L.t("Долгое нажатие — удалить правило.", "Uzoq bosish — qoidani o'chirish.", "Long-press to delete a rule.")));
        }

        private void renderScenarios(final JSONObject res) {
            header();
            LinearLayout row = UI.row(c);
            row.addView(UI.button(c, L.t("Создать сценарий", "Ssenariy yaratish", "Create scenario"), true, new Runnable() {
                @Override
                public void run() {
                    push(new RuleEditor(null));
                }
            }), UI.weight(1));
            row.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
            row.addView(UI.button(c, L.t("Шаблоны", "Shablonlar", "Templates"), false, new Runnable() {
                @Override
                public void run() {
                    push(new Templates());
                }
            }), UI.weight(1));
            body.addView(row);
            JSONArray items = res.optJSONArray("items");
            if (items == null || items.length() == 0) {
                body.addView(UI.empty(c, "bolt", L.t("Сценариев нет", "Ssenariylar yo'q", "No scenarios"),
                        L.t("ЕСЛИ происходит событие — ТО выполнить действия. Начните с готового шаблона.", "AGAR hodisa bo'lsa — UNDA amallarni bajar. Tayyor shablondan boshlang.",
                                "IF an event happens THEN run actions. Start from a template.")));
                return;
            }
            LinearLayout card = UI.card(c);
            UI.mt(card, 12);
            for (int i = 0; i < items.length(); i++) {
                final JSONObject r = items.optJSONObject(i);
                JSONObject trig = r.optJSONObject("trigger");
                String sub = L.t("ЕСЛИ ", "AGAR ", "IF ") + (trig == null ? "?" : trig.optString("type")) + " → " + r.optJSONArray("actions").length()
                        + L.t(" действ. · запусков ", " amal · ishga tushish ", " actions · runs ") + r.optInt("run_count");
                card.addView(UI.listRow(c, "bolt", r.optBoolean("enabled") ? Theme.accent : Theme.text3, r.optString("name"), sub, null, new Runnable() {
                    @Override
                    public void run() {
                        push(new RuleEditor(r));
                    }
                }));
            }
            body.addView(card);
            body.addView(UI.button(c, L.t("Журнал выполнений", "Bajarilish jurnali", "Execution log"), false, new Runnable() {
                @Override
                public void run() {
                    push(new Executions());
                }
            }));
        }
    }

    // =====================================================================================================
    /** Visual IF/THEN rule editor for the no-code automation builder. */
    public static final class RuleEditor extends Screen {
        private final JSONObject original;
        private JSONObject rule;
        static final String[] TRIGGERS = {"message", "keyword", "time", "media", "contact", "new_chat", "ai_class", "no_reply"};
        static final String[] ACTIONS = {"reply", "reply_template", "ai_reply", "set_mode", "afk_on", "afk_off", "notify", "tag", "timer", "remind", "handoff",
                "mark_read", "set_priority"};

        RuleEditor(JSONObject r) {
            original = r;
            try {
                rule = r == null ? new JSONObject("{\"name\":\"\",\"enabled\":true,\"trigger\":{\"type\":\"keyword\",\"keywords\":[]},\"conditions\":[],\"actions\":[],\"cooldown_sec\":60}")
                        : new JSONObject(r.toString());
            } catch (Exception e) {
                rule = new JSONObject();
            }
        }

        @Override
        public String title() { return original == null ? L.t("Новый сценарий", "Yangi ssenariy", "New scenario") : rule.optString("name"); }

        @Override
        public boolean refreshable() { return false; }

        @Override
        public void load() { render(); }

        private String trigLabel(String t) {
            if ("message".equals(t)) return L.t("Любое сообщение", "Har qanday xabar", "Any message");
            if ("keyword".equals(t)) return L.t("Ключевое слово", "Kalit so'z", "Keyword");
            if ("time".equals(t)) return L.t("Время", "Vaqt", "Time");
            if ("media".equals(t)) return L.t("Тип медиа", "Media turi", "Media type");
            if ("contact".equals(t)) return L.t("Контакт", "Kontakt", "Contact");
            if ("new_chat".equals(t)) return L.t("Новый чат", "Yangi chat", "New chat");
            if ("ai_class".equals(t)) return L.t("AI-классификация", "AI tasnifi", "AI classification");
            return L.t("Нет ответа N мин", "N daq javob yo'q", "No reply N min");
        }

        private void render() {
            body.removeAllViews();
            final EditText name = UI.input(c, L.t("Название сценария", "Ssenariy nomi", "Scenario name"), rule.optString("name"), false);
            body.addView(name);
            body.addView(UI.toggleRow(c, L.t("Включён", "Yoqilgan", "Enabled"), null, rule.optBoolean("enabled", true), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    put(rule, "enabled", v);
                }
            }));
            final JSONObject trig = rule.optJSONObject("trigger") == null ? new JSONObject() : rule.optJSONObject("trigger");
            put(rule, "trigger", trig);
            body.addView(UI.section(c, L.t("ЕСЛИ", "AGAR", "IF")));
            LinearLayout tc = UI.card(c);
            int ti = 0;
            String[] tl = new String[TRIGGERS.length];
            for (int i = 0; i < TRIGGERS.length; i++) {
                tl[i] = trigLabel(TRIGGERS[i]);
                if (TRIGGERS[i].equals(trig.optString("type"))) ti = i;
            }
            tc.addView(UI.chips(c, tl, ti, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    put(rule, "name", name.getText().toString());
                    JSONObject t = put(new JSONObject(), "type", TRIGGERS[v]);
                    put(rule, "trigger", t);
                    render();
                }
            }));
            final String tt = trig.optString("type");
            if ("keyword".equals(tt)) {
                final EditText kw = UI.input(c, L.t("Слова через запятую", "So'zlar vergul bilan", "Words, comma separated"), join(trig.optJSONArray("keywords")), false);
                UI.mt(kw, 10);
                kw.addTextChangedListener(new SimpleWatcher() {
                    @Override
                    public void changed(String s) {
                        JSONArray a = new JSONArray();
                        for (String w : s.split(",")) if (!w.trim().isEmpty()) a.put(w.trim());
                        put(trig, "keywords", a);
                    }
                });
                tc.addView(kw);
            } else if ("time".equals(tt)) {
                final EditText at = UI.input(c, "HH:MM", trig.optString("at", "23:00"), false);
                UI.mt(at, 10);
                put(trig, "at", at.getText().toString());
                at.addTextChangedListener(new SimpleWatcher() {
                    @Override
                    public void changed(String s) {
                        put(trig, "at", s.trim());
                    }
                });
                tc.addView(at);
            } else if ("media".equals(tt)) {
                final String[] types = {"voice", "video_note", "photo", "video", "audio", "document", "sticker"};
                int mi = 0;
                JSONArray cur = trig.optJSONArray("types");
                for (int i = 0; cur != null && i < types.length; i++) if (types[i].equals(cur.optString(0))) mi = i;
                put(trig, "types", new JSONArray().put(types[mi]));
                tc.addView(UI.mt(UI.chips(c, types, mi, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        put(trig, "types", new JSONArray().put(types[v]));
                        render();
                    }
                }), 10));
            } else if ("contact".equals(tt)) {
                final EditText ids = UI.input(c, L.t("ID чатов через запятую", "Chat ID'lari vergul bilan", "Chat IDs, comma separated"), join(trig.optJSONArray("chat_ids")), false);
                UI.mt(ids, 10);
                ids.addTextChangedListener(new SimpleWatcher() {
                    @Override
                    public void changed(String s) {
                        JSONArray a = new JSONArray();
                        for (String w : s.split(",")) {
                            try {
                                a.put(Long.parseLong(w.trim()));
                            } catch (Exception ignored) {
                                // skip
                            }
                        }
                        put(trig, "chat_ids", a);
                    }
                });
                tc.addView(ids);
            } else if ("ai_class".equals(tt)) {
                final String[] labels = {"urgent", "question", "order", "complaint", "greeting", "spam", "other"};
                int li = 0;
                for (int i = 0; i < labels.length; i++) if (labels[i].equals(trig.optString("label"))) li = i;
                put(trig, "label", labels[li]);
                tc.addView(UI.mt(UI.chips(c, labels, li, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        put(trig, "label", labels[v]);
                        render();
                    }
                }), 10));
            } else if ("no_reply".equals(tt)) {
                if (!trig.has("minutes")) put(trig, "minutes", 60);
                tc.addView(UI.slider(c, L.t("Минут без ответа", "Javobsiz daqiqalar", "Minutes without reply"), 5, 240, trig.optInt("minutes", 60), "", new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        put(trig, "minutes", v);
                    }
                }));
            }
            body.addView(tc);

            body.addView(UI.section(c, L.t("И УСЛОВИЯ", "VA SHARTLAR", "AND CONDITIONS")));
            LinearLayout cc = UI.card(c);
            final JSONArray conds = rule.optJSONArray("conditions") == null ? new JSONArray() : rule.optJSONArray("conditions");
            put(rule, "conditions", conds);
            for (int i = 0; i < conds.length(); i++) {
                final int idx = i;
                JSONObject cd = conds.optJSONObject(i);
                cc.addView(UI.listRow(c, "filter", Theme.INFO, cd.optString("type"), cd.toString(), "✕", new Runnable() {
                    @Override
                    public void run() {
                        conds.remove(idx);
                        render();
                    }
                }));
            }
            cc.addView(UI.smallButton(c, "+ " + L.t("условие", "shart", "condition"), new Runnable() {
                @Override
                public void run() {
                    UI.choose(c, L.t("Условие", "Shart", "Condition"), new String[]{L.t("Временное окно", "Vaqt oralig'i", "Time window"),
                            L.t("Дни недели (пн-пт)", "Ish kunlari (du-ju)", "Weekdays (Mon-Fri)"), L.t("Только при AFK", "Faqat AFK'da", "Only while AFK"),
                            L.t("Чат с тегом", "Tegli chat", "Chat has tag")}, new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            if (v == 0) {
                                UI.prompt(c, L.t("Окно", "Oraliq", "Window"), "22:00-08:00", "22:00-08:00", false, new UI.TextCallback() {
                                    @Override
                                    public void on(String w) {
                                        String[] p = w.split("-");
                                        if (p.length == 2) conds.put(put(put(obj("type", "time_window"), "start", p[0].trim()), "end", p[1].trim()));
                                        render();
                                    }
                                });
                            } else if (v == 1) {
                                conds.put(put(obj("type", "weekday"), "days", new JSONArray().put(1).put(2).put(3).put(4).put(5)));
                                render();
                            } else if (v == 2) {
                                conds.put(put(obj("type", "afk"), "active", true));
                                render();
                            } else {
                                UI.prompt(c, L.t("Тег", "Teg", "Tag"), "vip", "", false, new UI.TextCallback() {
                                    @Override
                                    public void on(String tag) {
                                        conds.put(put(obj("type", "chat_tag"), "tag", tag.trim()));
                                        render();
                                    }
                                });
                            }
                        }
                    });
                }
            }));
            body.addView(cc);

            body.addView(UI.section(c, L.t("ТО", "UNDA", "THEN")));
            LinearLayout ac = UI.card(c);
            final JSONArray acts = rule.optJSONArray("actions") == null ? new JSONArray() : rule.optJSONArray("actions");
            put(rule, "actions", acts);
            for (int i = 0; i < acts.length(); i++) {
                final int idx = i;
                JSONObject a = acts.optJSONObject(i);
                ac.addView(UI.listRow(c, "bolt", Theme.accent, (i + 1) + ". " + a.optString("type"), a.toString(), "✕", new Runnable() {
                    @Override
                    public void run() {
                        acts.remove(idx);
                        render();
                    }
                }));
            }
            ac.addView(UI.smallButton(c, "+ " + L.t("действие", "amal", "action"), new Runnable() {
                @Override
                public void run() {
                    UI.choose(c, L.t("Действие", "Amal", "Action"), ACTIONS, new UI.IntCallback() {
                        @Override
                        public void on(int v) {
                            addAction(ACTIONS[v], acts);
                        }
                    });
                }
            }));
            body.addView(ac);
            body.addView(UI.slider(c, L.t("Пауза между срабатываниями, с", "Ishga tushishlar orasidagi pauza, s", "Cooldown, s"), 0, 3600, rule.optInt("cooldown_sec", 60), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    put(rule, "cooldown_sec", v);
                }
            }));
            body.addView(UI.mt(UI.button(c, L.t("Тест без отправки", "Yubormasdan test", "Dry-run test"), false, new Runnable() {
                @Override
                public void run() {
                    put(rule, "name", name.getText().toString().isEmpty() ? "test" : name.getText().toString());
                    UI.prompt(c, L.t("Пример сообщения", "Namuna xabar", "Sample message"), "", "", false, new UI.TextCallback() {
                        @Override
                        public void on(String sample) {
                            JSONObject b = put(put(new JSONObject(), "rule", rule), "sample_text", sample);
                            api.post("/automation/test", b, new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {
                                    UI.info(c, r.optBoolean("would_fire") ? L.t("✅ Сработает", "✅ Ishlaydi", "✅ Would fire") : L.t("⏸ Не сработает", "⏸ Ishlamaydi", "⏸ Would not fire"),
                                            "trigger: " + r.optBoolean("trigger_matched") + "\nconditions: " + r.optBoolean("conditions_ok") + "\n" + r.optJSONArray("actions"));
                                }
                            });
                        }
                    });
                }
            }), 10));
            body.addView(UI.mt(UI.button(c, L.t("Сохранить", "Saqlash", "Save"), true, new Runnable() {
                @Override
                public void run() {
                    put(rule, "name", name.getText().toString().trim());
                    Api.Callback cb = new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast(L.t("Сценарий сохранён", "Ssenariy saqlandi", "Scenario saved"));
                            act.back();
                        }
                    };
                    if (original == null) api.post("/automation/rules", rule, cb);
                    else api.patch("/automation/rules/" + original.optInt("id"), rule, cb);
                }
            }), 10));
            if (original != null) {
                body.addView(UI.mt(UI.dangerButton(c, L.t("Удалить сценарий", "Ssenariyni o'chirish", "Delete scenario"), new Runnable() {
                    @Override
                    public void run() {
                        UI.confirm(c, L.t("Удалить сценарий?", "Ssenariy o'chirilsinmi?", "Delete scenario?"), original.optString("name"), L.t("Удалить", "O'chirish", "Delete"), new Runnable() {
                            @Override
                            public void run() {
                                api.delete("/automation/rules/" + original.optInt("id"), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        act.back();
                                    }
                                });
                            }
                        });
                    }
                }), 10));
            }
        }

        private void addAction(final String type, final JSONArray acts) {
            final JSONObject a = obj("type", type);
            if ("reply".equals(type) || "notify".equals(type) || "remind".equals(type)) {
                UI.prompt(c, type, L.t("Текст", "Matn", "Text"), "", true, new UI.TextCallback() {
                    @Override
                    public void on(String v) {
                        put(a, "text", v);
                        if ("remind".equals(type)) put(a, "minutes", 30);
                        acts.put(a);
                        render();
                    }
                });
            } else if ("reply_template".equals(type) || "tag".equals(type)) {
                UI.prompt(c, type, L.t("Имя", "Nom", "Name"), "", false, new UI.TextCallback() {
                    @Override
                    public void on(String v) {
                        put(a, "reply_template".equals(type) ? "name" : "tag", v.trim());
                        acts.put(a);
                        render();
                    }
                });
            } else if ("set_mode".equals(type)) {
                UI.choose(c, "mode", MODES, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        put(a, "mode", MODES[v]);
                        acts.put(a);
                        render();
                    }
                });
            } else if ("timer".equals(type)) {
                UI.prompt(c, L.t("Через сколько минут уведомить?", "Necha daqiqadan keyin?", "Notify after how many minutes?"), "30", "30", false, new UI.TextCallback() {
                    @Override
                    public void on(String v) {
                        try {
                            put(a, "minutes", Integer.parseInt(v.trim()));
                        } catch (Exception e) {
                            put(a, "minutes", 30);
                        }
                        put(a, "then", new JSONArray().put(put(obj("type", "notify"), "text", "⏰ " + rule.optString("name"))));
                        acts.put(a);
                        render();
                    }
                });
            } else if ("set_priority".equals(type)) {
                put(a, "value", 3);
                acts.put(a);
                render();
            } else {
                acts.put(a);
                render();
            }
        }

        private static String join(JSONArray a) {
            if (a == null) return "";
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < a.length(); i++) {
                if (i > 0) sb.append(", ");
                sb.append(a.opt(i));
            }
            return sb.toString();
        }
    }

    abstract static class SimpleWatcher implements android.text.TextWatcher {
        public abstract void changed(String s);

        @Override
        public void beforeTextChanged(CharSequence s, int a, int b, int c) {}

        @Override
        public void onTextChanged(CharSequence s, int a, int b, int c) {}

        @Override
        public void afterTextChanged(android.text.Editable e) { changed(e.toString()); }
    }

    public static final class Templates extends Screen {
        @Override
        public String title() { return L.t("Шаблоны автоматизации", "Avtomatlashtirish shablonlari", "Automation templates"); }

        @Override
        public void load() {
            loading();
            api.get("/automation/templates", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    JSONArray items = res.optJSONArray("items");
                    for (int i = 0; items != null && i < items.length(); i++) {
                        final JSONObject t = items.optJSONObject(i);
                        LinearLayout card = UI.card(c);
                        card.addView(UI.h3(c, t.optString("title")));
                        card.addView(UI.caption(c, t.optString("description") + " · " + t.optJSONArray("rules").length() + L.t(" правил", " qoida", " rules")));
                        card.addView(UI.mt(UI.smallButton(c, L.t("Установить", "O'rnatish", "Install"), new Runnable() {
                            @Override
                            public void run() {
                                api.post("/automation/templates/" + t.optString("id") + "/install", null, new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        toast(L.t("Шаблон установлен", "Shablon o'rnatildi", "Template installed"));
                                    }
                                });
                            }
                        }), 10));
                        body.addView(card);
                    }
                }
            });
        }
    }

    public static final class Executions extends Screen {
        @Override
        public String title() { return L.t("Журнал сценариев", "Ssenariylar jurnali", "Scenario log"); }

        @Override
        public void load() {
            loading();
            api.get("/automation/executions", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "bolt", L.t("Сценарии ещё не срабатывали", "Ssenariylar hali ishlamagan", "No runs yet"), null));
                        return;
                    }
                    LinearLayout card = UI.card(c);
                    for (int i = 0; i < items.length(); i++) {
                        JSONObject e = items.optJSONObject(i);
                        card.addView(UI.listRow(c, "bolt", "ok".equals(e.optString("status")) ? Theme.SUCCESS : Theme.WARNING,
                                "rule #" + e.optInt("rule_id") + " · " + e.optString("status"), e.optString("detail"), Fmt.dateTime(e.optLong("created_at")), null));
                    }
                    body.addView(card);
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Commands extends Screen {
        private String q = "";
        private int cat;
        private final String[] cats = {"all", "afk", "ai", "voice", "media", "games", "text", "profile", "autoreply", "system"};

        @Override
        public String title() { return L.t("Команды", "Buyruqlar", "Commands"); }

        @Override
        public void load() {
            if (body.getChildCount() == 0) loading();
            api.get("/commands", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    render(res);
                }
            });
        }

        private void render(final JSONObject res) {
            body.removeAllViews();
            final EditText search = UI.input(c, L.t("Поиск команды", "Buyruq qidirish", "Search command"), q, false);
            search.setOnEditorActionListener(new TextView.OnEditorActionListener() {
                @Override
                public boolean onEditorAction(TextView v, int a, android.view.KeyEvent e) {
                    q = search.getText().toString().trim().toLowerCase();
                    render(res);
                    return true;
                }
            });
            body.addView(search);
            body.addView(UI.mt(UI.chips(c, cats, cat, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    cat = v;
                    render(res);
                }
            }), 10));
            final String prefix = res.optString("prefix", ".");
            final String[] prefixes = {".", "!", "-", ","};
            int pi = 0;
            for (int i = 0; i < prefixes.length; i++) if (prefixes[i].equals(prefix)) pi = i;
            body.addView(UI.section(c, L.t("Префикс команд", "Buyruq prefiksi", "Command prefix")));
            body.addView(UI.chips(c, prefixes, pi, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    api.put("/commands/prefix", obj("prefix", prefixes[v]), new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            load();
                        }
                    });
                }
            }));
            body.addView(UI.mt(UI.button(c, L.t("Мои команды (конструктор)", "Mening buyruqlarim (konstruktor)", "My commands (builder)"), false, new Runnable() {
                @Override
                public void run() {
                    push(new CustomCommands());
                }
            }), 10));
            JSONArray items = res.optJSONArray("items");
            LinearLayout card = UI.card(c);
            UI.mt(card, 12);
            int shown = 0;
            for (int i = 0; items != null && i < items.length(); i++) {
                final JSONObject cmd = items.optJSONObject(i);
                if (cat > 0 && !cats[cat].equals(cmd.optString("category"))) continue;
                if (!q.isEmpty() && !(cmd.optString("name").contains(q) || cmd.optString("description").toLowerCase().contains(q) || cmd.optJSONArray("aliases").toString().contains(q)))
                    continue;
                shown++;
                String st = cmd.optString("status");
                int color = "IMPLEMENTED".equals(st) ? Theme.accent : "NOT_SUPPORTED".equals(st) ? Theme.text3 : Theme.WARNING;
                String sub = cmd.optString("description") + (cmd.optInt("calls_mine") > 0 ? " · " + cmd.optInt("calls_mine") + "×" : "");
                card.addView(UI.listRow(c, cmd.optBoolean("enabled_for_me") ? "terminal" : "pause", color, cmd.optString("name"), sub, null, new Runnable() {
                    @Override
                    public void run() {
                        push(new CommandDetail(cmd));
                    }
                }));
            }
            if (shown == 0) card.addView(UI.empty(c, "search", L.t("Ничего не найдено", "Hech narsa topilmadi", "Nothing found"), null));
            body.addView(UI.section(c, L.f("Команд: %d", "Buyruqlar: %d", "Commands: %d", shown)));
            body.addView(card);
        }
    }

    public static final class CommandDetail extends Screen {
        private final JSONObject cmd;

        CommandDetail(JSONObject cmd) { this.cmd = cmd; }

        @Override
        public String title() { return cmd.optString("name"); }

        @Override
        public void load() {
            body.removeAllViews();
            LinearLayout card = UI.card(c);
            card.addView(UI.h2(c, cmd.optString("name")));
            card.addView(UI.body2(c, cmd.optString("description")));
            card.addView(UI.divider(c));
            card.addView(UI.mono(c, cmd.optString("syntax")));
            JSONArray ex = cmd.optJSONArray("examples");
            for (int i = 0; ex != null && i < ex.length(); i++) card.addView(UI.mt(UI.mono(c, "› " + ex.optString(i)), 4));
            card.addView(UI.divider(c));
            card.addView(UI.keyValue(c, L.t("Категория", "Kategoriya", "Category"), cmd.optString("category")));
            card.addView(UI.keyValue(c, L.t("Алиасы", "Taxalluslar", "Aliases"), cmd.optJSONArray("aliases").toString().replace("[", "").replace("]", "").replace("\"", "")));
            card.addView(UI.keyValue(c, L.t("Статус", "Holat", "Status"), cmd.optString("status")));
            card.addView(UI.keyValue(c, L.t("Тариф", "Tarif", "Plan"), cmd.optString("min_plan").toUpperCase()));
            card.addView(UI.keyValue(c, L.t("Права бизнес-бота", "Biznes-bot huquqlari", "Business rights"), cmd.optJSONArray("rights").length() == 0 ? "—" : cmd.optJSONArray("rights").toString()));
            card.addView(UI.keyValue(c, L.t("Зависимости", "Bog'liqliklar", "Dependencies"), cmd.optJSONArray("deps").length() == 0 ? "—" : cmd.optJSONArray("deps").toString()));
            card.addView(UI.keyValue(c, L.t("Вызовов (мои / всего)", "Chaqiruvlar (meniki / jami)", "Calls (mine / total)"), cmd.optInt("calls_mine") + " / " + cmd.optInt("calls_total")));
            card.addView(UI.keyValue(c, L.t("Ошибок всего", "Jami xatolar", "Errors total"), String.valueOf(cmd.optInt("errors_total"))));
            if (!cmd.isNull("last_error") && !cmd.optString("last_error").isEmpty())
                card.addView(UI.keyValue(c, L.t("Последняя ошибка", "Oxirgi xato", "Last error"), cmd.optString("last_error")));
            if (!cmd.optString("notes").isEmpty()) card.addView(UI.mt(UI.caption(c, "ℹ️ " + cmd.optString("notes")), 6));
            body.addView(card);
            body.addView(UI.toggleRow(c, L.t("Команда включена для меня", "Buyruq men uchun yoqilgan", "Enabled for me"), null, cmd.optBoolean("enabled_for_me"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    api.patch("/commands/" + cmd.optString("id"), put(new JSONObject(), "enabled", v), new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast("✓");
                        }
                    });
                }
            }));
            if (act.isSuper()) {
                body.addView(UI.toggleRow(c, L.t("Включена глобально", "Global yoqilgan", "Enabled globally"), null, cmd.optBoolean("enabled_global"), new UI.BoolCallback() {
                    @Override
                    public void on(boolean v) {
                        api.patch("/commands/" + cmd.optString("id") + "/global", put(new JSONObject(), "enabled", v), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast("✓");
                            }
                        });
                    }
                }));
                final String[] plans = {"free", "plus", "pro", "vip"};
                int pi = 0;
                for (int i = 0; i < plans.length; i++) if (plans[i].equals(cmd.optString("min_plan"))) pi = i;
                body.addView(UI.caption(c, L.t("Минимальный тариф", "Minimal tarif", "Minimum plan")));
                body.addView(UI.mt(UI.chips(c, plans, pi, new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        api.patch("/commands/" + cmd.optString("id") + "/global", obj("min_plan", plans[v]), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast("✓");
                            }
                        });
                    }
                }), 6));
            }
            body.addView(UI.section(c, L.t("Безопасный тест", "Xavfsiz test", "Safe test")));
            final LinearLayout out = UI.card(c);
            final EditText input = UI.input(c, cmd.optString("syntax"), ex != null && ex.length() > 0 ? ex.optString(0) : cmd.optString("name"), false);
            out.addView(input);
            final TextView result = UI.mono(c, cmd.optBoolean("sandbox_safe") ? "" : L.t("Эта команда работает с чатами/медиа — тест покажет, что её нельзя безопасно симулировать.",
                    "Bu buyruq chat/media bilan ishlaydi — xavfsiz simulyatsiya qilib bo'lmaydi.", "This command touches chats/media and cannot be simulated safely."));
            out.addView(UI.mt(UI.button(c, L.t("Запустить тест (ничего не отправляется)", "Testni ishga tushirish (hech narsa yuborilmaydi)", "Run test (nothing is sent)"), true, new Runnable() {
                @Override
                public void run() {
                    api.post("/commands/test", obj("text", input.getText().toString()), new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            JSONArray o = r.optJSONArray("outputs");
                            StringBuilder sb = new StringBuilder(r.optBoolean("ok") ? "✅\n" : "⚠️ " + r.optString("error", "") + "\n");
                            for (int i = 0; o != null && i < o.length(); i++)
                                sb.append(android.text.Html.fromHtml(o.optJSONObject(i).optString("text", o.optJSONObject(i).optString("caption")))).append('\n');
                            result.setText(sb.toString());
                        }
                    });
                }
            }), 10));
            out.addView(UI.mt(result, 10));
            body.addView(out);
        }
    }

    public static final class CustomCommands extends Screen {
        @Override
        public String title() { return L.t("Конструктор команд", "Buyruq konstruktori", "Command builder"); }

        @Override
        public void load() {
            loading();
            api.get("/commands/custom", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    body.addView(UI.caption(c, L.t("Свои команды из безопасных действий: текст, случайный ответ, шаблон, режим, AFK, кубик, уведомление. Плейсхолдеры: {args} {name} {time} {date}.",
                            "Xavfsiz amallardan o'z buyruqlaringiz: matn, tasodifiy javob, shablon, rejim, AFK, zar, bildirishnoma.",
                            "Your own commands from safe actions: text, random reply, template, mode, AFK, dice, notification. Placeholders: {args} {name} {time} {date}.")));
                    body.addView(UI.mt(UI.button(c, L.t("Новая команда-ответ", "Yangi javob buyrug'i", "New text command"), true, new Runnable() {
                        @Override
                        public void run() {
                            create(false);
                        }
                    }), 10));
                    body.addView(UI.mt(UI.button(c, L.t("Новая команда «случайный ответ»", "Yangi «tasodifiy javob» buyrug'i", "New random-reply command"), false, new Runnable() {
                        @Override
                        public void run() {
                            create(true);
                        }
                    }), 8));
                    JSONArray items = res.optJSONArray("items");
                    LinearLayout card = UI.card(c);
                    UI.mt(card, 12);
                    if (items == null || items.length() == 0) card.addView(UI.caption(c, L.t("Пока нет своих команд", "Hozircha o'z buyruqlaringiz yo'q", "No custom commands yet")));
                    for (int i = 0; items != null && i < items.length(); i++) {
                        final JSONObject cc = items.optJSONObject(i);
                        card.addView(UI.listRow(c, "code", Theme.accent, "." + cc.optString("name"), cc.optJSONArray("actions").toString(), cc.optInt("uses") + "× ✕", new Runnable() {
                            @Override
                            public void run() {
                                UI.confirm(c, L.t("Удалить команду?", "Buyruq o'chirilsinmi?", "Delete command?"), "." + cc.optString("name"), L.t("Удалить", "O'chirish", "Delete"), new Runnable() {
                                    @Override
                                    public void run() {
                                        api.delete("/commands/custom/" + cc.optString("name"), new Cb(false) {
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
                    body.addView(card);
                }
            });
        }

        private void create(final boolean random) {
            UI.prompt(c, L.t("Имя команды (без точки)", "Buyruq nomi (nuqtasiz)", "Command name (no dot)"), "price", "", false, new UI.TextCallback() {
                @Override
                public void on(final String name) {
                    UI.prompt(c, random ? L.t("Варианты через |", "Variantlar | bilan", "Options separated by |") : L.t("Текст ответа", "Javob matni", "Reply text"),
                            random ? "да | нет | возможно" : "", "", true, new UI.TextCallback() {
                                @Override
                                public void on(String text) {
                                    JSONObject a;
                                    if (random) {
                                        JSONArray opts = new JSONArray();
                                        for (String o : text.split("\\|")) if (!o.trim().isEmpty()) opts.put(o.trim());
                                        a = put(obj("type", "random"), "options", opts);
                                    } else {
                                        a = put(obj("type", "text"), "text", text);
                                    }
                                    JSONObject b = put(put(new JSONObject(), "name", name.trim()), "actions", new JSONArray().put(a));
                                    api.post("/commands/custom", b, new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            toast("✓ ." + r.optString("name"));
                                            load();
                                        }
                                    });
                                }
                            });
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Media extends Screen {
        @Override
        public String title() { return "Media Studio"; }

        @Override
        public void load() {
            loading();
            api.get("/media/settings", new Cb() {
                @Override
                public void ok(final JSONObject s) {
                    api.get("/media/jobs" + (act.isAdmin() ? "?scope=global" : ""), new Cb() {
                        @Override
                        public void ok(JSONObject jobs) {
                            render(s, jobs);
                        }
                    });
                }
            });
        }

        private void render(final JSONObject s, JSONObject jobs) {
            body.removeAllViews();
            LinearLayout st = UI.tinted(c, s.optBoolean("ffmpeg") ? Theme.SUCCESS : Theme.DANGER);
            st.addView(UI.h3(c, s.optBoolean("ffmpeg") ? "FFmpeg ✓" : L.t("FFmpeg не найден: pkg install ffmpeg", "FFmpeg topilmadi: pkg install ffmpeg", "FFmpeg missing: pkg install ffmpeg")));
            st.addView(UI.caption(c, s.optString("ffmpeg_version")));
            body.addView(st);
            List<View> tiles = new ArrayList<View>();
            Object lim = s.opt("daily_limit");
            tiles.add(UI.statTile(c, "film", Theme.accent, L.t("Сегодня", "Bugun", "Today"), s.optInt("used_today") + " / " + (lim == null || JSONObject.NULL.equals(lim) ? "∞" : lim.toString())));
            tiles.add(UI.statTile(c, "download", Theme.INFO, L.t("Макс. файл", "Maks. fayl", "Max file"), s.optInt("max_input_mb") + " MB"));
            tiles.add(UI.statTile(c, "clock", Theme.WARNING, L.t("Макс. длительность", "Maks. davomiylik", "Max duration"), s.optInt("max_duration") + " s"));
            JSONObject q = jobs.optJSONObject("queue");
            tiles.add(UI.statTile(c, "server", Theme.SUCCESS, L.t("Очередь", "Navbat", "Queue"), q == null ? "—" : q.optInt("queued") + " / " + q.optInt("active")));
            body.addView(UI.mt(UI.grid(c, tiles, 2), 4));
            LinearLayout set = UI.card(c);
            set.addView(UI.toggleRow(c, L.t("Модуль Media включён", "Media moduli yoqilgan", "Media module enabled"), null, s.optBoolean("enabled"), new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    api.patch("/settings", put(new JSONObject(), "values", put(new JSONObject(), "media_enabled", v)), new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {}
                    });
                }
            }));
            set.addView(UI.toggleRow(c, L.t("Удалять команду из чата после результата", "Natijadan keyin buyruqni o'chirish", "Remove the command message after result"),
                    L.t("Нужно право «Удалять все сообщения»", "«Barcha xabarlarni o'chirish» huquqi kerak", "Requires the “delete all messages” right"), s.optBoolean("delete_commands"), new UI.BoolCallback() {
                        @Override
                        public void on(boolean v) {
                            api.patch("/settings", put(new JSONObject(), "values", put(new JSONObject(), "delete_commands", v)), new Cb(false) {
                                @Override
                                public void ok(JSONObject r) {}
                            });
                        }
                    }));
            body.addView(set);
            body.addView(UI.button(c, L.t("Демо эффектов", "Effektlar demosi", "Effects demo"), true, new Runnable() {
                @Override
                public void run() {
                    push(new MediaDemo(s.optJSONArray("demo_effects")));
                }
            }));
            if (act.isAdmin()) {
                body.addView(UI.space(c, 10));
                body.addView(UI.button(c, L.t("Очистить кэш и временные файлы", "Kesh va vaqtinchalik fayllarni tozalash", "Clean cache and temp files"), false, new Runnable() {
                    @Override
                    public void run() {
                        api.post("/media/cleanup", null, new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast(L.f("Удалено: %d", "O'chirildi: %d", "Removed: %d", r.optInt("removed")));
                            }
                        });
                    }
                }));
            }
            if (act.isSuper()) {
                body.addView(UI.section(c, L.t("Лимиты (глобально)", "Limitlar (global)", "Limits (global)")));
                LinearLayout lim2 = UI.card(c);
                lim2.addView(UI.slider(c, L.t("Макс. размер, МБ", "Maks. hajm, MB", "Max size, MB"), 1, 20, s.optInt("max_input_mb"), "", patch("max_input_mb")));
                lim2.addView(UI.slider(c, L.t("Макс. длительность, с", "Maks. davomiylik, s", "Max duration, s"), 10, 900, s.optInt("max_duration"), "", patch("max_duration")));
                lim2.addView(UI.slider(c, L.t("Реверс видео до, с", "Video reversi, s", "Video reverse up to, s"), 5, 180, s.optInt("max_reverse_video"), "", patch("max_reverse_video")));
                lim2.addView(UI.slider(c, L.t("Тайм-аут FFmpeg, с", "FFmpeg taym-auti, s", "FFmpeg timeout, s"), 10, 900, s.optInt("timeout"), "", patch("timeout")));
                body.addView(lim2);
            }
            body.addView(UI.section(c, L.t("Задачи", "Vazifalar", "Jobs")));
            LinearLayout jc = UI.card(c);
            JSONArray items = jobs.optJSONArray("items");
            if (items == null || items.length() == 0) jc.addView(UI.caption(c, L.t("Медиа-задач ещё не было", "Media vazifalar hali bo'lmagan", "No media jobs yet")));
            for (int i = 0; items != null && i < Math.min(40, items.length()); i++) {
                final JSONObject j = items.optJSONObject(i);
                String status = j.optString("status");
                int color = "done".equals(status) ? Theme.SUCCESS : "failed".equals(status) ? Theme.DANGER : "running".equals(status) ? Theme.INFO : Theme.text3;
                boolean active = "queued".equals(status) || "running".equals(status);
                jc.addView(UI.listRow(c, "film", color, "#" + j.optInt("id") + " " + j.optString("kind") + " · " + status,
                        (j.isNull("error") ? "" : j.optString("error") + " · ") + Fmt.dateTime(j.optLong("created_at")), active ? "✕" : null, active ? new Runnable() {
                            @Override
                            public void run() {
                                api.post("/media/jobs/" + j.optInt("id") + "/cancel", null, new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        load();
                                    }
                                });
                            }
                        } : null));
            }
            body.addView(jc);
        }

        private UI.IntCallback patch(final String key) {
            return new UI.IntCallback() {
                @Override
                public void on(int v) {
                    api.patch("/media/settings", put(new JSONObject(), key, v), new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast("✓");
                        }
                    });
                }
            };
        }
    }

    public static final class MediaDemo extends Screen {
        private final JSONArray effects;
        private LinearLayout preview;
        private MediaPlayer player;

        MediaDemo(JSONArray effects) { this.effects = effects; }

        @Override
        public String title() { return L.t("Демо эффектов", "Effektlar demosi", "Effects demo"); }

        @Override
        public boolean refreshable() { return false; }

        @Override
        public void onHide() {
            super.onHide();
            if (player != null) {
                player.release();
                player = null;
            }
        }

        @Override
        public void load() {
            body.removeAllViews();
            body.addView(UI.caption(c, L.t("Эффекты применяются к синтетическому тестовому файлу на сервере — ваши данные не используются.",
                    "Effektlar serverdagi sintetik test fayliga qo'llanadi — ma'lumotlaringiz ishlatilmaydi.",
                    "Effects are applied to a synthetic sample on the server — none of your data is used.")));
            preview = UI.card(c);
            UI.mt(preview, 10);
            preview.addView(UI.caption(c, L.t("Выберите эффект ниже", "Quyidan effektni tanlang", "Pick an effect below")));
            body.addView(preview);
            List<View> chips = new ArrayList<View>();
            for (int i = 0; effects != null && i < effects.length(); i++) {
                final String e = effects.optString(i);
                TextView ch = UI.chip(c, e, false, new Runnable() {
                    @Override
                    public void run() {
                        runEffect(e);
                    }
                });
                chips.add(ch);
            }
            body.addView(UI.grid(c, chips, 3));
        }

        private void runEffect(final String effect) {
            preview.removeAllViews();
            preview.addView(UI.caption(c, "⏳ " + effect));
            api.download("/media/demo/" + Uri.encode(effect), new Api.BytesCallback() {
                @Override
                public void ok(byte[] data, String ct) {
                    preview.removeAllViews();
                    preview.addView(UI.h3(c, effect + " · " + Fmt.bytes(data.length)));
                    if (ct != null && ct.startsWith("image/")) {
                        ImageView iv = new ImageView(c);
                        iv.setAdjustViewBounds(true);
                        iv.setImageBitmap(BitmapFactory.decodeByteArray(data, 0, data.length));
                        preview.addView(UI.mt(iv, 8));
                        return;
                    }
                    try {
                        File f = new File(c.getCacheDir(), "demo_" + effect.replace(":", "_") + (ct != null && ct.startsWith("video") ? ".mp4" : ".ogg"));
                        FileOutputStream fos = new FileOutputStream(f);
                        fos.write(data);
                        fos.close();
                        if (ct != null && ct.startsWith("video")) {
                            VideoView vv = new VideoView(c);
                            vv.setVideoURI(Uri.fromFile(f));
                            preview.addView(vv, UI.lp(UI.MATCH, Theme.dp(260)));
                            vv.start();
                        } else {
                            if (player != null) player.release();
                            player = new MediaPlayer();
                            player.setDataSource(f.getAbsolutePath());
                            player.prepare();
                            player.start();
                            preview.addView(UI.caption(c, "🔊 " + L.t("Воспроизводится", "Ijro etilmoqda", "Playing")));
                        }
                    } catch (Exception ex) {
                        preview.addView(UI.caption(c, "⚠️ " + ex.getMessage()));
                    }
                }

                @Override
                public void fail(ApiError err) {
                    preview.removeAllViews();
                    preview.addView(UI.caption(c, err.human()));
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Games extends Screen {
        @Override
        public String title() { return L.t("Игры", "O'yinlar", "Games"); }

        @Override
        public void load() {
            loading();
            api.get("/games", new Cb() {
                @Override
                public void ok(final JSONObject g) {
                    api.get("/games/leaderboard", new Cb() {
                        @Override
                        public void ok(final JSONObject lb) {
                            api.get("/games/sessions", new Cb() {
                                @Override
                                public void ok(JSONObject sessions) {
                                    render(g, lb, sessions);
                                }
                            });
                        }
                    });
                }
            });
        }

        private void setting(String key, Object v) {
            api.patch("/games/settings", put(new JSONObject(), key, v), new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    toast("✓");
                }
            });
        }

        private void render(JSONObject g, JSONObject lb, JSONObject sessions) {
            body.removeAllViews();
            JSONObject s = g.optJSONObject("settings");
            body.addView(UI.toggleRow(c, L.t("Игры включены", "O'yinlar yoqilgan", "Games enabled"), L.t("Развлечения без ставок", "Garovsiz ko'ngilochar", "Entertainment only, no bets"),
                    g.optBoolean("enabled"), new UI.BoolCallback() {
                        @Override
                        public void on(boolean v) {
                            setting("games_enabled", v);
                        }
                    }));
            LinearLayout list = UI.card(c);
            JSONArray items = g.optJSONArray("items");
            for (int i = 0; items != null && i < items.length(); i++) {
                final JSONObject it = items.optJSONObject(i);
                list.addView(UI.toggleRow(c, "." + it.optString("id") + " — " + it.optString("title"), null, it.optBoolean("enabled"), new UI.BoolCallback() {
                    @Override
                    public void on(boolean v) {
                        api.patch("/commands/" + it.optString("id"), put(new JSONObject(), "enabled", v), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {}
                        });
                    }
                }));
            }
            body.addView(list);
            if (s != null) {
                body.addView(UI.section(c, L.t("Настройки дуэли", "Duel sozlamalari", "Duel settings")));
                LinearLayout ds = UI.card(c);
                ds.addView(UI.slider(c, L.t("Мин. задержка сигнала, с", "Min. signal kechikishi, s", "Min signal delay, s"), 1, 9, s.optInt("duel_min_delay"), "", new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        setting("duel_min_delay", v);
                    }
                }));
                ds.addView(UI.slider(c, L.t("Макс. задержка сигнала, с", "Maks. signal kechikishi, s", "Max signal delay, s"), 2, 20, s.optInt("duel_max_delay"), "", new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        setting("duel_max_delay", v);
                    }
                }));
                ds.addView(UI.slider(c, L.t("Тайм-аут игры, с", "O'yin taym-auti, s", "Game timeout, s"), 30, 900, s.optInt("game_timeout_sec"), "", new UI.IntCallback() {
                    @Override
                    public void on(int v) {
                        setting("game_timeout_sec", v);
                    }
                }));
                body.addView(ds);
            }
            body.addView(UI.section(c, L.t("Активные сессии", "Faol sessiyalar", "Active sessions")));
            LinearLayout sc = UI.card(c);
            JSONArray ss = sessions.optJSONArray("items");
            if (ss == null || ss.length() == 0) sc.addView(UI.caption(c, L.t("Нет активных игр", "Faol o'yinlar yo'q", "No active games")));
            for (int i = 0; ss != null && i < ss.length(); i++) {
                final JSONObject se = ss.optJSONObject(i);
                sc.addView(UI.listRow(c, "game", Theme.accent, se.optString("game") + " · " + se.optString("status"), se.optJSONArray("players").toString(),
                        L.t("завершить", "tugatish", "end"), new Runnable() {
                            @Override
                            public void run() {
                                api.post("/games/sessions/" + se.optString("id") + "/end", null, new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        load();
                                    }
                                });
                            }
                        }));
            }
            body.addView(sc);
            body.addView(UI.section(c, L.t("Таблица лидеров", "Yetakchilar jadvali", "Leaderboard")));
            LinearLayout lc = UI.card(c);
            JSONArray top = lb.optJSONArray("items");
            if (top == null || top.length() == 0) lc.addView(UI.caption(c, L.t("Результатов пока нет", "Natijalar hali yo'q", "No results yet")));
            for (int i = 0; top != null && i < top.length(); i++) {
                JSONObject p = top.optJSONObject(i);
                String medal = i == 0 ? "🥇 " : i == 1 ? "🥈 " : i == 2 ? "🥉 " : (i + 1) + ". ";
                lc.addView(UI.keyValue(c, medal + p.optString("name", String.valueOf(p.optLong("player_id"))),
                        p.optInt("wins") + "W / " + p.optInt("losses") + "L · " + p.optInt("rating") + (p.isNull("best_ms") ? "" : " · ⚡" + p.optInt("best_ms") + "ms")));
            }
            body.addView(lc);
            body.addView(UI.dangerButton(c, L.t("Очистить историю игр", "O'yinlar tarixini tozalash", "Clear game history"), new Runnable() {
                @Override
                public void run() {
                    UI.confirm(c, L.t("Очистить историю?", "Tarix tozalansinmi?", "Clear history?"), L.t("Результаты и рейтинг будут удалены.", "Natijalar va reyting o'chiriladi.",
                            "Results and ratings will be deleted."), L.t("Очистить", "Tozalash", "Clear"), new Runnable() {
                        @Override
                        public void run() {
                            api.delete("/games/history", new Cb(false) {
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
    }
}

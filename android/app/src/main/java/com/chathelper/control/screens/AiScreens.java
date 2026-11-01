package com.chathelper.control.screens;

import android.graphics.Typeface;
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

/** AI Control Center: providers, profiles + prompt editor, playground, usage & costs, memory, drafts, privacy toggles. */
public final class AiScreens {
    private AiScreens() {}

    static final String[] STYLES = {"friendly", "professional", "funny", "smart", "short", "creative", "custom"};

    // =====================================================================================================
    public static final class Hub extends Screen {
        @Override
        public String title() { return L.t("AI-центр", "AI markazi", "AI Center"); }

        @Override
        public void load() {
            loading();
            api.get("/ai/providers", new Cb() {
                @Override
                public void ok(final JSONObject prov) {
                    api.get("/ai/usage", new Cb() {
                        @Override
                        public void ok(final JSONObject usage) {
                            api.get("/settings", new Cb() {
                                @Override
                                public void ok(final JSONObject settings) {
                                    api.get("/ai/profiles", new Cb() {
                                        @Override
                                        public void ok(JSONObject profiles) {
                                            render(prov, usage, settings.optJSONObject("values"), profiles);
                                        }
                                    });
                                }
                            });
                        }
                    });
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

        private void render(JSONObject prov, JSONObject usage, final JSONObject s, JSONObject profiles) {
            body.removeAllViews();
            boolean available = prov.optBoolean("available");
            LinearLayout hero = UI.tinted(c, available ? Theme.accent : Theme.WARNING);
            hero.addView(UI.h3(c, available ? L.t("AI готов к работе", "AI ishga tayyor", "AI is ready") : L.t("AI-провайдер не настроен", "AI provayder sozlanmagan", "No AI provider configured")));
            hero.addView(UI.caption(c, available ? "STT " + (prov.optBoolean("stt") ? "✓" : "—") + " · TTS " + (prov.optBoolean("tts") ? "✓" : "—")
                    : L.t("Добавьте OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY или COMPAT_* в backend/.env и перезапустите.",
                    "backend/.env ga OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY yoki COMPAT_* qo'shing va qayta ishga tushiring.",
                    "Add OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY or COMPAT_* to backend/.env and restart.")));
            body.addView(hero);

            List<View> tiles = new ArrayList<View>();
            tiles.add(UI.statTile(c, "sparkle", Theme.accent, L.t("Запросы сегодня", "Bugungi so'rovlar", "Requests today"),
                    usage.optInt("today_requests") + (usage.isNull("daily_limit") ? "" : " / " + usage.optInt("daily_limit"))));
            tiles.add(UI.statTile(c, "star", Theme.WARNING, L.t("Расход сегодня", "Bugungi xarajat", "Cost today"), Fmt.money(usage.optDouble("today_cost"))));
            tiles.add(UI.statTile(c, "code", Theme.INFO, L.t("Токены сегодня", "Bugungi tokenlar", "Tokens today"), Fmt.number(usage.optDouble("today_tokens"))));
            JSONObject q = usage.optJSONObject("queue");
            tiles.add(UI.statTile(c, "server", Theme.SUCCESS, L.t("Очередь AI", "AI navbati", "AI queue"), q == null ? "—" : q.optInt("in_flight") + " / " + q.optInt("waiting")));
            body.addView(UI.grid(c, tiles, 2));
            LinearLayout chart = UI.card(c);
            chart.addView(UI.h3(c, L.t("Запросы за 30 дней", "30 kunlik so'rovlar", "Requests · 30 days")));
            Chart ch = new Chart(c, Chart.BAR, Theme.accent);
            ch.setData(values(usage.optJSONArray("requests_series")), days(usage.optJSONArray("requests_series")));
            chart.addView(UI.mt(ch, 8));
            chart.addView(UI.caption(c, usage.optString("cost_note")));
            body.addView(chart);

            LinearLayout actions = UI.row(c);
            actions.addView(UI.button(c, "Playground", true, new Runnable() {
                @Override
                public void run() {
                    push(new Playground());
                }
            }), UI.weight(1));
            actions.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
            actions.addView(UI.button(c, L.t("Память", "Xotira", "Memory"), false, new Runnable() {
                @Override
                public void run() {
                    push(new Memory());
                }
            }), UI.weight(1));
            body.addView(actions);
            body.addView(UI.mt(UI.button(c, L.t("Черновики ответов", "Javob qoralamalari", "Reply drafts"), false, new Runnable() {
                @Override
                public void run() {
                    push(new Drafts());
                }
            }), 10));

            body.addView(UI.section(c, L.t("Провайдеры", "Provayderlar", "Providers")));
            LinearLayout pc = UI.card(c);
            JSONArray items = prov.optJSONArray("items");
            for (int i = 0; items != null && i < items.length(); i++) {
                JSONObject p = items.optJSONObject(i);
                boolean conf = p.optBoolean("configured");
                pc.addView(UI.listRow(c, "sparkle", conf ? Theme.SUCCESS : Theme.text3, p.optString("name") + (p.optBoolean("disabled") ? " (off)" : ""),
                        conf ? p.optString("model") + " · " + p.optJSONArray("supports").toString().replace("\"", "") : L.t("нет ключа", "kalit yo'q", "no key"), null, null));
            }
            if (act.isSuper()) {
                pc.addView(UI.mt(UI.smallButton(c, L.t("Проверить подключение API", "API ulanishini tekshirish", "Check API connectivity"), new Runnable() {
                    @Override
                    public void run() {
                        toast("⏳");
                        api.post("/ai/providers/check", null, new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                StringBuilder sb = new StringBuilder();
                                JSONArray n = r.names();
                                for (int i = 0; n != null && i < n.length(); i++) {
                                    String k = n.optString(i);
                                    JSONObject v = r.optJSONObject(k);
                                    if (v == null) continue;
                                    sb.append(k).append(": ").append(!v.optBoolean("configured") ? "—" : v.optBoolean("ok") ? "✅ " + v.optInt("latency_ms") + "ms" : "❌ " + v.optString("error")).append('\n');
                                }
                                UI.info(c, "AI API", sb.toString());
                            }
                        });
                    }
                }), 8));
            }
            body.addView(pc);

            body.addView(UI.section(c, L.t("Профили AI", "AI profillari", "AI profiles")));
            LinearLayout prof = UI.card(c);
            JSONArray ps = profiles.optJSONArray("items");
            if (ps == null || ps.length() == 0) prof.addView(UI.caption(c, L.t("Профилей нет — используются настройки ниже.", "Profillar yo'q — quyidagi sozlamalar ishlatiladi.",
                    "No profiles — the settings below are used.")));
            for (int i = 0; ps != null && i < ps.length(); i++) {
                final JSONObject p = ps.optJSONObject(i);
                prof.addView(UI.listRow(c, p.optInt("is_active") == 1 ? "star" : "user", p.optInt("is_active") == 1 ? Theme.WARNING : Theme.accent, p.optString("name"),
                        p.optString("provider") + (p.isNull("model") ? "" : "/" + p.optString("model")) + " · " + p.optString("mode"), null, new Runnable() {
                            @Override
                            public void run() {
                                push(new ProfileEditor(p));
                            }
                        }));
            }
            prof.addView(UI.mt(UI.smallButton(c, "+ " + L.t("профиль", "profil", "profile"), new Runnable() {
                @Override
                public void run() {
                    push(new ProfileEditor(null));
                }
            }), 8));
            body.addView(prof);

            body.addView(UI.section(c, L.t("Поведение AI", "AI xatti-harakati", "AI behaviour")));
            LinearLayout beh = UI.card(c);
            int si = 0;
            for (int i = 0; i < STYLES.length; i++) if (STYLES[i].equals(s.optString("ai_style"))) si = i;
            beh.addView(UI.caption(c, L.t("Характер по умолчанию", "Standart xarakter", "Default personality")));
            beh.addView(UI.mt(UI.chips(c, STYLES, si, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    set("ai_style", STYLES[v]);
                }
            }), 6));
            final String[] langs = {"auto", "ru", "uz", "en"};
            int li = 0;
            for (int i = 0; i < langs.length; i++) if (langs[i].equals(s.optString("ai_language"))) li = i;
            beh.addView(UI.mt(UI.caption(c, L.t("Язык ответов", "Javob tili", "Reply language")), 10));
            beh.addView(UI.mt(UI.chips(c, langs, li, new UI.IntCallback() {
                @Override
                public void on(int v) {
                    set("ai_language", langs[v]);
                }
            }), 6));
            beh.addView(UI.toggleRow(c, L.t("Ручное подтверждение ответов", "Javoblarni qo'lda tasdiqlash", "Manual reply confirmation"),
                    L.t("Черновик придёт вам в Telegram с кнопками", "Qoralama Telegram'ga tugmalar bilan keladi", "Drafts arrive in Telegram with buttons"), s.optBoolean("ai_confirm"), cb("ai_confirm")));
            beh.addView(UI.toggleRow(c, L.t("Расшифровка голосовых", "Ovozlilarni matnga", "Transcribe voice messages"), null, s.optBoolean("ai_auto_transcribe"), cb("ai_auto_transcribe")));
            beh.addView(UI.toggleRow(c, L.t("Ежедневная AI-сводка", "Kunlik AI xulosa", "Daily AI summary"), null, s.optBoolean("ai_daily_summary"), cb("ai_daily_summary")));
            beh.addView(UI.toggleRow(c, L.t("Определение приоритета чатов", "Chat ustuvorligini aniqlash", "Chat priority detection"), null, s.optBoolean("ai_priority_detection"), cb("ai_priority_detection")));
            beh.addView(UI.slider(c, L.t("Объединять сообщения, с", "Xabarlarni birlashtirish, s", "Batch messages, s"), 0, 60, s.optInt("ai_debounce_sec"), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    set("ai_debounce_sec", v);
                }
            }));
            beh.addView(UI.slider(c, L.t("Контекст (сообщений)", "Kontekst (xabarlar)", "Context (messages)"), 0, 40, s.optInt("ai_context_messages"), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    set("ai_context_messages", v);
                }
            }));
            beh.addView(UI.slider(c, L.t("Лимит AI-ответов на чат в день", "Kunlik chat uchun AI javob limiti", "AI replies per chat per day"), 1, 200, s.optInt("ai_reply_limit_per_chat_day"), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    set("ai_reply_limit_per_chat_day", v);
                }
            }));
            beh.addView(UI.listRow(c, "info", Theme.INFO, L.t("Пометка AI для собеседников", "Suhbatdoshlar uchun AI belgisi", "AI disclosure for contacts"), s.optString("ai_disclosure"), null, new Runnable() {
                @Override
                public void run() {
                    UI.prompt(c, L.t("Пометка AI (обязательна)", "AI belgisi (majburiy)", "AI disclosure (required)"), "", s.optString("ai_disclosure"), false, new UI.TextCallback() {
                        @Override
                        public void on(String v) {
                            set("ai_disclosure", v);
                            load();
                        }
                    });
                }
            }));
            body.addView(beh);
            body.addView(UI.section(c, L.t("Конфиденциальность AI", "AI maxfiyligi", "AI privacy")));
            LinearLayout pr = UI.card(c);
            pr.addView(UI.toggleRow(c, L.t("Хранить историю для контекста", "Kontekst uchun tarixni saqlash", "Store history for context"), null, s.optBoolean("ai_store_history"), cb("ai_store_history")));
            pr.addView(UI.toggleRow(c, L.t("Долгосрочная память (согласие)", "Uzoq muddatli xotira (rozilik)", "Long-term memory (consent)"), null, s.optBoolean("ai_long_memory"), cb("ai_long_memory")));
            pr.addView(UI.slider(c, L.t("Хранить историю, дней", "Tarixni saqlash, kun", "Keep history, days"), 0, 90, s.optInt("history_retention_days"), "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    set("history_retention_days", v);
                }
            }));
            body.addView(pr);
        }

        private UI.BoolCallback cb(final String key) {
            return new UI.BoolCallback() {
                @Override
                public void on(boolean v) {
                    set(key, v);
                }
            };
        }
    }

    // =====================================================================================================
    /** Visual prompt editor + profile parameters. */
    public static final class ProfileEditor extends Screen {
        private final JSONObject p;

        ProfileEditor(JSONObject p) { this.p = p; }

        @Override
        public String title() { return p == null ? L.t("Новый профиль", "Yangi profil", "New profile") : p.optString("name"); }

        @Override
        public boolean refreshable() { return false; }

        @Override
        public void load() {
            body.removeAllViews();
            final JSONObject d = p == null ? new JSONObject() : p;
            final EditText name = UI.input(c, L.t("Название", "Nomi", "Name"), d.optString("name"), false);
            body.addView(name);
            body.addView(UI.section(c, L.t("Системный prompt", "Tizim prompti", "System prompt")));
            final EditText prompt = UI.input(c, L.t("Например: Ты — вежливый менеджер студии…", "Masalan: Siz studiyaning xushmuomala menejerisiz…",
                    "e.g. You are a polite studio manager…"), d.isNull("system_prompt") ? "" : d.optString("system_prompt"), true);
            prompt.setMinLines(8);
            prompt.setTypeface(Typeface.MONOSPACE);
            prompt.setTextSize(13.5f);
            body.addView(prompt);
            final TextView counter = UI.caption(c, prompt.getText().length() + " / 4000 · ~" + (prompt.getText().length() / 4) + " tok");
            body.addView(counter);
            prompt.addTextChangedListener(new AutomationScreens.SimpleWatcher() {
                @Override
                public void changed(String s) {
                    counter.setText(s.length() + " / 4000 · ~" + (s.length() / 4) + " tok");
                }
            });
            String[][] snippets = {
                    {L.t("Тон", "Ohang", "Tone"), L.t("Отвечай дружелюбно и коротко.", "Do'stona va qisqa javob ber.", "Reply in a friendly, concise way.")},
                    {L.t("Бизнес", "Biznes", "Business"), L.t("Ты ассистент компании. Часы работы 10–19. Цены уточняет владелец.", "Siz kompaniya yordamchisisiz. Ish vaqti 10–19.",
                            "You are the company assistant. Hours 10–19. Prices are confirmed by the owner.")},
                    {L.t("Границы", "Chegaralar", "Limits"), L.t("Не обещай сроки и деньги. Если не уверен — передай владельцу.", "Muddat va pul va'da qilma. Ishonchsiz bo'lsang — egasiga topshir.",
                            "Never promise deadlines or money. If unsure — hand over to the owner.")},
                    {L.t("Язык", "Til", "Language"), L.t("Отвечай на языке собеседника (русский или узбекский).", "Suhbatdosh tilida javob ber (rus yoki o'zbek).",
                            "Reply in the contact's language (Russian or Uzbek).")},
            };
            LinearLayout sn = UI.row(c);
            for (final String[] s : snippets) {
                sn.addView(UI.chip(c, "+ " + s[0], false, new Runnable() {
                    @Override
                    public void run() {
                        prompt.append((prompt.getText().length() > 0 ? "\n" : "") + s[1]);
                    }
                }));
            }
            android.widget.HorizontalScrollView hs = new android.widget.HorizontalScrollView(c);
            hs.setHorizontalScrollBarEnabled(false);
            hs.addView(sn);
            body.addView(UI.mt(hs, 8));
            body.addView(UI.section(c, L.t("Параметры", "Parametrlar", "Parameters")));
            LinearLayout params = UI.card(c);
            final String[] providers = {"auto", "openai", "gemini", "anthropic", "compatible"};
            final int[] sel = {0, 0};
            for (int i = 0; i < providers.length; i++) if (providers[i].equals(d.optString("provider", "auto"))) sel[0] = i;
            for (int i = 0; i < STYLES.length; i++) if (STYLES[i].equals(d.optString("mode", "friendly"))) sel[1] = i;
            params.addView(UI.caption(c, L.t("Провайдер", "Provayder", "Provider")));
            params.addView(UI.mt(UI.chips(c, providers, sel[0], new UI.IntCallback() {
                @Override
                public void on(int v) {
                    sel[0] = v;
                    toast(providers[v]);
                }
            }), 6));
            final EditText model = UI.input(c, L.t("Модель (пусто = по умолчанию)", "Model (bo'sh = standart)", "Model (empty = default)"), d.isNull("model") ? "" : d.optString("model"), false);
            UI.mt(model, 10);
            params.addView(model);
            params.addView(UI.mt(UI.caption(c, L.t("Характер", "Xarakter", "Personality")), 10));
            params.addView(UI.mt(UI.chips(c, STYLES, sel[1], new UI.IntCallback() {
                @Override
                public void on(int v) {
                    sel[1] = v;
                    toast(STYLES[v]);
                }
            }), 6));
            final int[] temp = {(int) Math.round((d.isNull("temperature") ? 0.7 : d.optDouble("temperature", 0.7)) * 10)};
            params.addView(UI.slider(c, "Temperature ×0.1", 0, 20, temp[0], "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    temp[0] = v;
                }
            }));
            final int[] maxTok = {d.optInt("max_tokens", 600)};
            params.addView(UI.slider(c, L.t("Макс. ответ, токены", "Maks. javob, tokenlar", "Max answer, tokens"), 50, 4000, maxTok[0], "", new UI.IntCallback() {
                @Override
                public void on(int v) {
                    maxTok[0] = v;
                }
            }));
            body.addView(params);
            body.addView(UI.button(c, L.t("Сохранить", "Saqlash", "Save"), true, new Runnable() {
                @Override
                public void run() {
                    JSONObject b = new JSONObject();
                    put(b, "name", name.getText().toString().trim().isEmpty() ? "Profile" : name.getText().toString().trim());
                    put(b, "system_prompt", prompt.getText().toString());
                    put(b, "provider", providers[sel[0]]);
                    put(b, "model", model.getText().toString().trim().isEmpty() ? JSONObject.NULL : model.getText().toString().trim());
                    put(b, "mode", STYLES[sel[1]]);
                    put(b, "temperature", temp[0] / 10.0);
                    put(b, "max_tokens", maxTok[0]);
                    Cb done = new Cb(false) {
                        @Override
                        public void ok(JSONObject r) {
                            toast(L.t("Профиль сохранён", "Profil saqlandi", "Profile saved"));
                            act.back();
                        }
                    };
                    if (p == null) api.post("/ai/profiles", b, done);
                    else api.patch("/ai/profiles/" + p.optInt("id"), b, done);
                }
            }));
            if (p != null) {
                body.addView(UI.mt(UI.button(c, L.t("Сделать активным", "Faol qilish", "Make active"), false, new Runnable() {
                    @Override
                    public void run() {
                        api.post("/ai/profiles/" + p.optInt("id") + "/activate", null, new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                toast("⭐ " + p.optString("name"));
                            }
                        });
                    }
                }), 10));
                body.addView(UI.mt(UI.dangerButton(c, L.t("Удалить профиль", "Profilni o'chirish", "Delete profile"), new Runnable() {
                    @Override
                    public void run() {
                        api.delete("/ai/profiles/" + p.optInt("id"), new Cb(false) {
                            @Override
                            public void ok(JSONObject r) {
                                act.back();
                            }
                        });
                    }
                }), 10));
            }
        }
    }

    // =====================================================================================================
    public static final class Playground extends Screen {
        private LinearLayout out;

        @Override
        public String title() { return "AI Playground"; }

        @Override
        public boolean refreshable() { return false; }

        @Override
        public void load() {
            if (out != null) return;
            body.removeAllViews();
            body.addView(UI.caption(c, L.t("Тест без отправки сообщений собеседникам. Запросы учитываются в лимитах и расходах.",
                    "Suhbatdoshlarga xabar yubormasdan test. So'rovlar limit va xarajatlarda hisobga olinadi.",
                    "Test without messaging anyone. Requests count towards limits and costs.")));
            final EditText prompt = UI.input(c, L.t("Ваш запрос…", "So'rovingiz…", "Your prompt…"), "", true);
            UI.mt(prompt, 8);
            body.addView(prompt);
            final TextView est = UI.caption(c, "");
            prompt.addTextChangedListener(new AutomationScreens.SimpleWatcher() {
                @Override
                public void changed(String s) {
                    est.setText("≈ " + Math.max(1, s.length() / 4) + " tokens");
                }
            });
            body.addView(est);
            LinearLayout row = UI.row(c);
            UI.mt(row, 8);
            row.addView(UI.button(c, L.t("Ответ", "Javob", "Answer"), true, new Runnable() {
                @Override
                public void run() {
                    execute(prompt.getText().toString(), false);
                }
            }), UI.weight(1));
            row.addView(UI.space(c, 0), UI.lp(Theme.dp(10), 1));
            row.addView(UI.button(c, L.t("Сравнить модели", "Modellarni solishtirish", "Compare models"), false, new Runnable() {
                @Override
                public void run() {
                    execute(prompt.getText().toString(), true);
                }
            }), UI.weight(1));
            body.addView(row);
            out = UI.col(c);
            UI.mt(out, 12);
            body.addView(out);
        }

        private void execute(String text, boolean compare) {
            if (text.trim().isEmpty()) return;
            out.removeAllViews();
            out.addView(UI.skeletons(c, 1));
            if (compare) {
                api.post("/ai/compare", obj("prompt", text), new Cb(false) {
                    @Override
                    public void ok(JSONObject r) {
                        out.removeAllViews();
                        JSONArray items = r.optJSONArray("items");
                        for (int i = 0; items != null && i < items.length(); i++) {
                            JSONObject it = items.optJSONObject(i);
                            LinearLayout card = UI.card(c);
                            card.addView(UI.h3(c, it.optString("provider") + " / " + it.optString("model")));
                            card.addView(UI.caption(c, it.optInt("latency_ms") + " ms · " + it.optInt("tokens") + " tok · " + Fmt.money(it.optDouble("cost"))));
                            TextView t = UI.body(c, it.has("error") ? "⚠️ " + it.optString("error") : it.optString("text"));
                            t.setTextIsSelectable(true);
                            card.addView(UI.mt(t, 8));
                            out.addView(card);
                        }
                    }

                    @Override
                    public void fail(com.chathelper.control.core.ApiError err) {
                        out.removeAllViews();
                        out.addView(UI.error(c, err, null));
                    }
                });
                return;
            }
            api.post("/ai/playground", obj("prompt", text), new Cb(false) {
                @Override
                public void ok(JSONObject r) {
                    out.removeAllViews();
                    LinearLayout card = UI.card(c);
                    card.addView(UI.caption(c, r.optString("provider") + " / " + r.optString("model") + " · " + r.optInt("latency_ms") + " ms · "
                            + r.optInt("prompt_tokens") + "+" + r.optInt("completion_tokens") + " tok · " + Fmt.money(r.optDouble("cost_usd"))));
                    TextView t = UI.body(c, r.optString("text"));
                    t.setTextIsSelectable(true);
                    card.addView(UI.mt(t, 8));
                    out.addView(card);
                }

                @Override
                public void fail(com.chathelper.control.core.ApiError err) {
                    out.removeAllViews();
                    out.addView(UI.error(c, err, null));
                }
            });
        }
    }

    // =====================================================================================================
    public static final class Memory extends Screen {
        @Override
        public String title() { return L.t("Память AI", "AI xotirasi", "AI memory"); }

        @Override
        public void load() {
            loading();
            api.get("/ai/memory", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    body.addView(UI.caption(c, L.t("Факты, которые вы разрешили использовать AI. Только ваши данные, изолированы от других пользователей.",
                            "AI ishlatishiga ruxsat bergan faktlaringiz. Faqat sizning ma'lumotlaringiz.",
                            "Facts you allowed the AI to use. Only your data, isolated from other users.")));
                    body.addView(UI.mt(UI.button(c, L.t("Добавить факт", "Fakt qo'shish", "Add fact"), true, new Runnable() {
                        @Override
                        public void run() {
                            UI.prompt(c, L.t("Факт о вас", "Siz haqingizda fakt", "A fact about you"), "", "", true, new UI.TextCallback() {
                                @Override
                                public void on(String v) {
                                    api.post("/ai/memory", obj("content", v), new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            load();
                                        }
                                    });
                                }
                            });
                        }
                    }), 10));
                    JSONArray items = res.optJSONArray("items");
                    LinearLayout card = UI.card(c);
                    UI.mt(card, 12);
                    if (items == null || items.length() == 0) card.addView(UI.empty(c, "database", L.t("Память пуста", "Xotira bo'sh", "Memory is empty"), null));
                    for (int i = 0; items != null && i < items.length(); i++) {
                        final JSONObject m = items.optJSONObject(i);
                        card.addView(UI.listRow(c, "database", Theme.accent, m.optString("content"), m.optString("kind") + " · " + Fmt.dateTime(m.optLong("created_at")), "✕", new Runnable() {
                            @Override
                            public void run() {
                                api.delete("/ai/memory/" + m.optInt("id"), new Cb(false) {
                                    @Override
                                    public void ok(JSONObject r) {
                                        load();
                                    }
                                });
                            }
                        }));
                    }
                    body.addView(card);
                    body.addView(UI.dangerButton(c, L.t("Очистить всю память и историю", "Barcha xotira va tarixni tozalash", "Clear all memory and history"), new Runnable() {
                        @Override
                        public void run() {
                            UI.confirm(c, L.t("Очистить память?", "Xotira tozalansinmi?", "Clear memory?"), L.t("Факты и история диалогов AI будут удалены.",
                                    "Faktlar va AI suhbatlar tarixi o'chiriladi.", "Facts and AI conversation history will be deleted."), L.t("Очистить", "Tozalash", "Clear"), new Runnable() {
                                @Override
                                public void run() {
                                    api.delete("/ai/memory", new Cb(false) {
                                        @Override
                                        public void ok(JSONObject r) {
                                            toast(L.f("Удалено: %d", "O'chirildi: %d", "Deleted: %d", r.optInt("deleted")));
                                            load();
                                        }
                                    });
                                }
                            });
                        }
                    }));
                }
            });
        }
    }

    public static final class Drafts extends Screen {
        @Override
        public String title() { return L.t("Черновики AI", "AI qoralamalari", "AI drafts"); }

        @Override
        public void load() {
            loading();
            api.get("/ai/drafts", new Cb() {
                @Override
                public void ok(JSONObject res) {
                    body.removeAllViews();
                    JSONArray items = res.optJSONArray("items");
                    if (items == null || items.length() == 0) {
                        body.addView(UI.empty(c, "send", L.t("Черновиков нет", "Qoralamalar yo'q", "No drafts"),
                                L.t("Включите «Ручное подтверждение» — AI будет предлагать ответы на проверку.", "«Qo'lda tasdiqlash»ni yoqing.",
                                        "Enable manual confirmation — the AI will propose replies for review.")));
                        return;
                    }
                    for (int i = 0; i < items.length(); i++) {
                        final JSONObject d = items.optJSONObject(i);
                        LinearLayout card = UI.card(c);
                        card.addView(UI.caption(c, "#" + d.optInt("id") + " · " + d.optString("status") + " · " + Fmt.dateTime(d.optLong("created_at"))));
                        card.addView(UI.mt(UI.body2(c, "💬 " + d.optString("incoming_text")), 6));
                        card.addView(UI.mt(UI.body(c, "🤖 " + d.optString("draft_text")), 6));
                        if ("pending".equals(d.optString("status"))) {
                            LinearLayout row = UI.row(c);
                            UI.mt(row, 10);
                            String[][] acts = {{"send", L.t("Отправить", "Yuborish", "Send")}, {"alt", L.t("Другой", "Boshqa", "Another")}, {"rej", L.t("Отклонить", "Rad etish", "Reject")}};
                            for (final String[] a : acts) {
                                row.addView(UI.smallButton(c, a[1], new Runnable() {
                                    @Override
                                    public void run() {
                                        api.post("/ai/drafts/" + d.optInt("id") + "/" + a[0], null, new Cb(false) {
                                            @Override
                                            public void ok(JSONObject r) {
                                                toast(r.optString("result"));
                                                load();
                                            }
                                        });
                                    }
                                }));
                                row.addView(UI.space(c, 0), UI.lp(Theme.dp(6), 1));
                            }
                            card.addView(row);
                        }
                        body.addView(card);
                    }
                }
            });
        }
    }
}

package com.chathelper.control;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chathelper.control.core.Api;
import com.chathelper.control.core.ApiError;
import com.chathelper.control.core.Fmt;
import com.chathelper.control.core.L;
import com.chathelper.control.core.SessionStore;
import com.chathelper.control.screens.AdminScreens;
import com.chathelper.control.screens.AiScreens;
import com.chathelper.control.screens.AutomationScreens;
import com.chathelper.control.screens.HomeScreens;
import com.chathelper.control.screens.Screen;
import com.chathelper.control.screens.SettingsScreens;
import com.chathelper.control.ui.Icons;
import com.chathelper.control.ui.Theme;
import com.chathelper.control.ui.UI;
import com.chathelper.control.ui.widget.AuroraBackground;
import com.chathelper.control.ui.widget.BottomNav;
import com.chathelper.control.ui.widget.Glass;
import com.chathelper.control.ui.widget.Logo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Single-activity host: splash → pairing → tabbed shell with per-tab navigation stacks. */
public final class MainActivity extends Activity {
    private SessionStore store;
    private Api api;
    private FrameLayout root;
    private FrameLayout container;
    private FrameLayout toastLayer;
    private BottomNav nav;
    private TextView titleView;
    private ImageView backBtn;
    private TextView bellBadge;
    private View topBar;
    private JSONObject me = new JSONObject();
    @SuppressWarnings("unchecked")
    private final List<Screen>[] stacks = new List[5];
    private int tab;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable badgePoll = new Runnable() {
        @Override
        public void run() {
            refreshBadge();
            handler.postDelayed(this, 60000);
        }
    };

    public Api api() { return api; }

    public SessionStore store() { return store; }

    public JSONObject me() { return me; }

    public boolean can(String capability) {
        JSONArray caps = me.optJSONArray("capabilities");
        if (caps == null) return false;
        for (int i = 0; i < caps.length(); i++) if (capability.equals(caps.optString(i))) return true;
        return false;
    }

    public boolean isAdmin() { return can("users"); }

    public boolean isSuper() { return "super_admin".equals(me.optString("role")); }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        store = new SessionStore(this);
        L.init(store.get("lang", null));
        Theme.init(this, store.get("theme", Theme.SYSTEM), parseInt(store.get("accent", "0"), 0), parseFloat(store.get("motion", "1"), 1f));
        api = new Api(store);
        api.setAuthListener(new Api.AuthListener() {
            @Override
            public void onLoggedOut(ApiError reason) {
                toast(L.t("Сессия завершена. Войдите снова кодом из Telegram.", "Sessiya tugadi. Telegram'dagi kod bilan qayta kiring.",
                        "Session ended. Sign in again with a code from Telegram."));
                showPairing();
            }
        });
        String cached = store.me();
        if (cached != null) {
            try {
                me = new JSONObject(cached);
            } catch (Exception ignored) {
                me = new JSONObject();
            }
        }
        buildRoot();
        showSplash();
    }

    private static int parseInt(String s, int def) {
        try {
            return Integer.parseInt(s);
        } catch (Exception e) {
            return def;
        }
    }

    private static float parseFloat(String s, float def) {
        try {
            return Float.parseFloat(s);
        } catch (Exception e) {
            return def;
        }
    }

    private void styleWindow() {
        Window w = getWindow();
        w.setStatusBarColor(Theme.bgTop);
        w.setNavigationBarColor(Theme.bg);
        if (Build.VERSION.SDK_INT >= 23) {
            View d = w.getDecorView();
            int flags = d.getSystemUiVisibility();
            if (Theme.isDark()) flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            else flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 26) {
                if (Theme.isDark()) flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                else flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
            d.setSystemUiVisibility(flags);
        }
        w.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
    }

    private void buildRoot() {
        styleWindow();
        root = new FrameLayout(this);
        root.addView(new AuroraBackground(this), new FrameLayout.LayoutParams(-1, -1));
        container = new FrameLayout(this);
        root.addView(container, new FrameLayout.LayoutParams(-1, -1));
        toastLayer = new FrameLayout(this);
        toastLayer.setClickable(false);
        root.addView(toastLayer, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
    }

    // ---- splash ---------------------------------------------------------------------------------------
    private void showSplash() {
        container.removeAllViews();
        LinearLayout l = UI.col(this);
        l.setGravity(Gravity.CENTER);
        Logo logo = new Logo(this, 132);
        l.addView(logo);
        TextView name = UI.h1(this, "Chat helper");
        name.setGravity(Gravity.CENTER);
        name.setPadding(0, Theme.dp(10), 0, 0);
        l.addView(name);
        TextView sub = UI.text(this, "Control", 15, Theme.text2, false);
        sub.setLetterSpacing(0.3f);
        l.addView(sub);
        final TextView status = UI.caption(this, L.t("Проверка соединения…", "Ulanish tekshirilmoqda…", "Checking connection…"));
        status.setPadding(0, Theme.dp(28), 0, 0);
        l.addView(status);
        container.addView(l, new FrameLayout.LayoutParams(-1, -1));
        if (Theme.animationsOn()) {
            l.setAlpha(0f);
            l.setTranslationY(Theme.dp(16));
            l.animate().alpha(1f).translationY(0).setDuration(Theme.dur(420)).start();
        }
        if (!store.loggedIn()) {
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    showPairing();
                }
            }, Theme.animationsOn() ? 450 : 0);
            return;
        }
        api.get("/auth/me", new Api.Callback() {
            @Override
            public void ok(JSONObject res) {
                me = res;
                store.saveMe(res.toString());
                showShell();
            }

            @Override
            public void fail(ApiError err) {
                if (err.isNetwork()) {
                    status.setText(err.human());
                    status.setTextColor(Theme.WARNING);
                    // offline mode: open the shell with cached identity; screens show their own error states
                    handler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            showShell();
                        }
                    }, 1200);
                }
            }
        });
    }

    // ---- pairing ---------------------------------------------------------------------------------------
    public void showPairing() {
        handler.removeCallbacks(badgePoll);
        for (int i = 0; i < stacks.length; i++) stacks[i] = null;
        container.removeAllViews();
        LinearLayout l = UI.col(this);
        int p = Theme.dp(20);
        l.setPadding(p, Theme.dp(36), p, Theme.dp(40));
        LinearLayout head = UI.row(this);
        head.addView(new Logo(this, 64));
        LinearLayout ht = UI.col(this);
        ht.setPadding(Theme.dp(12), 0, 0, 0);
        ht.addView(UI.h2(this, "Chat helper Control"));
        ht.addView(UI.caption(this, L.t("Безопасное подключение к вашему боту", "Botingizga xavfsiz ulanish", "Secure connection to your bot")));
        head.addView(ht);
        l.addView(head);
        l.addView(UI.space(this, 22));

        LinearLayout steps = UI.card(this);
        steps.addView(UI.h3(this, L.t("Как подключиться", "Qanday ulanish", "How to connect")));
        String[][] st = {
                {"server", L.t("Запустите backend в Termux: ./scripts/start.sh", "Termux'da backend'ni ishga tushiring: ./scripts/start.sh",
                        "Start the backend in Termux: ./scripts/start.sh")},
                {"chat", L.t("Откройте бота Chat helper и отправьте /app", "Chat helper botini oching va /app yuboring", "Open the Chat helper bot and send /app")},
                {"key", L.t("Введите одноразовый код ниже (действует 5 минут)", "Bir martalik kodni kiriting (5 daqiqa amal qiladi)",
                        "Enter the one-time code below (valid for 5 minutes)")},
        };
        for (String[] s : st) steps.addView(UI.listRow(this, s[0], Theme.accent, s[1], null, null, null));
        l.addView(steps);

        LinearLayout form = UI.card(this);
        form.addView(UI.caption(this, L.t("Адрес backend", "Backend manzili", "Backend address")));
        final EditText server = UI.input(this, "http://127.0.0.1:8787", store.server(), false);
        server.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        UI.mt(server, 6);
        form.addView(server);
        final TextView serverState = UI.caption(this, "");
        serverState.setPadding(Theme.dp(4), Theme.dp(6), 0, 0);
        form.addView(serverState);
        form.addView(UI.space(this, 12));
        form.addView(UI.caption(this, L.t("Код из Telegram", "Telegram'dagi kod", "Code from Telegram")));
        final EditText code = UI.input(this, "ABCD-EFGH", "", false);
        code.setTypeface(Typeface.MONOSPACE);
        code.setTextSize(24);
        code.setGravity(Gravity.CENTER);
        code.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        code.setContentDescription("pairing code");
        UI.mt(code, 6);
        code.addTextChangedListener(new TextWatcher() {
            boolean busy;

            @Override
            public void beforeTextChanged(CharSequence s, int a, int b, int d) {}

            @Override
            public void onTextChanged(CharSequence s, int a, int b, int d) {}

            @Override
            public void afterTextChanged(Editable s) {
                if (busy) return;
                busy = true;
                String n = Fmt.pairingCode(s.toString());
                if (!n.equals(s.toString())) {
                    s.replace(0, s.length(), n);
                }
                busy = false;
            }
        });
        form.addView(code);
        form.addView(UI.space(this, 16));
        final TextView login = UI.button(this, L.t("Войти", "Kirish", "Sign in"), true, null);
        UI.onClick(login, new Runnable() {
            @Override
            public void run() {
                final String url = Fmt.serverUrl(server.getText().toString());
                if (url == null) {
                    toast(L.t("Для удалённого сервера нужен https://", "Masofaviy server uchun https:// kerak", "Remote servers require https://"));
                    return;
                }
                String cd = code.getText().toString();
                if (cd.replace("-", "").length() != 8) {
                    toast(L.t("Код состоит из 8 символов", "Kod 8 belgidan iborat", "The code has 8 characters"));
                    return;
                }
                login.setEnabled(false);
                login.setText(L.t("Подключение…", "Ulanmoqda…", "Connecting…"));
                api.pair(url, cd, new Api.Callback() {
                    @Override
                    public void ok(JSONObject res) {
                        me = res.optJSONObject("me") != null ? res.optJSONObject("me") : new JSONObject();
                        toast(L.t("Готово! Устройство подключено.", "Tayyor! Qurilma ulandi.", "Done! Device paired."));
                        showShell();
                    }

                    @Override
                    public void fail(ApiError err) {
                        login.setEnabled(true);
                        login.setText(L.t("Войти", "Kirish", "Sign in"));
                        toast(err.human());
                    }
                });
            }
        });
        form.addView(login);
        form.addView(UI.space(this, 8));
        form.addView(UI.button(this, L.t("Проверить сервер", "Serverni tekshirish", "Check server"), false, new Runnable() {
            @Override
            public void run() {
                String url = Fmt.serverUrl(server.getText().toString());
                if (url == null) {
                    serverState.setText(L.t("Неверный адрес", "Noto'g'ri manzil", "Invalid address"));
                    serverState.setTextColor(Theme.DANGER);
                    return;
                }
                serverState.setText(L.t("Проверка…", "Tekshirilmoqda…", "Checking…"));
                serverState.setTextColor(Theme.text3);
                api.health(url, new Api.Callback() {
                    @Override
                    public void ok(JSONObject res) {
                        serverState.setText("● " + res.optString("name") + " v" + res.optString("version") + " — " +
                                (res.optBoolean("bot_polling") ? L.t("бот работает", "bot ishlayapti", "bot is running") : L.t("бот не опрашивает Telegram", "bot Telegram'ni so'ramayapti", "bot is not polling")));
                        serverState.setTextColor(Theme.SUCCESS);
                    }

                    @Override
                    public void fail(ApiError err) {
                        serverState.setText(err.human());
                        serverState.setTextColor(Theme.DANGER);
                    }
                });
            }
        }));
        l.addView(form);
        TextView sec = UI.caption(this, L.t("🔒 Приложение не хранит токен бота. Сессия шифруется ключом Android Keystore и может быть отозвана из Telegram.",
                "🔒 Ilova bot tokenini saqlamaydi. Sessiya Android Keystore kaliti bilan shifrlanadi va Telegram orqali bekor qilinishi mumkin.",
                "🔒 The app never stores the bot token. The session is encrypted with an Android Keystore key and can be revoked from Telegram."));
        sec.setPadding(Theme.dp(6), Theme.dp(6), Theme.dp(6), 0);
        l.addView(sec);
        container.addView(UI.scroll(this, l), new FrameLayout.LayoutParams(-1, -1));
    }

    // ---- shell -------------------------------------------------------------------------------------------
    public void showShell() {
        container.removeAllViews();
        LinearLayout shell = UI.col(this);
        topBar = buildTopBar();
        shell.addView(topBar);
        FrameLayout content = new FrameLayout(this);
        shell.addView(content, new LinearLayout.LayoutParams(-1, 0, 1f));
        container.addView(shell, new FrameLayout.LayoutParams(-1, -1));
        boolean admin = isAdmin();
        nav = new BottomNav(this, new String[]{"home", admin ? "users" : "chat", "bolt", "sparkle", "gear"},
                new String[]{L.t("Главная", "Asosiy", "Home"), admin ? L.t("Люди", "Odamlar", "Users") : L.t("Чаты", "Chatlar", "Chats"),
                        L.t("Автоматика", "Avtomatika", "Automation"), "AI", L.t("Настройки", "Sozlamalar", "Settings")});
        nav.setListener(new BottomNav.Listener() {
            @Override
            public void onTab(int index) {
                switchTab(index);
            }
        });
        FrameLayout.LayoutParams np = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        np.setMargins(Theme.dp(14), 0, Theme.dp(14), Theme.dp(14));
        container.addView(nav, np);
        this.contentHost = content;
        for (int i = 0; i < stacks.length; i++) stacks[i] = new ArrayList<Screen>();
        tab = 0;
        showTop(true);
        handler.removeCallbacks(badgePoll);
        handler.post(badgePoll);
    }

    private FrameLayout contentHost;

    private Screen rootFor(int t) {
        switch (t) {
            case 0:
                return new HomeScreens.Dashboard();
            case 1:
                return isAdmin() ? new AdminScreens.Users() : new HomeScreens.Chats();
            case 2:
                return new AutomationScreens.Hub();
            case 3:
                return new AiScreens.Hub();
            default:
                return new SettingsScreens.Hub();
        }
    }

    private View buildTopBar() {
        LinearLayout bar = UI.row(this);
        bar.setPadding(Theme.dp(12), Theme.dp(14), Theme.dp(12), Theme.dp(8));
        backBtn = UI.icon(this, "back", Theme.text, 26);
        backBtn.setPadding(Theme.dp(2), Theme.dp(2), Theme.dp(2), Theme.dp(2));
        backBtn.setContentDescription(L.t("Назад", "Orqaga", "Back"));
        UI.onClick(backBtn, new Runnable() {
            @Override
            public void run() {
                back();
            }
        });
        bar.addView(backBtn, new LinearLayout.LayoutParams(Theme.dp(34), Theme.dp(34)));
        titleView = UI.h2(this, "");
        titleView.setPadding(Theme.dp(8), 0, 0, 0);
        titleView.setSingleLine(true);
        bar.addView(titleView, new LinearLayout.LayoutParams(0, -2, 1f));
        ImageView refresh = UI.icon(this, "refresh", Theme.text2, 24);
        refresh.setContentDescription(L.t("Обновить", "Yangilash", "Refresh"));
        UI.onClick(refresh, new Runnable() {
            @Override
            public void run() {
                Screen s = current();
                if (s != null) s.load();
            }
        });
        bar.addView(refresh, new LinearLayout.LayoutParams(Theme.dp(40), Theme.dp(28)));
        FrameLayout bell = new FrameLayout(this);
        ImageView bi = UI.icon(this, "bell", Theme.text2, 24);
        bell.addView(bi, new FrameLayout.LayoutParams(Theme.dp(24), Theme.dp(24), Gravity.CENTER));
        bellBadge = UI.text(this, "", 9.5f, 0xFFFFFFFF, true);
        bellBadge.setGravity(Gravity.CENTER);
        android.graphics.drawable.GradientDrawable g = new android.graphics.drawable.GradientDrawable();
        g.setShape(android.graphics.drawable.GradientDrawable.OVAL);
        g.setColor(Theme.DANGER);
        bellBadge.setBackground(g);
        bellBadge.setVisibility(View.GONE);
        bell.addView(bellBadge, new FrameLayout.LayoutParams(Theme.dp(16), Theme.dp(16), Gravity.TOP | Gravity.END));
        bell.setContentDescription(L.t("Уведомления", "Bildirishnomalar", "Notifications"));
        UI.onClick(bell, new Runnable() {
            @Override
            public void run() {
                push(new HomeScreens.Notifications());
            }
        });
        bar.addView(bell, new LinearLayout.LayoutParams(Theme.dp(40), Theme.dp(34)));
        return bar;
    }

    private void refreshBadge() {
        if (!store.loggedIn() || bellBadge == null) return;
        api.get("/notifications?unread=true", new Api.Callback() {
            @Override
            public void ok(JSONObject res) {
                int n = res.optInt("unread", 0);
                bellBadge.setText(n > 9 ? "9+" : String.valueOf(n));
                bellBadge.setVisibility(n > 0 ? View.VISIBLE : View.GONE);
            }

            @Override
            public void fail(ApiError err) {}
        });
    }

    private Screen current() {
        if (stacks[tab] == null || stacks[tab].isEmpty()) return null;
        return stacks[tab].get(stacks[tab].size() - 1);
    }

    private void showTop(boolean forward) {
        if (stacks[tab].isEmpty()) {
            Screen s = rootFor(tab);
            s.attach(this);
            stacks[tab].add(s);
        }
        final Screen s = current();
        View v = s.view();
        if (v.getParent() != null) ((android.view.ViewGroup) v.getParent()).removeView(v);
        contentHost.removeAllViews();
        contentHost.addView(v, new FrameLayout.LayoutParams(-1, -1));
        if (Theme.animationsOn()) {
            v.setAlpha(0f);
            v.setTranslationX(forward ? Theme.dp(24) : -Theme.dp(24));
            v.animate().alpha(1f).translationX(0).setDuration(Theme.dur(240)).start();
        }
        titleView.setText(s.title());
        backBtn.setVisibility(stacks[tab].size() > 1 ? View.VISIBLE : View.GONE);
        s.onShow();
    }

    public void switchTab(int t) {
        Screen cur = current();
        if (cur != null) cur.onHide();
        if (t == tab && stacks[tab].size() > 1) {
            while (stacks[tab].size() > 1) stacks[tab].remove(stacks[tab].size() - 1);
        }
        tab = t;
        if (nav != null && nav.selected() != t) nav.select(t, true);
        showTop(true);
    }

    public void push(Screen s) {
        if (stacks[tab] == null) return;
        Screen cur = current();
        if (cur != null) cur.onHide();
        s.attach(this);
        stacks[tab].add(s);
        showTop(true);
    }

    public void back() {
        if (stacks[tab] != null && stacks[tab].size() > 1) {
            current().onHide();
            stacks[tab].remove(stacks[tab].size() - 1);
            showTop(false);
        } else if (stacks[tab] != null && tab != 0) {
            switchTab(0);
        } else {
            finish();
        }
    }

    @Override
    public void onBackPressed() {
        if (stacks[0] == null) {
            super.onBackPressed();
            return;
        }
        back();
    }

    /** Re-resolves colors and rebuilds the UI (theme studio / language change). */
    public void applyAppearance() {
        Theme.resolve(this);
        buildRoot();
        if (store.loggedIn()) {
            int keep = tab;
            showShell();
            if (keep != 0) {
                nav.select(keep, false);
                switchTab(keep);
            }
        } else {
            showPairing();
        }
    }

    public void logout() {
        api.post("/auth/logout", null, null);
        store.clear();
        me = new JSONObject();
        showPairing();
    }

    public void toast(String msg) {
        final TextView t = UI.text(this, msg, 14, Theme.text, false);
        t.setPadding(Theme.dp(16), Theme.dp(12), Theme.dp(16), Theme.dp(12));
        t.setBackground(new Glass(Theme.dp(18), 0, true));
        t.setMaxLines(4);
        FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        p.setMargins(Theme.dp(20), 0, Theme.dp(20), Theme.dp(nav != null ? 104 : 28));
        toastLayer.addView(t, p);
        t.setAlpha(0f);
        t.setTranslationY(Theme.dp(12));
        t.animate().alpha(1f).translationY(0).setDuration(Math.max(1, Theme.dur(200))).start();
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                t.animate().alpha(0f).setDuration(Math.max(1, Theme.dur(250))).withEndAction(new Runnable() {
                    @Override
                    public void run() {
                        toastLayer.removeView(t);
                    }
                }).start();
            }
        }, 3200);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        if (Theme.SYSTEM.equals(Theme.mode)) {
            boolean wasDark = Theme.isDark();
            Theme.resolve(this);
            if (wasDark != Theme.isDark()) applyAppearance();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        Screen s = current();
        if (s != null && s.visible()) s.load();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        api.shutdown();
        super.onDestroy();
    }

    /** Small helper used by screens for consistent icon rows. */
    public static Icons icon(String name, int color) { return Icons.of(name, color); }
}

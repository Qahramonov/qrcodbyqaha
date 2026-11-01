package com.chathelper.control.screens;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;

import com.chathelper.control.MainActivity;
import com.chathelper.control.core.Api;
import com.chathelper.control.core.ApiError;
import com.chathelper.control.ui.Theme;
import com.chathelper.control.ui.UI;

import org.json.JSONArray;
import org.json.JSONObject;

/** Base class of every screen: owns a scrollable content column, loading/error states and API helpers. */
public abstract class Screen {
    protected MainActivity act;
    protected Context c;
    protected Api api;
    protected LinearLayout body;
    private ScrollView root;
    private boolean visible;

    public final void attach(MainActivity a) {
        act = a;
        c = a;
        api = a.api();
    }

    public abstract String title();

    public View view() {
        if (root == null) {
            body = UI.col(c);
            int p = Theme.dp(16);
            body.setPadding(p, Theme.dp(4), p, Theme.dp(120));
            root = UI.scroll(c, body);
            build();
        }
        return root;
    }

    /** Builds static content (optional). */
    protected void build() {}

    /** Loads data and renders it. */
    public void load() {}

    public void onShow() {
        visible = true;
        load();
    }

    public void onHide() { visible = false; }

    public boolean visible() { return visible; }

    public boolean refreshable() { return true; }

    protected void loading() {
        body.removeAllViews();
        body.addView(UI.skeletons(c, 4));
    }

    protected void fail(ApiError e) {
        body.removeAllViews();
        body.addView(UI.error(c, e, new Runnable() {
            @Override
            public void run() {
                load();
            }
        }));
    }

    protected void toast(String s) { act.toast(s); }

    protected void push(Screen s) { act.push(s); }

    protected void scrollTop() {
        if (root != null) root.scrollTo(0, 0);
    }

    /** Convenience callback that routes errors to the error state (or a toast when content already exists). */
    protected abstract class Cb implements Api.Callback {
        private final boolean replace;

        protected Cb() { this(true); }

        protected Cb(boolean replaceOnError) { replace = replaceOnError; }

        @Override
        public void fail(ApiError err) {
            if (err.isAuth()) return; // MainActivity handles forced logout
            if (replace) Screen.this.fail(err);
            else toast(err.human());
        }
    }

    // ---- JSON helpers -------------------------------------------------------------------------
    protected static double[] values(JSONArray series) {
        if (series == null) return new double[0];
        double[] v = new double[series.length()];
        for (int i = 0; i < v.length; i++) {
            JSONObject o = series.optJSONObject(i);
            v[i] = o == null ? 0 : o.optDouble("value", 0);
        }
        return v;
    }

    protected static String[] days(JSONArray series) {
        if (series == null || series.length() == 0) return new String[0];
        String first = series.optJSONObject(0).optString("day");
        String last = series.optJSONObject(series.length() - 1).optString("day");
        return new String[]{first.length() >= 10 ? first.substring(5) : first, last.length() >= 10 ? last.substring(5) : last};
    }

    protected static JSONObject obj(String... kv) {
        JSONObject o = new JSONObject();
        try {
            for (int i = 0; i + 1 < kv.length; i += 2) o.put(kv[i], kv[i + 1]);
        } catch (Exception ignored) {
            // keys are constants
        }
        return o;
    }

    protected static JSONObject put(JSONObject o, String k, Object v) {
        try {
            o.put(k, v);
        } catch (Exception ignored) {
            // never happens for valid keys
        }
        return o;
    }
}

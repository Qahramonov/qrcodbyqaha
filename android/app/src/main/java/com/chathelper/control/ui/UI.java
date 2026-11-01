package com.chathelper.control.ui;

import android.app.Dialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

import com.chathelper.control.core.ApiError;
import com.chathelper.control.core.L;
import com.chathelper.control.ui.widget.Glass;
import com.chathelper.control.ui.widget.Skeleton;
import com.chathelper.control.ui.widget.Toggle;

import java.util.List;

/** UI kit of Chat helper Control: typography, glass cards, buttons, chips, rows, inputs, dialogs, states. */
public final class UI {
    public interface IntCallback {
        void on(int value);
    }

    public interface BoolCallback {
        void on(boolean value);
    }

    public interface TextCallback {
        void on(String value);
    }

    public static final int MATCH = ViewGroup.LayoutParams.MATCH_PARENT, WRAP = ViewGroup.LayoutParams.WRAP_CONTENT;

    private UI() {}

    // ---- layout ---------------------------------------------------------------------------------------
    public static LinearLayout col(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    public static LinearLayout row(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    public static LinearLayout.LayoutParams lp(int w, int h) { return new LinearLayout.LayoutParams(w, h); }

    public static LinearLayout.LayoutParams weight(float wgt) { return new LinearLayout.LayoutParams(0, WRAP, wgt); }

    public static <T extends View> T mt(T v, int dpTop) {
        ViewGroup.LayoutParams p = v.getLayoutParams();
        LinearLayout.LayoutParams lp = p instanceof LinearLayout.LayoutParams ? (LinearLayout.LayoutParams) p : lp(MATCH, WRAP);
        lp.topMargin = Theme.dp(dpTop);
        v.setLayoutParams(lp);
        return v;
    }

    public static View space(Context c, int dp) {
        View v = new View(c);
        v.setLayoutParams(lp(1, Theme.dp(dp)));
        return v;
    }

    public static View divider(Context c) {
        View v = new View(c);
        v.setBackgroundColor(Theme.divider);
        LinearLayout.LayoutParams p = lp(MATCH, Math.max(1, Theme.dp(0.8f)));
        p.topMargin = Theme.dp(10);
        p.bottomMargin = Theme.dp(10);
        v.setLayoutParams(p);
        return v;
    }

    public static ScrollView scroll(Context c, View content) {
        ScrollView sv = new ScrollView(c);
        sv.setFillViewport(true);
        sv.setVerticalScrollBarEnabled(false);
        sv.setClipToPadding(false);
        sv.addView(content);
        return sv;
    }

    // ---- typography ----------------------------------------------------------------------------------
    public static TextView text(Context c, String s, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setLineSpacing(0, 1.12f);
        if (bold) t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        return t;
    }

    public static TextView h1(Context c, String s) {
        TextView t = text(c, s, Theme.DISPLAY, Theme.text, true);
        t.setLetterSpacing(-0.01f);
        return t;
    }

    public static TextView h2(Context c, String s) { return text(c, s, Theme.TITLE, Theme.text, true); }

    public static TextView h3(Context c, String s) { return text(c, s, Theme.HEADLINE, Theme.text, true); }

    public static TextView body(Context c, String s) { return text(c, s, Theme.BODY, Theme.text, false); }

    public static TextView body2(Context c, String s) { return text(c, s, Theme.BODY - 1, Theme.text2, false); }

    public static TextView caption(Context c, String s) { return text(c, s, Theme.CAPTION, Theme.text3, false); }

    public static TextView mono(Context c, String s) {
        TextView t = text(c, s, 13, Theme.text, false);
        t.setTypeface(Typeface.MONOSPACE);
        t.setTextIsSelectable(true);
        return t;
    }

    public static TextView section(Context c, String s) {
        TextView t = text(c, s.toUpperCase(), 11.5f, Theme.text3, true);
        t.setLetterSpacing(0.08f);
        t.setPadding(Theme.dp(4), Theme.dp(18), 0, Theme.dp(8));
        return t;
    }

    public static ImageView icon(Context c, String name, int color, int sizeDp) {
        ImageView iv = new ImageView(c);
        iv.setImageDrawable(Icons.of(name, color));
        iv.setLayoutParams(lp(Theme.dp(sizeDp), Theme.dp(sizeDp)));
        return iv;
    }

    // ---- surfaces -----------------------------------------------------------------------------------------
    public static LinearLayout card(Context c) {
        LinearLayout l = col(c);
        l.setBackground(new Glass(Theme.dp(Theme.R_CARD)));
        int p = Theme.dp(16);
        l.setPadding(p, p, p, p);
        LinearLayout.LayoutParams lp = lp(MATCH, WRAP);
        lp.bottomMargin = Theme.dp(12);
        l.setLayoutParams(lp);
        return l;
    }

    public static LinearLayout tinted(Context c, int color) {
        LinearLayout l = card(c);
        l.setBackground(new Glass(Theme.dp(Theme.R_CARD), color, false));
        return l;
    }

    public static View iconBubble(Context c, String icon, int color) {
        FrameLayout f = new FrameLayout(c);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(Theme.withAlpha(color, Theme.isDark() ? 0x2E : 0x22));
        f.setBackground(g);
        ImageView iv = icon(c, icon, color, 20);
        FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(Theme.dp(20), Theme.dp(20), Gravity.CENTER);
        f.addView(iv, p);
        f.setLayoutParams(lp(Theme.dp(40), Theme.dp(40)));
        return f;
    }

    // ---- interaction --------------------------------------------------------------------------------------
    public static void pressable(final View v) {
        v.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View view, MotionEvent e) {
                if (!Theme.animationsOn()) return false;
                if (e.getAction() == MotionEvent.ACTION_DOWN) view.animate().scaleX(0.97f).scaleY(0.97f).setDuration(Theme.dur(90)).start();
                else if (e.getAction() == MotionEvent.ACTION_UP || e.getAction() == MotionEvent.ACTION_CANCEL)
                    view.animate().scaleX(1f).scaleY(1f).setDuration(Theme.dur(160)).start();
                return false;
            }
        });
    }

    public static void onClick(View v, final Runnable r) {
        v.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK);
                r.run();
            }
        });
    }

    private static RippleDrawable ripple(android.graphics.drawable.Drawable content, float radius) {
        GradientDrawable mask = new GradientDrawable();
        mask.setCornerRadius(radius);
        mask.setColor(Color.WHITE);
        return new RippleDrawable(ColorStateList.valueOf(Theme.withAlpha(Theme.isDark() ? 0xFFFFFF : 0x141B3C, 0x30)), content, mask);
    }

    public static TextView button(Context c, String label, boolean primary, Runnable action) {
        TextView b = text(c, label, 15, primary ? Theme.onAccent() : Theme.text, true);
        b.setGravity(Gravity.CENTER);
        b.setPadding(Theme.dp(18), Theme.dp(13), Theme.dp(18), Theme.dp(13));
        float rad = Theme.dp(Theme.R_BUTTON);
        if (primary) {
            GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{Theme.accent, Theme.accent2()});
            g.setCornerRadius(rad);
            b.setBackground(ripple(g, rad));
        } else {
            b.setBackground(ripple(new Glass(rad), rad));
        }
        b.setLayoutParams(lp(MATCH, WRAP));
        pressable(b);
        if (action != null) onClick(b, action);
        return b;
    }

    public static TextView dangerButton(Context c, String label, Runnable action) {
        TextView b = button(c, label, false, action);
        b.setTextColor(Theme.DANGER);
        float rad = Theme.dp(Theme.R_BUTTON);
        b.setBackground(ripple(new Glass(rad, Theme.DANGER, false), rad));
        return b;
    }

    public static TextView smallButton(Context c, String label, Runnable action) {
        TextView b = button(c, label, false, action);
        b.setTextSize(13);
        b.setPadding(Theme.dp(12), Theme.dp(8), Theme.dp(12), Theme.dp(8));
        b.setLayoutParams(lp(WRAP, WRAP));
        return b;
    }

    public static TextView chip(Context c, String label, boolean selected, Runnable action) {
        TextView t = text(c, label, 13, selected ? Theme.onAccent() : Theme.text2, selected);
        t.setPadding(Theme.dp(14), Theme.dp(8), Theme.dp(14), Theme.dp(8));
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(Theme.dp(Theme.R_PILL));
        if (selected) g.setColors(new int[]{Theme.accent, Theme.accent2()});
        else {
            g.setColor(Theme.isDark() ? 0x14FFFFFF : 0x0D141B3C);
            g.setStroke(Math.max(1, Theme.dp(0.8f)), Theme.border);
        }
        g.setOrientation(GradientDrawable.Orientation.LEFT_RIGHT);
        t.setBackground(ripple(g, Theme.dp(Theme.R_PILL)));
        LinearLayout.LayoutParams p = lp(WRAP, WRAP);
        p.rightMargin = Theme.dp(8);
        t.setLayoutParams(p);
        if (action != null) onClick(t, action);
        return t;
    }

    /** Horizontal scrolling single-choice chips. */
    public static HorizontalScrollView chips(Context c, String[] labels, int selected, final IntCallback cb) {
        HorizontalScrollView hs = new HorizontalScrollView(c);
        hs.setHorizontalScrollBarEnabled(false);
        LinearLayout r = row(c);
        for (int i = 0; i < labels.length; i++) {
            final int idx = i;
            r.addView(chip(c, labels[i], i == selected, new Runnable() {
                @Override
                public void run() {
                    cb.on(idx);
                }
            }));
        }
        hs.addView(r);
        hs.setLayoutParams(lp(MATCH, WRAP));
        return hs;
    }

    public static View badge(Context c, String s, int color) {
        TextView t = text(c, s, 11, color, true);
        t.setPadding(Theme.dp(8), Theme.dp(3), Theme.dp(8), Theme.dp(3));
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(Theme.dp(Theme.R_PILL));
        g.setColor(Theme.withAlpha(color, Theme.isDark() ? 0x2A : 0x1E));
        t.setBackground(g);
        t.setLayoutParams(lp(WRAP, WRAP));
        return t;
    }

    // ---- rows -------------------------------------------------------------------------------------------------
    public static LinearLayout listRow(Context c, String icon, int iconColor, String title, String sub, String trailing, Runnable action) {
        LinearLayout r = row(c);
        r.setPadding(Theme.dp(4), Theme.dp(10), Theme.dp(4), Theme.dp(10));
        if (icon != null) {
            r.addView(iconBubble(c, icon, iconColor));
            r.addView(space(c, 0), lp(Theme.dp(12), 1));
        }
        LinearLayout tx = col(c);
        TextView t = body(c, title);
        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        t.setMaxLines(2);
        t.setEllipsize(TextUtils.TruncateAt.END);
        tx.addView(t);
        if (sub != null && !sub.isEmpty()) {
            TextView s = caption(c, sub);
            s.setMaxLines(3);
            s.setEllipsize(TextUtils.TruncateAt.END);
            tx.addView(s);
        }
        r.addView(tx, weight(1));
        if (trailing != null) {
            TextView tr = caption(c, trailing);
            tr.setPadding(Theme.dp(8), 0, 0, 0);
            r.addView(tr);
        }
        if (action != null) {
            r.addView(icon(c, "chevron", Theme.text3, 18));
            r.setBackground(ripple(new ColorDrawable(Color.TRANSPARENT), Theme.dp(14)));
            onClick(r, action);
        }
        return r;
    }

    public static LinearLayout toggleRow(Context c, String title, String sub, boolean on, final BoolCallback cb) {
        LinearLayout r = row(c);
        r.setPadding(Theme.dp(4), Theme.dp(10), Theme.dp(4), Theme.dp(10));
        LinearLayout tx = col(c);
        tx.addView(body(c, title));
        if (sub != null && !sub.isEmpty()) tx.addView(caption(c, sub));
        r.addView(tx, weight(1));
        Toggle t = new Toggle(c, on);
        t.setContentDescription(title);
        t.setListener(new Toggle.Listener() {
            @Override
            public void onChanged(Toggle tg, boolean checked) {
                cb.on(checked);
            }
        });
        r.addView(t);
        return r;
    }

    public static LinearLayout keyValue(Context c, String k, String v) {
        LinearLayout r = row(c);
        r.setPadding(0, Theme.dp(5), 0, Theme.dp(5));
        r.addView(body2(c, k), weight(1));
        TextView tv = body(c, v);
        tv.setGravity(Gravity.END);
        tv.setMaxLines(3);
        r.addView(tv, weight(1.2f));
        return r;
    }

    public static LinearLayout statTile(Context c, String icon, int color, String label, String value) {
        LinearLayout l = card(c);
        l.setPadding(Theme.dp(14), Theme.dp(14), Theme.dp(14), Theme.dp(14));
        LinearLayout top = row(c);
        top.addView(icon(c, icon, color, 18));
        TextView lab = caption(c, "  " + label);
        lab.setMaxLines(1);
        lab.setEllipsize(TextUtils.TruncateAt.END);
        top.addView(lab, weight(1));
        l.addView(top);
        TextView v = text(c, value, 22, Theme.text, true);
        v.setPadding(0, Theme.dp(6), 0, 0);
        v.setMaxLines(1);
        l.addView(v);
        return l;
    }

    /** Arrange views in a grid with equal-width columns. */
    public static LinearLayout grid(Context c, List<View> views, int cols) {
        LinearLayout g = col(c);
        LinearLayout current = null;
        for (int i = 0; i < views.size(); i++) {
            if (i % cols == 0) {
                current = row(c);
                current.setGravity(Gravity.TOP);
                g.addView(current, lp(MATCH, WRAP));
            }
            View v = views.get(i);
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, WRAP, 1f);
            p.rightMargin = (i % cols == cols - 1) ? 0 : Theme.dp(10);
            p.bottomMargin = Theme.dp(10);
            v.setLayoutParams(p);
            current.addView(v);
        }
        if (current != null) {
            int rem = views.size() % cols;
            if (rem != 0) for (int i = rem; i < cols; i++) current.addView(new View(c), new LinearLayout.LayoutParams(0, 1, 1f));
        }
        return g;
    }

    public static EditText input(Context c, String hint, String value, boolean multiline) {
        EditText e = new EditText(c);
        e.setHint(hint);
        e.setText(value == null ? "" : value);
        e.setTextColor(Theme.text);
        e.setHintTextColor(Theme.text3);
        e.setTextSize(15);
        e.setPadding(Theme.dp(14), Theme.dp(12), Theme.dp(14), Theme.dp(12));
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(Theme.dp(Theme.R_FIELD));
        g.setColor(Theme.isDark() ? 0x1AFFFFFF : 0xFFFFFFFF);
        g.setStroke(Math.max(1, Theme.dp(1)), Theme.border);
        e.setBackground(g);
        if (multiline) {
            e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
            e.setMinLines(3);
            e.setGravity(Gravity.TOP | Gravity.START);
        } else {
            e.setSingleLine(true);
        }
        e.setLayoutParams(lp(MATCH, WRAP));
        return e;
    }

    public static LinearLayout slider(Context c, final String title, final int min, int max, int value, final String unit, final IntCallback cb) {
        LinearLayout l = col(c);
        l.setPadding(Theme.dp(4), Theme.dp(8), Theme.dp(4), Theme.dp(8));
        final TextView label = body(c, title + ": " + value + unit);
        l.addView(label);
        SeekBar sb = new SeekBar(c);
        sb.setMax(max - min);
        sb.setProgress(value - min);
        sb.setProgressTintList(ColorStateList.valueOf(Theme.accent));
        sb.setThumbTintList(ColorStateList.valueOf(Theme.accent));
        sb.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar s, int p, boolean user) {
                label.setText(title + ": " + (p + min) + unit);
            }

            @Override
            public void onStartTrackingTouch(SeekBar s) {}

            @Override
            public void onStopTrackingTouch(SeekBar s) {
                cb.on(s.getProgress() + min);
            }
        });
        l.addView(sb, lp(MATCH, WRAP));
        return l;
    }

    // ---- states -------------------------------------------------------------------------------------------------
    public static LinearLayout empty(Context c, String icon, String title, String sub) {
        LinearLayout l = col(c);
        l.setGravity(Gravity.CENTER_HORIZONTAL);
        l.setPadding(Theme.dp(24), Theme.dp(28), Theme.dp(24), Theme.dp(28));
        View b = iconBubble(c, icon, Theme.accent);
        b.setLayoutParams(lp(Theme.dp(56), Theme.dp(56)));
        l.addView(b);
        TextView t = h3(c, title);
        t.setGravity(Gravity.CENTER);
        t.setPadding(0, Theme.dp(12), 0, Theme.dp(4));
        l.addView(t);
        if (sub != null) {
            TextView s = body2(c, sub);
            s.setGravity(Gravity.CENTER);
            l.addView(s);
        }
        return l;
    }

    public static LinearLayout error(Context c, ApiError e, Runnable retry) {
        LinearLayout l = tinted(c, Theme.DANGER);
        LinearLayout r = row(c);
        r.addView(icon(c, e.isNetwork() ? "server" : "warning", Theme.DANGER, 22));
        TextView t = h3(c, "  " + (e.isNetwork() ? L.t("Backend недоступен", "Backend mavjud emas", "Backend unreachable") : L.t("Ошибка", "Xatolik", "Error")));
        r.addView(t);
        l.addView(r);
        TextView m = body2(c, e.human());
        m.setPadding(0, Theme.dp(6), 0, Theme.dp(10));
        l.addView(m);
        if (retry != null) l.addView(button(c, L.t("Повторить", "Qayta urinish", "Retry"), false, retry));
        return l;
    }

    public static LinearLayout skeletons(Context c, int n) {
        LinearLayout l = col(c);
        for (int i = 0; i < n; i++) {
            Skeleton s = new Skeleton(c, i == 0 ? 120 : 64);
            LinearLayout.LayoutParams p = lp(MATCH, WRAP);
            p.bottomMargin = Theme.dp(12);
            l.addView(s, p);
        }
        return l;
    }

    // ---- dialogs --------------------------------------------------------------------------------------------------
    public static Dialog sheet(Context c, View content) {
        Dialog d = new Dialog(c);
        d.requestWindowFeature(Window.FEATURE_NO_TITLE);
        LinearLayout box = col(c);
        box.setBackground(new Glass(Theme.dp(26), 0, true));
        int p = Theme.dp(20);
        box.setPadding(p, p, p, p);
        box.addView(content);
        ScrollView sv = scroll(c, box);
        FrameLayout wrap = new FrameLayout(c);
        wrap.setPadding(Theme.dp(16), Theme.dp(16), Theme.dp(16), Theme.dp(16));
        wrap.addView(sv);
        d.setContentView(wrap);
        Window w = d.getWindow();
        if (w != null) {
            w.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            w.setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT);
            w.setDimAmount(Theme.isDark() ? 0.6f : 0.35f);
            w.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        }
        return d;
    }

    public static void confirm(Context c, String title, String msg, String yes, final Runnable onYes) {
        LinearLayout l = col(c);
        l.addView(h2(c, title));
        TextView m = body2(c, msg);
        m.setPadding(0, Theme.dp(8), 0, Theme.dp(16));
        l.addView(m);
        final Dialog[] d = new Dialog[1];
        LinearLayout btns = row(c);
        btns.addView(button(c, L.t("Отмена", "Bekor", "Cancel"), false, new Runnable() {
            @Override
            public void run() {
                d[0].dismiss();
            }
        }), weight(1));
        btns.addView(space(c, 0), lp(Theme.dp(10), 1));
        btns.addView(button(c, yes, true, new Runnable() {
            @Override
            public void run() {
                d[0].dismiss();
                onYes.run();
            }
        }), weight(1));
        l.addView(btns);
        d[0] = sheet(c, l);
        d[0].show();
    }

    public static void prompt(Context c, String title, String hint, String initial, boolean multiline, final TextCallback cb) {
        LinearLayout l = col(c);
        l.addView(h2(c, title));
        final EditText e = input(c, hint, initial, multiline);
        mt(e, 12);
        l.addView(e);
        final Dialog[] d = new Dialog[1];
        LinearLayout btns = row(c);
        mt(btns, 16);
        btns.addView(button(c, L.t("Отмена", "Bekor", "Cancel"), false, new Runnable() {
            @Override
            public void run() {
                d[0].dismiss();
            }
        }), weight(1));
        btns.addView(space(c, 0), lp(Theme.dp(10), 1));
        btns.addView(button(c, L.t("Готово", "Tayyor", "Done"), true, new Runnable() {
            @Override
            public void run() {
                d[0].dismiss();
                cb.on(e.getText().toString());
            }
        }), weight(1));
        l.addView(btns);
        d[0] = sheet(c, l);
        d[0].show();
        e.requestFocus();
    }

    /** Dangerous action: the user must type a confirmation word. */
    public static void typedConfirm(Context c, String title, String msg, final String word, final TextCallback onOk) {
        prompt(c, title + "\n" + msg, L.f("Введите %s", "%s ni kiriting", "Type %s", word), "", false, new TextCallback() {
            @Override
            public void on(String value) {
                onOk.on(value.trim());
            }
        });
    }

    public static void choose(Context c, String title, String[] items, final IntCallback cb) {
        LinearLayout l = col(c);
        l.addView(h2(c, title));
        final Dialog[] d = new Dialog[1];
        for (int i = 0; i < items.length; i++) {
            final int idx = i;
            l.addView(listRow(c, null, 0, items[i], null, null, new Runnable() {
                @Override
                public void run() {
                    d[0].dismiss();
                    cb.on(idx);
                }
            }));
        }
        d[0] = sheet(c, l);
        d[0].show();
    }

    public static void info(Context c, String title, String msg) {
        LinearLayout l = col(c);
        l.addView(h2(c, title));
        TextView m = body2(c, msg);
        m.setTextIsSelectable(true);
        m.setPadding(0, Theme.dp(8), 0, Theme.dp(16));
        l.addView(m);
        final Dialog[] d = new Dialog[1];
        l.addView(button(c, "OK", true, new Runnable() {
            @Override
            public void run() {
                d[0].dismiss();
            }
        }));
        d[0] = sheet(c, l);
        d[0].show();
    }
}

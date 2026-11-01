package com.chathelper.control.ui.widget;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.animation.DecelerateInterpolator;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chathelper.control.ui.Icons;
import com.chathelper.control.ui.Theme;

/** Floating glass bottom navigation with an animated pill indicator. */
public final class BottomNav extends LinearLayout {
    public interface Listener {
        void onTab(int index);
    }

    private final Paint pill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final LinearLayout[] items;
    private final Icons[] icons;
    private final TextView[] texts;
    private int selected;
    private float pillX = -1;
    private Listener listener;

    public BottomNav(Context c, String[] iconNames, String[] labels) {
        super(c);
        setOrientation(HORIZONTAL);
        setWillNotDraw(false);
        int pad = Theme.dp(6);
        setPadding(pad, pad, pad, pad);
        setBackground(new Glass(Theme.dp(26), 0, false));
        items = new LinearLayout[labels.length];
        icons = new Icons[labels.length];
        texts = new TextView[labels.length];
        for (int i = 0; i < labels.length; i++) {
            final int idx = i;
            LinearLayout item = new LinearLayout(c);
            item.setOrientation(VERTICAL);
            item.setGravity(Gravity.CENTER);
            item.setPadding(0, Theme.dp(7), 0, Theme.dp(6));
            ImageView iv = new ImageView(c);
            icons[i] = Icons.of(iconNames[i], Theme.text2);
            iv.setImageDrawable(icons[i]);
            item.addView(iv, new LayoutParams(Theme.dp(22), Theme.dp(22)));
            TextView tv = new TextView(c);
            tv.setText(labels[i]);
            tv.setTextSize(10.5f);
            tv.setSingleLine(true);
            tv.setGravity(Gravity.CENTER);
            tv.setPadding(0, Theme.dp(2), 0, 0);
            texts[i] = tv;
            item.addView(tv);
            item.setContentDescription(labels[i]);
            item.setOnClickListener(new OnClickListener() {
                @Override
                public void onClick(View v) {
                    v.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK);
                    select(idx, true);
                    if (listener != null) listener.onTab(idx);
                }
            });
            items[i] = item;
            addView(item, new LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f));
        }
        applyColors();
    }

    public void setListener(Listener l) { listener = l; }

    public int selected() { return selected; }

    public void applyColors() {
        pill.setColor(Theme.withAlpha(Theme.accent, Theme.isDark() ? 0x33 : 0x24));
        for (int i = 0; i < items.length; i++) {
            boolean on = i == selected;
            icons[i].setColor(on ? Theme.accent : Theme.text2);
            texts[i].setTextColor(on ? Theme.text : Theme.text3);
            texts[i].setTypeface(on ? Typeface.create("sans-serif-medium", Typeface.NORMAL) : Typeface.DEFAULT);
        }
        invalidate();
    }

    public void select(int idx, boolean animate) {
        selected = idx;
        applyColors();
        if (getWidth() == 0) {
            pillX = -1;
            return;
        }
        final float target = items[idx].getLeft();
        if (!animate || !Theme.animationsOn() || pillX < 0) {
            pillX = target;
            invalidate();
            return;
        }
        ValueAnimator a = ValueAnimator.ofFloat(pillX, target);
        a.setDuration(Theme.dur(280));
        a.setInterpolator(new DecelerateInterpolator(1.8f));
        a.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator an) {
                pillX = (Float) an.getAnimatedValue();
                invalidate();
            }
        });
        a.start();
    }

    @Override
    protected void onLayout(boolean changed, int l, int t, int r, int b) {
        super.onLayout(changed, l, t, r, b);
        if (pillX < 0 && items.length > 0) pillX = items[selected].getLeft();
    }

    @Override
    protected void onDraw(Canvas c) {
        super.onDraw(c);
        if (items.length == 0) return;
        View it = items[selected];
        float x = pillX < 0 ? it.getLeft() : pillX;
        rect.set(x + Theme.dp(4), it.getTop() + Theme.dp(2), x + it.getWidth() - Theme.dp(4), it.getBottom() - Theme.dp(2));
        c.drawRoundRect(rect, Theme.dp(18), Theme.dp(18), pill);
    }
}

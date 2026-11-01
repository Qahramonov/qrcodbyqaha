package com.chathelper.control.ui.widget;

import android.animation.ArgbEvaluator;
import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.animation.OvershootInterpolator;

import com.chathelper.control.ui.Theme;

/** Animated switch with a springy thumb, accent track and haptic tick. */
public final class Toggle extends View {
    public interface Listener {
        void onChanged(Toggle t, boolean checked);
    }

    private final Paint track = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint thumb = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF r = new RectF();
    private boolean checked;
    private float pos;
    private Listener listener;
    private ValueAnimator anim;

    public Toggle(Context c, boolean checked) {
        super(c);
        this.checked = checked;
        this.pos = checked ? 1f : 0f;
        thumb.setColor(0xFFFFFFFF);
        thumb.setShadowLayer(Theme.dp(2), 0, Theme.dp(1), 0x40000000);
        setLayerType(LAYER_TYPE_SOFTWARE, null);
        setClickable(true);
        setFocusable(true);
        setContentDescription("switch");
        setOnClickListener(new OnClickListener() {
            @Override
            public void onClick(View v) {
                setChecked(!Toggle.this.checked, true);
                performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
                if (listener != null) listener.onChanged(Toggle.this, Toggle.this.checked);
            }
        });
    }

    public void setListener(Listener l) { listener = l; }

    public boolean isChecked() { return checked; }

    public void setChecked(boolean value, boolean animate) {
        checked = value;
        if (anim != null) anim.cancel();
        float target = value ? 1f : 0f;
        if (!animate || !Theme.animationsOn()) {
            pos = target;
            invalidate();
            return;
        }
        anim = ValueAnimator.ofFloat(pos, target);
        anim.setDuration(Theme.dur(260));
        anim.setInterpolator(new OvershootInterpolator(1.6f));
        anim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator a) {
                pos = (Float) a.getAnimatedValue();
                invalidate();
            }
        });
        anim.start();
    }

    @Override
    protected void onMeasure(int w, int h) {
        setMeasuredDimension(Theme.dp(50), Theme.dp(30));
    }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight();
        float p = Math.max(0f, Math.min(1f, pos));
        int off = Theme.isDark() ? 0x33FFFFFF : 0x26141B3C;
        track.setColor((Integer) new ArgbEvaluator().evaluate(p, off, Theme.accent));
        r.set(0, 0, w, h);
        c.drawRoundRect(r, h / 2, h / 2, track);
        float pad = Theme.dp(3);
        float rad = h / 2 - pad;
        float cx = pad + rad + (w - 2 * pad - 2 * rad) * pos;
        c.drawCircle(cx, h / 2, rad, thumb);
    }
}

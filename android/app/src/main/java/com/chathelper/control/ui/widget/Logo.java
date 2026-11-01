package com.chathelper.control.ui.widget;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.BlurMaskFilter;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.view.View;
import android.view.animation.LinearInterpolator;

import com.chathelper.control.ui.Theme;

/** Animated Chat helper logo: gradient speech bubble, glowing halo, orbiting spark. */
public final class Logo extends View {
    private final Paint glow = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint body = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint mark = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint spark = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path bubble = new Path();
    private final RectF r = new RectF();
    private final int sizeDp;
    private float t;
    private ValueAnimator anim;

    public Logo(Context c, int sizeDp) {
        super(c);
        this.sizeDp = sizeDp;
        setLayerType(LAYER_TYPE_SOFTWARE, null);
        glow.setMaskFilter(new BlurMaskFilter(Theme.dp(sizeDp / 6f), BlurMaskFilter.Blur.NORMAL));
        mark.setStyle(Paint.Style.STROKE);
        mark.setStrokeCap(Paint.Cap.ROUND);
        mark.setColor(0xFFFFFFFF);
        spark.setColor(0xFFFFFFFF);
    }

    @Override
    protected void onMeasure(int w, int h) {
        setMeasuredDimension(Theme.dp(sizeDp), Theme.dp(sizeDp));
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        if (!Theme.animationsOn()) return;
        anim = ValueAnimator.ofFloat(0f, 1f);
        anim.setDuration(2600);
        anim.setRepeatCount(ValueAnimator.INFINITE);
        anim.setInterpolator(new LinearInterpolator());
        anim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator a) {
                t = (Float) a.getAnimatedValue();
                invalidate();
            }
        });
        anim.start();
    }

    @Override
    protected void onDetachedFromWindow() {
        if (anim != null) anim.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onDraw(Canvas c) {
        float s = getWidth();
        float pad = s * 0.18f;
        float pulse = 1f + 0.04f * (float) Math.sin(t * Math.PI * 2);
        c.save();
        c.scale(pulse, pulse, s / 2, s / 2);
        r.set(pad, pad, s - pad, s - pad * 1.25f);
        bubble.reset();
        bubble.addRoundRect(r, s * 0.2f, s * 0.2f, Path.Direction.CW);
        bubble.moveTo(r.left + s * 0.16f, r.bottom - 2);
        bubble.lineTo(r.left + s * 0.12f, s - pad * 0.55f);
        bubble.lineTo(r.left + s * 0.33f, r.bottom - 2);
        bubble.close();
        glow.setColor(Theme.withAlpha(Theme.accent, 0x90));
        c.drawPath(bubble, glow);
        body.setShader(new LinearGradient(r.left, r.top, r.right, r.bottom, Theme.accent, Theme.accent2(), Shader.TileMode.CLAMP));
        c.drawPath(bubble, body);
        // "check-spark" mark inside the bubble
        mark.setStrokeWidth(s * 0.055f);
        float cx = s / 2, cy = (r.top + r.bottom) / 2;
        c.drawLine(cx - s * 0.14f, cy, cx - s * 0.04f, cy + s * 0.09f, mark);
        c.drawLine(cx - s * 0.04f, cy + s * 0.09f, cx + s * 0.15f, cy - s * 0.1f, mark);
        c.restore();
        double a = t * Math.PI * 2;
        float orbit = s * 0.44f;
        float sx = s / 2 + (float) Math.cos(a) * orbit, sy = s / 2 + (float) Math.sin(a) * orbit * 0.55f;
        spark.setAlpha(Theme.animationsOn() ? 230 : 0);
        c.drawCircle(sx, sy, s * 0.03f, spark);
    }
}

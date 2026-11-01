package com.chathelper.control.ui.widget;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.view.View;
import android.view.animation.LinearInterpolator;

import com.chathelper.control.ui.Theme;

/** Animated aurora background: three soft radial "blobs" drifting slowly behind glass panels. */
public final class AuroraBackground extends View {
    private final Paint base = new Paint();
    private final Paint blob = new Paint(Paint.ANTI_ALIAS_FLAG);
    private ValueAnimator anim;
    private float t;

    public AuroraBackground(Context c) {
        super(c);
        setLayerType(LAYER_TYPE_HARDWARE, null);
    }

    public void restart() {
        if (anim != null) anim.cancel();
        invalidate();
        if (!Theme.animationsOn()) return;
        anim = ValueAnimator.ofFloat(0f, 1f);
        anim.setDuration((long) (36000 / Math.max(0.5f, Theme.motion)));
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
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        restart();
    }

    @Override
    protected void onDetachedFromWindow() {
        if (anim != null) anim.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onDraw(Canvas c) {
        int w = getWidth(), h = getHeight();
        base.setShader(new LinearGradient(0, 0, 0, h, Theme.bgTop, Theme.bg, Shader.TileMode.CLAMP));
        c.drawRect(0, 0, w, h, base);
        double a = t * Math.PI * 2;
        drawBlob(c, w * (0.18f + 0.10f * (float) Math.sin(a)), h * (0.12f + 0.05f * (float) Math.cos(a)), w * 0.75f, Theme.blobA);
        drawBlob(c, w * (0.92f + 0.06f * (float) Math.cos(a * 1.3)), h * (0.38f + 0.08f * (float) Math.sin(a)), w * 0.65f, Theme.blobB);
        drawBlob(c, w * (0.35f + 0.12f * (float) Math.sin(a * 0.7)), h * (0.95f + 0.03f * (float) Math.cos(a)), w * 0.8f, Theme.blobC);
    }

    private void drawBlob(Canvas c, float x, float y, float r, int color) {
        blob.setShader(new RadialGradient(x, y, r, color, Theme.withAlpha(color, 0), Shader.TileMode.CLAMP));
        c.drawCircle(x, y, r, blob);
    }
}

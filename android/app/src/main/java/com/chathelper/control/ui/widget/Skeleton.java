package com.chathelper.control.ui.widget;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Shader;
import android.view.View;
import android.view.animation.LinearInterpolator;

import com.chathelper.control.ui.Theme;

/** Shimmering placeholder block shown while data loads. */
public final class Skeleton extends View {
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF r = new RectF();
    private final int heightDp;
    private float shift;
    private ValueAnimator anim;

    public Skeleton(Context c, int heightDp) {
        super(c);
        this.heightDp = heightDp;
    }

    @Override
    protected void onMeasure(int w, int h) {
        setMeasuredDimension(MeasureSpec.getSize(w), Theme.dp(heightDp));
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        if (!Theme.animationsOn()) return;
        anim = ValueAnimator.ofFloat(-1f, 2f);
        anim.setDuration(1300);
        anim.setRepeatCount(ValueAnimator.INFINITE);
        anim.setInterpolator(new LinearInterpolator());
        anim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator a) {
                shift = (Float) a.getAnimatedValue();
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
        float w = getWidth();
        int baseC = Theme.isDark() ? 0x14FFFFFF : 0x0F141B3C;
        int hiC = Theme.isDark() ? 0x29FFFFFF : 0x1F141B3C;
        float x = w * shift;
        p.setShader(new LinearGradient(x - w * 0.4f, 0, x, 0, new int[]{baseC, hiC, baseC}, null, Shader.TileMode.CLAMP));
        r.set(0, 0, w, getHeight());
        float rad = Theme.dp(14);
        c.drawRoundRect(r, rad, rad, p);
    }
}

package com.chathelper.control.ui.widget;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.view.View;
import android.view.animation.DecelerateInterpolator;

import com.chathelper.control.core.Fmt;
import com.chathelper.control.ui.Theme;

/** Lightweight line / bar chart with gradient fill, grow-in animation and min/max labels. */
public final class Chart extends View {
    public static final int LINE = 0, BAR = 1;
    private final int type;
    private double[] values = new double[0];
    private String[] labels = new String[0];
    private int color;
    private float progress = 1f;
    private final Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint area = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint grid = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint label = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint dot = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF rect = new RectF();

    public Chart(Context c, int type, int color) {
        super(c);
        this.type = type;
        this.color = color;
        line.setStyle(Paint.Style.STROKE);
        line.setStrokeWidth(Theme.dp(2.4f));
        line.setStrokeCap(Paint.Cap.ROUND);
        line.setStrokeJoin(Paint.Join.ROUND);
        grid.setStrokeWidth(Theme.dp(1));
        label.setTextSize(Theme.sp(10.5f));
        dot.setStyle(Paint.Style.FILL);
    }

    public void setData(double[] v, String[] l) {
        values = v == null ? new double[0] : v;
        labels = l == null ? new String[0] : l;
        if (Theme.animationsOn()) {
            ValueAnimator a = ValueAnimator.ofFloat(0f, 1f);
            a.setDuration(Theme.dur(700));
            a.setInterpolator(new DecelerateInterpolator(2f));
            a.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
                @Override
                public void onAnimationUpdate(ValueAnimator an) {
                    progress = (Float) an.getAnimatedValue();
                    invalidate();
                }
            });
            a.start();
        } else {
            progress = 1f;
            invalidate();
        }
    }

    public boolean isEmpty() {
        for (double d : values) if (d != 0) return false;
        return true;
    }

    @Override
    protected void onMeasure(int w, int h) {
        int width = MeasureSpec.getSize(w);
        setMeasuredDimension(width, Theme.dp(150));
    }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight();
        float left = Theme.dp(4), right = w - Theme.dp(4), top = Theme.dp(18), bottom = h - Theme.dp(18);
        grid.setColor(Theme.divider);
        for (int i = 0; i <= 3; i++) {
            float y = top + (bottom - top) * i / 3f;
            c.drawLine(left, y, right, y, grid);
        }
        label.setColor(Theme.text3);
        int n = values.length;
        if (n == 0) return;
        double max = 0;
        for (double d : values) max = Math.max(max, d);
        if (max <= 0) max = 1;
        c.drawText("max " + Fmt.number(max), left, top - Theme.dp(5), label);
        if (labels.length > 0) {
            c.drawText(labels[0], left, h - Theme.dp(3), label);
            String last = labels[labels.length - 1];
            c.drawText(last, right - label.measureText(last), h - Theme.dp(3), label);
        }
        if (type == BAR) {
            float slot = (right - left) / n;
            float bw = Math.max(Theme.dp(3), slot * 0.62f);
            area.setShader(new LinearGradient(0, top, 0, bottom, color, Theme.withAlpha(color, 0x55), Shader.TileMode.CLAMP));
            for (int i = 0; i < n; i++) {
                float vh = (float) ((bottom - top) * (values[i] / max) * progress);
                if (vh < 1) continue;
                float x = left + slot * i + (slot - bw) / 2;
                rect.set(x, bottom - vh, x + bw, bottom);
                c.drawRoundRect(rect, bw / 2.5f, bw / 2.5f, area);
            }
            return;
        }
        path.reset();
        float step = n > 1 ? (right - left) / (n - 1) : 0;
        float px = 0, py = 0;
        for (int i = 0; i < n; i++) {
            float x = left + step * i;
            float y = (float) (bottom - (bottom - top) * (values[i] / max) * progress);
            if (i == 0) {
                path.moveTo(x, y);
            } else {
                float cx = (px + x) / 2;
                path.cubicTo(cx, py, cx, y, x, y);
            }
            px = x;
            py = y;
        }
        Path fillPath = new Path(path);
        fillPath.lineTo(px, bottom);
        fillPath.lineTo(left, bottom);
        fillPath.close();
        area.setShader(new LinearGradient(0, top, 0, bottom, Theme.withAlpha(color, 0x66), Theme.withAlpha(color, 0x00), Shader.TileMode.CLAMP));
        c.drawPath(fillPath, area);
        line.setShader(new LinearGradient(left, 0, right, 0, Theme.accent2(), color, Shader.TileMode.CLAMP));
        c.drawPath(path, line);
        dot.setColor(color);
        c.drawCircle(px, py, Theme.dp(4), dot);
        dot.setColor(Theme.withAlpha(color, 0x40));
        c.drawCircle(px, py, Theme.dp(8), dot);
    }
}

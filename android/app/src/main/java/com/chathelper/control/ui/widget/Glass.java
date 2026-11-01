package com.chathelper.control.ui.widget;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;

import com.chathelper.control.ui.Theme;

/**
 * "Liquid glass" panel: translucent vertical gradient, hairline border and a soft specular highlight on the top
 * edge. Cheap to draw (no real-time blur), so it stays smooth on mid-range phones.
 */
public final class Glass extends Drawable {
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint shine = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final float radius;
    private int tint;
    private boolean strong;

    public Glass(float radiusPx) {
        this(radiusPx, 0, false);
    }

    public Glass(float radiusPx, int tint, boolean strong) {
        this.radius = radiusPx;
        this.tint = tint;
        this.strong = strong;
        stroke.setStyle(Paint.Style.STROKE);
        stroke.setStrokeWidth(Math.max(1f, Theme.dp(1) * 0.75f));
        shine.setStyle(Paint.Style.STROKE);
        shine.setStrokeWidth(Theme.dp(1.2f));
    }

    public Glass tint(int color) {
        tint = color;
        onBoundsChange(getBounds());
        invalidateSelf();
        return this;
    }

    @Override
    protected void onBoundsChange(Rect b) {
        rect.set(b.left + 0.5f, b.top + 0.5f, b.right - 0.5f, b.bottom - 0.5f);
        int top, bottom;
        if (tint != 0) {
            top = Theme.withAlpha(tint, Theme.isDark() ? 0x3A : 0x2A);
            bottom = Theme.withAlpha(tint, Theme.isDark() ? 0x14 : 0x10);
        } else if (strong) {
            top = Theme.surfaceStrong;
            bottom = Theme.surfaceStrong;
        } else {
            top = Theme.isDark() ? Theme.withAlpha(0xFFFFFF, Theme.isAmoled() ? 0x12 : 0x1C) : 0xE6FFFFFF;
            bottom = Theme.surface;
        }
        fill.setShader(new LinearGradient(0, b.top, 0, b.bottom, top, bottom, Shader.TileMode.CLAMP));
        stroke.setColor(tint != 0 ? Theme.withAlpha(tint, 0x55) : Theme.border);
        shine.setShader(new LinearGradient(b.left, 0, b.right, 0,
                new int[]{0x00FFFFFF, Theme.highlight, 0x00FFFFFF}, new float[]{0f, 0.5f, 1f}, Shader.TileMode.CLAMP));
    }

    @Override
    public void draw(Canvas c) {
        c.drawRoundRect(rect, radius, radius, fill);
        c.drawRoundRect(rect, radius, radius, stroke);
        float inset = radius * 0.6f;
        c.drawLine(rect.left + inset, rect.top + 1.2f, rect.right - inset, rect.top + 1.2f, shine);
    }

    @Override
    public void setAlpha(int alpha) {
        fill.setAlpha(alpha);
        stroke.setAlpha(alpha);
    }

    @Override
    public void setColorFilter(ColorFilter cf) {
        fill.setColorFilter(cf);
    }

    @Override
    public int getOpacity() { return PixelFormat.TRANSLUCENT; }
}

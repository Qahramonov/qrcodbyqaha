package com.chathelper.control.ui;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;

/**
 * Original line-icon set drawn with Canvas primitives on a 24×24 grid (no image assets, crisp at any density,
 * recolorable). Each icon is a small vector "program".
 */
public final class Icons extends Drawable {
    private final String name;
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF r = new RectF();
    private int color;

    public Icons(String name, int color) {
        this.name = name;
        this.color = color;
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setStrokeJoin(Paint.Join.ROUND);
        fill.setStyle(Paint.Style.FILL);
    }

    public static Icons of(String name, int color) { return new Icons(name, color); }

    public void setColor(int c) {
        color = c;
        invalidateSelf();
    }

    @Override
    public void draw(Canvas c) {
        float w = getBounds().width(), h = getBounds().height();
        float s = Math.min(w, h) / 24f;
        c.save();
        c.translate(getBounds().left + (w - 24 * s) / 2f, getBounds().top + (h - 24 * s) / 2f);
        c.scale(s, s);
        p.setColor(color);
        p.setStrokeWidth(1.9f);
        fill.setColor(color);
        drawIcon(c);
        c.restore();
    }

    private void line(Canvas c, float x1, float y1, float x2, float y2) { c.drawLine(x1, y1, x2, y2, p); }

    private void rr(Canvas c, float l, float t, float rr_, float b, float rad) {
        r.set(l, t, rr_, b);
        c.drawRoundRect(r, rad, rad, p);
    }

    private void circle(Canvas c, float x, float y, float rad) { c.drawCircle(x, y, rad, p); }

    private void dot(Canvas c, float x, float y, float rad) { c.drawCircle(x, y, rad, fill); }

    private void poly(Canvas c, boolean close, float... xy) {
        path.reset();
        path.moveTo(xy[0], xy[1]);
        for (int i = 2; i < xy.length; i += 2) path.lineTo(xy[i], xy[i + 1]);
        if (close) path.close();
        c.drawPath(path, p);
    }

    private void arc(Canvas c, float l, float t, float rr_, float b, float start, float sweep) {
        r.set(l, t, rr_, b);
        c.drawArc(r, start, sweep, false, p);
    }

    private void drawIcon(Canvas c) {
        switch (name) {
            case "home":
                poly(c, false, 3.5f, 11, 12, 4, 20.5f, 11);
                poly(c, false, 5.5f, 9.5f, 5.5f, 20, 18.5f, 20, 18.5f, 9.5f);
                rr(c, 10, 14, 14, 20, 1.5f);
                break;
            case "users":
                circle(c, 9, 8, 3.5f);
                arc(c, 2.5f, 13, 15.5f, 26, 200, 140);
                circle(c, 17, 9, 2.6f);
                arc(c, 13.5f, 14, 22.5f, 24, 215, 110);
                break;
            case "user":
                circle(c, 12, 8, 4);
                arc(c, 4, 14, 20, 30, 200, 140);
                break;
            case "bolt":
                poly(c, true, 13.5f, 2.5f, 5, 13.5f, 11.5f, 13.5f, 10.5f, 21.5f, 19, 10.5f, 12.5f, 10.5f);
                break;
            case "sparkle":
                path.reset();
                path.moveTo(12, 3);
                path.quadTo(13, 11, 21, 12);
                path.quadTo(13, 13, 12, 21);
                path.quadTo(11, 13, 3, 12);
                path.quadTo(11, 11, 12, 3);
                c.drawPath(path, p);
                dot(c, 19, 5, 1.2f);
                dot(c, 5.5f, 18.5f, 1f);
                break;
            case "gear":
                circle(c, 12, 12, 3.2f);
                for (int i = 0; i < 8; i++) {
                    double a = Math.PI / 4 * i;
                    line(c, 12 + (float) Math.cos(a) * 6.3f, 12 + (float) Math.sin(a) * 6.3f, 12 + (float) Math.cos(a) * 8.6f, 12 + (float) Math.sin(a) * 8.6f);
                }
                circle(c, 12, 12, 6.3f);
                break;
            case "link":
                rr(c, 2.5f, 8.5f, 13, 15.5f, 3.5f);
                rr(c, 11, 8.5f, 21.5f, 15.5f, 3.5f);
                break;
            case "chat":
                path.reset();
                r.set(3, 4, 21, 17);
                path.addRoundRect(r, 5, 5, Path.Direction.CW);
                c.drawPath(path, p);
                poly(c, false, 8, 17, 6.5f, 21, 12, 17);
                dot(c, 8.5f, 10.5f, 1.1f);
                dot(c, 12, 10.5f, 1.1f);
                dot(c, 15.5f, 10.5f, 1.1f);
                break;
            case "moon":
                path.reset();
                path.moveTo(19.5f, 14.5f);
                path.cubicTo(15, 17.5f, 8, 14, 9.5f, 4.5f);
                path.cubicTo(4, 6.5f, 2.5f, 14, 7, 18.5f);
                path.cubicTo(11, 22, 17, 20.5f, 19.5f, 14.5f);
                c.drawPath(path, p);
                break;
            case "film":
                rr(c, 3, 5, 21, 19, 3);
                line(c, 7, 5, 7, 19);
                line(c, 17, 5, 17, 19);
                line(c, 3, 12, 21, 12);
                break;
            case "game":
                rr(c, 2.5f, 7, 21.5f, 17.5f, 5);
                line(c, 7.5f, 10.5f, 7.5f, 14.5f);
                line(c, 5.5f, 12.5f, 9.5f, 12.5f);
                dot(c, 15.5f, 11, 1.2f);
                dot(c, 17.5f, 13.5f, 1.2f);
                break;
            case "terminal":
                rr(c, 3, 4.5f, 21, 19.5f, 3);
                poly(c, false, 7, 9.5f, 10, 12, 7, 14.5f);
                line(c, 12, 15, 16.5f, 15);
                break;
            case "chart":
                line(c, 4, 20, 20, 20);
                rr(c, 5.5f, 12, 8.5f, 20, 1);
                rr(c, 10.5f, 7, 13.5f, 20, 1);
                rr(c, 15.5f, 10, 18.5f, 20, 1);
                break;
            case "shield":
                path.reset();
                path.moveTo(12, 3);
                path.lineTo(19.5f, 6);
                path.cubicTo(19.5f, 13, 17, 18, 12, 21);
                path.cubicTo(7, 18, 4.5f, 13, 4.5f, 6);
                path.close();
                c.drawPath(path, p);
                poly(c, false, 8.5f, 12, 11, 14.5f, 15.5f, 9.5f);
                break;
            case "crown":
                poly(c, true, 3.5f, 8, 7.5f, 12, 12, 5, 16.5f, 12, 20.5f, 8, 19, 18, 5, 18);
                break;
            case "megaphone":
                poly(c, true, 4, 10, 15, 5, 15, 19, 4, 14);
                line(c, 7, 14.5f, 8.5f, 20);
                arc(c, 15, 9, 20, 15, -60, 120);
                break;
            case "bell":
                path.reset();
                path.moveTo(6, 16.5f);
                path.lineTo(6, 11);
                path.cubicTo(6, 7, 8.5f, 4.5f, 12, 4.5f);
                path.cubicTo(15.5f, 4.5f, 18, 7, 18, 11);
                path.lineTo(18, 16.5f);
                path.lineTo(19.5f, 18);
                path.lineTo(4.5f, 18);
                path.close();
                c.drawPath(path, p);
                arc(c, 9.5f, 18, 14.5f, 22, 0, 180);
                break;
            case "pulse":
                poly(c, false, 2.5f, 12, 7, 12, 9.5f, 6, 13.5f, 18, 16, 12, 21.5f, 12);
                break;
            case "flag":
                line(c, 5, 3, 5, 21);
                poly(c, true, 5, 4, 18, 4, 15.5f, 8.5f, 18, 13, 5, 13);
                break;
            case "server":
                rr(c, 3.5f, 4, 20.5f, 10.5f, 2.5f);
                rr(c, 3.5f, 13.5f, 20.5f, 20, 2.5f);
                dot(c, 7, 7.2f, 1.1f);
                dot(c, 7, 16.8f, 1.1f);
                break;
            case "search":
                circle(c, 10.5f, 10.5f, 6);
                line(c, 15, 15, 20.5f, 20.5f);
                break;
            case "plus":
                line(c, 12, 5, 12, 19);
                line(c, 5, 12, 19, 12);
                break;
            case "trash":
                line(c, 4, 6.5f, 20, 6.5f);
                poly(c, false, 6, 6.5f, 7, 20, 17, 20, 18, 6.5f);
                poly(c, false, 9, 6.5f, 9.5f, 3.5f, 14.5f, 3.5f, 15, 6.5f);
                break;
            case "check":
                poly(c, false, 4.5f, 12.5f, 9.5f, 17.5f, 19.5f, 6.5f);
                break;
            case "close":
                line(c, 6, 6, 18, 18);
                line(c, 18, 6, 6, 18);
                break;
            case "chevron":
                poly(c, false, 9, 5, 16, 12, 9, 19);
                break;
            case "back":
                poly(c, false, 15, 5, 8, 12, 15, 19);
                break;
            case "refresh":
                arc(c, 4.5f, 4.5f, 19.5f, 19.5f, 30, 290);
                poly(c, false, 19.5f, 4.5f, 19.8f, 9.6f, 14.8f, 9);
                break;
            case "play":
                poly(c, true, 7, 4.5f, 19, 12, 7, 19.5f);
                break;
            case "pause":
                line(c, 9, 5, 9, 19);
                line(c, 15, 5, 15, 19);
                break;
            case "logout":
                poly(c, false, 13, 4, 5, 4, 5, 20, 13, 20);
                line(c, 10, 12, 21, 12);
                poly(c, false, 17.5f, 8.5f, 21, 12, 17.5f, 15.5f);
                break;
            case "key":
                circle(c, 8, 12, 4);
                line(c, 12, 12, 21, 12);
                line(c, 18, 12, 18, 15.5f);
                line(c, 15, 12, 15, 14.5f);
                break;
            case "globe":
                circle(c, 12, 12, 8.5f);
                line(c, 3.5f, 12, 20.5f, 12);
                arc(c, 8, 3.5f, 16, 20.5f, 0, 360);
                break;
            case "palette":
                path.reset();
                path.moveTo(12, 3.5f);
                path.cubicTo(6.5f, 3.5f, 3.5f, 7.5f, 3.5f, 12);
                path.cubicTo(3.5f, 17, 7.5f, 20.5f, 11.5f, 20.5f);
                path.cubicTo(13.5f, 20.5f, 13.5f, 18, 12.5f, 16.5f);
                path.cubicTo(11.5f, 15, 13, 13.5f, 15, 14);
                path.cubicTo(18.5f, 15, 20.5f, 13, 20.5f, 10.5f);
                path.cubicTo(20.5f, 6.5f, 16.5f, 3.5f, 12, 3.5f);
                c.drawPath(path, p);
                dot(c, 8, 10, 1.3f);
                dot(c, 12, 7.5f, 1.3f);
                dot(c, 16, 9.5f, 1.3f);
                break;
            case "info":
                circle(c, 12, 12, 8.5f);
                line(c, 12, 11, 12, 16.5f);
                dot(c, 12, 7.8f, 1.2f);
                break;
            case "warning":
                poly(c, true, 12, 3.5f, 21, 19.5f, 3, 19.5f);
                line(c, 12, 9.5f, 12, 14);
                dot(c, 12, 16.8f, 1.1f);
                break;
            case "lock":
                rr(c, 5, 10.5f, 19, 20.5f, 2.5f);
                arc(c, 8, 4, 16, 14, 180, 180);
                line(c, 8, 9, 8, 10.5f);
                line(c, 16, 9, 16, 10.5f);
                break;
            case "phone":
                rr(c, 7, 2.5f, 17, 21.5f, 2.5f);
                line(c, 10.5f, 18.5f, 13.5f, 18.5f);
                break;
            case "clock":
                circle(c, 12, 12, 8.5f);
                poly(c, false, 12, 7, 12, 12, 15.5f, 14);
                break;
            case "star":
                poly(c, true, 12, 3.5f, 14.6f, 9, 20.5f, 9.6f, 16, 13.5f, 17.3f, 19.5f, 12, 16.4f, 6.7f, 19.5f, 8, 13.5f, 3.5f, 9.6f, 9.4f, 9);
                break;
            case "download":
                line(c, 12, 4, 12, 15);
                poly(c, false, 7.5f, 10.5f, 12, 15, 16.5f, 10.5f);
                line(c, 5, 19.5f, 19, 19.5f);
                break;
            case "mic":
                rr(c, 9, 3, 15, 14, 3);
                arc(c, 6, 7, 18, 17, 0, 180);
                line(c, 12, 17, 12, 21);
                break;
            case "image":
                rr(c, 3, 4.5f, 21, 19.5f, 3);
                circle(c, 9, 9.5f, 1.8f);
                poly(c, false, 4, 18, 10, 12.5f, 14, 16, 16.5f, 13.5f, 20.5f, 17.5f);
                break;
            case "code":
                poly(c, false, 8.5f, 7, 3.5f, 12, 8.5f, 17);
                poly(c, false, 15.5f, 7, 20.5f, 12, 15.5f, 17);
                line(c, 13.5f, 5, 10.5f, 19);
                break;
            case "help":
                circle(c, 12, 12, 8.5f);
                arc(c, 9, 6.5f, 15, 12, 190, 260);
                line(c, 12, 12, 12, 13.8f);
                dot(c, 12, 16.8f, 1.1f);
                break;
            case "grid":
                rr(c, 4, 4, 10.5f, 10.5f, 2);
                rr(c, 13.5f, 4, 20, 10.5f, 2);
                rr(c, 4, 13.5f, 10.5f, 20, 2);
                rr(c, 13.5f, 13.5f, 20, 20, 2);
                break;
            case "database":
                arc(c, 5, 3.5f, 19, 8.5f, 0, 360);
                line(c, 5, 6, 5, 18);
                line(c, 19, 6, 19, 18);
                arc(c, 5, 15.5f, 19, 20.5f, 0, 180);
                arc(c, 5, 9.5f, 19, 14.5f, 0, 180);
                break;
            case "eye":
                path.reset();
                path.moveTo(2.5f, 12);
                path.quadTo(12, 3, 21.5f, 12);
                path.quadTo(12, 21, 2.5f, 12);
                c.drawPath(path, p);
                circle(c, 12, 12, 3);
                break;
            case "send":
                poly(c, true, 3.5f, 11, 20.5f, 4, 14, 20.5f, 11, 13.5f);
                line(c, 11, 13.5f, 20.5f, 4);
                break;
            case "filter":
                poly(c, true, 3.5f, 5, 20.5f, 5, 14, 12.5f, 14, 19, 10, 17, 10, 12.5f);
                break;
            case "dot":
                dot(c, 12, 12, 4);
                break;
            default:
                circle(c, 12, 12, 8);
        }
    }

    @Override
    public void setAlpha(int alpha) {
        p.setAlpha(alpha);
        fill.setAlpha(alpha);
    }

    @Override
    public void setColorFilter(ColorFilter cf) {
        p.setColorFilter(cf);
        fill.setColorFilter(cf);
    }

    @Override
    public int getOpacity() { return PixelFormat.TRANSLUCENT; }

    @Override
    public int getIntrinsicWidth() { return Theme.dp(24); }

    @Override
    public int getIntrinsicHeight() { return Theme.dp(24); }
}

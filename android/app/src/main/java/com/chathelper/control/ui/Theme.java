package com.chathelper.control.ui;

import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.provider.Settings;
import android.util.TypedValue;

/**
 * Design tokens of Chat helper Control ("Aurora Glass"): colors for Dark / Light / AMOLED, accent presets,
 * typography scale, spacing, radii and motion. All UI code reads colors from here so themes switch instantly.
 */
public final class Theme {
    public static final String DARK = "dark", LIGHT = "light", AMOLED = "amoled", SYSTEM = "system";

    public static final int[] ACCENTS = {
            0xFF7C5CFF, // Violet (default)
            0xFF2EC5FF, // Cyan
            0xFF22C55E, // Emerald
            0xFFFF5C8A, // Rose
            0xFFF5A524, // Amber
            0xFF5B7CFF, // Indigo
            0xFFA3E635, // Lime
            0xFFFF7A45, // Orange
    };
    public static final String[] ACCENT_NAMES = {"Violet", "Cyan", "Emerald", "Rose", "Amber", "Indigo", "Lime", "Orange"};

    // runtime state
    public static String mode = SYSTEM;
    public static int accent = ACCENTS[0];
    public static float motion = 1f;          // 0 = off, 0.5 = reduced, 1 = normal, 1.5 = rich
    public static boolean systemReducedMotion;
    private static boolean dark = true;
    private static boolean amoled = false;
    private static float density = 3f;
    private static float scaledDensity = 3f;

    // resolved palette
    public static int bg, bgTop, surface, surfaceStrong, border, highlight, text, text2, text3, divider, blobA, blobB, blobC, scrim;
    public static final int SUCCESS = 0xFF34D399, WARNING = 0xFFFBBF24, DANGER = 0xFFF87171, INFO = 0xFF60A5FA;

    private Theme() {}

    public static void init(Context ctx, String savedMode, int savedAccent, float savedMotion) {
        density = ctx.getResources().getDisplayMetrics().density;
        scaledDensity = ctx.getResources().getDisplayMetrics().scaledDensity;
        mode = savedMode == null ? SYSTEM : savedMode;
        accent = savedAccent == 0 ? ACCENTS[0] : savedAccent;
        motion = savedMotion < 0 ? 1f : savedMotion;
        try {
            systemReducedMotion = Settings.Global.getFloat(ctx.getContentResolver(), Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f;
        } catch (Exception e) {
            systemReducedMotion = false;
        }
        resolve(ctx);
    }

    public static void resolve(Context ctx) {
        boolean sysDark = (ctx.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        dark = DARK.equals(mode) || AMOLED.equals(mode) || (SYSTEM.equals(mode) && sysDark);
        amoled = AMOLED.equals(mode);
        if (dark) {
            bg = amoled ? 0xFF000000 : 0xFF0A0C16;
            bgTop = amoled ? 0xFF000000 : 0xFF11142A;
            surface = amoled ? 0x0FFFFFFF : 0x14FFFFFF;
            surfaceStrong = amoled ? 0xFF0B0B0F : 0xFF161A33;
            border = 0x1FFFFFFF;
            highlight = 0x24FFFFFF;
            text = 0xFFF2F4FF;
            text2 = 0xFFA9AECB;
            text3 = 0xFF6F7497;
            divider = 0x14FFFFFF;
            scrim = 0xB3000000;
            blobA = withAlpha(accent, amoled ? 0x22 : 0x55);
            blobB = amoled ? 0x1A2EC5FF : 0x402EC5FF;
            blobC = amoled ? 0x14FF5C8A : 0x33FF5C8A;
        } else {
            bg = 0xFFF3F5FB;
            bgTop = 0xFFFFFFFF;
            surface = 0xC8FFFFFF;
            surfaceStrong = 0xFFFFFFFF;
            border = 0x1A141B3C;
            highlight = 0xCCFFFFFF;
            text = 0xFF12142A;
            text2 = 0xFF555B7C;
            text3 = 0xFF8A8FAD;
            divider = 0x14141B3C;
            scrim = 0x66141B3C;
            blobA = withAlpha(accent, 0x38);
            blobB = 0x2E2EC5FF;
            blobC = 0x24FF5C8A;
        }
    }

    public static boolean isDark() { return dark; }

    public static boolean isAmoled() { return amoled; }

    public static int accent2() {
        // secondary accent for gradients: rotate hue by ~55°
        float[] hsv = new float[3];
        Color.colorToHSV(accent, hsv);
        hsv[0] = (hsv[0] + 55) % 360;
        return Color.HSVToColor(hsv);
    }

    public static int onAccent() { return 0xFFFFFFFF; }

    public static int withAlpha(int color, int alpha) { return (color & 0x00FFFFFF) | (alpha << 24); }

    public static int tint(int color, float alpha) { return withAlpha(color, Math.max(0, Math.min(255, (int) (alpha * 255)))); }

    // ---- metrics ----------------------------------------------------------------------------------
    public static int dp(float v) { return Math.round(v * density); }

    public static float sp(float v) { return v * scaledDensity; }

    public static float px(Context c, float dp) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, dp, c.getResources().getDisplayMetrics());
    }

    // typography scale (sp)
    public static final float DISPLAY = 28, TITLE = 20, HEADLINE = 17, BODY = 15, CAPTION = 12.5f, MICRO = 11;
    // spacing (dp)
    public static final int S1 = 4, S2 = 8, S3 = 12, S4 = 16, S5 = 20, S6 = 24;
    // radii (dp)
    public static final int R_CARD = 22, R_BUTTON = 16, R_FIELD = 14, R_PILL = 999;

    // ---- motion -------------------------------------------------------------------------------------
    public static boolean animationsOn() { return motion > 0.01f && !systemReducedMotion; }

    public static long dur(long base) {
        if (!animationsOn()) return 0;
        return (long) (base * Math.min(1.25f, Math.max(0.5f, motion)));
    }
}

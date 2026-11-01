package com.chathelper.control.core;

import java.util.Locale;

/** In-app localization (Russian / Uzbek / English). Every UI string is given in all three languages at the call site. */
public final class L {
    public static final String RU = "ru";
    public static final String UZ = "uz";
    public static final String EN = "en";
    private static String lang = RU;

    private L() {}

    public static void init(String saved) {
        if (saved != null && (saved.equals(RU) || saved.equals(UZ) || saved.equals(EN))) {
            lang = saved;
            return;
        }
        String sys = Locale.getDefault().getLanguage();
        lang = "uz".equals(sys) ? UZ : ("en".equals(sys) ? EN : RU);
    }

    public static String lang() { return lang; }

    public static void set(String l) { init(l); }

    /** t(ru, uz, en) */
    public static String t(String ru, String uz, String en) {
        if (UZ.equals(lang)) return uz;
        if (EN.equals(lang)) return en;
        return ru;
    }

    public static String f(String ru, String uz, String en, Object... args) {
        return String.format(Locale.US, t(ru, uz, en), args);
    }
}

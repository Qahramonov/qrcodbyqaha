package com.chathelper.control.core;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Pure formatting helpers (no Android dependencies, unit-tested on the JVM). */
public final class Fmt {
    private Fmt() {}

    public static String number(double v) {
        if (Double.isNaN(v)) return "—";
        double a = Math.abs(v);
        if (a >= 1_000_000) return trim(v / 1_000_000.0) + "M";
        if (a >= 10_000) return trim(v / 1000.0) + "K";
        if (v == Math.rint(v)) return String.valueOf((long) v);
        return trim(v);
    }

    private static String trim(double v) {
        String s = String.format(Locale.US, "%.2f", v);
        while (s.contains(".") && (s.endsWith("0") || s.endsWith("."))) s = s.substring(0, s.length() - 1);
        return s;
    }

    public static String money(double usd) {
        if (usd == 0) return "$0";
        if (usd < 0.01) return String.format(Locale.US, "$%.4f", usd);
        return String.format(Locale.US, "$%.2f", usd);
    }

    public static String bytes(long b) {
        if (b < 1024) return b + " B";
        if (b < 1024 * 1024) return trim(b / 1024.0) + " KB";
        if (b < 1024L * 1024 * 1024) return trim(b / 1048576.0) + " MB";
        return trim(b / 1073741824.0) + " GB";
    }

    public static String duration(long sec) {
        if (sec < 0) sec = 0;
        long d = sec / 86400, h = (sec % 86400) / 3600, m = (sec % 3600) / 60;
        String dd = L.t("д", "k", "d"), hh = L.t("ч", "s", "h"), mm = L.t("м", "d", "m");
        if (d > 0) return d + dd + " " + h + hh;
        if (h > 0) return h + hh + " " + m + mm;
        if (m > 0) return m + mm;
        return sec + L.t("с", "s", "s");
    }

    public static String dateTime(long unix) {
        if (unix <= 0) return "—";
        return new SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.US).format(new Date(unix * 1000L));
    }

    public static String time(long unix) {
        if (unix <= 0) return "—";
        return new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date(unix * 1000L));
    }

    public static String ago(long unix, long nowUnix) {
        if (unix <= 0) return "—";
        long d = Math.max(0, nowUnix - unix);
        if (d < 60) return L.t("только что", "hozirgina", "just now");
        return duration(d) + " " + L.t("назад", "oldin", "ago");
    }

    public static String percent(double ratio) {
        return Math.round(ratio * 100) + "%";
    }

    /** Normalizes a pairing code typed by the user: ABCD-EFGH (ambiguous chars removed). */
    public static String pairingCode(String raw) {
        if (raw == null) return "";
        StringBuilder sb = new StringBuilder();
        String allowed = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        for (char c : raw.toUpperCase(Locale.US).toCharArray()) {
            if (allowed.indexOf(c) >= 0) sb.append(c);
            if (sb.length() == 8) break;
        }
        if (sb.length() > 4) sb.insert(4, '-');
        return sb.toString();
    }

    /** Validates and normalizes the backend URL. Only http on loopback, https anywhere. */
    public static String serverUrl(String raw) {
        if (raw == null) return null;
        String s = raw.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://" + s;
        String host = s.replaceFirst("^https?://", "");
        int slash = host.indexOf('/');
        if (slash >= 0) host = host.substring(0, slash);
        int colon = host.lastIndexOf(':');
        String h = colon > 0 ? host.substring(0, colon) : host;
        if (h.isEmpty()) return null;
        boolean loopback = h.equals("127.0.0.1") || h.equals("localhost") || h.equals("10.0.2.2") || h.equals("[::1]");
        if (s.startsWith("http://") && !loopback) return null;
        return s;
    }
}

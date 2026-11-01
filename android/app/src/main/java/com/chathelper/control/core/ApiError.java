package com.chathelper.control.core;

import org.json.JSONObject;

/** Structured API error: {"error": {"code": "...", "message": "..."}} or a network failure (status 0). */
public final class ApiError {
    public final int status;
    public final String code;
    public final String message;

    public ApiError(int status, String code, String message) {
        this.status = status;
        this.code = code == null ? "error" : code;
        this.message = message == null ? "" : message;
    }

    public static ApiError parse(int status, String body) {
        try {
            JSONObject o = new JSONObject(body);
            JSONObject e = o.optJSONObject("error");
            if (e != null) return new ApiError(status, e.optString("code", "error"), e.optString("message", ""));
        } catch (Exception ignored) {
            // not JSON
        }
        return new ApiError(status, "http_" + status, body == null ? "" : body.length() > 200 ? body.substring(0, 200) : body);
    }

    public static ApiError network(String msg) {
        return new ApiError(0, "network", msg);
    }

    public boolean isNetwork() { return status == 0; }

    public boolean isAuth() { return status == 401; }

    /** Human readable, localized message for the UI. */
    public String human() {
        if (isNetwork()) {
            return L.t("Нет связи с backend. Запущен ли Chat helper в Termux? (./scripts/start.sh)",
                    "Backend bilan aloqa yo'q. Chat helper Termux'da ishlayaptimi? (./scripts/start.sh)",
                    "Cannot reach the backend. Is Chat helper running in Termux? (./scripts/start.sh)");
        }
        if ("invalid_code".equals(code)) return L.t("Неверный или истёкший код. Получите новый: /app в боте.",
                "Kod noto'g'ri yoki eskirgan. Yangisini oling: botda /app.", "Invalid or expired code. Get a new one: /app in the bot.");
        if ("rate_limited".equals(code) || status == 429) return L.t("Слишком много попыток. Подождите немного.",
                "Juda ko'p urinish. Biroz kuting.", "Too many attempts. Please wait.");
        if (status == 403) return L.t("Недостаточно прав для этого действия.", "Bu amal uchun huquq yetarli emas.", "You don't have permission for this.");
        if (status == 401) return L.t("Сессия истекла — войдите заново.", "Sessiya tugadi — qayta kiring.", "Session expired — sign in again.");
        if (status == 404) return L.t("Не найдено.", "Topilmadi.", "Not found.");
        return message.isEmpty() ? ("HTTP " + status) : message;
    }

    @Override
    public String toString() { return status + " " + code + ": " + message; }
}

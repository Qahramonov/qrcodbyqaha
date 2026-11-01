package com.chathelper.control.core;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.Charset;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * REST client for the Chat helper backend (/api/v1). Runs requests on a small thread pool, delivers results on
 * the main thread, transparently refreshes expired access tokens (rotation) and reports forced logouts.
 */
public final class Api {
    public interface Callback {
        void ok(JSONObject res);

        void fail(ApiError err);
    }

    public interface BytesCallback {
        void ok(byte[] data, String contentType);

        void fail(ApiError err);
    }

    public interface AuthListener {
        void onLoggedOut(ApiError reason);
    }

    private static final Charset UTF8 = Charset.forName("UTF-8");
    private final SessionStore store;
    private final ExecutorService pool = Executors.newFixedThreadPool(3);
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Object refreshLock = new Object();
    private AuthListener authListener;
    public volatile long lastOkAt;
    public volatile ApiError lastError;

    public Api(SessionStore store) {
        this.store = store;
    }

    public void setAuthListener(AuthListener l) { authListener = l; }

    public SessionStore store() { return store; }

    // ---- public verbs ------------------------------------------------------------------------
    public void get(String path, Callback cb) { call("GET", path, null, true, cb); }

    public void post(String path, JSONObject body, Callback cb) { call("POST", path, body == null ? new JSONObject() : body, true, cb); }

    public void patch(String path, JSONObject body, Callback cb) { call("PATCH", path, body, true, cb); }

    public void put(String path, JSONObject body, Callback cb) { call("PUT", path, body, true, cb); }

    public void delete(String path, Callback cb) { call("DELETE", path, null, true, cb); }

    public void health(String server, final Callback cb) {
        final String base = server;
        pool.execute(new Runnable() {
            @Override
            public void run() {
                final Result r = raw(base, "GET", "/health", null, null);
                deliver(r, cb);
            }
        });
    }

    public void pair(final String server, final String code, final Callback cb) {
        pool.execute(new Runnable() {
            @Override
            public void run() {
                JSONObject body = new JSONObject();
                try {
                    body.put("code", code);
                    body.put("device_id", store.deviceId());
                    body.put("device_name", store.deviceName());
                    body.put("platform", "android");
                    body.put("app_version", "1.0.0");
                } catch (Exception ignored) {
                    // never happens
                }
                Result r = raw(server, "POST", "/auth/pair", body, null);
                if (r.ok()) {
                    store.setServer(server);
                    store.saveTokens(r.json.optString("access_token"), r.json.optString("refresh_token"));
                    JSONObject me = r.json.optJSONObject("me");
                    if (me != null) store.saveMe(me.toString());
                }
                deliver(r, cb);
            }
        });
    }

    public void download(final String path, final BytesCallback cb) {
        pool.execute(new Runnable() {
            @Override
            public void run() {
                final Result r = authed("GET", path, null, true);
                main.post(new Runnable() {
                    @Override
                    public void run() {
                        if (r.status >= 200 && r.status < 300 && r.bytes != null) cb.ok(r.bytes, r.contentType);
                        else cb.fail(r.error());
                    }
                });
            }
        });
    }

    public void shutdown() { pool.shutdownNow(); }

    // ---- internals ----------------------------------------------------------------------------
    private void call(final String method, final String path, final JSONObject body, final boolean auth, final Callback cb) {
        pool.execute(new Runnable() {
            @Override
            public void run() {
                Result r = auth ? authed(method, path, body, false) : raw(store.server(), method, path, body, null);
                deliver(r, cb);
            }
        });
    }

    private void deliver(final Result r, final Callback cb) {
        if (r.ok()) lastOkAt = System.currentTimeMillis();
        else lastError = r.error();
        if (cb == null) return;
        main.post(new Runnable() {
            @Override
            public void run() {
                if (r.ok()) cb.ok(r.json == null ? new JSONObject() : r.json);
                else cb.fail(r.error());
            }
        });
    }

    private Result authed(String method, String path, JSONObject body, boolean binary) {
        String token = store.access();
        Result r = token == null ? null : raw(store.server(), method, path, body, token, binary);
        if (r == null || r.status == 401) {
            if (!refresh(token)) {
                final ApiError err = r != null ? r.error() : new ApiError(401, "unauthorized", "not signed in");
                if (r == null || !r.isNetwork()) {
                    store.clear();
                    main.post(new Runnable() {
                        @Override
                        public void run() {
                            if (authListener != null) authListener.onLoggedOut(err);
                        }
                    });
                }
                return r != null ? r : new Result(401, null, "{\"error\":{\"code\":\"unauthorized\",\"message\":\"not signed in\"}}", null);
            }
            r = raw(store.server(), method, path, body, store.access(), binary);
        }
        return r;
    }

    private boolean refresh(String usedAccess) {
        synchronized (refreshLock) {
            String current = store.access();
            if (current != null && !current.equals(usedAccess)) return true; // another thread already refreshed
            String rt = store.refresh();
            if (rt == null) return false;
            JSONObject body = new JSONObject();
            try {
                body.put("refresh_token", rt);
            } catch (Exception ignored) {
                return false;
            }
            Result r = raw(store.server(), "POST", "/auth/refresh", body, null);
            if (r.ok()) {
                store.saveTokens(r.json.optString("access_token"), r.json.optString("refresh_token"));
                return true;
            }
            return r.isNetwork(); // keep the session on network errors
        }
    }

    private Result raw(String server, String method, String path, JSONObject body, String token) {
        return raw(server, method, path, body, token, false);
    }

    private Result raw(String server, String method, String path, JSONObject body, String token, boolean binary) {
        HttpURLConnection c = null;
        try {
            URL url = new URL(server + "/api/v1" + path);
            c = (HttpURLConnection) url.openConnection();
            c.setConnectTimeout(8000);
            c.setReadTimeout(path.startsWith("/ai/") || path.startsWith("/media/demo") || path.startsWith("/system/checks") ? 120000 : 30000);
            try {
                c.setRequestMethod(method);
            } catch (java.net.ProtocolException pe) {
                // Some HttpURLConnection implementations reject PATCH: tunnel it through POST (backend honours the override)
                c.setRequestMethod("POST");
                c.setRequestProperty("X-HTTP-Method-Override", method);
                setMethodPatch(c);
            }
            c.setRequestProperty("Accept", "application/json");
            c.setRequestProperty("User-Agent", "ChatHelperControl/1.0 Android");
            if (token != null) c.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null) {
                byte[] data = body.toString().getBytes(UTF8);
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                c.setFixedLengthStreamingMode(data.length);
                OutputStream os = c.getOutputStream();
                os.write(data);
                os.close();
            }
            int status = c.getResponseCode();
            InputStream is = status >= 400 ? c.getErrorStream() : c.getInputStream();
            byte[] bytes = is == null ? new byte[0] : readAll(is);
            String ctype = c.getContentType();
            if (binary && status < 400) return new Result(status, bytes, null, ctype);
            return new Result(status, null, new String(bytes, UTF8), ctype);
        } catch (Exception e) {
            return new Result(0, null, null, null, e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static void setMethodPatch(HttpURLConnection c) {
        try {
            java.lang.reflect.Field f = HttpURLConnection.class.getDeclaredField("method");
            f.setAccessible(true);
            f.set(c, "PATCH");
        } catch (Exception ignored) {
            // falls back to POST + X-HTTP-Method-Override
        }
    }

    private static byte[] readAll(InputStream is) throws java.io.IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
        is.close();
        return bos.toByteArray();
    }

    static final class Result {
        final int status;
        final byte[] bytes;
        final String text;
        final String contentType;
        final String netError;
        JSONObject json;

        Result(int status, byte[] bytes, String text, String contentType) {
            this(status, bytes, text, contentType, null);
        }

        Result(int status, byte[] bytes, String text, String contentType, String netError) {
            this.status = status;
            this.bytes = bytes;
            this.text = text;
            this.contentType = contentType;
            this.netError = netError;
            if (text != null && status >= 200 && status < 300) {
                try {
                    json = new JSONObject(text);
                } catch (Exception e) {
                    json = new JSONObject();
                }
            }
        }

        boolean ok() { return status >= 200 && status < 300 && (json != null || bytes != null); }

        boolean isNetwork() { return status == 0; }

        ApiError error() {
            if (status == 0) return ApiError.network(netError);
            return ApiError.parse(status, text);
        }
    }
}

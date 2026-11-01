package com.chathelper.control.core;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.Charset;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.UUID;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Stores the server URL and session tokens. Tokens are encrypted with an AES-256-GCM key that lives in the
 * Android Keystore (non-exportable, hardware-backed where available). No Telegram token is ever stored in the app.
 */
public final class SessionStore {
    private static final String PREFS = "chat_helper_session";
    private static final String KEY_ALIAS = "chat_helper_control_tokens";
    private static final Charset UTF8 = Charset.forName("UTF-8");

    private final SharedPreferences prefs;
    private String access;
    private String refresh;

    public SessionStore(Context ctx) {
        prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        access = decrypt(prefs.getString("access", null));
        refresh = decrypt(prefs.getString("refresh", null));
    }

    public String server() { return prefs.getString("server", "http://127.0.0.1:8787"); }

    public void setServer(String url) { prefs.edit().putString("server", url).apply(); }

    public String deviceId() {
        String id = prefs.getString("device_id", null);
        if (id == null) {
            id = "and-" + UUID.randomUUID().toString().substring(0, 18);
            prefs.edit().putString("device_id", id).apply();
        }
        return id;
    }

    public String deviceName() { return (Build.MANUFACTURER + " " + Build.MODEL).trim(); }

    public synchronized String access() { return access; }

    public synchronized String refresh() { return refresh; }

    public synchronized boolean loggedIn() { return refresh != null && !refresh.isEmpty(); }

    public synchronized void saveTokens(String a, String r) {
        access = a;
        refresh = r;
        prefs.edit().putString("access", encrypt(a)).putString("refresh", encrypt(r)).apply();
    }

    public synchronized void clear() {
        access = null;
        refresh = null;
        prefs.edit().remove("access").remove("refresh").remove("me").apply();
    }

    public void saveMe(String json) { prefs.edit().putString("me", json).apply(); }

    public String me() { return prefs.getString("me", null); }

    public String get(String k, String def) { return prefs.getString("ui_" + k, def); }

    public void put(String k, String v) { prefs.edit().putString("ui_" + k, v).apply(); }

    // ---- crypto -----------------------------------------------------------------------------
    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(KEY_ALIAS)) {
            return ((KeyStore.SecretKeyEntry) ks.getEntry(KEY_ALIAS, null)).getSecretKey();
        }
        KeyGenerator kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        kg.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return kg.generateKey();
    }

    static String encrypt(String plain) {
        if (plain == null) return null;
        try {
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, key());
            byte[] iv = c.getIV();
            byte[] ct = c.doFinal(plain.getBytes(UTF8));
            byte[] out = new byte[iv.length + ct.length + 1];
            out[0] = (byte) iv.length;
            System.arraycopy(iv, 0, out, 1, iv.length);
            System.arraycopy(ct, 0, out, 1 + iv.length, ct.length);
            return "k1:" + Base64.encodeToString(out, Base64.NO_WRAP);
        } catch (Exception e) {
            // Keystore unavailable (very old/broken devices): keep the session in memory only.
            return null;
        }
    }

    static String decrypt(String stored) {
        if (stored == null || !stored.startsWith("k1:")) return null;
        try {
            byte[] all = Base64.decode(stored.substring(3), Base64.NO_WRAP);
            int ivLen = all[0];
            byte[] iv = new byte[ivLen];
            System.arraycopy(all, 1, iv, 0, ivLen);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            byte[] pt = c.doFinal(all, 1 + ivLen, all.length - 1 - ivLen);
            return new String(pt, UTF8);
        } catch (Exception e) {
            return null;
        }
    }

    static byte[] random(int n) {
        byte[] b = new byte[n];
        new SecureRandom().nextBytes(b);
        return b;
    }
}

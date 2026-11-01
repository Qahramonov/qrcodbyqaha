package com.chathelper.control;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.chathelper.control.core.ApiError;
import com.chathelper.control.core.Fmt;
import com.chathelper.control.core.L;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

/** Pure logic: formatting, pairing code normalisation, server URL policy, API error parsing. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 34)
public class FmtTest {
    @Test
    public void numbers() {
        assertEquals("0", Fmt.number(0));
        assertEquals("42", Fmt.number(42));
        assertEquals("1.5", Fmt.number(1.5));
        assertEquals("12.3K", Fmt.number(12300));
        assertEquals("2M", Fmt.number(2_000_000));
        assertEquals("$0", Fmt.money(0));
        assertEquals("$0.0012", Fmt.money(0.0012));
        assertEquals("$1.25", Fmt.money(1.25));
        assertEquals("1.5 KB", Fmt.bytes(1536));
    }

    @Test
    public void durations() {
        L.set(L.EN);
        assertEquals("45s", Fmt.duration(45));
        assertEquals("2m", Fmt.duration(125));
        assertEquals("1h 1m", Fmt.duration(3660));
        assertEquals("2d 3h", Fmt.duration(2 * 86400 + 3 * 3600));
        L.set(L.RU);
        assertEquals("1ч 1м", Fmt.duration(3660));
    }

    @Test
    public void pairingCode() {
        assertEquals("ABCD-EFGH", Fmt.pairingCode("abcd efgh"));
        assertEquals("ABCD-EFGH", Fmt.pairingCode("ABCD-EFGH-XYZ"));
        assertEquals("AB", Fmt.pairingCode("a0b1"));  // 0,1,O,I are excluded (ambiguous)
        assertEquals("", Fmt.pairingCode(null));
    }

    @Test
    public void serverUrlPolicy() {
        assertEquals("http://127.0.0.1:8787", Fmt.serverUrl("127.0.0.1:8787/"));
        assertEquals("http://localhost:8787", Fmt.serverUrl("http://localhost:8787"));
        assertEquals("https://my.host:8443", Fmt.serverUrl("https://my.host:8443"));
        assertNull("plain http to a remote host must be refused", Fmt.serverUrl("http://192.168.1.5:8787"));
        assertNull(Fmt.serverUrl("http://evil.example.com"));
        assertNull(Fmt.serverUrl("   "));
    }

    @Test
    public void apiErrors() {
        ApiError e = ApiError.parse(401, "{\"error\":{\"code\":\"token_expired\",\"message\":\"Access token expired\"}}");
        assertEquals("token_expired", e.code);
        assertTrue(e.isAuth());
        assertFalse(e.isNetwork());
        ApiError n = ApiError.network("ConnectException");
        assertTrue(n.isNetwork());
        L.set(L.EN);
        assertTrue(n.human().contains("Termux"));
        ApiError raw = ApiError.parse(502, "Bad gateway");
        assertEquals("http_502", raw.code);
        L.set(L.RU);
        assertTrue(ApiError.parse(429, "{}").human().contains("попыток"));
    }
}

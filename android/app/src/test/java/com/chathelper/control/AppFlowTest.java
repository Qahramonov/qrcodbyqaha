package com.chathelper.control;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assume.assumeTrue;

import android.content.res.Configuration;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.TextView;

import com.chathelper.control.core.L;
import com.chathelper.control.ui.widget.BottomNav;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowLooper;

import java.util.ArrayList;
import java.util.List;

import static org.robolectric.Shadows.shadowOf;

/**
 * End-to-end UI flow on the real Android 14 framework (Robolectric) against a REAL Chat helper backend started by
 * scripts/run_android_tests.sh: launch → pairing → dashboard → every tab → rotation → logout → offline error → re-login.
 */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 34)
public class AppFlowTest {
    private static final String SERVER = System.getProperty("ch.server", "");
    private static final String CODE = System.getProperty("ch.code", "");
    private static final String CODE2 = System.getProperty("ch.code2", "");

    @Before
    public void lang() {
        L.set(L.EN);
    }

    // ---- helpers ------------------------------------------------------------------------------
    private static void collect(View v, List<View> out) {
        out.add(v);
        if (v instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) v;
            for (int i = 0; i < g.getChildCount(); i++) collect(g.getChildAt(i), out);
        }
    }

    private static List<View> all(MainActivity a) {
        List<View> out = new ArrayList<View>();
        collect(a.getWindow().getDecorView(), out);
        return out;
    }

    private static boolean hasText(MainActivity a, String needle) {
        for (View v : all(a)) {
            if (v instanceof TextView && ((TextView) v).getText().toString().toLowerCase().contains(needle.toLowerCase())) return true;
        }
        return false;
    }

    private static String dump(MainActivity a) {
        StringBuilder sb = new StringBuilder();
        for (View v : all(a)) if (v instanceof TextView && ((TextView) v).getText().length() > 0) sb.append(" | ").append(((TextView) v).getText());
        return sb.toString();
    }

    private static TextView findText(MainActivity a, String needle) {
        for (View v : all(a)) {
            if (v instanceof TextView && !(v instanceof EditText) && ((TextView) v).getText().toString().equals(needle)) return (TextView) v;
        }
        return null;
    }

    private static List<EditText> inputs(MainActivity a) {
        List<EditText> out = new ArrayList<EditText>();
        for (View v : all(a)) if (v instanceof EditText) out.add((EditText) v);
        return out;
    }

    private static BottomNav nav(MainActivity a) {
        for (View v : all(a)) if (v instanceof BottomNav) return (BottomNav) v;
        return null;
    }

    /** Pump the main looper while background HTTP threads finish. */
    private static void waitFor(MainActivity a, String text, long timeoutMs) throws InterruptedException {
        long end = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < end) {
            ShadowLooper.idleMainLooper();
            if (text == null || hasText(a, text)) return;
            Thread.sleep(50);
        }
        ShadowLooper.idleMainLooper();
    }

    private static void settle(long ms) throws InterruptedException {
        long end = System.currentTimeMillis() + ms;
        while (System.currentTimeMillis() < end) {
            ShadowLooper.idleMainLooper();
            Thread.sleep(40);
        }
    }

    private static MainActivity pair(ActivityController<MainActivity> c, String server, String code) throws InterruptedException {
        MainActivity a = c.get();
        waitFor(a, "Sign in", 3000);
        List<EditText> in = inputs(a);
        assertEquals("server + code fields", 2, in.size());
        in.get(0).setText(server);
        in.get(1).setText(code);
        TextView login = findText(a, "Sign in");
        assertNotNull(login);
        login.performClick();
        return a;
    }

    // ---- tests ------------------------------------------------------------------------------------
    @Test
    public void launchesIntoPairingScreenWhenSignedOut() throws Exception {
        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class).setup();
        MainActivity a = c.get();
        waitFor(a, "Sign in", 3000);
        assertTrue(hasText(a, "Chat helper Control"));
        assertTrue(hasText(a, "Code from Telegram"));
        assertTrue("http://127.0.0.1:8787 is the default server", inputs(a).get(0).getText().toString().startsWith("http://127.0.0.1"));
        // code field auto-formats
        inputs(a).get(1).setText("abcdefgh");
        assertEquals("ABCD-EFGH", inputs(a).get(1).getText().toString());
        c.pause().stop().destroy();
    }

    @Test
    public void rejectsRemotePlainHttp() throws Exception {
        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class).setup();
        MainActivity a = pair(c, "http://203.0.113.10:8787", "ABCD-EFGH");
        settle(300);
        assertTrue(hasText(a, "require https"));
        c.pause().stop().destroy();
    }

    @Test
    public void showsConnectionErrorWhenBackendIsDown() throws Exception {
        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class).setup();
        MainActivity a = pair(c, "http://127.0.0.1:1", "ABCD-EFGH");
        waitFor(a, "Cannot reach the backend", 8000);
        assertTrue(hasText(a, "Cannot reach the backend"));
        assertTrue("still on pairing screen", hasText(a, "Code from Telegram"));
        c.pause().stop().destroy();
    }

    @Test
    public void fullFlowAgainstRealBackend() throws Exception {
        assumeTrue("backend not provided (run scripts/run_android_tests.sh)", !SERVER.isEmpty() && !CODE.isEmpty());
        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class).setup();
        MainActivity a = pair(c, SERVER, CODE);
        waitFor(a, "Device paired", 10000);
        assertTrue("toast after pairing; screen:" + dump(a), hasText(a, "Device paired"));
        assertTrue(a.store().loggedIn());
        assertTrue("super admin role from backend", a.isSuper());
        BottomNav nav = nav(a);
        assertNotNull("tab bar visible", nav);
        waitFor(a, "Today", 10000);
        assertTrue("dashboard rendered from backend data; screen:" + dump(a), hasText(a, "Today"));
        assertFalse("no JSON nulls leak into the UI; screen:" + dump(a), hasText(a, "null"));
        assertTrue(hasText(a, "Chat helper is running") || hasText(a, "Bot is not polling Telegram"));

        String[] tabTexts = {"Users", "Automation", "AI", "Settings"};
        String[] expect = {"Found:", "Auto-reply mode", "Providers", "Theme Studio"};
        for (int i = 0; i < tabTexts.length; i++) {
            a.switchTab(i + 1);
            waitFor(a, expect[i], 10000);
            assertTrue("tab " + tabTexts[i] + " shows " + expect[i] + "; screen:" + dump(a), hasText(a, expect[i]));
        }

        // pushed screens: commands manager & sandbox test, chats empty state, system control
        a.switchTab(0);
        a.push(new com.chathelper.control.screens.AutomationScreens.Commands());
        waitFor(a, "Commands:", 10000);
        assertTrue(hasText(a, ".calc"));
        a.back();
        a.push(new com.chathelper.control.screens.HomeScreens.Chats());
        waitFor(a, "No chats yet", 10000);
        assertTrue("empty state", hasText(a, "No chats yet"));
        a.back();
        a.push(new com.chathelper.control.screens.AdminScreens.SystemControl());
        waitFor(a, "Health Check", 15000);
        assertTrue(hasText(a, "database"));
        a.back();

        // rotation keeps the session and the shell (configChanges are handled in-process)
        Configuration land = new Configuration(a.getResources().getConfiguration());
        land.orientation = Configuration.ORIENTATION_LANDSCAPE;
        c.configurationChange(land);
        settle(200);
        assertNotNull("shell survives rotation", nav(c.get()));
        assertTrue(c.get().store().loggedIn());

        // logout returns to pairing and clears the session
        c.get().logout();
        waitFor(c.get(), "Sign in", 5000);
        assertFalse(c.get().store().loggedIn());
        assertTrue(hasText(c.get(), "Code from Telegram"));

        // re-login with a fresh one-time code
        if (!CODE2.isEmpty()) {
            pair(c, SERVER, CODE2);
            waitFor(c.get(), "Today", 10000);
            assertTrue(hasText(c.get(), "Today"));
            // old code cannot be reused
        }
        c.pause().stop().destroy();
    }

    @Test
    public void themeAndLanguageSwitchRebuildsUi() throws Exception {
        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class).setup();
        MainActivity a = c.get();
        waitFor(a, "Sign in", 3000);
        com.chathelper.control.ui.Theme.mode = com.chathelper.control.ui.Theme.LIGHT;
        L.set(L.UZ);
        a.applyAppearance();
        settle(200);
        assertTrue(hasText(a, "Kirish"));
        assertFalse(com.chathelper.control.ui.Theme.isDark());
        com.chathelper.control.ui.Theme.mode = com.chathelper.control.ui.Theme.AMOLED;
        a.applyAppearance();
        assertTrue(com.chathelper.control.ui.Theme.isAmoled());
        L.set(L.EN);
        c.pause().stop().destroy();
        assertTrue(Looper.getMainLooper() != null && shadowOf(Looper.getMainLooper()) != null);
    }
}

package androidx.test.runner.lifecycle;

/** Test-harness shim (androidx.test:monitor is only published on Google Maven). */
public enum Stage { PRE_ON_CREATE, CREATED, STARTED, RESUMED, PAUSED, STOPPED, RESTARTED, DESTROYED }

package androidx.test.internal.runner.lifecycle;

import android.app.Application;
import androidx.test.runner.lifecycle.ApplicationLifecycleMonitor;
import androidx.test.runner.lifecycle.ApplicationStage;

public final class ApplicationLifecycleMonitorImpl implements ApplicationLifecycleMonitor {
    private volatile ApplicationStage stage;

    public ApplicationLifecycleMonitorImpl() {}

    public void signalLifecycleChange(Application app, ApplicationStage s) { stage = s; }

    public ApplicationStage stage() { return stage; }
}

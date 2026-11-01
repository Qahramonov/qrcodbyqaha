package androidx.test.internal.runner.lifecycle;

import android.app.Activity;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitor;
import androidx.test.runner.lifecycle.Stage;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;

public final class ActivityLifecycleMonitorImpl implements ActivityLifecycleMonitor {
    private final Map<Activity, Stage> stages = new WeakHashMap<Activity, Stage>();

    public ActivityLifecycleMonitorImpl() {}

    public synchronized void signalLifecycleChange(Stage stage, Activity activity) { stages.put(activity, stage); }

    @Override
    public synchronized Stage getLifecycleStageOf(Activity activity) {
        Stage s = stages.get(activity);
        return s == null ? Stage.PRE_ON_CREATE : s;
    }

    @Override
    public synchronized Collection<Activity> getActivitiesInStage(Stage stage) {
        List<Activity> out = new ArrayList<Activity>();
        for (Map.Entry<Activity, Stage> e : stages.entrySet()) if (e.getValue() == stage) out.add(e.getKey());
        return out;
    }
}

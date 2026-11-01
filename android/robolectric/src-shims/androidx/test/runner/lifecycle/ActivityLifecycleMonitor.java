package androidx.test.runner.lifecycle;

import android.app.Activity;
import java.util.Collection;

public interface ActivityLifecycleMonitor {
    Stage getLifecycleStageOf(Activity activity);

    Collection<Activity> getActivitiesInStage(Stage stage);
}

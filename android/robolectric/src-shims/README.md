# androidx.test shims (test harness only)

Robolectric 4.x references ~20 classes from `androidx.test:monitor` / `espresso-idling-resource`, which are
published only on Google Maven. In environments where Google Maven is unreachable these minimal,
signature-compatible stand-ins let Robolectric boot. They are compiled ONLY into the JVM test classpath and are
never part of the Chat helper Control APK. With normal internet access you can delete this folder and remove the
`<exclusions>` in `pom.xml` to use the official artifacts.

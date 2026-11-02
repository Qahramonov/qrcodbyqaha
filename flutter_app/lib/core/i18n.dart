import 'strings.dart';

const supportedLangs = ['ru', 'uz'];

/// App UI strings in Russian and Uzbek (Latin). Texts that come from the server (status titles, command
/// descriptions, template names …) are already localized by the backend for the account's language.
///
/// Usage: `final t = ref.watch(stringsProvider); Text(t('home.title'))`, placeholders: `t('x', {'n': 3})`.
class T {
  const T(this.lang);

  final String lang;

  String call(String key, [Map<String, Object?> args = const {}]) {
    var s = (lang == 'uz' ? uzStrings[key] : ruStrings[key]) ?? ruStrings[key] ?? key;
    args.forEach((k, v) => s = s.replaceAll('{$k}', '$v'));
    return s;
  }

  bool has(String key) => ruStrings.containsKey(key);
}

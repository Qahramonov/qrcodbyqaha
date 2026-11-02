/// Tolerant JSON helpers: the API is the source of truth, the UI never crashes on a missing or differently typed field.
typedef Json = Map<String, dynamic>;

Json asMap(Object? v) => v is Map ? v.map((k, val) => MapEntry('$k', val)) : <String, dynamic>{};

List<dynamic> asList(Object? v) => v is List ? v : const [];

List<Json> asMaps(Object? v) => asList(v).whereType<Map>().map(asMap).toList();

String str(Object? v, [String fallback = '']) => v == null ? fallback : '$v';

int integer(Object? v, [int fallback = 0]) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? fallback;
}

double number(Object? v, [double fallback = 0]) {
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? fallback;
}

bool flag(Object? v) => v == true || v == 1 || v == '1' || v == 'true';

/// Unix seconds → local "dd.MM.yyyy HH:mm" (no intl dependency needed).
String fmtTime(Object? unixSeconds, {bool withDate = true}) {
  final s = integer(unixSeconds);
  if (s <= 0) return '—';
  final d = DateTime.fromMillisecondsSinceEpoch(s * 1000);
  String two(int x) => x.toString().padLeft(2, '0');
  final time = '${two(d.hour)}:${two(d.minute)}';
  return withDate ? '${two(d.day)}.${two(d.month)}.${d.year} $time' : time;
}

/// Seconds → compact duration like "2h 5m" / "45s" (units are universal symbols).
String fmtDuration(Object? seconds) {
  var s = integer(seconds);
  if (s <= 0) return '0s';
  final d = s ~/ 86400;
  s %= 86400;
  final h = s ~/ 3600;
  s %= 3600;
  final m = s ~/ 60;
  final sec = s % 60;
  final parts = <String>[
    if (d > 0) '${d}d',
    if (h > 0) '${h}h',
    if (m > 0) '${m}m',
    if (d == 0 && h == 0 && sec > 0) '${sec}s',
  ];
  return parts.take(2).join(' ');
}

/// Strips HTML tags the bot uses for Telegram formatting (b, i, code, a …) for plain display.
String stripHtml(String html) => html
    .replaceAll(RegExp(r'<br\s*/?>'), '\n')
    .replaceAll(RegExp(r'<[^>]+>'), '')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&#x27;', "'")
    .replaceAll('&amp;', '&');

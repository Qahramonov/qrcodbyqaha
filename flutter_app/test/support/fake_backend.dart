import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:chat_helper_control/app.dart';
import 'package:chat_helper_control/core/api.dart';
import 'package:chat_helper_control/core/json.dart';
import 'package:chat_helper_control/core/session.dart';
import 'package:chat_helper_control/core/storage.dart';
import 'package:chat_helper_control/router.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Real responses of the Chat helper backend, recorded by tests/backend/record_api_samples.py.
final Map<String, dynamic> _samples = asMap(jsonDecode(File('test/fixtures/api_samples.json').readAsStringSync()));

class Recorded {
  Recorded(this.method, this.path, this.query, this.body);

  final String method;
  final String path;
  final Map<String, dynamic> query;
  final Object? body;

  @override
  String toString() => '$method $path $query $body';
}

/// Dio adapter answering from the recorded samples (by role) — no network involved.
class FakeBackend implements HttpClientAdapter {
  FakeBackend(this.role, {this.lang = 'ru', this.connected = true})
      : samples = {...asMap(_samples[role]), if (lang == 'uz') ...asMap(_samples['${role}_uz'])} {
    final me = _deepCopy(asMap(asMap(samples['GET /auth/me'])['body']));
    (me['settings'] as Map)['lang'] = lang;
    if (!connected) me['connections'] = <dynamic>[];
    samples['GET /auth/me'] = {'status': 200, 'body': me};
    final pair = _deepCopy(asMap(samples['POST /auth/pair']));
    pair['me'] = me;
    samples['POST /auth/pair'] = pair;
    if (!connected) {
      final ob = _deepCopy(asMap(asMap(samples['GET /onboarding'])['body']));
      ob['connected'] = false;
      samples['GET /onboarding'] = {'status': 200, 'body': ob};
    }
  }

  final String role;
  final String lang;
  final bool connected;
  final Map<String, dynamic> samples;
  final List<Recorded> requests = [];

  /// Extra answers: "METHOD /path" → (status, body).
  final Map<String, (int, Object)> overrides = {};

  static Json _deepCopy(Json m) => asMap(jsonDecode(jsonEncode(m)));

  static final _ids = <RegExp, String>{
    RegExp(r'^/chats/-?\d+$'): '/chats/{chat_id}',
    RegExp(r'^/chats/-?\d+/controls$'): '/chats/{chat_id}/controls',
    RegExp(r'^/users/\d+$'): '/users/{uid}',
    RegExp(r'^/connections/[^/]+/inspector$'): '/connections/{conn_id}/inspector',
  };

  List<String> _candidates(String method, Uri uri) {
    final path = uri.path.replaceFirst('/api/v1', '');
    final out = <String>[];
    if (uri.query.isNotEmpty) out.add('$method $path?${uri.query}');
    final keep = Map.of(uri.queryParameters)..removeWhere((k, _) => k != 'scope' && k != 'all');
    if (keep.isNotEmpty && keep['scope'] != 'self') {
      out.add('$method $path?${keep.entries.map((e) => '${e.key}=${e.value}').join('&')}');
    }
    out.add('$method $path');
    for (final e in _ids.entries) {
      if (e.key.hasMatch(path)) out.add('$method ${e.value}');
    }
    return out;
  }

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    final method = o.method.toUpperCase();
    final uri = o.uri;
    requests.add(Recorded(method, uri.path.replaceFirst('/api/v1', ''), uri.queryParameters, o.data));
    for (final key in _candidates(method, uri)) {
      final ov = overrides[key];
      if (ov != null) return _json(ov.$1, ov.$2);
    }
    for (final key in _candidates(method, uri)) {
      final hit = samples[key];
      if (hit is Map) {
        final m = asMap(hit);
        if (m.containsKey('status') && m.containsKey('body')) return _json(integer(m['status']), m['body'] as Object);
        return _json(200, m);
      }
    }
    if (method == 'GET') {
      return _json(404, {
        'error': {'code': 'not_found', 'message': 'Not found'}
      });
    }
    return _json(200, {'ok': true});
  }

  ResponseBody _json(int status, Object body) =>
      ResponseBody.fromString(jsonEncode(body), status, headers: {
        Headers.contentTypeHeader: ['application/json; charset=utf-8'],
      });

  Iterable<Recorded> sent(String method, String path) => requests.where((r) => r.method == method && r.path == path);

  @override
  void close({bool force = false}) {}
}

class TestApp {
  TestApp(this.backend, this.store, this.container);

  final FakeBackend backend;
  final MemoryStore store;
  final ProviderContainer container;

  void go(String location) => container.read(routerProvider).go(location);

  /// Location of the top-most route (pushed routes included).
  String get location => container.read(routerProvider).state.uri.toString();
}

/// Lets futures resolve and frames render without waiting for endless animations (spinners).
Future<void> settle(WidgetTester tester, [int frames = 12]) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

Future<TestApp> pumpApp(WidgetTester tester,
    {String role = 'user', String lang = 'ru', bool paired = true, bool connected = true, String? location}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.75;
  addTearDown(tester.view.reset);
  final backend = FakeBackend(role, lang: lang, connected: connected);
  final store = MemoryStore({
    'lang': lang,
    if (paired) ...{'server': 'http://127.0.0.1:8787', 'access': 'test-access', 'refresh': 'test-refresh'},
  });
  final api = ApiClient(store: store, adapter: backend);
  api.dio.options
    ..connectTimeout = null
    ..receiveTimeout = null
    ..sendTimeout = null;
  // decode on the test isolate (Dio decodes large bodies in a background isolate, which fake test time never waits for)
  api.dio.transformer = SyncTransformer();
  await tester.pumpWidget(ProviderScope(
    retry: (_, _) => null,
    overrides: [storeProvider.overrideWithValue(store), apiProvider.overrideWithValue(api)],
    child: const ChatHelperApp(),
  ));
  await settle(tester);
  final container = ProviderScope.containerOf(tester.element(find.byType(ChatHelperApp)));
  final app = TestApp(backend, store, container);
  if (location != null) {
    app.go(location);
    await settle(tester);
  }
  return app;
}

/// All texts currently rendered (Text, RichText via EditableText excluded).
List<String> renderedTexts(WidgetTester tester) => tester
    .widgetList<Text>(find.byType(Text))
    .map((t) => t.data ?? t.textSpan?.toPlainText() ?? '')
    .where((s) => s.isNotEmpty)
    .toList();

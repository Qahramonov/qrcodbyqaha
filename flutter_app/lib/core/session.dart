import 'dart:async';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api.dart';
import 'config.dart';
import 'i18n.dart';
import 'json.dart';
import 'storage.dart';

enum SessionStatus { loading, offline, unpaired, ready }

/// What the app knows about the paired account. Everything role-related comes from the server (`/auth/me`);
/// the app never decides on its own that someone is an administrator.
class SessionState {
  const SessionState(this.status, {this.me = const {}, this.error});

  final SessionStatus status;
  final Json me;
  final ApiException? error;

  String get role => str(me['role'], 'user');
  bool get isSuper => role == 'super_admin';
  bool get connected => asMaps(me['connections']).any((c) => flag(c['is_enabled']));
  Json get settings => asMap(me['settings']);
  Json get user => asMap(me['user']);
  String get plan => str(me['plan'], 'free');
  List<String> get capabilities => asList(me['capabilities']).map((e) => '$e').toList();

  String? get lang {
    final l = str(settings['lang']);
    return supportedLangs.contains(l) ? l : null;
  }
}

final storeProvider = Provider<KeyValueStore>((ref) => SecureStore());

final apiProvider = Provider<ApiClient>((ref) => ApiClient(store: ref.watch(storeProvider)));

final sessionProvider = NotifierProvider<SessionController, SessionState>(SessionController.new);

/// Language chosen before pairing (stored locally); after pairing the account setting wins.
final localLangProvider = NotifierProvider<LocalLang, String>(LocalLang.new);

final stringsProvider = Provider<T>((ref) {
  final session = ref.watch(sessionProvider);
  return T(session.lang ?? ref.watch(localLangProvider));
});

/// Generic GET of an API path (may contain a query string), e.g. `ref.watch(jsonProvider('/chats?page=2'))`.
final jsonProvider = FutureProvider.autoDispose.family<Json, String>((ref, path) {
  final uri = Uri.parse(path);
  return ref.watch(apiProvider).get(uri.path, query: uri.queryParameters.isEmpty ? null : uri.queryParameters);
});

class LocalLang extends Notifier<String> {
  @override
  String build() {
    unawaited(_load());
    return 'ru';
  }

  Future<void> _load() async {
    final v = await ref.read(storeProvider).read('lang');
    if (v != null && supportedLangs.contains(v) && ref.mounted) state = v;
  }

  Future<void> set(String lang) async {
    state = lang;
    await ref.read(storeProvider).write('lang', lang);
  }
}

class SessionController extends Notifier<SessionState> {
  @override
  SessionState build() {
    ref.read(apiProvider).onSessionExpired = () {
      if (ref.mounted) state = const SessionState(SessionStatus.unpaired);
    };
    unawaited(Future.microtask(start));
    return const SessionState(SessionStatus.loading);
  }

  ApiClient get _api => ref.read(apiProvider);

  Future<void> start() async {
    await _api.load();
    if (!_api.hasSession) {
      state = const SessionState(SessionStatus.unpaired);
      return;
    }
    await refresh();
  }

  /// Reloads `/auth/me` (role, plan, connections, settings).
  Future<void> refresh() async {
    try {
      final me = await _api.get('/auth/me');
      if (ref.mounted) state = SessionState(SessionStatus.ready, me: me);
    } on ApiException catch (e) {
      if (!ref.mounted) return;
      if (e.isUnauthorized) {
        await _api.clearSession();
        state = const SessionState(SessionStatus.unpaired);
      } else {
        state = SessionState(SessionStatus.offline, me: state.me, error: e);
      }
    }
  }

  /// One-time code from the bot (`/app`) → session tokens stored in the Android Keystore.
  Future<void> pair(String server, String code) async {
    await _api.setServer(server);
    final store = ref.read(storeProvider);
    var device = await store.read('device_id');
    if (device == null) {
      final rnd = Random.secure();
      device = List.generate(16, (_) => rnd.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
      await store.write('device_id', device);
    }
    final res = await _api.post('/auth/pair', {
      'code': code.trim(),
      'device_id': device,
      'device_name': 'Android · ${AppInfo.name}',
      'platform': 'android',
      'app_version': AppInfo.version,
    });
    await _api.saveTokens(res);
    state = SessionState(SessionStatus.ready, me: asMap(res['me']));
  }

  Future<void> logout() async {
    try {
      await _api.post('/auth/logout');
    } on ApiException {
      // the server may be offline — the local session is removed anyway
    }
    await _api.clearSession();
    state = const SessionState(SessionStatus.unpaired);
  }

  Future<void> setLang(String lang) async {
    await ref.read(localLangProvider.notifier).set(lang);
    if (state.status == SessionStatus.ready) {
      await _api.patch('/settings', {
        'values': {'lang': lang}
      });
      await refresh();
    }
  }
}

import 'dart:async';

import 'package:dio/dio.dart';

import 'config.dart';
import 'json.dart';
import 'storage.dart';

/// Error returned by the Chat helper API (`{"error": {"code", "message"}}`) or a network failure (status == null).
class ApiException implements Exception {
  ApiException(this.status, this.code, this.message, {this.retryAfter});

  final int? status;
  final String code;
  final String message;
  final int? retryAfter;

  bool get isNetwork => status == null;
  bool get isUnauthorized => status == 401;
  bool get isNotFound => status == 404;

  @override
  String toString() => 'ApiException($status, $code, $message)';
}

/// Thin REST client for `/api/v1`: bearer tokens, single-flight token refresh on 401, uniform errors.
class ApiClient {
  ApiClient({required this.store, HttpClientAdapter? adapter})
      : dio = Dio(BaseOptions(
          connectTimeout: const Duration(seconds: 8),
          receiveTimeout: const Duration(seconds: 60),
          sendTimeout: const Duration(seconds: 30),
          responseType: ResponseType.json,
          headers: {'Accept': 'application/json'},
        )) {
    if (adapter != null) dio.httpClientAdapter = adapter;
  }

  final KeyValueStore store;
  final Dio dio;
  String? baseUrl;
  String? _access;
  String? _refresh;
  Completer<bool>? _refreshing;

  /// Called when the refresh token is rejected: the session is over and the app must pair again.
  void Function()? onSessionExpired;

  bool get hasSession => baseUrl != null && _refresh != null;

  Future<void> load() async {
    baseUrl = await store.read('server');
    _access = await store.read('access');
    _refresh = await store.read('refresh');
  }

  Future<void> setServer(String url) async {
    baseUrl = normalizeServer(url);
    await store.write('server', baseUrl);
  }

  Future<void> saveTokens(Json pair) async {
    _access = str(pair['access_token']);
    _refresh = str(pair['refresh_token']);
    await store.write('access', _access);
    await store.write('refresh', _refresh);
  }

  Future<void> clearSession() async {
    _access = null;
    _refresh = null;
    await store.write('access', null);
    await store.write('refresh', null);
  }

  Future<Json> get(String path, {Map<String, dynamic>? query}) => send('GET', path, query: query);
  Future<Json> post(String path, [Object? body]) => send('POST', path, body: body ?? const <String, dynamic>{});
  Future<Json> put(String path, [Object? body]) => send('PUT', path, body: body ?? const <String, dynamic>{});
  Future<Json> patch(String path, [Object? body]) => send('PATCH', path, body: body ?? const <String, dynamic>{});
  Future<Json> delete(String path) => send('DELETE', path);

  Future<Json> send(String method, String path, {Object? body, Map<String, dynamic>? query, bool retried = false}) async {
    final base = baseUrl;
    if (base == null) throw ApiException(null, 'no_server', 'Server is not configured');
    try {
      final r = await dio.request<dynamic>(
        '$base/api/v1$path',
        data: body,
        queryParameters: query,
        options: Options(method: method, headers: {if (_access != null) 'Authorization': 'Bearer $_access'}),
      );
      final data = r.data;
      return data is Map ? asMap(data) : <String, dynamic>{'data': data};
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      if (status == 401 && !retried && _refresh != null && !path.startsWith('/auth/pair') && !path.startsWith('/auth/refresh')) {
        if (await _refreshTokens()) return send(method, path, body: body, query: query, retried: true);
        await clearSession();
        onSessionExpired?.call();
      }
      throw _toApiException(e);
    }
  }

  Future<bool> _refreshTokens() async {
    final pending = _refreshing;
    if (pending != null) return pending.future;
    final c = Completer<bool>();
    _refreshing = c;
    try {
      final r = await dio.post<dynamic>('$baseUrl/api/v1/auth/refresh', data: {'refresh_token': _refresh});
      await saveTokens(asMap(r.data));
      c.complete(true);
    } on DioException {
      c.complete(false);
    } finally {
      _refreshing = null;
    }
    return c.future;
  }

  static ApiException _toApiException(DioException e) {
    final r = e.response;
    if (r == null) return ApiException(null, 'network', e.message ?? 'Network error');
    final err = asMap(asMap(r.data)['error']);
    final retry = int.tryParse(r.headers.value('retry-after') ?? '');
    return ApiException(r.statusCode, str(err['code'], 'http_${r.statusCode}'), str(err['message'], r.statusMessage ?? ''),
        retryAfter: retry);
  }
}

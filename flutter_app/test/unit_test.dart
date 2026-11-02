import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:chat_helper_control/core/api.dart';
import 'package:chat_helper_control/core/config.dart';
import 'package:chat_helper_control/core/i18n.dart';
import 'package:chat_helper_control/core/json.dart';
import 'package:chat_helper_control/core/storage.dart';
import 'package:chat_helper_control/core/strings.dart';
import 'package:chat_helper_control/core/theme.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Scripted adapter: answers requests in order.
class Scripted implements HttpClientAdapter {
  Scripted(this.answers);

  final List<(int, Object)> answers;
  final List<RequestOptions> seen = [];

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? s, Future<void>? c) async {
    seen.add(o);
    final (status, body) = answers.removeAt(0);
    return ResponseBody.fromString(jsonEncode(body), status, headers: {
      Headers.contentTypeHeader: ['application/json']
    });
  }

  @override
  void close({bool force = false}) {}
}

final cyrillic = RegExp('[А-Яа-яЁё]');

void main() {
  group('server address', () {
    test('normalizes input', () {
      expect(normalizeServer('127.0.0.1:8787'), 'http://127.0.0.1:8787');
      expect(normalizeServer('http://127.0.0.1:8787/api/v1/'), 'http://127.0.0.1:8787');
      expect(normalizeServer('bot.example.com'), 'https://bot.example.com');
      expect(normalizeServer(' https://x.example/ '), 'https://x.example');
    });

    test('plain http only for this phone (Termux) or the emulator host', () {
      expect(validateServer('http://127.0.0.1:8787'), isNull);
      expect(validateServer('http://localhost:8787'), isNull);
      expect(validateServer('http://10.0.2.2:8787'), isNull);
      expect(validateServer('https://bot.example.com'), isNull);
      expect(validateServer('http://192.168.1.5:8787'), 'pair.err_https');
      expect(validateServer('http://bot.example.com'), 'pair.err_https');
      expect(validateServer('ftp://x'), 'pair.err_url');
      expect(validateServer('nonsense'), 'pair.err_url');
    });
  });

  group('API client', () {
    Future<ApiClient> client(Scripted adapter) async {
      final store = MemoryStore({'server': 'http://127.0.0.1:8787', 'access': 'old', 'refresh': 'refresh-token-1'});
      final api = ApiClient(store: store, adapter: adapter);
      await api.load();
      return api;
    }

    test('refreshes the access token once on 401 and retries the request', () async {
      final adapter = Scripted([
        (401, {'error': {'code': 'token_expired', 'message': 'expired'}}),
        (200, {'access_token': 'new', 'refresh_token': 'refresh-token-2'}),
        (200, {'ok': true}),
      ]);
      final api = await client(adapter);
      expect(await api.get('/dashboard'), {'ok': true});
      expect(adapter.seen.map((o) => o.uri.path), ['/api/v1/dashboard', '/api/v1/auth/refresh', '/api/v1/dashboard']);
      expect(adapter.seen.last.headers['Authorization'], 'Bearer new');
      expect(await api.store.read('refresh'), 'refresh-token-2');
    });

    test('a rejected refresh ends the session', () async {
      var expired = false;
      final adapter = Scripted([
        (401, {'error': {'code': 'token_expired', 'message': 'expired'}}),
        (401, {'error': {'code': 'invalid_refresh', 'message': 'bad'}}),
      ]);
      final api = await client(adapter)
        ..onSessionExpired = () => expired = true;
      await expectLater(api.get('/dashboard'), throwsA(isA<ApiException>().having((e) => e.status, 'status', 401)));
      expect(expired, isTrue);
      expect(api.hasSession, isFalse);
      expect(await api.store.read('access'), isNull);
    });

    test('maps the uniform error body', () async {
      final api = await client(Scripted([
        (404, {'error': {'code': 'not_found', 'message': 'Not found'}}),
      ]));
      await expectLater(
          api.get('/users'),
          throwsA(isA<ApiException>()
              .having((e) => e.status, 'status', 404)
              .having((e) => e.code, 'code', 'not_found')
              .having((e) => e.isNotFound, 'isNotFound', isTrue)));
    });
  });

  group('localization', () {
    test('Russian and Uzbek have exactly the same keys', () {
      expect(uzStrings.keys.toSet().difference(ruStrings.keys.toSet()), isEmpty);
      expect(ruStrings.keys.toSet().difference(uzStrings.keys.toSet()), isEmpty);
    });

    test('placeholders match between languages', () {
      final ph = RegExp(r'\{(\w+)\}');
      for (final k in ruStrings.keys) {
        final a = ph.allMatches(ruStrings[k]!).map((m) => m[1]).toSet();
        final b = ph.allMatches(uzStrings[k]!).map((m) => m[1]).toSet();
        expect(b, a, reason: k);
      }
    });

    test('Uzbek texts are Latin script', () {
      const allowed = {'auto.keywords_hint'}; // example keywords include a Russian word users may receive
      for (final e in uzStrings.entries) {
        if (!allowed.contains(e.key)) expect(cyrillic.hasMatch(e.value), isFalse, reason: e.key);
      }
    });

    test('every key used in the code exists', () {
      final used = <String>{};
      final call = RegExp(r"""\bt\(\s*'([^'$]+)'""");
      final routeKey = RegExp(r"""'((?:nav|admin)\.[a-z_]+)'""");
      for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'))) {
        final src = f.readAsStringSync();
        used.addAll(call.allMatches(src).map((m) => m[1]!));
        used.addAll(routeKey.allMatches(src).map((m) => m[1]!));
      }
      used.removeAll({'x', 'home.title'}); // doc-comment examples in i18n.dart
      expect(used.length, greaterThan(400));
      expect(used.where((k) => !ruStrings.containsKey(k)).toList(), isEmpty);
    });

    test('dynamic keys built at runtime exist', () {
      const families = {
        'right': ['can_reply', 'can_read_messages', 'can_delete_sent_messages', 'can_delete_all_messages', 'can_edit_name', 'can_edit_bio',
          'can_edit_profile_photo', 'can_edit_username', 'can_change_gift_settings', 'can_view_gifts_and_stars',
          'can_convert_gifts_to_stars', 'can_transfer_and_upgrade_gifts', 'can_transfer_stars', 'can_manage_stories'],
        'wizard.step': ['copy_username', 'open_settings', 'chat_automation', 'add_bot', 'choose_chats', 'grant_rights', 'check'],
        'controls': ['mute', 'protect', 'nogif', 'nomute', 'mute_hint', 'protect_hint', 'nogif_hint', 'nomute_hint',
          'autoreply_enabled', 'ai_enabled', 'afk_enabled', 'for_600s', 'for_3600s', 'for_86400s'],
        'ai.style': ['friendly', 'professional', 'funny', 'smart', 'short', 'creative', 'custom'],
        'twin.mode': ['auto', 'manual', 'draft', 'disabled'],
        'twin.length': ['short', 'medium', 'long'],
        'twin.persona': ['neutral', 'male', 'female'],
        'twin': ['formality', 'humor', 'emoji', 'slang'],
        'mute.type': ['all', 'text', 'media', 'photo', 'video', 'voice', 'circle', 'gif', 'sticker', 'document', 'audio'],
        'anim.speed': ['slow', 'normal', 'fast', 'turbo'],
        'afk.kind': ['afk', 'sleep'],
        'cat': ['afk', 'ai', 'voice', 'media', 'games', 'text', 'profile', 'autoreply', 'chat', 'system'],
        'cmd.where': ['any', 'business', 'private'],
        'auto.trigger': ['ai_class', 'contact', 'keyword', 'media', 'message', 'new_chat', 'no_reply', 'time'],
        'auto.action': ['reply', 'reply_template', 'ai_reply', 'set_mode', 'afk_on', 'afk_off', 'notify', 'tag', 'timer', 'remind', 'handoff',
          'mark_read', 'set_priority'],
        'auto.match': ['contains', 'word', 'exact'],
        'auto.label': ['urgent', 'question', 'order', 'complaint', 'greeting', 'spam', 'other'],
        'rem.status': ['pending', 'done', 'failed', 'cancelled'],
        'stat': ['messages_in', 'messages_out', 'auto_replies', 'ai_requests', 'commands', 'media_jobs', 'games_played', 'errors',
          'revenue_stars', 'connections_new'],
        'limit': ['ai_requests_day', 'media_jobs_day', 'autoreply_rules', 'automation_rules', 'custom_commands', 'stt_minutes_day'],
        'set': ['delete_commands', 'automation_paused', 'notify_important', 'notify_new_chats', 'notify_disconnect', 'chat_activity',
          'store_previews', 'delete_commands_hint', 'automation_paused_hint', 'notify_important_hint', 'notify_new_chats_hint',
          'notify_disconnect_hint', 'chat_activity_hint', 'store_previews_hint', 'controls_place.chat', 'controls_place.dm', 'place.chat', 'place.dm'],
        'admin.media': ['max_input_mb', 'max_duration', 'max_reverse_video', 'timeout'],
        'cmd': ['test_not_a_command', 'test_unknown_command', 'test_not_sandbox_safe', 'test_failed'],
        'ai': ['draft_send', 'draft_alt', 'draft_rej', 'draft_btn_send', 'draft_btn_alt', 'draft_btn_rej'],
      };
      final missing = [
        for (final e in families.entries)
          for (final s in e.value)
            if (!ruStrings.containsKey('${e.key}.$s')) '${e.key}.$s',
      ];
      expect(missing, isEmpty);
    });

    test('T falls back to Russian, then to the key; placeholders are filled', () {
      expect(const T('uz')('common.save'), 'Saqlash');
      expect(const T('ru')('common.save'), 'Сохранить');
      expect(const T('xx')('common.save'), 'Сохранить');
      expect(const T('ru')('no.such.key'), 'no.such.key');
      expect(const T('ru')('home.hello', {'name': 'Kamron'}), 'Привет, Kamron!');
    });
  });

  test('theme constants match design/tokens.json', () {
    final tokens = asMap(jsonDecode(File('design/tokens.json').readAsStringSync()));
    final color = asMap(tokens['color']);
    Color hex(String s) => Color(int.parse(s.length == 7 ? 'FF${s.substring(1)}' : s.substring(1), radix: 16));
    final expected = {
      Tokens.bgTop: asMap(color['bg'])['top'],
      Tokens.bgBottom: asMap(color['bg'])['bottom'],
      Tokens.bgElevated: asMap(color['bg'])['elevated'],
      Tokens.blue: asMap(color['accent'])['blue'],
      Tokens.violet: asMap(color['accent'])['violet'],
      Tokens.cyan: asMap(color['accent'])['cyan'],
      Tokens.textPrimary: asMap(color['text'])['primary'],
      Tokens.textSecondary: asMap(color['text'])['secondary'],
      Tokens.textMuted: asMap(color['text'])['muted'],
      Tokens.glassFill: asMap(color['glass'])['fill'],
      Tokens.glassBorder: asMap(color['glass'])['border'],
      Tokens.glassHighlight: asMap(color['glass'])['highlight'],
      Tokens.success: asMap(color['status'])['success'],
      Tokens.warning: asMap(color['status'])['warning'],
      Tokens.danger: asMap(color['status'])['danger'],
      Tokens.info: asMap(color['status'])['info'],
    };
    expected.forEach((c, v) { final s = v as String; expect(c, hex(s), reason: s); });
    final radius = asMap(tokens['radius']);
    expect([Tokens.rSm, Tokens.rMd, Tokens.rLg, Tokens.rPill], [radius['sm'], radius['md'], radius['lg'], radius['pill']].map(number).toList());
    final font = asMap(tokens['font']);
    expect(Tokens.fontFamily, font['family']);
    expect([Tokens.display, Tokens.title, Tokens.subtitle, Tokens.body, Tokens.caption],
        ['display', 'title', 'subtitle', 'body', 'caption'].map((k) => number(asMap(font[k])['size'])).toList());
    expect(Tokens.glassBlur, number(asMap(tokens['blur'])['glass']));
  });

  test('json helpers are tolerant', () {
    expect(integer('12'), 12);
    expect(integer(null, 5), 5);
    expect(flag(1), isTrue);
    expect(flag('true'), isTrue);
    expect(flag(0), isFalse);
    expect(asMaps([{'a': 1}, 3, null]).length, 1);
    expect(stripHtml('<b>A</b> &amp; <i>B</i>'), 'A & B');
    expect(fmtDuration(3660), '1h 1m');
    expect(fmtDuration(0), '0s');
  });
}

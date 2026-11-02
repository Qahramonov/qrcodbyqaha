import 'package:chat_helper_control/core/session.dart';
import 'package:chat_helper_control/router.dart';
import 'package:flutter_test/flutter_test.dart';

SessionState ready({String role = 'user', bool connected = true, Map<String, dynamic> extra = const {}}) => SessionState(
      SessionStatus.ready,
      me: {
        'role': role,
        'connections': [
          if (connected) {'id': 'bc', 'is_enabled': true, 'status': 'connected'},
        ],
        'settings': {'lang': 'ru'},
        ...extra,
      },
    );

void main() {
  group('admin section exists only for the super admin', () {
    final adminPaths = ['/admin', '/admin/users', '/admin/users/42', '/admin/system', '/admin/logs', '/admin/broadcast', '/admin/security'];

    test('a regular user is sent home from every admin route', () {
      for (final p in adminPaths) {
        expect(guard(ready(), p), '/home', reason: p);
      }
    });

    test('a not-yet-connected user cannot reach admin routes either', () {
      for (final p in adminPaths) {
        expect(guard(ready(connected: false), p), '/home', reason: p);
      }
    });

    test('client-side fields cannot fake the role', () {
      final forged = ready(extra: {'is_super_admin': true, 'capabilities': ['users', 'system'], 'user': {'id': 8053614984}});
      expect(forged.isSuper, isFalse);
      for (final p in adminPaths) {
        expect(guard(forged, p), '/home', reason: p);
      }
      expect(guard(ready(role: 'moderator'), '/admin'), '/home');
      expect(guard(ready(role: 'admin'), '/admin'), '/home');
    });

    test('the super admin (role reported by the server) opens them', () {
      for (final p in adminPaths) {
        expect(guard(ready(role: 'super_admin'), p), isNull, reason: p);
      }
      expect(guard(ready(role: 'super_admin', connected: false), '/admin'), isNull);
    });
  });

  group('session states', () {
    test('loading shows the splash, offline the offline screen', () {
      expect(guard(const SessionState(SessionStatus.loading), '/home'), '/splash');
      expect(guard(const SessionState(SessionStatus.loading), '/splash'), isNull);
      expect(guard(const SessionState(SessionStatus.offline), '/chats'), '/offline');
    });

    test('unpaired: only welcome, pairing and language', () {
      const s = SessionState(SessionStatus.unpaired);
      expect(guard(s, '/welcome'), isNull);
      expect(guard(s, '/pair'), isNull);
      expect(guard(s, '/language'), isNull);
      expect(guard(s, '/home'), '/welcome');
      expect(guard(s, '/admin'), '/welcome');
    });

    test('paired users leave the onboarding screens', () {
      for (final p in ['/splash', '/welcome', '/pair', '/offline', '/']) {
        expect(guard(ready(), p), '/home', reason: p);
      }
    });

    test('features stay locked until the Telegram account is connected', () {
      final s = ready(connected: false);
      for (final p in ['/home', '/chats', '/chats/5', '/mute', '/ai', '/commands', '/automation']) {
        expect(guard(s, p), '/wizard', reason: p);
      }
      for (final p in preConnectRoutes) {
        expect(guard(s, p), isNull, reason: p);
      }
      expect(guard(ready(), '/chats/5'), isNull);
    });
  });

  test('every user hub route and admin route is registered', () {
    final paths = appRoutes.map((r) => (r as dynamic).path as String).toSet();
    expect(paths.length, greaterThanOrEqualTo(40));
    expect(paths.where((p) => p.startsWith('/admin')).length, greaterThanOrEqualTo(15));
  });
}

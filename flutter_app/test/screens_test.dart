import 'package:chat_helper_control/core/strings.dart';
import 'package:chat_helper_control/core/widgets.dart';
import 'package:chat_helper_control/features/home.dart';
import 'package:chat_helper_control/features/tools.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_backend.dart';

const userRoutes = {
  '/home': 'Chat helper',
  '/chats': 'nav.chats',
  '/chats/5550000001': 'controls.title',
  '/permissions': 'nav.permissions',
  '/ai': 'nav.ai',
  '/ai/twin': 'nav.twin',
  '/ai/playground': 'nav.playground',
  '/afk': 'nav.afk',
  '/mute': 'nav.mute',
  '/protect': 'nav.protect',
  '/animations': 'nav.animations',
  '/media': 'nav.media',
  '/games': 'nav.games',
  '/commands': 'nav.commands',
  '/reminders': 'nav.reminders',
  '/automation': 'nav.automation',
  '/profile': 'nav.profile',
  '/stats': 'nav.stats',
  '/subscription': 'nav.subscription',
  '/language': 'nav.language',
  '/settings': 'nav.settings',
  '/wizard': 'wizard.title',
};

const adminRoutes = {
  '/admin': 'Super Admin',
  '/admin/users': 'admin.users',
  '/admin/users/4200000001': 'admin.user',
  '/admin/connections': 'admin.connections',
  '/admin/permissions': 'admin.permissions',
  '/admin/ai': 'admin.ai',
  '/admin/media': 'admin.media',
  '/admin/games': 'admin.games',
  '/admin/commands': 'admin.commands',
  '/admin/payments': 'admin.payments',
  '/admin/analytics': 'admin.analytics',
  '/admin/broadcast': 'admin.broadcast',
  '/admin/security': 'admin.security',
  '/admin/system': 'admin.system',
  '/admin/logs': 'admin.logs',
  '/admin/diagnostics': 'admin.diagnostics',
};

String title(String key, String lang) => (lang == 'uz' ? uzStrings[key] : ruStrings[key]) ?? key;

Future<void> expectScreen(WidgetTester tester, TestApp app, String route, String titleKey, String lang) async {
  app.go(route);
  await settle(tester);
  expect(tester.takeException(), isNull, reason: route);
  expect(app.location, route, reason: 'redirected away from $route');
  expect(find.descendant(of: find.byType(AppBar), matching: find.text(title(titleKey, lang))), findsOneWidget, reason: route);
  expect(find.byKey(const Key('error-text')), findsNothing, reason: 'error state on $route');
  expect(find.byType(LoadingView), findsNothing, reason: 'still loading on $route');
}

void main() {
  for (final lang in ['ru', 'uz']) {
    testWidgets('every user screen renders with real API data ($lang)', (tester) async {
      final app = await pumpApp(tester, lang: lang);
      for (final e in userRoutes.entries) {
        await expectScreen(tester, app, e.key, e.value, lang);
      }
    });

    testWidgets('every Super Admin screen renders for the super admin ($lang)', (tester) async {
      final app = await pumpApp(tester, role: 'admin', lang: lang);
      for (final e in adminRoutes.entries) {
        await expectScreen(tester, app, e.key, e.value, lang);
      }
    });
  }

  testWidgets('Uzbek UI shows no Russian app strings', (tester) async {
    final app = await pumpApp(tester, role: 'admin', lang: 'uz');
    final ruOnly = {for (final k in ruStrings.keys) if (ruStrings[k] != uzStrings[k]) ruStrings[k]!};
    for (final route in [...userRoutes.keys, ...adminRoutes.keys]) {
      app.go(route);
      await settle(tester);
      final leaked = renderedTexts(tester).where(ruOnly.contains).toList();
      expect(leaked, isEmpty, reason: route);
    }
  });

  group('admin section is invisible to everyone else', () {
    testWidgets('no Super Admin tile for a regular user and /admin routes bounce home', (tester) async {
      final app = await pumpApp(tester, location: '/home');
      expect(find.byKey(const Key('hub-/admin')), findsNothing);
      expect(find.text('Super Admin'), findsNothing);
      for (final route in adminRoutes.keys) {
        app.go(route);
        await settle(tester);
        expect(app.location, '/home', reason: route);
        expect(find.byType(HomeScreen), findsOneWidget);
      }
      // the app never even asked the server for admin data
      expect(app.backend.requests.where((r) => r.path.startsWith('/users') || r.path.startsWith('/system') || r.path.startsWith('/security')),
          isEmpty);
      expect(app.backend.requests.where((r) => r.query['scope'] == 'global'), isEmpty);
    });

    testWidgets('the super admin sees the entry and opens the panel', (tester) async {
      final app = await pumpApp(tester, role: 'admin', location: '/home');
      await tester.scrollUntilVisible(find.byKey(const Key('hub-/admin')), 300, scrollable: find.byType(Scrollable).first);
      await tester.tap(find.byKey(const Key('hub-/admin')));
      await settle(tester);
      expect(app.location, '/admin');
      expect(find.text('Super Admin'), findsWidgets);
    });
  });

  testWidgets('a not-yet-connected account only gets the connection wizard', (tester) async {
    final app = await pumpApp(tester, connected: false, location: '/chats');
    expect(app.location, '/wizard');
    expect(find.text(ruStrings['wizard.not_connected']!), findsOneWidget);
    await tester.scrollUntilVisible(find.text(ruStrings['wizard.open_settings']!), 300, scrollable: find.byType(Scrollable).first);
    expect(find.text(ruStrings['wizard.open_settings']!), findsOneWidget);
    expect(find.byKey(const Key('hub-/chats')), findsNothing);
    app.go('/settings');
    await settle(tester);
    expect(app.location, '/settings');
  });

  testWidgets('pairing with a one-time code', (tester) async {
    final app = await pumpApp(tester, paired: false);
    expect(app.location, '/welcome');
    await tester.tap(find.byKey(const Key('welcome-pair')));
    await settle(tester);
    expect(app.location, '/pair');
    // plain http to a remote host is refused before any request
    await tester.enterText(find.byKey(const Key('pair-server')), 'http://192.168.1.5:8787');
    await tester.enterText(find.byKey(const Key('pair-code')), 'ABCD-EFGH');
    await tester.tap(find.byKey(const Key('pair-submit')));
    await settle(tester);
    expect(find.text(ruStrings['pair.err_https']!), findsOneWidget);
    expect(app.backend.sent('POST', '/auth/pair'), isEmpty);
    await tester.enterText(find.byKey(const Key('pair-server')), '127.0.0.1:8787');
    await tester.tap(find.byKey(const Key('pair-submit')));
    await settle(tester);
    final pair = app.backend.sent('POST', '/auth/pair').single.body as Map;
    expect(pair['code'], 'ABCD-EFGH');
    expect(pair['platform'], 'android');
    expect((pair['device_id'] as String).length, 32);
    expect(app.location, '/home');
    expect(await app.store.read('access'), 'ACCESS');
    expect(await app.store.read('server'), 'http://127.0.0.1:8787');
  });

  testWidgets('wrong pairing code shows a clear error', (tester) async {
    final app = await pumpApp(tester, paired: false, location: '/pair');
    app.backend.overrides['POST /auth/pair'] = (400, {
      'error': {'code': 'invalid_code', 'message': 'Invalid or expired code'}
    });
    await tester.enterText(find.byKey(const Key('pair-code')), 'WRONG-CODE');
    await tester.tap(find.byKey(const Key('pair-submit')));
    await settle(tester);
    expect(find.text(ruStrings['pair.err_code']!), findsOneWidget);
    expect(app.location, '/pair');
  });

  testWidgets('enabling Mute asks for confirmation and sends confirm=true', (tester) async {
    final app = await pumpApp(tester, location: '/chats/5550000001');
    await tester.tap(find.byKey(const Key('module-mute')));
    await settle(tester);
    expect(find.text(ruStrings['controls.mute_confirm_title']!), findsOneWidget);
    expect(app.backend.sent('PATCH', '/chats/5550000001/controls'), isEmpty);
    await tester.tap(find.text(ruStrings['common.confirm']!));
    await settle(tester);
    final body = app.backend.sent('PATCH', '/chats/5550000001/controls').single.body as Map;
    expect(body, {'module': 'mute', 'enabled': true, 'confirm': true});
  });

  testWidgets('AFK, reminders, commands sandbox and automation talk to the API', (tester) async {
    final app = await pumpApp(tester, location: '/afk');
    await tester.scrollUntilVisible(find.byKey(const Key('afk-on')), 200, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.byKey(const Key('afk-on')));
    await settle(tester);
    expect((app.backend.sent('POST', '/afk/enable').single.body as Map)['minutes'], 60);

    app.go('/reminders');
    await settle(tester);
    await tester.tap(find.byKey(const Key('reminder-add')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('reminder-text')), 'Позвонить маме');
    await tester.tap(find.byKey(const Key('reminder-save')));
    await settle(tester);
    expect(app.backend.sent('POST', '/reminders').single.body, {'text': 'Позвонить маме', 'in_sec': 3600});

    app.go('/commands');
    await settle(tester);
    await tester.tap(find.byKey(const Key('cmd-test-run')));
    await settle(tester);
    expect(app.backend.sent('POST', '/commands/test').single.body, {'text': '.calc 2+2*2'});
    expect(find.textContaining('= 6'), findsOneWidget);

    app.go('/automation');
    await settle(tester);
    await tester.tap(find.byKey(const Key('rule-new')));
    await settle(tester);
    await tester.enterText(find.byType(TextField).at(1), 'цена, narx');
    final builderList = find.descendant(of: find.byType(RuleBuilderScreen), matching: find.byType(Scrollable)).first;
    await tester.scrollUntilVisible(find.byKey(const Key('rule-save')), 300, scrollable: builderList);
    await tester.drag(builderList, const Offset(0, -300));
    // earlier confirmations are still on screen as snackbars at the bottom — dismiss them
    tester.state<ScaffoldMessengerState>(find.byType(ScaffoldMessenger)).clearSnackBars();
    await settle(tester);
    await tester.tap(find.byKey(const Key('rule-save')));
    await settle(tester);
    final rule = app.backend.sent('POST', '/automation/rules').single.body as Map;
    expect(rule['trigger'], {'type': 'keyword', 'keywords': ['цена', 'narx'], 'match': 'contains'});
    expect((rule['actions'] as List).single['type'], 'reply');
  });
}

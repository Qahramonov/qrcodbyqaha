// Renders real screens (real widgets + recorded API responses + the bundled Inter font) to PNG files.
// Not a regression test: run on demand and copy the files to docs/screenshots/:
//   flutter test --update-goldens --tags screenshots test/screenshots_test.dart
@Tags(['screenshots'])
library;

import 'dart:io';

import 'package:chat_helper_control/app.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_backend.dart';

Future<void> _loadFonts() async {
  Future<ByteData> file(String path) async => ByteData.sublistView(await File(path).readAsBytes());
  final inter = FontLoader('Inter')
    ..addFont(rootBundle.load('assets/fonts/Inter-Regular.otf'))
    ..addFont(rootBundle.load('assets/fonts/Inter-SemiBold.otf'))
    ..addFont(rootBundle.load('assets/fonts/Inter-Bold.otf'));
  await inter.load();
  final sdk = Platform.environment['FLUTTER_ROOT'] ?? '/root/sdk/flutter';
  final icons = FontLoader('MaterialIcons')..addFont(file('$sdk/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf'));
  await icons.load();
  const emoji = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf';
  if (File(emoji).existsSync()) {
    final e = FontLoader('Noto Color Emoji')..addFont(file(emoji));
    await e.load();
  }
}

const shots = <(String, String, String, bool, String)>[
  // (file, role, lang, connected, route)
  ('01_welcome_ru', 'user', 'ru', true, '/welcome'),
  ('02_pairing_ru', 'user', 'ru', true, '/pair'),
  ('03_wizard_ru', 'user', 'ru', false, '/wizard'),
  ('04_home_ru', 'user', 'ru', true, '/home'),
  ('05_chat_controls_ru', 'user', 'ru', true, '/chats/5550000001'),
  ('06_permissions_ru', 'user', 'ru', true, '/permissions'),
  ('07_mute_ru', 'user', 'ru', true, '/mute'),
  ('08_ai_twin_ru', 'user', 'ru', true, '/ai/twin'),
  ('09_animations_ru', 'user', 'ru', true, '/animations'),
  ('10_commands_ru', 'user', 'ru', true, '/commands'),
  ('11_automation_ru', 'user', 'ru', true, '/automation'),
  ('12_subscription_ru', 'user', 'ru', true, '/subscription'),
  ('13_home_uz', 'user', 'uz', true, '/home'),
  ('14_wizard_uz', 'user', 'uz', false, '/wizard'),
  ('15_admin_home_ru', 'admin', 'ru', true, '/admin'),
  ('16_admin_system_ru', 'admin', 'ru', true, '/admin/system'),
  ('17_admin_users_uz', 'admin', 'uz', true, '/admin/users'),
];

void main() {
  setUpAll(_loadFonts);

  for (final (name, role, lang, connected, route) in shots) {
    testWidgets(name, (tester) async {
      final paired = route != '/welcome' && route != '/pair';
      await pumpApp(tester, role: role, lang: lang, paired: paired, connected: connected, location: route);
      tester.view.physicalSize = const Size(1080, 2340);
      tester.view.devicePixelRatio = 2.75;
      await settle(tester, 20);
      await expectLater(find.byType(ChatHelperApp), matchesGoldenFile('screenshots/$name.png'));
    });
  }
}

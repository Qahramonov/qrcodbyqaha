import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/session.dart';
import 'core/widgets.dart';
import 'features/account.dart';
import 'features/admin.dart';
import 'features/ai.dart';
import 'features/chats.dart';
import 'features/home.dart';
import 'features/modules.dart';
import 'features/onboarding.dart';
import 'features/tools.dart';

/// Screens a user may open before their Telegram account is connected (mirrors the bot's lock).
const preConnectRoutes = {'/wizard', '/language', '/settings', '/profile', '/subscription'};

/// Screens available without a paired session.
const unpairedRoutes = {'/welcome', '/pair', '/language'};

/// Route guard — a pure function of the session so it can be unit-tested.
///
/// * The admin section (`/admin`, `/admin/...`) exists only for the account the server reports as `super_admin`;
///   anyone else is sent home as if the route did not exist (the backend answers those API routes with 404 too).
/// * Until the Telegram account is connected, everything except the connection wizard and account basics is locked.
String? guard(SessionState s, String location) {
  final path = Uri.parse(location).path;
  switch (s.status) {
    case SessionStatus.loading:
      return path == '/splash' ? null : '/splash';
    case SessionStatus.offline:
      return path == '/offline' ? null : '/offline';
    case SessionStatus.unpaired:
      return unpairedRoutes.contains(path) ? null : '/welcome';
    case SessionStatus.ready:
      if (const {'/splash', '/welcome', '/pair', '/offline', '/'}.contains(path)) return '/home';
      if (path == '/admin' || path.startsWith('/admin/')) return s.isSuper ? null : '/home';
      if (!s.connected && !s.isSuper && !preConnectRoutes.contains(path)) return '/wizard';
      return null;
  }
}

int _id(GoRouterState s, String name) => int.tryParse(s.pathParameters[name] ?? '') ?? 0;

final List<RouteBase> appRoutes = [
  GoRoute(path: '/splash', builder: (_, _) => const SplashScreen()),
  GoRoute(path: '/offline', builder: (_, _) => const OfflineScreen()),
  GoRoute(path: '/welcome', builder: (_, _) => const WelcomeScreen()),
  GoRoute(path: '/pair', builder: (_, _) => const PairingScreen()),
  GoRoute(path: '/wizard', builder: (_, _) => const WizardScreen()),
  GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
  GoRoute(path: '/chats', builder: (_, _) => const ChatsScreen()),
  GoRoute(path: '/chats/:id', builder: (_, s) => ChatControlsScreen(chatId: _id(s, 'id'))),
  GoRoute(path: '/permissions', builder: (_, _) => const PermissionsScreen()),
  GoRoute(path: '/ai', builder: (_, _) => const AiScreen()),
  GoRoute(path: '/ai/twin', builder: (_, _) => const TwinScreen()),
  GoRoute(path: '/ai/playground', builder: (_, _) => const PlaygroundScreen()),
  GoRoute(path: '/afk', builder: (_, _) => const AfkScreen()),
  GoRoute(path: '/mute', builder: (_, _) => const MuteScreen()),
  GoRoute(path: '/protect', builder: (_, _) => const ProtectScreen()),
  GoRoute(path: '/animations', builder: (_, _) => const AnimationsScreen()),
  GoRoute(path: '/media', builder: (_, _) => const MediaScreen()),
  GoRoute(path: '/games', builder: (_, _) => const GamesScreen()),
  GoRoute(path: '/commands', builder: (_, _) => const CommandsScreen()),
  GoRoute(path: '/reminders', builder: (_, _) => const RemindersScreen()),
  GoRoute(path: '/automation', builder: (_, _) => const AutomationScreen()),
  GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen()),
  GoRoute(path: '/stats', builder: (_, _) => const StatsScreen()),
  GoRoute(path: '/subscription', builder: (_, _) => const SubscriptionScreen()),
  GoRoute(path: '/language', builder: (_, _) => const LanguageScreen()),
  GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen()),
  // ---- Super Admin only (see guard) ----
  GoRoute(path: '/admin', builder: (_, _) => const AdminHomeScreen()),
  GoRoute(path: '/admin/users', builder: (_, _) => const AdminUsersScreen()),
  GoRoute(path: '/admin/users/:uid', builder: (_, s) => AdminUserScreen(uid: _id(s, 'uid'))),
  GoRoute(path: '/admin/connections', builder: (_, _) => const AdminConnectionsScreen()),
  GoRoute(path: '/admin/permissions', builder: (_, _) => const AdminPermissionsScreen()),
  GoRoute(path: '/admin/ai', builder: (_, _) => const AdminAiScreen()),
  GoRoute(path: '/admin/media', builder: (_, _) => const AdminMediaScreen()),
  GoRoute(path: '/admin/games', builder: (_, _) => const AdminGamesScreen()),
  GoRoute(path: '/admin/commands', builder: (_, _) => const AdminCommandsScreen()),
  GoRoute(path: '/admin/payments', builder: (_, _) => const AdminPaymentsScreen()),
  GoRoute(path: '/admin/analytics', builder: (_, _) => const StatsScreen(global: true)),
  GoRoute(path: '/admin/broadcast', builder: (_, _) => const AdminBroadcastScreen()),
  GoRoute(path: '/admin/security', builder: (_, _) => const AdminSecurityScreen()),
  GoRoute(path: '/admin/system', builder: (_, _) => const AdminSystemScreen()),
  GoRoute(path: '/admin/logs', builder: (_, _) => const AdminLogsScreen()),
  GoRoute(path: '/admin/diagnostics', builder: (_, _) => const AdminDiagnosticsScreen()),
];

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<int>(0);
  ref.listen<SessionState>(sessionProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);
  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: refresh,
    redirect: (context, state) => guard(ref.read(sessionProvider), state.uri.toString()),
    routes: appRoutes,
    errorBuilder: (context, state) => const NotFoundScreen(),
  );
});

class NotFoundScreen extends ConsumerWidget {
  const NotFoundScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('err.not_found'),
      body: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          EmptyView(t('err.not_found'), icon: Icons.explore_off_outlined),
          FilledButton(onPressed: () => context.go('/home'), child: Text(t('nav.home'))),
        ]),
      ),
    );
  }
}

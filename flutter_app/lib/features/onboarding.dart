import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';

class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 72});

  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          gradient: Tokens.accentGradient,
          borderRadius: BorderRadius.circular(size * 0.3),
          boxShadow: [BoxShadow(color: Tokens.violet.withValues(alpha: 0.45), blurRadius: 28, spreadRadius: 1)],
        ),
        child: Icon(Icons.forum_rounded, color: Colors.white, size: size * 0.5),
      );
}

class SplashScreen extends ConsumerWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const BrandMark(size: 88),
            const SizedBox(height: Tokens.lg),
            Text(AppInfo.name, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: Tokens.xs),
            Text(t('splash.loading'), style: const TextStyle(color: Tokens.textSecondary)),
            const SizedBox(height: Tokens.xl),
            const SizedBox(width: 28, height: 28, child: CircularProgressIndicator(strokeWidth: 2.5)),
          ]),
        ),
      ),
    );
  }
}

class OfflineScreen extends ConsumerWidget {
  const OfflineScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final s = ref.watch(sessionProvider);
    final server = ref.read(apiProvider).baseUrl ?? AppInfo.defaultServer;
    return AppScaffold(
      title: t('offline.title'),
      body: ListView(padding: pagePadding, children: [
        GlassCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.wifi_off_rounded, color: Tokens.warning, size: 36),
            const SizedBox(height: Tokens.sm),
            Text(t('offline.body'), style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: Tokens.xs),
            Text(t('offline.hint'), style: const TextStyle(color: Tokens.textSecondary)),
            const SizedBox(height: Tokens.sm),
            KVRow(t('offline.server'), server),
            if (s.error != null) KVRow(t('offline.error'), errorText(t, s.error!)),
          ]),
        ),
        FilledButton.icon(
          onPressed: () => ref.read(sessionProvider.notifier).refresh(),
          icon: const Icon(Icons.refresh),
          label: Text(t('common.retry')),
        ),
        const SizedBox(height: Tokens.sm),
        OutlinedButton(onPressed: () => ref.read(sessionProvider.notifier).logout(), child: Text(t('offline.repair'))),
      ]),
    );
  }
}

class WelcomeScreen extends ConsumerWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final lang = t.lang;
    Widget bullet(IconData icon, String text) => Padding(
          padding: const EdgeInsets.symmetric(vertical: Tokens.xs),
          child: Row(children: [
            Icon(icon, color: Tokens.cyan, size: 22),
            const SizedBox(width: Tokens.sm),
            Expanded(child: Text(text)),
          ]),
        );
    return AppBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: SafeArea(
          child: ListView(padding: const EdgeInsets.all(Tokens.xl), children: [
            Row(children: [
              const BrandMark(size: 56),
              const Spacer(),
              ChoiceRow(
                options: const ['ru', 'uz'],
                selected: lang,
                labels: (l) => l == 'ru' ? 'RU' : 'UZ',
                onSelected: (l) => ref.read(sessionProvider.notifier).setLang(l),
              ),
            ]),
            const SizedBox(height: Tokens.xxl),
            Text(t('welcome.title'), style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: Tokens.sm),
            Text(t('welcome.subtitle'), style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.subtitle)),
            const SizedBox(height: Tokens.xl),
            GlassCard(
              child: Column(children: [
                bullet(Icons.verified_user_outlined, t('welcome.b1')),
                bullet(Icons.tune_rounded, t('welcome.b2')),
                bullet(Icons.auto_awesome_outlined, t('welcome.b3')),
                bullet(Icons.lock_outline_rounded, t('welcome.b4')),
              ]),
            ),
            const SizedBox(height: Tokens.md),
            FilledButton(key: const Key('welcome-pair'), onPressed: () => context.go('/pair'), child: Text(t('welcome.pair'))),
            const SizedBox(height: Tokens.sm),
            Text(t('welcome.how'), textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
          ]),
        ),
      ),
    );
  }
}

class PairingScreen extends ConsumerStatefulWidget {
  const PairingScreen({super.key});

  @override
  ConsumerState<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends ConsumerState<PairingScreen> {
  final _server = TextEditingController(text: AppInfo.defaultServer);
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    ref.read(storeProvider).read('server').then((v) {
      if (v != null && mounted) _server.text = v;
    });
  }

  @override
  void dispose() {
    _server.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final t = ref.read(stringsProvider);
    final server = normalizeServer(_server.text);
    final bad = validateServer(server);
    if (bad != null) {
      setState(() => _error = t(bad));
      return;
    }
    if (_code.text.trim().length < 4) {
      setState(() => _error = t('pair.err_code_short'));
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).pair(server, _code.text);
    } on ApiException catch (e) {
      setState(() => _error = e.isNetwork
          ? t('pair.err_network')
          : (e.status == 400 || e.status == 401 || e.status == 403 || e.status == 404)
              ? t('pair.err_code')
              : errorText(t, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('pair.title'),
      body: ListView(padding: pagePadding, children: [
        GlassCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t('pair.steps_title'), style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: Tokens.xs),
            Text(t('pair.steps')),
          ]),
        ),
        const SizedBox(height: Tokens.xs),
        TextField(
          key: const Key('pair-code'),
          controller: _code,
          textCapitalization: TextCapitalization.characters,
          autocorrect: false,
          style: const TextStyle(fontSize: Tokens.title, letterSpacing: 3, fontWeight: FontWeight.w700),
          decoration: InputDecoration(labelText: t('pair.code'), hintText: 'ABCD-EFGH', prefixIcon: const Icon(Icons.key_rounded)),
        ),
        const SizedBox(height: Tokens.md),
        TextField(
          key: const Key('pair-server'),
          controller: _server,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: InputDecoration(labelText: t('pair.server'), helperText: t('pair.server_hint'), prefixIcon: const Icon(Icons.dns_outlined)),
        ),
        if (_error != null) ...[
          const SizedBox(height: Tokens.md),
          Text(_error!, key: const Key('pair-error'), style: const TextStyle(color: Tokens.danger)),
        ],
        const SizedBox(height: Tokens.lg),
        FilledButton(
          key: const Key('pair-submit'),
          onPressed: _busy ? null : _submit,
          child: _busy
              ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
              : Text(t('pair.submit')),
        ),
      ]),
    );
  }
}

/// Telegram "Chat automation" connection wizard: what to do in Telegram and a live check of the connection.
class WizardScreen extends ConsumerWidget {
  const WizardScreen({super.key});

  static const rightIcons = {
    'can_reply': Icons.reply_rounded,
    'can_read_messages': Icons.done_all_rounded,
    'can_delete_sent_messages': Icons.delete_outline_rounded,
    'can_delete_all_messages': Icons.delete_sweep_outlined,
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final session = ref.watch(sessionProvider);
    return AppScaffold(
      title: t('wizard.title'),
      actions: [
        IconButton(tooltip: t('nav.language'), onPressed: () => context.push('/language'), icon: const Icon(Icons.translate_rounded)),
        IconButton(tooltip: t('nav.settings'), onPressed: () => context.push('/settings'), icon: const Icon(Icons.settings_outlined)),
      ],
      body: ApiView('/onboarding', builder: (context, ref, d) {
        final bot = str(d['bot_username']);
        final connected = flag(d['connected']);
        final steps = asList(d['steps']).map((e) => '$e').toList();
        Future<void> check() async {
          ref.invalidate(jsonProvider('/onboarding'));
          await ref.read(sessionProvider.notifier).refresh();
          if (context.mounted) {
            toast(context, ref.read(sessionProvider).connected ? t('wizard.ok') : t('wizard.not_yet'));
          }
        }

        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Row(children: [
              Icon(connected ? Icons.check_circle_rounded : Icons.link_off_rounded,
                  color: connected ? Tokens.success : Tokens.warning, size: 36),
              const SizedBox(width: Tokens.sm),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(connected ? t('wizard.connected') : t('wizard.not_connected'), style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: Tokens.xxs),
                  Text(connected ? t('wizard.connected_body') : t('wizard.locked_body'),
                      style: const TextStyle(color: Tokens.textSecondary)),
                ]),
              ),
            ]),
          ),
          if (connected || session.isSuper)
            FilledButton(onPressed: () => context.go('/home'), child: Text(t('wizard.to_menu')))
          else ...[
            SectionHeader(t('wizard.steps')),
            GlassCard(
              child: Column(children: [
                for (var i = 0; i < steps.length; i++)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: CircleAvatar(
                      radius: 14,
                      backgroundColor: Tokens.blue.withValues(alpha: 0.25),
                      child: Text('${i + 1}', style: const TextStyle(fontSize: Tokens.caption, fontWeight: FontWeight.w700)),
                    ),
                    title: Text(t('wizard.step.${steps[i]}', {'bot': '@$bot'})),
                  ),
              ]),
            ),
            if (bot.isNotEmpty)
              GlassCard(
                child: Row(children: [
                  const Icon(Icons.smart_toy_outlined, color: Tokens.cyan),
                  const SizedBox(width: Tokens.sm),
                  Expanded(child: Text('@$bot', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: Tokens.subtitle))),
                  TextButton.icon(
                    onPressed: () => copyText(context, t, '@$bot'),
                    icon: const Icon(Icons.copy_rounded, size: 18),
                    label: Text(t('common.copy')),
                  ),
                ]),
              ),
            FilledButton.icon(
              onPressed: () async {
                final ok = await launchUrl(Uri.parse(str(d['settings_link'], 'tg://settings/edit')), mode: LaunchMode.externalApplication)
                    .catchError((_) => false);
                if (!ok && context.mounted) toast(context, t('wizard.open_failed'));
              },
              icon: const Icon(Icons.open_in_new_rounded),
              label: Text(t('wizard.open_settings')),
            ),
            const SizedBox(height: Tokens.sm),
            OutlinedButton.icon(onPressed: check, icon: const Icon(Icons.refresh_rounded), label: Text(t('wizard.check'))),
            SectionHeader(t('wizard.rights')),
            GlassCard(
              child: Column(children: [
                for (final r in asList(d['recommended_rights']))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(rightIcons['$r'] ?? Icons.check_rounded, color: Tokens.success),
                    title: Text(t('right.$r')),
                  ),
              ]),
            ),
            SectionHeader(t('wizard.never')),
            GlassCard(
              child: Column(children: [
                for (final r in asList(d['never_grant']))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.block_rounded, color: Tokens.danger),
                    title: Text(t('right.$r')),
                  ),
                Text(t('wizard.never_body'), style: Theme.of(context).textTheme.bodySmall),
              ]),
            ),
          ],
          const SizedBox(height: Tokens.md),
          TextButton(onPressed: () => ref.read(sessionProvider.notifier).logout(), child: Text(t('settings.logout'))),
        ]);
      }),
    );
  }
}

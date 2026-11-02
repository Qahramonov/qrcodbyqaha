import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/config.dart';
import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import 'ai.dart' show patchSettings;

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final session = ref.watch(sessionProvider);
    final u = session.user;
    final name = [str(u['first_name']), str(u['last_name'])].where((e) => e.isNotEmpty).join(' ');
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.profile'),
      body: ListView(padding: pagePadding, children: [
        GlassCard(
          child: Row(children: [
            CircleAvatar(
              radius: 30,
              backgroundColor: Tokens.violet.withValues(alpha: 0.35),
              child: Text(name.isEmpty ? '?' : name.characters.first.toUpperCase(), style: const TextStyle(fontSize: Tokens.title)),
            ),
            const SizedBox(width: Tokens.md),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name.isEmpty ? '—' : name, style: Theme.of(context).textTheme.titleLarge),
                if (str(u['username']).isNotEmpty) Text('@${u['username']}', style: const TextStyle(color: Tokens.textSecondary)),
                Text('ID ${str(u['id'])}', style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: Tokens.xs),
                Wrap(spacing: 6, children: [
                  Pill(session.plan.toUpperCase(), color: Tokens.warning),
                  if (session.isSuper) const Pill('Super Admin', color: Tokens.violet),
                ]),
              ]),
            ),
          ]),
        ),
        SectionHeader(t('profile.connections')),
        ApiView('/connections', builder: (context, ref, d) {
          final items = asMaps(d['items']);
          return Column(children: [
            if (items.isEmpty)
              GlassCard(
                onTap: () => context.push('/wizard'),
                child: ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.link_off_rounded, color: Tokens.warning),
                  title: Text(t('wizard.not_connected')),
                  trailing: const Icon(Icons.chevron_right),
                ),
              ),
            for (final c in items)
              GlassCard(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(str(c['status_title']), style: const TextStyle(fontWeight: FontWeight.w600)),
                  KVRow(t('profile.connected_at'), fmtTime(c['connected_at'])),
                  KVRow(t('profile.modules'), '${integer(c['available_modules'])} / ${integer(c['total_modules'])}'),
                  SwitchRow(
                    title: t('profile.pause'),
                    subtitle: t('profile.pause_hint'),
                    value: flag(c['paused']),
                    onChanged: (v) => act(context, ref, () => api.post('/connections/${c['id']}/${v ? 'pause' : 'resume'}'), reload: ['/connections']),
                  ),
                ]),
              ),
          ]);
        }),
        SectionHeader(t('profile.devices')),
        ApiView('/auth/sessions', builder: (context, ref, d) {
          final items = asMaps(d['items']).where((s) => s['revoked_at'] == null).toList();
          return GlassCard(
            child: Column(children: [
              for (final s in items)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(flag(s['current']) ? Icons.smartphone : Icons.devices_other, color: flag(s['current']) ? Tokens.success : Tokens.textSecondary),
                  title: Text(str(s['device_name'], str(s['platform']))),
                  subtitle: Text('${t('profile.last_used')}: ${fmtTime(s['last_used_at'])}${flag(s['current']) ? ' · ${t('profile.this_device')}' : ''}'),
                  trailing: flag(s['current'])
                      ? null
                      : IconButton(
                          tooltip: t('profile.revoke'),
                          icon: const Icon(Icons.logout_rounded, color: Tokens.danger),
                          onPressed: () => act(context, ref, () => api.delete('/auth/sessions/${s['id']}'), reload: ['/auth/sessions']),
                        ),
                ),
            ]),
          );
        }),
        SectionHeader(t('profile.delegation')),
        ApiView('/delegation', builder: (context, ref, d) {
          return GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('profile.delegation_hint'), style: Theme.of(context).textTheme.bodySmall),
              for (final sc in asMaps(d['scopes']))
                SwitchRow(
                  title: str(sc['title'], str(sc['scope'])),
                  subtitle: sc['expires_at'] == null ? null : t('profile.until', {'t': fmtTime(sc['expires_at'])}),
                  value: flag(sc['granted']),
                  onChanged: (v) async {
                    if (v &&
                        !await confirmDialog(context, t, title: t('profile.delegate_title'), body: t('profile.delegate_body', {'s': str(sc['title'])}))) {
                      return;
                    }
                    if (context.mounted) {
                      await act(context, ref, () => api.put('/delegation/${sc['scope']}', {'granted': v}), reload: ['/delegation']);
                    }
                  },
                ),
            ]),
          );
        }),
        SectionHeader(t('profile.data')),
        GlassCard(
          child: Column(children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.download_outlined),
              title: Text(t('profile.export')),
              subtitle: Text(t('profile.export_hint'), style: Theme.of(context).textTheme.bodySmall),
              onTap: () => showModalBottomSheet<void>(context: context, backgroundColor: Tokens.bgElevated, builder: (_) => const _ExportSheet()),
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.logout_rounded, color: Tokens.danger),
              title: Text(t('settings.logout')),
              onTap: () async {
                if (await confirmDialog(context, t, title: t('settings.logout'), body: t('settings.logout_body')) && context.mounted) {
                  await ref.read(sessionProvider.notifier).logout();
                }
              },
            ),
          ]),
        ),
      ]),
    );
  }
}

class _ExportSheet extends ConsumerWidget {
  const _ExportSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.6,
        child: ApiView('/export', builder: (context, ref, d) {
          final entries = d.entries.where((e) => e.value is List || e.value is Map).toList();
          return ListView(padding: const EdgeInsets.all(Tokens.md), children: [
            Text(t('profile.export'), style: Theme.of(context).textTheme.titleLarge),
            Text(t('profile.export_done', {'t': fmtTime(d['exported_at'])}), style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: Tokens.sm),
            for (final e in entries)
              KVRow(e.key, e.value is List ? '${(e.value as List).length}' : '${(e.value as Map).length} ${t('profile.fields')}'),
          ]);
        }),
      ),
    );
  }
}

class StatsScreen extends ConsumerStatefulWidget {
  const StatsScreen({super.key, this.global = false});

  final bool global;

  @override
  ConsumerState<StatsScreen> createState() => _StatsScreenState();
}

class _StatsScreenState extends ConsumerState<StatsScreen> {
  int _days = 7;

  String _date(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final now = DateTime.now();
    final from = _date(now.subtract(Duration(days: _days - 1)));
    final path = '/analytics/overview?from=$from&to=${_date(now)}&scope=${widget.global ? 'global' : 'self'}';
    const series = ['messages_in', 'messages_out', 'auto_replies', 'ai_requests', 'commands', 'media_jobs', 'games_played', 'errors'];
    return AppScaffold(
      title: widget.global ? t('admin.analytics') : t('nav.stats'),
      body: ApiView(path, builder: (context, ref, d) {
        final totals = asMap(d['totals']);
        final s = asMap(d['series']);
        return ListView(padding: pagePadding, children: [
          ChoiceRow(
            options: const ['7', '30', '90'],
            selected: '$_days',
            labels: (x) => t('stats.days', {'n': x}),
            onSelected: (x) => setState(() => _days = int.parse(x)),
          ),
          const SizedBox(height: Tokens.sm),
          StatGrid([
            for (final k in series.take(4))
              StatTile(label: t('stat.$k'), value: '${integer(totals[k])}', icon: Icons.insights_rounded),
            if (widget.global) StatTile(label: t('stat.revenue_stars'), value: '${integer(totals['revenue_stars'])} ⭐', color: Tokens.warning),
            if (widget.global) StatTile(label: t('stat.connections_new'), value: '${integer(totals['connections_new'])}', color: Tokens.success),
          ]),
          for (final k in series)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(t('stat.$k'), style: const TextStyle(fontWeight: FontWeight.w600))),
                  Text('${integer(totals[k])}', style: const TextStyle(color: Tokens.textSecondary)),
                ]),
                const SizedBox(height: Tokens.xs),
                SparkBars(SparkBars.fromSeries(s[k]), color: k == 'errors' ? Tokens.danger : Tokens.blue, height: 48),
              ]),
            ),
          Text('${d['from']} — ${d['to']}', textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
        ]);
      }),
    );
  }
}

class SubscriptionScreen extends ConsumerWidget {
  const SubscriptionScreen({super.key});

  static const limitKeys = ['ai_requests_day', 'media_jobs_day', 'autoreply_rules', 'automation_rules', 'custom_commands', 'stt_minutes_day'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.subscription'),
      body: ApiView('/subscriptions/me', builder: (context, ref, me) {
        final sub = me['subscription'] == null ? null : asMap(me['subscription']);
        final limits = asMap(me['limits']);
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Icon(Icons.workspace_premium_rounded, color: Tokens.warning, size: 32),
                const SizedBox(width: Tokens.sm),
                Text(str(me['plan']).toUpperCase(), style: Theme.of(context).textTheme.headlineMedium),
              ]),
              if (sub != null) KVRow(t('sub.until'), fmtTime(sub['expires_at'])),
              const Divider(height: Tokens.xl),
              for (final k in limitKeys)
                KVRow(t('limit.$k'), integer(limits[k], -2) == -1 ? '∞' : '${limits[k] ?? '—'}'),
            ]),
          ),
          SectionHeader(t('sub.plans')),
          ApiView('/subscriptions/plans', builder: (context, ref, d) {
            final payments = flag(d['payments_enabled']);
            return Column(children: [
              for (final pl in asMaps(d['items']).where((p) => p['id'] != 'free'))
                GlassCard(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Expanded(child: Text(str(pl['name']), style: Theme.of(context).textTheme.titleMedium)),
                      Pill('${integer(pl['price_stars'])} ⭐ / ${integer(pl['duration_days'])} ${t('sub.days')}', color: Tokens.warning),
                    ]),
                    const SizedBox(height: Tokens.xxs),
                    Text(str(pl['description']), style: const TextStyle(color: Tokens.textSecondary)),
                  ]),
                ),
              GlassCard(
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Text(payments ? t('sub.buy_in_telegram') : t('sub.payments_off'), style: Theme.of(context).textTheme.bodySmall),
                  if (payments) ...[
                    const SizedBox(height: Tokens.xs),
                    _OpenBotButton(label: t('sub.open_bot')),
                  ],
                ]),
              ),
            ]);
          }),
          SectionHeader(t('sub.promo')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              OutlinedButton.icon(
                onPressed: () async {
                  final code = await promptText(context, t, title: t('sub.promo'), hint: 'ABCD1234', maxLength: 32);
                  if (code != null && code.length >= 4 && context.mounted) {
                    await act(context, ref, () async {
                      await api.post('/subscriptions/redeem', {'code': code});
                      await ref.read(sessionProvider.notifier).refresh();
                    }, done: t('sub.promo_ok'), reload: ['/subscriptions/me']);
                  }
                },
                icon: const Icon(Icons.redeem_outlined),
                label: Text(t('sub.enter_promo')),
              ),
              const SizedBox(height: Tokens.xs),
              OutlinedButton.icon(
                onPressed: () => act(context, ref, () async {
                  await api.post('/subscriptions/trial');
                  await ref.read(sessionProvider.notifier).refresh();
                }, done: t('sub.trial_ok'), reload: ['/subscriptions/me']),
                icon: const Icon(Icons.hourglass_top_rounded),
                label: Text(t('sub.trial')),
              ),
            ]),
          ),
        ]);
      }),
    );
  }
}

/// Opens the bot chat in Telegram (Stars payments happen there, never inside this app).
class _OpenBotButton extends ConsumerWidget {
  const _OpenBotButton({required this.label});

  final String label;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider('/onboarding'));
    final bot = async.value == null ? '' : str(async.value!['bot_username']);
    return FilledButton.icon(
      onPressed: bot.isEmpty
          ? null
          : () async {
              final ok = await launchUrl(Uri.parse('https://t.me/$bot'), mode: LaunchMode.externalApplication).catchError((_) => false);
              if (!ok && context.mounted) toast(context, t('wizard.open_failed'));
            },
      icon: const Icon(Icons.open_in_new_rounded),
      label: Text(label),
    );
  }
}

class LanguageScreen extends ConsumerWidget {
  const LanguageScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    Widget option(String code, String flagEmoji, String name) => GlassCard(
          key: Key('lang-$code'),
          onTap: () => act(context, ref, () => ref.read(sessionProvider.notifier).setLang(code), done: name),
          child: Row(children: [
            Text(flagEmoji, style: const TextStyle(fontSize: 28)),
            const SizedBox(width: Tokens.md),
            Expanded(child: Text(name, style: Theme.of(context).textTheme.titleMedium)),
            if (t.lang == code) const Icon(Icons.check_circle_rounded, color: Tokens.success),
          ]),
        );
    return AppScaffold(
      title: t('nav.language'),
      body: ListView(padding: pagePadding, children: [
        option('ru', '🇷🇺', 'Русский'),
        option('uz', '🇺🇿', "O'zbekcha"),
        const SizedBox(height: Tokens.sm),
        Text(t('lang.hint'), style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  static const toggles = [
    'delete_commands', 'automation_paused', 'notify_important', 'notify_new_chats', 'notify_disconnect', 'chat_activity', 'store_previews',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.settings'),
      body: ApiView('/settings', builder: (context, ref, d) {
        final v = asMap(d['values']);
        return ListView(padding: pagePadding, children: [
          SectionHeader(t('settings.general')),
          GlassCard(
            child: Column(children: [
              for (final k in toggles)
                SwitchRow(title: t('set.$k'), subtitle: t('set.${k}_hint'), value: flag(v[k]), onChanged: (x) => patchSettings(context, ref, {k: x})),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('set.controls_place')),
                subtitle: Text(t('set.controls_place.${str(v['controls_place'], 'chat')}')),
                trailing: ChoiceRow(
                  options: const ['chat', 'dm'],
                  selected: str(v['controls_place'], 'chat'),
                  labels: (x) => t('set.place.$x'),
                  onSelected: (x) => patchSettings(context, ref, {'controls_place': x}),
                ),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('set.timezone')),
                subtitle: Text(str(v['timezone']).isEmpty ? t('set.timezone_default') : str(v['timezone'])),
                trailing: const Icon(Icons.edit_outlined),
                onTap: () async {
                  final x = await promptText(context, t, title: t('set.timezone'), initial: str(v['timezone']), hint: 'Asia/Tashkent');
                  if (x != null && context.mounted) await patchSettings(context, ref, {'timezone': x});
                },
              ),
            ]),
          ),
          SectionHeader(t('settings.app')),
          GlassCard(
            child: Column(children: [
              KVRow(t('settings.server'), ref.read(apiProvider).baseUrl ?? AppInfo.defaultServer),
              KVRow(t('settings.version'), AppInfo.version),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.translate_rounded),
                title: Text(t('nav.language')),
                onTap: () => context.push('/language'),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.support_agent_rounded),
                title: Text(t('settings.support')),
                onTap: () async {
                  final m = await promptText(context, t, title: t('settings.support'), hint: t('settings.support_hint'), maxLines: 4, maxLength: 2000);
                  if (m != null && m.length >= 3 && context.mounted) {
                    await act(context, ref, () => api.post('/support', {'message': m}), done: t('settings.support_sent'));
                  }
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.new_releases_outlined),
                title: Text(t('settings.changelog')),
                onTap: () => showModalBottomSheet<void>(context: context, backgroundColor: Tokens.bgElevated, builder: (_) => const _Changelog()),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.logout_rounded, color: Tokens.danger),
                title: Text(t('settings.logout')),
                onTap: () async {
                  if (await confirmDialog(context, t, title: t('settings.logout'), body: t('settings.logout_body')) && context.mounted) {
                    await ref.read(sessionProvider.notifier).logout();
                  }
                },
              ),
            ]),
          ),
        ]);
      }),
    );
  }
}

class _Changelog extends ConsumerWidget {
  const _Changelog();

  @override
  Widget build(BuildContext context, WidgetRef ref) => SafeArea(
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.6,
          child: ApiView('/changelog', builder: (context, ref, d) {
            return ListView(padding: const EdgeInsets.all(Tokens.md), children: [
              for (final v in asMaps(d['items'])) ...[
                Text('v${v['version']} · ${v['date']}', style: Theme.of(context).textTheme.titleMedium),
                for (final i in asList(v['items'])) Padding(padding: const EdgeInsets.only(top: 4), child: Text('• $i')),
                const SizedBox(height: Tokens.md),
              ],
            ]);
          }),
        ),
      );
}

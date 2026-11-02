import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';

class HubItem {
  const HubItem(this.route, this.labelKey, this.icon, [this.color = Tokens.blue]);

  final String route;
  final String labelKey;
  final IconData icon;
  final Color color;
}

/// The user sections of the app (the Super Admin entry is added separately and only for the super admin).
const userHub = [
  HubItem('/chats', 'nav.chats', Icons.forum_outlined, Tokens.blue),
  HubItem('/permissions', 'nav.permissions', Icons.verified_user_outlined, Tokens.cyan),
  HubItem('/ai', 'nav.ai', Icons.auto_awesome_outlined, Tokens.violet),
  HubItem('/ai/twin', 'nav.twin', Icons.face_retouching_natural_outlined, Tokens.violet),
  HubItem('/ai/playground', 'nav.playground', Icons.science_outlined, Tokens.violet),
  HubItem('/afk', 'nav.afk', Icons.bedtime_outlined, Tokens.cyan),
  HubItem('/mute', 'nav.mute', Icons.volume_off_outlined, Tokens.warning),
  HubItem('/protect', 'nav.protect', Icons.shield_outlined, Tokens.success),
  HubItem('/animations', 'nav.animations', Icons.animation_outlined, Tokens.blue),
  HubItem('/media', 'nav.media', Icons.movie_filter_outlined, Tokens.blue),
  HubItem('/games', 'nav.games', Icons.sports_esports_outlined, Tokens.success),
  HubItem('/commands', 'nav.commands', Icons.terminal_rounded, Tokens.cyan),
  HubItem('/reminders', 'nav.reminders', Icons.alarm_outlined, Tokens.warning),
  HubItem('/automation', 'nav.automation', Icons.account_tree_outlined, Tokens.violet),
  HubItem('/stats', 'nav.stats', Icons.insights_outlined, Tokens.blue),
  HubItem('/subscription', 'nav.subscription', Icons.workspace_premium_outlined, Tokens.warning),
  HubItem('/profile', 'nav.profile', Icons.person_outline_rounded, Tokens.cyan),
  HubItem('/language', 'nav.language', Icons.translate_rounded, Tokens.cyan),
  HubItem('/settings', 'nav.settings', Icons.settings_outlined, Tokens.textSecondary),
];

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final session = ref.watch(sessionProvider);
    final name = str(session.user['first_name'], t('home.friend'));
    return AppScaffold(
      title: 'Chat helper',
      actions: [
        IconButton(
          key: const Key('notifications'),
          tooltip: t('home.notifications'),
          onPressed: () => showModalBottomSheet<void>(
            context: context,
            isScrollControlled: true,
            backgroundColor: Tokens.bgElevated,
            builder: (_) => const NotificationsSheet(),
          ),
          icon: const Icon(Icons.notifications_none_rounded),
        ),
      ],
      body: ApiView('/dashboard?scope=self', builder: (context, ref, d) {
        final today = asMap(d['today']);
        final bot = asMap(d['bot']);
        final conns = asMap(d['connections']);
        final charts = asMap(d['charts']);
        return ListView(padding: pagePadding, children: [
          Text(t('home.hello', {'name': name}), style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: Tokens.xs),
          Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
            Pill(session.plan.toUpperCase(), color: Tokens.warning),
            Pill(
              str(conns['status']) == 'connected' ? t('home.connected') : t('home.not_connected'),
              color: str(conns['status']) == 'connected' ? Tokens.success : Tokens.danger,
            ),
            if (session.isSuper) const Pill('Super Admin', color: Tokens.violet),
            if (flag(asMap(d['me'])['afk'])) Pill(t('home.afk_on'), color: Tokens.cyan),
          ]),
          if (!flag(bot['polling']))
            Padding(
              padding: const EdgeInsets.only(top: Tokens.sm),
              child: GlassCard(
                child: Row(children: [
                  const Icon(Icons.warning_amber_rounded, color: Tokens.warning),
                  const SizedBox(width: Tokens.sm),
                  Expanded(child: Text(t('home.bot_not_polling'))),
                ]),
              ),
            ),
          if (flag(bot['maintenance']))
            GlassCard(child: Text(t('home.maintenance'), style: const TextStyle(color: Tokens.warning))),
          SectionHeader(t('home.today')),
          StatGrid([
            StatTile(label: t('stat.messages_in'), value: '${integer(today['messages_in'])}', icon: Icons.south_west_rounded),
            StatTile(label: t('stat.messages_out'), value: '${integer(today['messages_out'])}', icon: Icons.north_east_rounded),
            StatTile(
                label: t('stat.auto_replies'), value: '${integer(today['auto_replies'])}', icon: Icons.quickreply_outlined, color: Tokens.cyan),
            StatTile(label: t('stat.commands'), value: '${integer(today['commands'])}', icon: Icons.terminal_rounded, color: Tokens.violet),
          ]),
          const SizedBox(height: Tokens.sm),
          GlassCard(
            onTap: () => context.push('/chats'),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(t('home.messages_14d'), style: Theme.of(context).textTheme.titleMedium)),
                Pill(t('home.unanswered', {'n': integer(d['unanswered'])}), color: Tokens.warning),
              ]),
              const SizedBox(height: Tokens.sm),
              SparkBars(SparkBars.fromSeries(charts['messages'])),
            ]),
          ),
          SectionHeader(t('home.sections')),
          _HubGrid(items: [
            if (session.isSuper) const HubItem('/admin', 'nav.admin', Icons.admin_panel_settings_outlined, Tokens.violet),
            ...userHub,
          ]),
          if (asMaps(d['recent_events']).isNotEmpty) ...[
            SectionHeader(t('home.events')),
            GlassCard(
              child: Column(children: [
                for (final e in asMaps(d['recent_events']).take(6))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      str(e['level']) == 'warning' ? Icons.warning_amber_rounded : Icons.bolt_rounded,
                      color: str(e['level']) == 'warning' ? Tokens.warning : Tokens.cyan,
                    ),
                    title: Text(t.has('event.${e['kind']}') ? t('event.${e['kind']}') : str(e['kind'])),
                    trailing: Text(fmtTime(e['ts'], withDate: false), style: Theme.of(context).textTheme.bodySmall),
                  ),
              ]),
            ),
          ],
        ]);
      }),
    );
  }
}

class _HubGrid extends ConsumerWidget {
  const _HubGrid({required this.items});

  final List<HubItem> items;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return LayoutBuilder(builder: (context, c) {
      final cols = c.maxWidth > 560 ? 3 : 2;
      final w = (c.maxWidth - (cols - 1) * Tokens.sm) / cols;
      return Wrap(spacing: Tokens.sm, runSpacing: Tokens.sm, children: [
        for (final it in items)
          SizedBox(
            width: w,
            child: HubTile(
              key: Key('hub-${it.route}'),
              icon: it.icon,
              label: t(it.labelKey),
              color: it.color,
              onTap: () => context.push(it.route),
            ),
          ),
      ]);
    });
  }
}

class NotificationsSheet extends ConsumerWidget {
  const NotificationsSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.7,
        child: ApiView('/notifications', builder: (context, ref, d) {
          final items = asMaps(d['items']);
          return ListView(padding: const EdgeInsets.all(Tokens.md), children: [
            Row(children: [
              Expanded(child: Text(t('home.notifications'), style: Theme.of(context).textTheme.titleLarge)),
              if (integer(d['unread']) > 0)
                TextButton(
                  onPressed: () => act(context, ref, () => ref.read(apiProvider).post('/notifications/read', {'ids': null}),
                      done: t('home.all_read'), reload: ['/notifications']),
                  child: Text(t('home.mark_read')),
                ),
            ]),
            if (items.isEmpty) EmptyView(t('home.no_notifications'), icon: Icons.notifications_off_outlined),
            for (final n in items)
              GlassCard(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    if (n['read_at'] == null) const Padding(padding: EdgeInsets.only(right: 6), child: Icon(Icons.circle, size: 8, color: Tokens.blue)),
                    Expanded(child: Text(str(n['title']), style: const TextStyle(fontWeight: FontWeight.w600))),
                    Text(fmtTime(n['created_at']), style: Theme.of(context).textTheme.bodySmall),
                  ]),
                  if (str(n['body']).isNotEmpty) ...[const SizedBox(height: Tokens.xxs), Text(stripHtml(str(n['body'])))],
                ]),
              ),
          ]);
        }),
      ),
    );
  }
}

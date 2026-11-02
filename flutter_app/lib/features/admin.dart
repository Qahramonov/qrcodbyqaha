// Super Admin screens. The router only opens /admin/* for the account whose role the server reports as
// `super_admin`; the backend independently answers every admin route with 404 for anyone else.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import 'home.dart' show HubItem;
import 'modules.dart' show MediaJobsList;

const adminHub = [
  HubItem('/admin/users', 'admin.users', Icons.people_alt_outlined, Tokens.blue),
  HubItem('/admin/connections', 'admin.connections', Icons.link_rounded, Tokens.cyan),
  HubItem('/admin/permissions', 'admin.permissions', Icons.verified_user_outlined, Tokens.cyan),
  HubItem('/admin/ai', 'admin.ai', Icons.auto_awesome_outlined, Tokens.violet),
  HubItem('/admin/media', 'admin.media', Icons.movie_filter_outlined, Tokens.blue),
  HubItem('/admin/games', 'admin.games', Icons.sports_esports_outlined, Tokens.success),
  HubItem('/admin/commands', 'admin.commands', Icons.terminal_rounded, Tokens.cyan),
  HubItem('/admin/payments', 'admin.payments', Icons.payments_outlined, Tokens.warning),
  HubItem('/admin/analytics', 'admin.analytics', Icons.insights_outlined, Tokens.blue),
  HubItem('/admin/broadcast', 'admin.broadcast', Icons.campaign_outlined, Tokens.warning),
  HubItem('/admin/security', 'admin.security', Icons.security_outlined, Tokens.danger),
  HubItem('/admin/system', 'admin.system', Icons.memory_rounded, Tokens.textSecondary),
  HubItem('/admin/logs', 'admin.logs', Icons.receipt_long_outlined, Tokens.textSecondary),
  HubItem('/admin/diagnostics', 'admin.diagnostics', Icons.health_and_safety_outlined, Tokens.success),
];

Future<void> _emergency(BuildContext context, WidgetRef ref, bool enable) async {
  final t = ref.read(stringsProvider);
  final word = enable ? 'STOP' : 'RESUME';
  final typed = await promptText(context, t, title: enable ? t('admin.es_on') : t('admin.es_off'), hint: t('admin.type_word', {'w': word}));
  if (typed == null || !context.mounted) return;
  await act(context, ref, () => ref.read(apiProvider).post('/security/emergency-stop', {'enabled': enable, 'confirm': typed}),
      reload: ['/dashboard?scope=global', '/system/status']);
}

class AdminHomeScreen extends ConsumerWidget {
  const AdminHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: 'Super Admin',
      body: ApiView('/dashboard?scope=global', builder: (context, ref, d) {
        final today = asMap(d['today']);
        final users = asMap(d['users']);
        final conns = asMap(d['connections']);
        final bot = asMap(d['bot']);
        final subs = asMap(d['subscriptions']);
        final es = flag(bot['emergency_stop']);
        return ListView(padding: pagePadding, children: [
          Wrap(spacing: 6, runSpacing: 6, children: [
            Pill(flag(bot['polling']) ? t('admin.polling_on') : t('admin.polling_off'), color: flag(bot['polling']) ? Tokens.success : Tokens.danger),
            if (flag(bot['maintenance'])) Pill(t('admin.maintenance'), color: Tokens.warning),
            if (es) Pill(t('admin.es_active'), color: Tokens.danger),
            Pill('v${str(d['version'])}', color: Tokens.cyan),
          ]),
          const SizedBox(height: Tokens.sm),
          StatGrid([
            StatTile(label: t('admin.users_total'), value: '${integer(users['total'])}', icon: Icons.people_alt_outlined),
            StatTile(label: t('admin.users_today'), value: '${integer(users['active_today'])}', icon: Icons.today_outlined, color: Tokens.cyan),
            StatTile(label: t('admin.conns_active'), value: '${integer(conns['active'])} / ${integer(conns['total'])}', icon: Icons.link_rounded, color: Tokens.success),
            StatTile(label: t('stat.revenue_stars'), value: '${integer(subs['revenue_stars'])} ⭐', icon: Icons.star_rounded, color: Tokens.warning),
            StatTile(label: t('stat.messages_in'), value: '${integer(today['messages_in'])}', icon: Icons.south_west_rounded),
            StatTile(label: t('stat.errors'), value: '${integer(today['errors'])}', icon: Icons.error_outline, color: Tokens.danger),
          ]),
          const SizedBox(height: Tokens.sm),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('admin.active_users_14d'), style: const TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: Tokens.xs),
              SparkBars(SparkBars.fromSeries(asMap(d['charts'])['active_users']), color: Tokens.violet),
            ]),
          ),
          GlassCard(
            child: Column(children: [
              SwitchRow(
                title: t('admin.es'),
                subtitle: t('admin.es_hint'),
                value: es,
                onChanged: (v) => _emergency(context, ref, v),
              ),
              SwitchRow(
                title: t('admin.maintenance'),
                subtitle: t('admin.maintenance_hint'),
                value: flag(bot['maintenance']),
                onChanged: (v) => act(context, ref, () => ref.read(apiProvider).post('/system/maintenance', {'enabled': v}),
                    reload: ['/dashboard?scope=global']),
              ),
            ]),
          ),
          SectionHeader(t('admin.sections')),
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth > 560 ? 3 : 2;
            final w = (c.maxWidth - (cols - 1) * Tokens.sm) / cols;
            return Wrap(spacing: Tokens.sm, runSpacing: Tokens.sm, children: [
              for (final it in adminHub)
                SizedBox(
                  width: w,
                  child: HubTile(key: Key('hub-${it.route}'), icon: it.icon, label: t(it.labelKey), color: it.color, onTap: () => context.push(it.route)),
                ),
            ]);
          }),
        ]);
      }),
    );
  }
}

class AdminUsersScreen extends ConsumerStatefulWidget {
  const AdminUsersScreen({super.key});

  @override
  ConsumerState<AdminUsersScreen> createState() => _AdminUsersScreenState();
}

class _AdminUsersScreenState extends ConsumerState<AdminUsersScreen> {
  String _q = '';
  int _page = 1;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final path = '/users?page=$_page&page_size=30${_q.isEmpty ? '' : '&q=${Uri.encodeQueryComponent(_q)}'}';
    return AppScaffold(
      title: t('admin.users'),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Tokens.md, 0, Tokens.md, Tokens.xs),
          child: TextField(
            textInputAction: TextInputAction.search,
            onSubmitted: (v) => setState(() {
              _q = v.trim();
              _page = 1;
            }),
            decoration: InputDecoration(hintText: t('admin.users_search'), prefixIcon: const Icon(Icons.search_rounded)),
          ),
        ),
        Expanded(
          child: ApiView(path, builder: (context, ref, d) {
            final items = asMaps(d['items']);
            final pages = (integer(d['total']) / 30).ceil();
            return ListView(padding: pagePadding, children: [
              Text(t('admin.users_found', {'n': integer(d['total'])}), style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: Tokens.xs),
              for (final u in items)
                GlassCard(
                  onTap: () => context.push('/admin/users/${u['id']}'),
                  child: Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${str(u['first_name'])} ${str(u['last_name'])}'.trim(), style: const TextStyle(fontWeight: FontWeight.w600)),
                        Text('${u['username'] == null ? '' : '@${u['username']} · '}ID ${u['id']}', style: Theme.of(context).textTheme.bodySmall),
                      ]),
                    ),
                    Pill(str(u['plan']).toUpperCase(), color: Tokens.warning),
                    const SizedBox(width: 6),
                    Pill(str(u['status']), color: u['status'] == 'active' ? Tokens.success : Tokens.danger),
                  ]),
                ),
              if (pages > 1)
                Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  IconButton(onPressed: _page > 1 ? () => setState(() => _page--) : null, icon: const Icon(Icons.chevron_left)),
                  Text('$_page / $pages'),
                  IconButton(onPressed: _page < pages ? () => setState(() => _page++) : null, icon: const Icon(Icons.chevron_right)),
                ]),
            ]);
          }),
        ),
      ]),
    );
  }
}

class AdminUserScreen extends ConsumerWidget {
  const AdminUserScreen({super.key, required this.uid});

  final int uid;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    final path = '/users/$uid';
    return AppScaffold(
      title: t('admin.user'),
      body: ApiView(path, builder: (context, ref, d) {
        final u = asMap(d['user']);
        final usage = asMap(d['usage']);
        final restricted = u['status'] == 'restricted';
        final isSelf = str(d['role']) == 'super_admin';
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${str(u['first_name'])} ${str(u['last_name'])}'.trim(), style: Theme.of(context).textTheme.titleLarge),
              Text('${u['username'] == null ? '' : '@${u['username']} · '}ID ${u['id']}', style: const TextStyle(color: Tokens.textSecondary)),
              const SizedBox(height: Tokens.xs),
              KVRow(t('admin.plan'), str(d['plan']).toUpperCase()),
              KVRow(t('admin.status'), str(u['status'])),
              if (u['restricted_reason'] != null) KVRow(t('admin.reason'), str(u['restricted_reason'])),
              KVRow(t('admin.registered'), fmtTime(u['created_at'])),
              KVRow(t('admin.last_seen'), fmtTime(u['last_seen_at'])),
            ]),
          ),
          SectionHeader(t('admin.usage')),
          GlassCard(
            child: Column(children: [
              KVRow(t('admin.ai_total'), '${integer(usage['ai_requests_total'])} · \$${number(usage['ai_cost_total']).toStringAsFixed(3)}'),
              KVRow(t('admin.ai_today'), '${integer(usage['ai_today'])}'),
              KVRow(t('admin.media_today'), '${integer(usage['media_today'])}'),
              KVRow(t('admin.commands_total'), '${integer(usage['commands_total'])}'),
            ]),
          ),
          SectionHeader(t('admin.connections')),
          for (final c in asMaps(d['connections']))
            GlassCard(child: KVRow(str(c['id']), '${str(c['status'])} · ${fmtTime(c['connected_at'])}')),
          Text(str(d['note']), style: Theme.of(context).textTheme.bodySmall),
          if (!isSelf) ...[
            SectionHeader(t('admin.actions')),
            Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
              for (final plan in const ['plus', 'pro', 'vip'])
                OutlinedButton(
                  onPressed: () => act(context, ref, () => api.post('/users/$uid/subscription', {'plan_id': plan, 'days': 30}),
                      done: t('admin.granted', {'p': plan.toUpperCase()}), reload: [path]),
                  child: Text(t('admin.grant', {'p': plan.toUpperCase()})),
                ),
              OutlinedButton(
                onPressed: () => act(context, ref, () => api.delete('/users/$uid/subscription'), reload: [path]),
                child: Text(t('admin.revoke_sub')),
              ),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: restricted ? Tokens.success : Tokens.danger),
                onPressed: () async {
                  if (restricted) {
                    await act(context, ref, () => api.post('/users/$uid/restore'), reload: [path]);
                    return;
                  }
                  final reason = await promptText(context, t, title: t('admin.restrict'), hint: t('admin.reason'), maxLength: 300);
                  if (reason != null && reason.length >= 2 && context.mounted) {
                    await act(context, ref, () => api.post('/users/$uid/restrict', {'reason': reason}), reload: [path]);
                  }
                },
                child: Text(restricted ? t('admin.restore') : t('admin.restrict')),
              ),
            ]),
          ],
        ]);
      }),
    );
  }
}

class AdminConnectionsScreen extends ConsumerWidget {
  const AdminConnectionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('admin.connections'),
      body: ApiView('/connections?all=true', builder: (context, ref, d) {
        final items = asMaps(d['items']);
        return ListView(padding: pagePadding, children: [
          if (items.isEmpty) EmptyView(t('admin.no_connections')),
          for (final c in items)
            GlassCard(
              onTap: () => context.push('/admin/users/${c['user_id']}'),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(c['username'] == null ? 'ID ${c['user_id']}' : '@${c['username']}', style: const TextStyle(fontWeight: FontWeight.w600))),
                  Text(str(c['status_title'])),
                ]),
                KVRow(t('admin.rights_granted'), '${asMap(c['rights']).values.where(flag).length} / ${asMap(c['rights']).length}'),
                KVRow(t('profile.modules'), '${integer(c['available_modules'])} / ${integer(c['total_modules'])}'),
                KVRow(t('admin.last_event'), fmtTime(c['last_event_at'])),
                if (flag(c['paused'])) Text(t('admin.paused_by_owner'), style: const TextStyle(color: Tokens.warning)),
              ]),
            ),
        ]);
      }),
    );
  }
}

class AdminPermissionsScreen extends ConsumerWidget {
  const AdminPermissionsScreen({super.key});

  static const keyRights = ['can_reply', 'can_read_messages', 'can_delete_sent_messages', 'can_delete_all_messages'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('admin.permissions'),
      body: ApiView('/admin/chat-controls', builder: (context, ref, cc) {
        final active = asMap(cc['active']);
        return ListView(padding: pagePadding, children: [
          SectionHeader(t('admin.controls_active')),
          GlassCard(
            child: Column(children: [
              if (active.isEmpty) Text(t('admin.controls_none'), style: const TextStyle(color: Tokens.textSecondary)),
              for (final e in active.entries) KVRow(t('controls.${e.key}'), '${e.value}'),
              KVRow(t('admin.cards'), '${integer(cc['cards'])}'),
              KVRow(t('admin.filter_events'), '${asList(cc['filter_events_24h']).length}'),
            ]),
          ),
          SectionHeader(t('admin.rights_matrix')),
          ApiView('/connections?all=true', builder: (context, ref, d) {
            final items = asMaps(d['items']);
            return GlassCard(
              child: Column(children: [
                for (final r in keyRights)
                  KVRow(t('right.$r'), '${items.where((c) => flag(asMap(c['rights'])[r])).length} / ${items.length}'),
              ]),
            );
          }),
        ]);
      }),
    );
  }
}

class AdminAiScreen extends ConsumerWidget {
  const AdminAiScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.ai'),
      body: ApiView('/ai/providers', builder: (context, ref, d) {
        final items = asMaps(d['items']);
        final disabled = items.where((p) => flag(p['disabled'])).map((p) => str(p['name'])).toSet();
        return ListView(padding: pagePadding, children: [
          for (final p in items)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(str(p['name']), style: Theme.of(context).textTheme.titleMedium)),
                  Pill(flag(p['configured']) ? t('admin.key_set') : t('admin.no_key'), color: flag(p['configured']) ? Tokens.success : Tokens.textMuted),
                ]),
                KVRow(t('admin.model'), str(p['model'])),
                SwitchRow(
                  title: t('admin.provider_enabled'),
                  value: !flag(p['disabled']),
                  onChanged: (on) {
                    final next = {...disabled};
                    on ? next.remove(p['name']) : next.add(str(p['name']));
                    act(context, ref, () => api.patch('/ai/system', {'disabled': next.toList()}), reload: ['/ai/providers']);
                  },
                ),
              ]),
            ),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('admin.default_provider'), style: const TextStyle(color: Tokens.textSecondary)),
              const SizedBox(height: Tokens.xs),
              ChoiceRow(
                options: ['auto', ...items.map((p) => str(p['name']))],
                selected: str(d['default'], 'auto'),
                onSelected: (v) => act(context, ref, () => api.patch('/ai/system', {'default_provider': v}), reload: ['/ai/providers']),
              ),
              const SizedBox(height: Tokens.sm),
              OutlinedButton.icon(
                onPressed: () => act(context, ref, () => api.post('/ai/providers/check'), done: t('admin.checked'), reload: ['/ai/providers']),
                icon: const Icon(Icons.network_check_rounded),
                label: Text(t('admin.check_providers')),
              ),
            ]),
          ),
          SectionHeader(t('admin.ai_usage')),
          ApiView('/ai/usage?scope=global', builder: (context, ref, u) {
            return GlassCard(
              child: Column(children: [
                KVRow(t('ai.today_requests'), '${integer(u['today_requests'])}'),
                KVRow(t('ai.today_cost'), '\$${number(u['today_cost']).toStringAsFixed(4)}'),
                KVRow(t('admin.budget'), u['daily_budget_usd'] == null ? '—' : '\$${u['daily_budget_usd']}'),
                const SizedBox(height: Tokens.xs),
                SparkBars(SparkBars.fromSeries(u['cost_series']), color: Tokens.warning),
              ]),
            );
          }),
        ]);
      }),
    );
  }
}

class AdminMediaScreen extends ConsumerWidget {
  const AdminMediaScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.media'),
      body: ApiView('/media/stats?scope=global', builder: (context, ref, d) {
        final q = asMap(d['queue']);
        final tmp = asMap(d['tmp']);
        return ListView(padding: pagePadding, children: [
          StatGrid([
            StatTile(label: t('admin.queued'), value: '${integer(q['queued'])}', icon: Icons.queue_rounded),
            StatTile(label: t('admin.processed'), value: '${integer(q['processed'])}', icon: Icons.done_all_rounded, color: Tokens.success),
            StatTile(label: t('admin.failed'), value: '${integer(q['failed'])}', icon: Icons.error_outline, color: Tokens.danger),
            StatTile(label: t('admin.tmp'), value: '${(integer(tmp['bytes']) / 1048576).toStringAsFixed(1)} MB', icon: Icons.folder_outlined, color: Tokens.cyan),
          ]),
          const SizedBox(height: Tokens.sm),
          OutlinedButton.icon(
            onPressed: () => act(context, ref, () => api.post('/media/cleanup'), done: t('admin.cleaned'), reload: ['/media/stats?scope=global']),
            icon: const Icon(Icons.cleaning_services_outlined),
            label: Text(t('admin.cleanup_tmp')),
          ),
          SectionHeader(t('admin.limits')),
          ApiView('/media/settings', builder: (context, ref, s) {
            Future<void> setLimit(String key, String title, int current) async {
              final v = await promptText(context, t, title: title, initial: '$current');
              final n = int.tryParse(v ?? '');
              if (n != null && context.mounted) await act(context, ref, () => api.patch('/media/settings', {key: n}), reload: ['/media/settings']);
            }

            return GlassCard(
              child: Column(children: [
                for (final e in const {'max_input_mb': 'MB', 'max_duration': 's', 'max_reverse_video': 's', 'timeout': 's'}.entries)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(t('admin.media.${e.key}')),
                    subtitle: Text('${integer(s[e.key])} ${e.value}'),
                    trailing: const Icon(Icons.edit_outlined),
                    onTap: () => setLimit(e.key, t('admin.media.${e.key}'), integer(s[e.key])),
                  ),
              ]),
            );
          }),
          SectionHeader(t('media.jobs')),
          const MediaJobsList(path: '/media/jobs?scope=global'),
        ]);
      }),
    );
  }
}

class AdminGamesScreen extends ConsumerWidget {
  const AdminGamesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('admin.games'),
      body: ApiView('/games/sessions?scope=global', builder: (context, ref, d) {
        final items = asMaps(d['items']);
        return ListView(padding: pagePadding, children: [
          SectionHeader(t('admin.game_sessions', {'n': items.length})),
          if (items.isEmpty) GlassCard(child: EmptyView(t('admin.no_sessions'), icon: Icons.sports_esports_outlined)),
          for (final g in items)
            GlassCard(
              child: Row(children: [
                Expanded(child: Text('${str(g['game'])} · #${g['id']} · ${fmtTime(g['created_at'])}')),
                TextButton(
                  onPressed: () => act(context, ref, () => ref.read(apiProvider).post('/games/sessions/${g['id']}/end'),
                      reload: ['/games/sessions?scope=global']),
                  child: Text(t('admin.end')),
                ),
              ]),
            ),
        ]);
      }),
    );
  }
}

class AdminCommandsScreen extends ConsumerStatefulWidget {
  const AdminCommandsScreen({super.key});

  @override
  ConsumerState<AdminCommandsScreen> createState() => _AdminCommandsScreenState();
}

class _AdminCommandsScreenState extends ConsumerState<AdminCommandsScreen> {
  String _q = '';

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.commands'),
      body: ApiView('/commands', builder: (context, ref, d) {
        final items = asMaps(d['items']).where((c) => _q.isEmpty || str(c['id']).contains(_q)).toList();
        return ListView(padding: pagePadding, children: [
          TextField(
            onChanged: (v) => setState(() => _q = v.trim().toLowerCase()),
            decoration: InputDecoration(hintText: t('cmd.search', {'n': integer(d['count'])}), prefixIcon: const Icon(Icons.search_rounded)),
          ),
          const SizedBox(height: Tokens.xs),
          GlassCard(child: Text(t('admin.commands_hint'), style: Theme.of(context).textTheme.bodySmall)),
          for (final c in items)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(
                    child: Text('${str(c['name'])}${flag(c['admin_only']) ? '  👑' : ''}',
                        style: const TextStyle(fontWeight: FontWeight.w700, fontFamily: 'monospace')),
                  ),
                  Text('${integer(c['calls_total'])} · ${integer(c['errors_total'])}⚠', style: Theme.of(context).textTheme.bodySmall),
                  Switch(
                    value: flag(c['enabled_global']),
                    onChanged: (v) => act(context, ref, () => api.patch('/commands/${c['id']}/global', {'enabled': v}), reload: ['/commands']),
                  ),
                ]),
                Wrap(spacing: 6, children: [
                  for (final plan in const ['free', 'plus', 'pro', 'vip'])
                    ChoiceChip(
                      label: Text(plan.toUpperCase()),
                      selected: str(c['min_plan']) == plan,
                      onSelected: (_) => act(context, ref, () => api.patch('/commands/${c['id']}/global', {'min_plan': plan}), reload: ['/commands']),
                    ),
                ]),
                if (c['last_error'] != null) Text(str(c['last_error']), style: const TextStyle(color: Tokens.danger, fontSize: Tokens.caption)),
              ]),
            ),
        ]);
      }),
    );
  }
}

class AdminPaymentsScreen extends ConsumerWidget {
  const AdminPaymentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.payments'),
      body: ApiView('/subscriptions/stats', builder: (context, ref, st) {
        return ListView(padding: pagePadding, children: [
          StatGrid([
            StatTile(label: t('stat.revenue_stars'), value: '${integer(st['revenue_stars'])} ⭐', icon: Icons.star_rounded, color: Tokens.warning),
            StatTile(label: t('admin.expiring'), value: '${integer(st['expiring_3d'])}', icon: Icons.timer_outlined, color: Tokens.danger),
          ]),
          const SizedBox(height: Tokens.sm),
          GlassCard(
            child: Column(children: [
              for (final e in asMap(st['active_by_plan']).entries) KVRow(e.key.toUpperCase(), '${e.value}'),
            ]),
          ),
          SectionHeader(t('admin.payments_list')),
          ApiView('/payments?scope=global', builder: (context, ref, d) {
            final items = asMaps(d['items']);
            return Column(children: [
              if (!flag(d['enabled'])) GlassCard(child: Text(t('admin.payments_off'), style: const TextStyle(color: Tokens.warning))),
              if (items.isEmpty) GlassCard(child: EmptyView(t('admin.no_payments'), icon: Icons.receipt_outlined)),
              for (final p in items)
                GlassCard(
                  child: Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${integer(p['amount'])} ⭐ · ${str(p['plan_id']).toUpperCase()} · ID ${p['user_id']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                        Text('${str(p['status'])} · ${fmtTime(p['created_at'])}', style: Theme.of(context).textTheme.bodySmall),
                      ]),
                    ),
                    if (p['status'] == 'paid')
                      TextButton(
                        onPressed: () async {
                          if (await confirmDialog(context, t, title: t('admin.refund'), body: t('admin.refund_body', {'n': integer(p['amount'])}), danger: true) &&
                              context.mounted) {
                            await act(context, ref, () => api.post('/payments/${p['id']}/refund', {'confirm': true}), reload: ['/payments?scope=global']);
                          }
                        },
                        child: Text(t('admin.refund'), style: const TextStyle(color: Tokens.danger)),
                      ),
                  ]),
                ),
            ]);
          }),
          SectionHeader(t('admin.promo')),
          ApiView('/subscriptions/promo', builder: (context, ref, d) {
            return GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                for (final p in asMaps(d['items']))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(str(p['code']), style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w700)),
                    subtitle: Text('${str(p['plan_id']).toUpperCase()} · ${integer(p['days'])} d · ${integer(p['used_count'])}/${integer(p['max_uses'])}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () => act(context, ref, () => api.delete('/subscriptions/promo/${p['code']}'), reload: ['/subscriptions/promo']),
                    ),
                  ),
                Wrap(spacing: 6, children: [
                  for (final plan in const ['plus', 'pro', 'vip'])
                    OutlinedButton(
                      onPressed: () => act(context, ref, () => api.post('/subscriptions/promo', {'plan_id': plan, 'days': 30, 'max_uses': 1}),
                          done: t('admin.promo_created'), reload: ['/subscriptions/promo']),
                      child: Text(t('admin.promo_new', {'p': plan.toUpperCase()})),
                    ),
                ]),
              ]),
            );
          }),
        ]);
      }),
    );
  }
}

class AdminBroadcastScreen extends ConsumerWidget {
  const AdminBroadcastScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.broadcast'),
      floating: FloatingActionButton.extended(
        onPressed: () async {
          final text = await promptText(context, t, title: t('admin.bc_new'), hint: t('admin.bc_text'), maxLines: 6, maxLength: 4096);
          if (text == null || text.isEmpty || !context.mounted) return;
          await act(context, ref, () => api.post('/broadcasts', {'text': text, 'segment': <String, dynamic>{}}), done: t('admin.bc_draft'), reload: ['/broadcasts']);
        },
        icon: const Icon(Icons.add),
        label: Text(t('admin.bc_new')),
      ),
      body: ApiView('/broadcasts', builder: (context, ref, d) {
        final items = asMaps(d['items']);
        return ListView(padding: pagePadding, children: [
          GlassCard(child: Text(t('admin.bc_hint'), style: Theme.of(context).textTheme.bodySmall)),
          if (items.isEmpty) EmptyView(t('admin.bc_none'), icon: Icons.campaign_outlined),
          for (final b in items)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text('#${b['id']} · ${str(b['status'])}', style: const TextStyle(fontWeight: FontWeight.w600))),
                  Text('${integer(b['sent'])}/${integer(b['total'])}'),
                ]),
                const SizedBox(height: Tokens.xxs),
                Text(stripHtml(str(b['text'])), maxLines: 4, overflow: TextOverflow.ellipsis),
                if (b['status'] == 'draft')
                  Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                    TextButton(
                      onPressed: () => act(context, ref, () => api.post('/broadcasts/${b['id']}/preview'), done: t('admin.bc_preview_sent')),
                      child: Text(t('admin.bc_preview')),
                    ),
                    TextButton(
                      onPressed: () => act(context, ref, () => api.post('/broadcasts/${b['id']}/cancel'), reload: ['/broadcasts']),
                      child: Text(t('common.cancel')),
                    ),
                    FilledButton(
                      onPressed: () async {
                        final est = await api.post('/broadcasts/estimate', <String, dynamic>{});
                        if (!context.mounted) return;
                        if (await confirmDialog(context, t,
                                title: t('admin.bc_start'), body: t('admin.bc_start_body', {'n': integer(est['recipients'])}), danger: true) &&
                            context.mounted) {
                          await act(context, ref, () => api.post('/broadcasts/${b['id']}/start', {'confirm': true}), reload: ['/broadcasts']);
                        }
                      },
                      child: Text(t('admin.bc_start')),
                    ),
                  ]),
              ]),
            ),
          const SizedBox(height: 72),
        ]);
      }),
    );
  }
}

class AdminSecurityScreen extends ConsumerWidget {
  const AdminSecurityScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.security'),
      body: ApiView('/security/suspicious', builder: (context, ref, s) {
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Column(children: [
              KVRow(t('admin.lockout'), flag(s['lockout_active']) ? t('admin.lockout_on', {'t': fmtTime(s['lockout_until'])}) : '—'),
              KVRow(t('admin.failed_ips'), '${asList(s['failed_by_ip']).length}'),
              KVRow(t('admin.rate_blocked'), '${integer(s['rate_limiter_blocked'])}'),
              KVRow(t('admin.loop_guard'), '${integer(asMap(s['loop_guard'])['tripped_chats'])}'),
            ]),
          ),
          Row(children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () async {
                  if (await confirmDialog(context, t, title: t('admin.revoke_all'), body: t('admin.revoke_all_body'), danger: true) && context.mounted) {
                    await act(context, ref, () => api.post('/security/revoke-all'), reload: ['/security/sessions']);
                  }
                },
                child: Text(t('admin.revoke_all')),
              ),
            ),
            const SizedBox(width: Tokens.sm),
            Expanded(
              child: FilledButton(
                style: FilledButton.styleFrom(backgroundColor: Tokens.danger),
                onPressed: () => _emergency(context, ref, true),
                child: Text(t('admin.es')),
              ),
            ),
          ]),
          SectionHeader(t('admin.logins')),
          ApiView('/security/logins', builder: (context, ref, d) {
            return GlassCard(
              child: Column(children: [
                for (final l in asMaps(d['items']).take(20))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(flag(l['success']) ? Icons.login_rounded : Icons.block_rounded, color: flag(l['success']) ? Tokens.success : Tokens.danger),
                    title: Text('${str(l['device_name'], '—')} · ${str(l['reason'])}'),
                    subtitle: Text('${str(l['ip'])} · ID ${str(l['user_id'], '—')} · ${fmtTime(l['created_at'])}'),
                  ),
              ]),
            );
          }),
          SectionHeader(t('admin.sessions')),
          ApiView('/security/sessions', builder: (context, ref, d) {
            return GlassCard(
              child: Column(children: [
                for (final se in asMaps(d['items']).where((x) => x['revoked_at'] == null))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text('${str(se['device_name'])} · ID ${se['user_id']}'),
                    subtitle: Text('${str(se['last_ip'])} · ${fmtTime(se['last_used_at'])}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.logout_rounded, color: Tokens.danger),
                      onPressed: () => act(context, ref, () => api.delete('/security/sessions/${se['id']}'), reload: ['/security/sessions']),
                    ),
                  ),
              ]),
            );
          }),
          SectionHeader(t('admin.audit')),
          ApiView('/security/audit', builder: (context, ref, d) {
            return GlassCard(
              child: Column(children: [
                for (final a in asMaps(d['items']).take(50))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(str(a['action']), style: TextStyle(color: str(a['action']).startsWith('security.') ? Tokens.warning : null)),
                    subtitle: Text('${str(a['actor_type'])} ${str(a['actor_id'])} → ${str(a['target_type'])} ${str(a['target_id'])}'),
                    trailing: Text(fmtTime(a['created_at']), style: Theme.of(context).textTheme.bodySmall),
                  ),
              ]),
            );
          }),
        ]);
      }),
    );
  }
}

class AdminSystemScreen extends ConsumerWidget {
  const AdminSystemScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('admin.system'),
      body: ApiView('/system/status', builder: (context, ref, d) {
        final res = asMap(d['resources']);
        final runtime = asMap(d['runtime']);
        final paused = asList(runtime['paused_modules']).map((e) => '$e').toSet();
        final sched = asMap(d['scheduler']);
        return ListView(padding: pagePadding, children: [
          StatGrid([
            StatTile(label: 'RAM', value: '${integer(res['process_rss_mb'])} MB', icon: Icons.memory_rounded),
            StatTile(label: 'CPU', value: '${number(res['cpu_percent']).toStringAsFixed(0)}%', icon: Icons.speed_rounded, color: Tokens.cyan),
            StatTile(label: t('admin.disk_free'), value: '${integer(asMap(res['disk'])['free_mb'])} MB', icon: Icons.sd_storage_outlined, color: Tokens.success),
            StatTile(label: t('admin.uptime'), value: fmtDuration(res['uptime_sec']), icon: Icons.timer_outlined, color: Tokens.violet),
          ]),
          SectionHeader(t('admin.modules')),
          GlassCard(
            child: Column(children: [
              for (final m in asList(runtime['modules']).map((e) => '$e'))
                SwitchRow(
                  title: m,
                  value: !paused.contains(m),
                  onChanged: (on) {
                    final next = {...paused};
                    on ? next.remove(m) : next.add(m);
                    act(context, ref, () => api.put('/system/modules', {'paused': next.toList()}), reload: ['/system/status']);
                  },
                ),
            ]),
          ),
          SectionHeader(t('admin.scheduler')),
          GlassCard(
            child: Column(children: [
              KVRow(t('admin.runs'), '${integer(sched['runs'])} · ${t('admin.failures')} ${integer(sched['failures'])}'),
              for (final j in asMaps(sched['jobs']))
                KVRow(str(j['name']), '${fmtDuration(j['interval'])} · ${integer(j['runs'])}', valueColor: j['last_error'] == null ? null : Tokens.danger),
            ]),
          ),
          SectionHeader(t('admin.maintenance_ops')),
          Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
            OutlinedButton(onPressed: () => act(context, ref, () => api.post('/system/backup', <String, dynamic>{}), done: t('admin.backup_done'), reload: ['/system/backups']), child: Text(t('admin.backup'))),
            OutlinedButton(onPressed: () => act(context, ref, () => api.post('/system/cleanup'), done: t('admin.cleaned')), child: Text(t('admin.cleanup'))),
            for (final c in const ['media_queue', 'scheduler', 'ai_clients'])
              OutlinedButton(
                onPressed: () => act(context, ref, () => api.post('/system/restart/$c'), done: t('admin.restarted', {'c': c}), reload: ['/system/status']),
                child: Text(t('admin.restart', {'c': c})),
              ),
          ]),
          SectionHeader(t('admin.backups')),
          ApiView('/system/backups', builder: (context, ref, b) {
            final items = asMaps(b['items']);
            return GlassCard(
              child: Column(children: [
                KVRow(t('admin.backup_every'), '${integer(b['interval_hours'])} h · keep ${integer(b['keep'])}'),
                if (items.isEmpty) Text(t('admin.no_backups'), style: const TextStyle(color: Tokens.textSecondary)),
                for (final f in items.take(10)) KVRow(str(f['name']), '${(integer(f['size']) / 1024).toStringAsFixed(0)} KB · ${fmtTime(f['created_at'])}'),
              ]),
            );
          }),
        ]);
      }),
    );
  }
}

class AdminLogsScreen extends ConsumerStatefulWidget {
  const AdminLogsScreen({super.key});

  @override
  ConsumerState<AdminLogsScreen> createState() => _AdminLogsScreenState();
}

class _AdminLogsScreenState extends ConsumerState<AdminLogsScreen> {
  String _level = 'WARNING';

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final path = '/system/logs?limit=300${_level == 'ALL' ? '' : '&level=$_level'}';
    return AppScaffold(
      title: t('admin.logs'),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Tokens.md),
          child: ChoiceRow(options: const ['ALL', 'INFO', 'WARNING', 'ERROR'], selected: _level, onSelected: (l) => setState(() => _level = l)),
        ),
        Expanded(
          child: ApiView(path, builder: (context, ref, d) {
            final items = asMaps(d['items']);
            return ListView(padding: pagePadding, children: [
              if (items.isEmpty) EmptyView(t('admin.no_logs'), icon: Icons.check_circle_outline),
              for (final l in items.reversed)
                GlassCard(
                  padding: const EdgeInsets.all(Tokens.sm),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Pill(str(l['level']), color: l['level'] == 'ERROR' ? Tokens.danger : l['level'] == 'WARNING' ? Tokens.warning : Tokens.cyan),
                      const SizedBox(width: 6),
                      Expanded(child: Text(str(l['logger']), style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
                      Text(fmtTime(l['ts'], withDate: false), style: Theme.of(context).textTheme.bodySmall),
                    ]),
                    const SizedBox(height: 4),
                    SelectableText(str(l['message']), style: const TextStyle(fontFamily: 'monospace', fontSize: Tokens.caption)),
                  ]),
                ),
            ]);
          }),
        ),
      ]),
    );
  }
}

class AdminDiagnosticsScreen extends ConsumerWidget {
  const AdminDiagnosticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('admin.diagnostics'),
      body: ApiView('/system/checks', builder: (context, ref, d) {
        final checks = asMap(d['checks']);
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Row(children: [
              Icon(flag(d['ok']) ? Icons.verified_rounded : Icons.report_problem_outlined, color: flag(d['ok']) ? Tokens.success : Tokens.warning, size: 32),
              const SizedBox(width: Tokens.sm),
              Expanded(child: Text(flag(d['ok']) ? t('admin.all_ok') : t('admin.has_issues'), style: Theme.of(context).textTheme.titleMedium)),
              Text(fmtTime(d['ts'], withDate: false), style: Theme.of(context).textTheme.bodySmall),
            ]),
          ),
          for (final e in checks.entries)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(flag(asMap(e.value)['ok']) ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                      color: flag(asMap(e.value)['ok']) ? Tokens.success : Tokens.warning),
                  const SizedBox(width: Tokens.xs),
                  Text(e.key, style: const TextStyle(fontWeight: FontWeight.w600)),
                ]),
                for (final kv in asMap(e.value).entries.where((x) => x.key != 'ok'))
                  KVRow(kv.key, kv.value is Map ? (flag(asMap(kv.value)['configured']) ? '✅' : '—') : '${kv.value}'),
              ]),
            ),
          SectionHeader(t('admin.db')),
          ApiView('/system/db-integrity', builder: (context, ref, db) {
            return GlassCard(
              child: Column(children: [
                KVRow(t('admin.db_size'), '${(integer(db['bytes']) / 1048576).toStringAsFixed(2)} MB'),
                KVRow(t('admin.schema'), 'v${integer(db['schema_version'])}'),
                KVRow('integrity_check', asList(db['integrity']).join(', ')),
                KVRow(t('admin.fk_errors'), '${integer(db['foreign_key_errors'])}'),
              ]),
            );
          }),
        ]);
      }),
    );
  }
}

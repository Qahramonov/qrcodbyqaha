import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';

class ChatsScreen extends ConsumerStatefulWidget {
  const ChatsScreen({super.key});

  @override
  ConsumerState<ChatsScreen> createState() => _ChatsScreenState();
}

class _ChatsScreenState extends ConsumerState<ChatsScreen> {
  String _q = '';
  int _page = 1;
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final path = '/chats?page=$_page&page_size=30${_q.isEmpty ? '' : '&q=${Uri.encodeQueryComponent(_q)}'}';
    return AppScaffold(
      title: t('nav.chats'),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Tokens.md, 0, Tokens.md, Tokens.xs),
          child: TextField(
            controller: _search,
            textInputAction: TextInputAction.search,
            onSubmitted: (v) => setState(() {
              _q = v.trim();
              _page = 1;
            }),
            decoration: InputDecoration(hintText: t('chats.search'), prefixIcon: const Icon(Icons.search_rounded)),
          ),
        ),
        Expanded(
          child: ApiView(path, builder: (context, ref, d) {
            final items = asMaps(d['items']);
            final total = integer(d['total']);
            final pages = (total / 30).ceil();
            return ListView(padding: pagePadding, children: [
              if (items.isEmpty) EmptyView(t('chats.empty'), icon: Icons.forum_outlined),
              for (final c in items) _ChatTile(c),
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

class _ChatTile extends ConsumerWidget {
  const _ChatTile(this.c);

  final Json c;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final title = str(c['title'], '#${c['chat_id']}');
    final unanswered = integer(c['unanswered']);
    final muted = integer(c['muted_until']) > DateTime.now().millisecondsSinceEpoch ~/ 1000;
    return GlassCard(
      onTap: () => context.push('/chats/${c['chat_id']}'),
      child: Row(children: [
        CircleAvatar(
          backgroundColor: Tokens.violet.withValues(alpha: 0.3),
          child: Text(title.isEmpty ? '?' : title.characters.first.toUpperCase()),
        ),
        const SizedBox(width: Tokens.sm),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Flexible(child: Text(title, style: const TextStyle(fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
              if (c['username'] != null)
                Flexible(
                    child: Text('  @${c['username']}', style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
            ]),
            const SizedBox(height: 2),
            Text(str(c['last_preview']), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Tokens.textSecondary)),
          ]),
        ),
        const SizedBox(width: Tokens.xs),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(fmtTime(c['last_incoming_at'], withDate: false), style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 4),
          Row(mainAxisSize: MainAxisSize.min, children: [
            if (muted) const Icon(Icons.volume_off_rounded, size: 16, color: Tokens.warning),
            if (flag(c['whitelisted'])) const Icon(Icons.star_rounded, size: 16, color: Tokens.success),
            if (unanswered > 0) ...[const SizedBox(width: 4), Pill('$unanswered', color: Tokens.warning)],
          ]),
          if (flag(c['ignored'])) Text(t('chats.ignored'), style: Theme.of(context).textTheme.bodySmall),
        ]),
      ]),
    );
  }
}

/// Per-chat controls: the same modules as the inline control cards in Telegram (.mute, .protect, .nogif, .nomute).
class ChatControlsScreen extends ConsumerWidget {
  const ChatControlsScreen({super.key, required this.chatId});

  final int chatId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final path = '/chats/$chatId/controls';
    return AppScaffold(
      title: t('controls.title'),
      body: ApiView(path, builder: (context, ref, d) {
        final modules = asMap(d['modules']);
        final chat = asMap(d['chat']);
        final api = ref.read(apiProvider);

        Future<void> setModule(String module, bool enabled, {int? untilFor}) async {
          var confirm = false;
          if (module == 'mute' && enabled && flag(d['mute_confirm_required'])) {
            confirm = await confirmDialog(context, t, title: t('controls.mute_confirm_title'), body: t('controls.mute_confirm_body'));
            if (!confirm) return;
          }
          if (!context.mounted) return;
          await act(context, ref, () => api.patch(path, {
                'module': module,
                'enabled': enabled,
                'until_for': ?untilFor,
                if (confirm) 'confirm': true,
              }), reload: [path, '/mute', '/protect']);
        }

        Future<void> setChat(String key, Object? value) =>
            act(context, ref, () => api.patch('/chats/$chatId', {key: value}), reload: [path, '/chats/$chatId']);

        Widget moduleTile(String module, IconData icon) {
          final m = asMap(modules[module]);
          final on = flag(m['enabled']);
          final until = m['until_at'];
          return GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(icon, color: on ? Tokens.warning : Tokens.textSecondary),
                const SizedBox(width: Tokens.sm),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(t('controls.$module'), style: const TextStyle(fontWeight: FontWeight.w600)),
                    Text(t('controls.${module}_hint'), style: Theme.of(context).textTheme.bodySmall),
                    if (on && until != null) Text(t('controls.until', {'t': fmtTime(until)}), style: Theme.of(context).textTheme.bodySmall),
                  ]),
                ),
                Switch(key: Key('module-$module'), value: on, onChanged: (v) => setModule(module, v)),
              ]),
              if (module == 'mute' && !on)
                Wrap(spacing: Tokens.xs, children: [
                  for (final p in const [600, 3600, 86400])
                    ActionChip(
                      label: Text(t('controls.for_${p}s')),
                      onPressed: () => setModule('mute', true, untilFor: p),
                    ),
                ]),
            ]),
          );
        }

        return ListView(padding: pagePadding, children: [
          Text(str(d['title'], '#$chatId'), style: Theme.of(context).textTheme.headlineMedium),
          if (d['username'] != null) Text('@${d['username']}', style: const TextStyle(color: Tokens.textSecondary)),
          SectionHeader(t('controls.modules')),
          moduleTile('mute', Icons.volume_off_outlined),
          moduleTile('protect', Icons.shield_outlined),
          moduleTile('nogif', Icons.gif_box_outlined),
          moduleTile('nomute', Icons.notifications_paused_outlined),
          SectionHeader(t('controls.chat_settings')),
          GlassCard(
            child: Column(children: [
              for (final key in const ['autoreply_enabled', 'ai_enabled', 'afk_enabled'])
                SwitchRow(
                  title: t('controls.$key'),
                  subtitle: chat[key] == null ? t('controls.default') : null,
                  value: chat[key] == null ? true : flag(chat[key]),
                  onChanged: (v) => setChat(key, v),
                ),
              SwitchRow(title: t('controls.ignored'), subtitle: t('controls.ignored_hint'), value: flag(chat['ignored']), onChanged: (v) => setChat('ignored', v)),
            ]),
          ),
          SectionHeader(t('controls.danger')),
          GlassCard(
            child: Column(children: [
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.history_toggle_off_rounded, color: Tokens.warning),
                title: Text(t('controls.clear_history')),
                subtitle: Text(t('controls.clear_history_hint'), style: Theme.of(context).textTheme.bodySmall),
                onTap: () async {
                  if (await confirmDialog(context, t, title: t('controls.clear_history'), body: t('controls.clear_history_hint'), danger: true) &&
                      context.mounted) {
                    await act(context, ref, () => api.delete('/chats/$chatId/history'), done: t('common.done'));
                  }
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.delete_forever_outlined, color: Tokens.danger),
                title: Text(t('controls.delete_data')),
                subtitle: Text(t('controls.delete_data_hint'), style: Theme.of(context).textTheme.bodySmall),
                onTap: () async {
                  if (await confirmDialog(context, t, title: t('controls.delete_data'), body: t('controls.delete_data_hint'), danger: true) &&
                      context.mounted) {
                    final ok = await act(context, ref, () => api.delete('/chats/$chatId/data'), done: t('common.done'), reload: ['/chats?page=1&page_size=30']);
                    if (ok && context.mounted) context.pop();
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

/// Business bot rights as granted in Telegram → which features and commands work.
class PermissionsScreen extends ConsumerWidget {
  const PermissionsScreen({super.key});

  static const dangerous = {'can_transfer_stars', 'can_transfer_and_upgrade_gifts', 'can_convert_gifts_to_stars'};

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('nav.permissions'),
      body: ApiView('/permissions', builder: (context, ref, d) {
        final conns = asMaps(d['connections']);
        return ListView(padding: pagePadding, children: [
          if (conns.isEmpty) EmptyView(t('perm.none'), icon: Icons.link_off_rounded),
          for (final c in conns) ...[
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(str(c['status_title']), style: Theme.of(context).textTheme.titleMedium)),
                  TextButton.icon(
                    onPressed: () => act(context, ref, () => ref.read(apiProvider).post('/connections/${c['connection_id']}/refresh'),
                        done: t('perm.refreshed'), reload: ['/permissions']),
                    icon: const Icon(Icons.sync_rounded, size: 18),
                    label: Text(t('perm.refresh')),
                  ),
                ]),
                KVRow(t('perm.updated'), fmtTime(c['last_update'])),
                for (final a in asList(c['advice'])) Padding(padding: const EdgeInsets.only(top: 6), child: Text('💡 $a')),
              ]),
            ),
            SectionHeader(t('perm.rights')),
            GlassCard(
              padding: const EdgeInsets.symmetric(horizontal: Tokens.sm, vertical: Tokens.xxs),
              child: Column(children: [
                for (final r in asMaps(c['rights']))
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    leading: Icon(
                      flag(r['granted']) ? (dangerous.contains(r['right']) ? Icons.warning_amber_rounded : Icons.check_circle_rounded) : Icons.cancel_outlined,
                      color: flag(r['granted']) ? (dangerous.contains(r['right']) ? Tokens.danger : Tokens.success) : Tokens.textMuted,
                    ),
                    title: Text(str(r['title'])),
                    subtitle: Text(
                      dangerous.contains(r['right']) && flag(r['granted'])
                          ? t('perm.dangerous')
                          : t('perm.commands', {'n': asList(r['commands']).length}),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    children: [
                      if (asList(r['commands']).isNotEmpty)
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Padding(
                            padding: const EdgeInsets.only(bottom: Tokens.xs),
                            child: Wrap(spacing: 6, runSpacing: 6, children: [for (final cmd in asList(r['commands'])) Pill('.$cmd', color: Tokens.cyan)]),
                          ),
                        ),
                    ],
                  ),
              ]),
            ),
            SectionHeader(t('perm.features')),
            GlassCard(
              child: Column(children: [
                for (final cap in asMaps(c['capabilities']))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    leading: Icon(flag(cap['available']) ? Icons.check_rounded : Icons.lock_outline_rounded,
                        color: flag(cap['available']) ? Tokens.success : Tokens.warning),
                    title: Text(str(cap['description'])),
                    subtitle: flag(cap['available'])
                        ? null
                        : Text(t('perm.needs', {'r': asList(cap['missing_titles']).join(', ')}), style: Theme.of(context).textTheme.bodySmall),
                  ),
              ]),
            ),
          ],
          GlassCard(child: Text(t('perm.how_to_change'), style: Theme.of(context).textTheme.bodySmall)),
        ]);
      }),
    );
  }
}

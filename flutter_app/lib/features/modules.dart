import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import 'ai.dart' show patchSettings;

class AfkScreen extends ConsumerStatefulWidget {
  const AfkScreen({super.key});

  @override
  ConsumerState<AfkScreen> createState() => _AfkScreenState();
}

class _AfkScreenState extends ConsumerState<AfkScreen> {
  final _reason = TextEditingController();
  int? _minutes = 60;
  String _kind = 'afk';

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.afk'),
      body: ApiView('/afk', builder: (context, ref, d) {
        final active = d['active'] == null ? null : asMap(d['active']);
        final stats = asMap(d['stats']);
        return ListView(padding: pagePadding, children: [
          if (active != null)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  const Icon(Icons.bedtime_rounded, color: Tokens.cyan, size: 32),
                  const SizedBox(width: Tokens.sm),
                  Expanded(child: Text(t('afk.active'), style: Theme.of(context).textTheme.titleMedium)),
                ]),
                const SizedBox(height: Tokens.xs),
                if (str(active['reason']).isNotEmpty) KVRow(t('afk.reason'), str(active['reason'])),
                KVRow(t('afk.since'), fmtTime(active['started_at'])),
                if (active['ends_at'] != null) KVRow(t('afk.until'), fmtTime(active['ends_at'])),
                KVRow(t('afk.replied'), '${integer(active['replies_sent'])}'),
                const SizedBox(height: Tokens.sm),
                FilledButton(
                  key: const Key('afk-off'),
                  onPressed: () => act(context, ref, () => api.post('/afk/disable'), done: t('afk.off_done'), reload: ['/afk', '/afk/history']),
                  child: Text(t('afk.turn_off')),
                ),
              ]),
            )
          else
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(t('afk.enable_title'), style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: Tokens.sm),
                TextField(controller: _reason, maxLength: 300, decoration: InputDecoration(labelText: t('afk.reason'), hintText: t('afk.reason_hint'))),
                Text(t('afk.duration'), style: const TextStyle(color: Tokens.textSecondary)),
                const SizedBox(height: Tokens.xs),
                Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
                  for (final m in const [30, 60, 120, 480, 1440, 0])
                    ChoiceChip(
                      label: Text(m == 0 ? t('afk.no_limit') : fmtDuration(m * 60)),
                      selected: (_minutes ?? 0) == m,
                      onSelected: (_) => setState(() => _minutes = m == 0 ? null : m),
                    ),
                ]),
                const SizedBox(height: Tokens.sm),
                ChoiceRow(options: const ['afk', 'sleep'], selected: _kind, labels: (k) => t('afk.kind.$k'), onSelected: (k) => setState(() => _kind = k)),
                const SizedBox(height: Tokens.md),
                FilledButton(
                  key: const Key('afk-on'),
                  onPressed: () => act(
                    context,
                    ref,
                    () => api.post('/afk/enable', {
                      'reason': _reason.text.trim().isEmpty ? null : _reason.text.trim(),
                      'minutes': _minutes,
                      'kind': _kind,
                    }),
                    done: t('afk.on_done'),
                    reload: ['/afk'],
                  ),
                  child: Text(t('afk.turn_on')),
                ),
              ]),
            ),
          SectionHeader(t('afk.stats')),
          StatGrid([
            StatTile(label: t('afk.sessions'), value: '${integer(stats['sessions'])}', icon: Icons.repeat_rounded),
            StatTile(label: t('afk.total'), value: fmtDuration(stats['total_sec']), icon: Icons.timer_outlined, color: Tokens.cyan),
            StatTile(label: t('afk.messages'), value: '${integer(stats['messages'])}', icon: Icons.mark_chat_unread_outlined, color: Tokens.violet),
            StatTile(label: t('afk.replies'), value: '${integer(stats['replies'])}', icon: Icons.quickreply_outlined, color: Tokens.success),
          ]),
          SectionHeader(t('afk.preview')),
          const _AfkPreview(),
          SectionHeader(t('afk.history')),
          const _AfkHistory(),
        ]);
      }),
    );
  }
}

class _AfkPreview extends ConsumerWidget {
  const _AfkPreview();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(jsonProvider('/afk/preview'));
    return GlassCard(
      child: async.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(e),
        data: (d) => Text(stripHtml(str(d['html']))),
      ),
    );
  }
}

class _AfkHistory extends ConsumerWidget {
  const _AfkHistory();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider('/afk/history'));
    return async.when(
      loading: () => const LoadingView(),
      error: (e, _) => ErrorView(e),
      data: (d) {
        final items = asMaps(d['items']);
        if (items.isEmpty) return GlassCard(child: EmptyView(t('afk.no_history'), icon: Icons.history_rounded));
        return GlassCard(
          child: Column(children: [
            for (final h in items.take(20))
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(str(h['reason'], t('afk.no_reason'))),
                subtitle: Text('${fmtTime(h['started_at'])} → ${fmtTime(h['ended_at'])}'),
                trailing: Text('${integer(h['replies_sent'])} ↩︎'),
              ),
          ]),
        );
      },
    );
  }
}

class MuteScreen extends ConsumerWidget {
  const MuteScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.mute'),
      body: ApiView('/mute', builder: (context, ref, d) {
        final defaults = asMap(d['defaults']);
        final types = asList(defaults['types']).map((e) => '$e').toSet();
        final active = asMaps(d['active']);
        final stats = asMap(d['stats_24h']);

        Future<void> save(Map<String, Object?> body) => act(context, ref, () => api.put('/mute/settings', body), reload: ['/mute']);

        return ListView(padding: pagePadding, children: [
          GlassCard(child: Text(t('mute.intro'), style: Theme.of(context).textTheme.bodySmall)),
          StatGrid([
            StatTile(label: t('mute.deleted_24h'), value: '${integer(stats['deleted'])}', icon: Icons.delete_sweep_outlined, color: Tokens.warning),
            StatTile(label: t('mute.failed_24h'), value: '${integer(stats['failed'])}', icon: Icons.error_outline, color: Tokens.danger),
          ]),
          SectionHeader(t('mute.active', {'n': active.length})),
          if (active.isEmpty) GlassCard(child: EmptyView(t('mute.none'), icon: Icons.volume_up_outlined)),
          for (final m in active)
            GlassCard(
              onTap: () => context.push('/chats/${m['chat_id']}'),
              child: Row(children: [
                const Icon(Icons.volume_off_rounded, color: Tokens.warning),
                const SizedBox(width: Tokens.sm),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(str(m['title'], '#${m['chat_id']}'), style: const TextStyle(fontWeight: FontWeight.w600)),
                    Text(t('controls.${str(m['module'], 'mute')}'), style: const TextStyle(color: Tokens.warning, fontSize: Tokens.caption)),
                    Text(m['until_at'] == null ? t('mute.forever') : t('controls.until', {'t': fmtTime(m['until_at'])}),
                        style: Theme.of(context).textTheme.bodySmall),
                  ]),
                ),
                TextButton(
                  onPressed: () => act(
                    context,
                    ref,
                    () => api.patch('/chats/${m['chat_id']}/controls', {'module': str(m['module'], 'mute'), 'enabled': false}),
                    done: t('mute.unmuted'),
                    reload: ['/mute'],
                  ),
                  child: Text(t('mute.unmute')),
                ),
              ]),
            ),
          SectionHeader(t('mute.defaults')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('mute.types'), style: const TextStyle(color: Tokens.textSecondary)),
              const SizedBox(height: Tokens.xs),
              Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
                for (final ty in asList(d['types']).map((e) => '$e'))
                  FilterChip(
                    label: Text(t('mute.type.$ty')),
                    selected: types.contains(ty),
                    onSelected: (on) {
                      final next = {...types};
                      if (ty == 'all') {
                        next
                          ..clear()
                          ..add('all');
                      } else {
                        next.remove('all');
                        on ? next.add(ty) : next.remove(ty);
                        if (next.isEmpty) next.add('all');
                      }
                      save({'types': next.toList()});
                    },
                  ),
              ]),
              SwitchRow(title: t('mute.report'), subtitle: t('mute.report_hint'), value: flag(defaults['report']), onChanged: (v) => save({'report': v})),
              SwitchRow(
                title: t('mute.ask_confirmation'),
                value: flag(d['confirm_required']),
                onChanged: (v) => save({'ask_confirmation': v}),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('mute.whitelist')),
                subtitle: Text(asList(defaults['whitelist']).isEmpty ? t('mute.whitelist_empty') : asList(defaults['whitelist']).join(', ')),
                trailing: const Icon(Icons.edit_outlined),
                onTap: () async {
                  final v = await promptText(context, t,
                      title: t('mute.whitelist'), hint: t('mute.whitelist_hint'), initial: asList(defaults['whitelist']).join(', '));
                  if (v != null && context.mounted) {
                    await save({'whitelist': v.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).take(30).toList()});
                  }
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('mute.keep')),
                subtitle: Text(asList(defaults['keep']).isEmpty ? t('mute.keep_empty') : asList(defaults['keep']).join(', ')),
                trailing: const Icon(Icons.edit_outlined),
                onTap: () async {
                  final v = await promptText(context, t, title: t('mute.keep'), hint: t('mute.keep_hint'), initial: asList(defaults['keep']).join(', '));
                  if (v != null && context.mounted) {
                    await save({'keep': v.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).take(50).toList()});
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

class ProtectScreen extends ConsumerWidget {
  const ProtectScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.protect'),
      body: ApiView('/protect', builder: (context, ref, d) {
        final items = asMaps(d['items']);
        return ListView(padding: pagePadding, children: [
          GlassCard(child: Text(str(d['note'], t('protect.intro')), style: Theme.of(context).textTheme.bodySmall)),
          if (items.isEmpty) GlassCard(child: EmptyView(t('protect.none'), icon: Icons.shield_outlined)),
          for (final p in items)
            GlassCard(
              onTap: () => context.push('/chats/${p['chat_id']}'),
              child: Row(children: [
                const Icon(Icons.shield_rounded, color: Tokens.success),
                const SizedBox(width: Tokens.sm),
                Expanded(child: Text(str(p['title'], '#${p['chat_id']}'), style: const TextStyle(fontWeight: FontWeight.w600))),
                TextButton(
                  onPressed: () => act(context, ref, () => api.patch('/chats/${p['chat_id']}/controls', {'module': 'protect', 'enabled': false}),
                      reload: ['/protect']),
                  child: Text(t('protect.off')),
                ),
              ]),
            ),
          GlassCard(child: Text(t('protect.how'), style: Theme.of(context).textTheme.bodySmall)),
        ]);
      }),
    );
  }
}

class AnimationsScreen extends ConsumerWidget {
  const AnimationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('nav.animations'),
      body: ApiView('/animations', builder: (context, ref, d) => _AnimStudio(data: d, key: ValueKey(d.hashCode))),
    );
  }
}

class _AnimStudio extends ConsumerStatefulWidget {
  const _AnimStudio({super.key, required this.data});

  final Json data;

  @override
  ConsumerState<_AnimStudio> createState() => _AnimStudioState();
}

class _AnimStudioState extends ConsumerState<_AnimStudio> {
  late String type = str(asMap(widget.data['defaults'])['type'], 'typewriter');
  late String speed = str(asMap(widget.data['defaults'])['speed'], 'fast');
  late int repeats = integer(asMap(widget.data['defaults'])['repeats'], 1);
  final _text = TextEditingController(text: 'Chat helper');
  List<String> _frames = const [];
  int _frame = 0;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    _text.dispose();
    super.dispose();
  }

  double get _interval {
    final s = asMaps(widget.data['speeds']).firstWhere((x) => x['id'] == speed, orElse: () => {'interval_sec': 0.5});
    return number(s['interval_sec'], 0.5);
  }

  Future<void> _preview() async {
    final t = ref.read(stringsProvider);
    final text = _text.text.trim();
    if (text.isEmpty) return;
    try {
      final r = await ref.read(apiProvider).post('/animations/preview', {'kind': type, 'text': text});
      _timer?.cancel();
      setState(() {
        _frames = asList(r['frames']).map((e) => '$e').toList();
        _frame = 0;
      });
      _timer = Timer.periodic(Duration(milliseconds: (_interval * 1000).round()), (tm) {
        if (!mounted || _frame >= _frames.length - 1) {
          tm.cancel();
          return;
        }
        setState(() => _frame++);
      });
    } on Object catch (e) {
      if (mounted) toast(context, errorText(t, e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final types = asMaps(widget.data['types']);
    final speeds = asMaps(widget.data['speeds']);
    return ListView(padding: pagePadding, children: [
      GlassCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Container(
            height: 90,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.25), borderRadius: BorderRadius.circular(Tokens.rMd)),
            child: Text(
              _frames.isEmpty ? t('anim.preview_empty') : _frames[_frame],
              key: const Key('anim-frame'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: Tokens.title, fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(height: Tokens.sm),
          TextField(controller: _text, maxLength: 200, decoration: InputDecoration(labelText: t('anim.text'))),
          OutlinedButton.icon(onPressed: _preview, icon: const Icon(Icons.play_circle_outline), label: Text(t('anim.play'))),
        ]),
      ),
      SectionHeader(t('anim.type')),
      GlassCard(
        child: Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
          for (final ty in types)
            ChoiceChip(label: Text(str(ty['title'], str(ty['id']))), selected: ty['id'] == type, onSelected: (_) => setState(() => type = str(ty['id']))),
        ]),
      ),
      SectionHeader(t('anim.speed')),
      GlassCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          ChoiceRow(
            options: speeds.map((s) => str(s['id'])).toList(),
            selected: speed,
            labels: (s) => t('anim.speed.$s'),
            onSelected: (s) => setState(() => speed = s),
          ),
          const SizedBox(height: Tokens.xs),
          Text(t('anim.speed_hint'), style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: Tokens.sm),
          Text(t('anim.repeats'), style: const TextStyle(color: Tokens.textSecondary)),
          ChoiceRow(options: const ['1', '2', '3'], selected: '$repeats', onSelected: (r) => setState(() => repeats = int.parse(r))),
        ]),
      ),
      FilledButton.icon(
        key: const Key('anim-save'),
        onPressed: () => act(context, ref, () => ref.read(apiProvider).put('/animations/settings', {'type': type, 'speed': speed, 'repeats': repeats}),
            reload: ['/animations']),
        icon: const Icon(Icons.save_outlined),
        label: Text(t('anim.save_default')),
      ),
      const SizedBox(height: Tokens.sm),
      Text(t('anim.usage'), style: Theme.of(context).textTheme.bodySmall),
    ]);
  }
}

class MediaScreen extends ConsumerWidget {
  const MediaScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('nav.media'),
      body: ApiView('/media/settings', builder: (context, ref, d) {
        final ff = flag(d['ffmpeg']);
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SwitchRow(
                title: t('media.enabled'),
                subtitle: t('media.enabled_hint'),
                value: flag(d['enabled']),
                onChanged: (v) => patchSettings(context, ref, {'media_enabled': v}, reload: ['/media/settings']),
              ),
              KVRow('FFmpeg', ff ? '✅ ${str(d['ffmpeg_version']).split(' ').take(3).join(' ')}' : t('media.no_ffmpeg'),
                  valueColor: ff ? null : Tokens.warning),
              KVRow(t('media.today'), '${integer(d['used_today'])} / ${d['daily_limit'] ?? '∞'}'),
              KVRow(t('media.max_input'), '${integer(d['max_input_mb'])} MB'),
              KVRow(t('media.max_duration'), fmtDuration(d['max_duration'])),
              if (flag(d['paused_global'])) Text(t('media.paused'), style: const TextStyle(color: Tokens.warning)),
            ]),
          ),
          SectionHeader(t('media.effects')),
          GlassCard(
            child: Wrap(spacing: 6, runSpacing: 6, children: [for (final e in asList(d['demo_effects'])) Pill('.$e', color: Tokens.cyan)]),
          ),
          GlassCard(child: Text(t('media.how'), style: Theme.of(context).textTheme.bodySmall)),
          SectionHeader(t('media.jobs')),
          const _MediaJobs(path: '/media/jobs?scope=self'),
        ]);
      }),
    );
  }
}

class _MediaJobs extends ConsumerWidget {
  const _MediaJobs({required this.path, this.canCancel = false});

  final String path;
  final bool canCancel;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider(path));
    return async.when(
      loading: () => const LoadingView(),
      error: (e, _) => ErrorView(e),
      data: (d) {
        final items = asMaps(d['items']);
        if (items.isEmpty) return GlassCard(child: EmptyView(t('media.no_jobs'), icon: Icons.movie_outlined));
        return Column(children: [
          for (final j in items.take(30))
            GlassCard(
              child: Row(children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('.${str(j['kind'])}  #${j['id']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                    Text('${str(j['status'])} · ${fmtTime(j['created_at'])}', style: Theme.of(context).textTheme.bodySmall),
                    if (str(j['error']).isNotEmpty) Text(str(j['error']), style: const TextStyle(color: Tokens.danger)),
                  ]),
                ),
                if (canCancel && (j['status'] == 'queued' || j['status'] == 'running'))
                  TextButton(
                    onPressed: () => act(context, ref, () => ref.read(apiProvider).post('/media/jobs/${j['id']}/cancel'), reload: [path]),
                    child: Text(t('common.cancel')),
                  ),
              ]),
            ),
        ]);
      },
    );
  }
}

/// Exposed for the admin media screen.
class MediaJobsList extends StatelessWidget {
  const MediaJobsList({super.key, required this.path});

  final String path;

  @override
  Widget build(BuildContext context) => _MediaJobs(path: path, canCancel: true);
}

class GamesScreen extends ConsumerWidget {
  const GamesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.games'),
      body: ApiView('/games', builder: (context, ref, d) {
        final st = asMap(d['settings']);
        Future<void> save(Map<String, Object?> body) => act(context, ref, () => api.patch('/games/settings', body), reload: ['/games']);
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Column(children: [
              SwitchRow(title: t('games.enabled'), subtitle: t('games.enabled_hint'), value: flag(st['games_enabled']), onChanged: (v) => save({'games_enabled': v})),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('games.timeout')),
                subtitle: Text(fmtDuration(st['game_timeout_sec'])),
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  IconButton(
                    onPressed: integer(st['game_timeout_sec']) > 30 ? () => save({'game_timeout_sec': (integer(st['game_timeout_sec']) - 30).clamp(30, 900)}) : null,
                    icon: const Icon(Icons.remove_circle_outline),
                  ),
                  IconButton(
                    onPressed: integer(st['game_timeout_sec']) < 900 ? () => save({'game_timeout_sec': (integer(st['game_timeout_sec']) + 30).clamp(30, 900)}) : null,
                    icon: const Icon(Icons.add_circle_outline),
                  ),
                ]),
              ),
            ]),
          ),
          SectionHeader(t('games.list')),
          GlassCard(
            child: Column(children: [
              for (final g in asMaps(d['items']))
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(flag(g['enabled']) ? Icons.sports_esports : Icons.block, color: flag(g['enabled']) ? Tokens.success : Tokens.textMuted),
                  title: Text(str(g['title'], str(g['id']))),
                  trailing: Pill('.${g['id']}', color: Tokens.cyan),
                ),
            ]),
          ),
          SectionHeader(t('games.leaderboard')),
          const _Leaderboard(),
        ]);
      }),
    );
  }
}

class _Leaderboard extends ConsumerWidget {
  const _Leaderboard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider('/games/leaderboard'));
    return async.when(
      loading: () => const LoadingView(),
      error: (e, _) => ErrorView(e),
      data: (d) {
        final items = asMaps(d['items']);
        if (items.isEmpty) return GlassCard(child: EmptyView(t('games.no_scores'), icon: Icons.emoji_events_outlined));
        return GlassCard(
          child: Column(children: [
            for (var i = 0; i < items.length && i < 20; i++)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: Text('${i + 1}', style: const TextStyle(fontWeight: FontWeight.w700)),
                title: Text(str(items[i]['name'], str(items[i]['player_id']))),
                trailing: Text('${integer(items[i]['wins'])} 🏆 · ${integer(items[i]['rating'])}'),
              ),
          ]),
        );
      },
    );
  }
}

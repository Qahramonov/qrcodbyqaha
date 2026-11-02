import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';

const aiStyles = ['friendly', 'professional', 'funny', 'smart', 'short', 'creative', 'custom'];

Future<void> patchSettings(BuildContext context, WidgetRef ref, Map<String, Object?> values, {List<String> reload = const []}) => act(
      context,
      ref,
      () async {
        await ref.read(apiProvider).patch('/settings', {'values': values});
        await ref.read(sessionProvider.notifier).refresh();
      },
      reload: ['/settings', ...reload],
    );

class AiScreen extends ConsumerWidget {
  const AiScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final s = ref.watch(sessionProvider).settings;
    return AppScaffold(
      title: t('nav.ai'),
      body: ApiView('/ai/providers', builder: (context, ref, prov) {
        final available = flag(prov['available']);
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Row(children: [
              Icon(available ? Icons.auto_awesome : Icons.key_off_outlined, color: available ? Tokens.success : Tokens.warning, size: 32),
              const SizedBox(width: Tokens.sm),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(available ? t('ai.available') : t('ai.unavailable'), style: Theme.of(context).textTheme.titleMedium),
                  Text(available ? t('ai.available_hint') : t('ai.unavailable_hint'), style: Theme.of(context).textTheme.bodySmall),
                ]),
              ),
            ]),
          ),
          Row(children: [
            Expanded(child: OutlinedButton.icon(onPressed: () => context.push('/ai/twin'), icon: const Icon(Icons.face_retouching_natural), label: Text(t('nav.twin')))),
            const SizedBox(width: Tokens.sm),
            Expanded(child: OutlinedButton.icon(onPressed: () => context.push('/ai/playground'), icon: const Icon(Icons.science_outlined), label: Text(t('nav.playground')))),
          ]),
          SectionHeader(t('ai.usage')),
          const _UsageCard(path: '/ai/usage?scope=self'),
          SectionHeader(t('ai.settings')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('ai.style'), style: const TextStyle(color: Tokens.textSecondary)),
              const SizedBox(height: Tokens.xs),
              ChoiceRow(
                options: aiStyles,
                selected: str(s['ai_style'], 'friendly'),
                labels: (v) => t('ai.style.$v'),
                onSelected: (v) => patchSettings(context, ref, {'ai_style': v}),
              ),
              const SizedBox(height: Tokens.xs),
              SwitchRow(
                title: t('ai.confirm'),
                subtitle: t('ai.confirm_hint'),
                value: flag(s['ai_confirm']),
                onChanged: (v) => patchSettings(context, ref, {'ai_confirm': v}),
              ),
              SwitchRow(
                title: t('ai.store_history'),
                subtitle: t('ai.store_history_hint'),
                value: flag(s['ai_store_history']),
                onChanged: (v) => patchSettings(context, ref, {'ai_store_history': v}),
              ),
              SwitchRow(
                title: t('ai.long_memory'),
                value: flag(s['ai_long_memory']),
                onChanged: (v) => patchSettings(context, ref, {'ai_long_memory': v}),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('ai.disclosure')),
                subtitle: Text(str(s['ai_disclosure'], '🤖 AI')),
                trailing: const Icon(Icons.edit_outlined),
                onTap: () async {
                  final v = await promptText(context, t, title: t('ai.disclosure'), initial: str(s['ai_disclosure']), maxLength: 80);
                  if (v != null && v.isNotEmpty && context.mounted) await patchSettings(context, ref, {'ai_disclosure': v});
                },
              ),
            ]),
          ),
          SectionHeader(t('ai.drafts')),
          const _Drafts(),
          SectionHeader(t('ai.memory')),
          const _Memory(),
        ]);
      }),
    );
  }
}

class _UsageCard extends ConsumerWidget {
  const _UsageCard({required this.path});

  final String path;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider(path));
    return async.when(
      loading: () => const LoadingView(),
      error: (e, _) => GlassCard(child: ErrorView(e, onRetry: () => ref.invalidate(jsonProvider(path)))),
      data: (u) => GlassCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          KVRow(t('ai.today_requests'), '${integer(u['today_requests'])}${u['daily_limit'] == null ? '' : ' / ${u['daily_limit']}'}'),
          KVRow(t('ai.today_tokens'), '${integer(u['today_tokens'])}'),
          KVRow(t('ai.today_cost'), '\$${number(u['today_cost']).toStringAsFixed(4)}'),
          const SizedBox(height: Tokens.sm),
          SparkBars(SparkBars.fromSeries(u['requests_series']), color: Tokens.violet),
          const SizedBox(height: Tokens.xs),
          Text(str(u['cost_note']), style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
    );
  }
}

class _Drafts extends ConsumerWidget {
  const _Drafts();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider('/ai/drafts'));
    return async.when(
      loading: () => const LoadingView(),
      error: (e, _) => GlassCard(child: ErrorView(e)),
      data: (d) {
        final items = asMaps(d['items']);
        if (items.isEmpty) return GlassCard(child: EmptyView(t('ai.no_drafts'), icon: Icons.drafts_outlined));
        return Column(children: [
          for (final dr in items)
            GlassCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(str(dr['chat_title'], '#${dr['chat_id']}'), style: const TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: Tokens.xxs),
                Text(str(dr['text'])),
                const SizedBox(height: Tokens.xs),
                Wrap(spacing: Tokens.xs, children: [
                  for (final a in const ['send', 'alt', 'rej'])
                    OutlinedButton(
                      onPressed: () => act(context, ref, () => ref.read(apiProvider).post('/ai/drafts/${dr['id']}/$a'),
                          done: t('ai.draft_$a'), reload: ['/ai/drafts']),
                      child: Text(t('ai.draft_btn_$a')),
                    ),
                ]),
              ]),
            ),
        ]);
      },
    );
  }
}

class _Memory extends ConsumerWidget {
  const _Memory();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final async = ref.watch(jsonProvider('/ai/memory'));
    final api = ref.read(apiProvider);
    return async.when(
      loading: () => const LoadingView(),
      error: (e, _) => GlassCard(child: ErrorView(e)),
      data: (d) {
        final items = asMaps(d['items']);
        return GlassCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (items.isEmpty) Text(t('ai.memory_empty'), style: const TextStyle(color: Tokens.textSecondary)),
            for (final m in items)
              ListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                title: Text(str(m['content'])),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () => act(context, ref, () => api.delete('/ai/memory/${m['id']}'), reload: ['/ai/memory']),
                ),
              ),
            Row(children: [
              TextButton.icon(
                onPressed: () async {
                  final v = await promptText(context, t, title: t('ai.memory_add'), hint: t('ai.memory_hint'), maxLines: 3, maxLength: 1000);
                  if (v != null && v.length >= 2 && context.mounted) {
                    await act(context, ref, () => api.post('/ai/memory', {'content': v}), reload: ['/ai/memory']);
                  }
                },
                icon: const Icon(Icons.add),
                label: Text(t('ai.memory_add')),
              ),
              const Spacer(),
              if (items.isNotEmpty)
                TextButton(
                  onPressed: () async {
                    if (await confirmDialog(context, t, title: t('ai.memory_clear'), body: t('ai.memory_clear_body'), danger: true) &&
                        context.mounted) {
                      await act(context, ref, () => api.delete('/ai/memory'), reload: ['/ai/memory']);
                    }
                  },
                  child: Text(t('ai.memory_clear'), style: const TextStyle(color: Tokens.danger)),
                ),
            ]),
          ]),
        );
      },
    );
  }
}

/// AI Twin: replies in the owner's manner — learns only from examples the owner adds voluntarily.
class TwinScreen extends ConsumerWidget {
  const TwinScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('nav.twin'),
      body: ApiView('/ai/twin', builder: (context, ref, d) => _TwinForm(data: d, key: ValueKey(d.hashCode))),
    );
  }
}

class _TwinForm extends ConsumerStatefulWidget {
  const _TwinForm({super.key, required this.data});

  final Json data;

  @override
  ConsumerState<_TwinForm> createState() => _TwinFormState();
}

class _TwinFormState extends ConsumerState<_TwinForm> {
  late Json p = Map.of(asMap(widget.data['profile']));
  final _preview = TextEditingController();
  String? _previewReply;
  bool _busy = false;

  Json get options => asMap(widget.data['options']);

  @override
  void dispose() {
    _preview.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    const fields = [
      'mode', 'name', 'language', 'manner', 'style', 'formality', 'humor', 'length', 'emoji', 'slang', 'profanity_filter',
      'reply_delay_sec', 'active_from', 'active_to', 'custom_prompt', 'persona',
    ];
    final body = {for (final f in fields) if (p[f] != null) f: p[f]};
    await act(context, ref, () => ref.read(apiProvider).put('/ai/twin', body), reload: ['/ai/twin']);
  }

  Future<void> _runPreview() async {
    final t = ref.read(stringsProvider);
    if (_preview.text.trim().isEmpty) return;
    setState(() => _busy = true);
    try {
      final r = await ref.read(apiProvider).post('/ai/twin/preview', {'text': _preview.text.trim()});
      setState(() => _previewReply = str(r['reply'], str(r['text'])));
    } on Object catch (e) {
      setState(() => _previewReply = errorText(t, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _slider(String key) {
    final t = ref.watch(stringsProvider);
    final v = integer(p[key], 50).clamp(0, 100).toDouble();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('${t('twin.$key')}: ${v.round()}', style: const TextStyle(color: Tokens.textSecondary)),
      Slider(value: v, max: 100, divisions: 20, onChanged: (x) => setState(() => p[key] = x.round())),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final examples = asList(p['examples']);
    final api = ref.read(apiProvider);
    return ListView(padding: pagePadding, children: [
      GlassCard(child: Text(t('twin.intro'), style: Theme.of(context).textTheme.bodySmall)),
      SectionHeader(t('twin.mode')),
      GlassCard(
        child: ChoiceRow(
          options: asList(options['modes']).map((e) => '$e').toList(),
          selected: str(p['mode'], 'disabled'),
          labels: (m) => t('twin.mode.$m'),
          onSelected: (m) => setState(() => p['mode'] = m),
        ),
      ),
      SectionHeader(t('twin.identity')),
      GlassCard(
        child: Column(children: [
          TextFormField(
            initialValue: str(p['name']),
            maxLength: 60,
            decoration: InputDecoration(labelText: t('twin.name')),
            onChanged: (v) => p['name'] = v,
          ),
          TextFormField(
            initialValue: str(p['manner']),
            maxLength: 500,
            maxLines: 3,
            decoration: InputDecoration(labelText: t('twin.manner'), hintText: t('twin.manner_hint')),
            onChanged: (v) => p['manner'] = v,
          ),
          const SizedBox(height: Tokens.xs),
          Align(alignment: Alignment.centerLeft, child: Text(t('ai.style'), style: const TextStyle(color: Tokens.textSecondary))),
          const SizedBox(height: Tokens.xs),
          ChoiceRow(
            options: asList(options['styles']).map((e) => '$e').toList(),
            selected: str(p['style'], 'friendly'),
            labels: (v) => t('ai.style.$v'),
            onSelected: (v) => setState(() => p['style'] = v),
          ),
          const SizedBox(height: Tokens.sm),
          Align(alignment: Alignment.centerLeft, child: Text(t('twin.length'), style: const TextStyle(color: Tokens.textSecondary))),
          const SizedBox(height: Tokens.xs),
          ChoiceRow(
            options: asList(options['lengths']).map((e) => '$e').toList(),
            selected: str(p['length'], 'medium'),
            labels: (v) => t('twin.length.$v'),
            onSelected: (v) => setState(() => p['length'] = v),
          ),
          const SizedBox(height: Tokens.sm),
          Align(alignment: Alignment.centerLeft, child: Text(t('twin.persona'), style: const TextStyle(color: Tokens.textSecondary))),
          const SizedBox(height: Tokens.xs),
          ChoiceRow(
            options: asList(options['personas']).map((e) => '$e').toList(),
            selected: str(p['persona'], 'neutral'),
            labels: (v) => t('twin.persona.$v'),
            onSelected: (v) => setState(() => p['persona'] = v),
          ),
        ]),
      ),
      SectionHeader(t('twin.tone')),
      GlassCard(
        child: Column(children: [
          _slider('formality'),
          _slider('humor'),
          _slider('emoji'),
          _slider('slang'),
          SwitchRow(title: t('twin.profanity_filter'), value: flag(p['profanity_filter']), onChanged: (v) => setState(() => p['profanity_filter'] = v)),
        ]),
      ),
      SectionHeader(t('twin.schedule')),
      GlassCard(
        child: Column(children: [
          Row(children: [
            Expanded(
              child: TextFormField(
                initialValue: str(p['active_from']),
                decoration: InputDecoration(labelText: t('twin.active_from'), hintText: '09:00'),
                onChanged: (v) => p['active_from'] = v.isEmpty ? null : v,
              ),
            ),
            const SizedBox(width: Tokens.sm),
            Expanded(
              child: TextFormField(
                initialValue: str(p['active_to']),
                decoration: InputDecoration(labelText: t('twin.active_to'), hintText: '22:00'),
                onChanged: (v) => p['active_to'] = v.isEmpty ? null : v,
              ),
            ),
          ]),
          const SizedBox(height: Tokens.sm),
          Text('${t('twin.delay')}: ${integer(p['reply_delay_sec'])} s', style: const TextStyle(color: Tokens.textSecondary)),
          Slider(
            value: integer(p['reply_delay_sec']).clamp(0, 300).toDouble(),
            max: 300,
            divisions: 30,
            onChanged: (x) => setState(() => p['reply_delay_sec'] = x.round()),
          ),
          TextFormField(
            initialValue: str(p['custom_prompt']),
            maxLength: 2000,
            maxLines: 3,
            decoration: InputDecoration(labelText: t('twin.custom_prompt')),
            onChanged: (v) => p['custom_prompt'] = v,
          ),
        ]),
      ),
      FilledButton.icon(key: const Key('twin-save'), onPressed: _save, icon: const Icon(Icons.save_outlined), label: Text(t('common.save'))),
      SectionHeader(t('twin.examples', {'n': examples.length})),
      GlassCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t('twin.examples_hint'), style: Theme.of(context).textTheme.bodySmall),
          for (final e in examples.take(20))
            Padding(padding: const EdgeInsets.only(top: 6), child: Text('• ${e is Map ? str(e['text']) : e}')),
          Row(children: [
            TextButton.icon(
              onPressed: () async {
                final v = await promptText(context, t, title: t('twin.add_example'), maxLines: 3, maxLength: 1000);
                if (v != null && v.isNotEmpty && context.mounted) {
                  await act(context, ref, () => api.post('/ai/twin/examples', {'text': v}), reload: ['/ai/twin']);
                }
              },
              icon: const Icon(Icons.add),
              label: Text(t('twin.add_example')),
            ),
            const Spacer(),
            if (examples.isNotEmpty)
              TextButton(
                onPressed: () => act(context, ref, () => api.delete('/ai/twin/examples'), reload: ['/ai/twin']),
                child: Text(t('twin.clear_examples'), style: const TextStyle(color: Tokens.danger)),
              ),
          ]),
        ]),
      ),
      SectionHeader(t('twin.preview')),
      GlassCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          TextField(controller: _preview, decoration: InputDecoration(hintText: t('twin.preview_hint'))),
          const SizedBox(height: Tokens.sm),
          OutlinedButton(onPressed: _busy ? null : _runPreview, child: Text(t('twin.preview_run'))),
          if (_previewReply != null) ...[const SizedBox(height: Tokens.sm), Text(_previewReply!, key: const Key('twin-preview'))],
        ]),
      ),
    ]);
  }
}

class PlaygroundScreen extends ConsumerStatefulWidget {
  const PlaygroundScreen({super.key});

  @override
  ConsumerState<PlaygroundScreen> createState() => _PlaygroundScreenState();
}

class _PlaygroundScreenState extends ConsumerState<PlaygroundScreen> {
  final _prompt = TextEditingController();
  Json? _result;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _prompt.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    final t = ref.read(stringsProvider);
    if (_prompt.text.trim().isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await ref.read(apiProvider).post('/ai/playground', {'prompt': _prompt.text.trim()});
      setState(() => _result = r);
    } on Object catch (e) {
      setState(() => _error = errorText(t, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final r = _result;
    return AppScaffold(
      title: t('nav.playground'),
      body: ListView(padding: pagePadding, children: [
        GlassCard(child: Text(t('play.hint'), style: Theme.of(context).textTheme.bodySmall)),
        TextField(
          key: const Key('play-prompt'),
          controller: _prompt,
          minLines: 3,
          maxLines: 8,
          maxLength: 8000,
          decoration: InputDecoration(hintText: t('play.prompt')),
        ),
        FilledButton.icon(
          key: const Key('play-run'),
          onPressed: _busy ? null : _run,
          icon: const Icon(Icons.play_arrow_rounded),
          label: Text(_busy ? t('play.running') : t('play.run')),
        ),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: Tokens.md), child: Text(_error!, style: const TextStyle(color: Tokens.danger))),
        if (r != null) ...[
          SectionHeader(t('play.result')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SelectableText(str(r['text'])),
              const Divider(height: Tokens.xl),
              KVRow(t('play.provider'), '${str(r['provider'])} · ${str(r['model'])}'),
              KVRow(t('play.tokens'), '${integer(r['prompt_tokens'])} + ${integer(r['completion_tokens'])}'),
            ]),
          ),
        ],
      ]),
    );
  }
}

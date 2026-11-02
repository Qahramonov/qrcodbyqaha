import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/json.dart';
import '../core/session.dart';
import '../core/theme.dart';
import '../core/widgets.dart';

class CommandsScreen extends ConsumerStatefulWidget {
  const CommandsScreen({super.key});

  @override
  ConsumerState<CommandsScreen> createState() => _CommandsScreenState();
}

class _CommandsScreenState extends ConsumerState<CommandsScreen> {
  String _q = '';
  final _test = TextEditingController(text: '.calc 2+2*2');
  List<Json>? _testOut;

  @override
  void dispose() {
    _test.dispose();
    super.dispose();
  }

  Future<void> _runTest() async {
    final t = ref.read(stringsProvider);
    try {
      final r = await ref.read(apiProvider).post('/commands/test', {'text': _test.text.trim()});
      setState(() => _testOut = r['ok'] == false && asMaps(r['outputs']).isEmpty
          ? [
              {'type': 'error', 'text': t('cmd.test_${str(r['error'], 'failed')}')}
            ]
          : asMaps(r['outputs']));
    } on Object catch (e) {
      setState(() => _testOut = [
            {'type': 'error', 'text': errorText(t, e)}
          ]);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.commands'),
      body: ApiView('/commands', builder: (context, ref, d) {
        final prefix = str(d['prefix'], '.');
        final q = _q.toLowerCase();
        final items = asMaps(d['items'])
            .where((c) => q.isEmpty || str(c['id']).contains(q) || str(c['description']).toLowerCase().contains(q))
            .toList();
        final byCat = <String, List<Json>>{};
        for (final c in items) {
          byCat.putIfAbsent(str(c['category']), () => []).add(c);
        }
        return ListView(padding: pagePadding, children: [
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(t('cmd.prefix'), style: Theme.of(context).textTheme.titleMedium)),
                for (final p in const ['.', '!', '-', ','])
                  Padding(
                    padding: const EdgeInsets.only(left: 6),
                    child: ChoiceChip(
                      label: Text(p, style: const TextStyle(fontWeight: FontWeight.w700)),
                      selected: p == prefix,
                      onSelected: (_) => act(context, ref, () => api.put('/commands/prefix', {'prefix': p}), reload: ['/commands']),
                    ),
                  ),
              ]),
              Text(t('cmd.prefix_hint'), style: Theme.of(context).textTheme.bodySmall),
            ]),
          ),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text(t('cmd.test'), style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: Tokens.xs),
              Row(children: [
                Expanded(child: TextField(key: const Key('cmd-test'), controller: _test, decoration: InputDecoration(hintText: t('cmd.test_hint')))),
                const SizedBox(width: Tokens.xs),
                IconButton.filled(key: const Key('cmd-test-run'), onPressed: _runTest, icon: const Icon(Icons.play_arrow_rounded)),
              ]),
              for (final o in _testOut ?? const <Json>[])
                Padding(
                  padding: const EdgeInsets.only(top: Tokens.xs),
                  child: Text(stripHtml(str(o['text'], str(o['caption']))),
                      style: TextStyle(color: o['type'] == 'error' ? Tokens.danger : Tokens.textPrimary)),
                ),
              const SizedBox(height: Tokens.xxs),
              Text(t('cmd.test_note'), style: Theme.of(context).textTheme.bodySmall),
            ]),
          ),
          TextField(
            onChanged: (v) => setState(() => _q = v.trim()),
            decoration: InputDecoration(hintText: t('cmd.search', {'n': integer(d['count'])}), prefixIcon: const Icon(Icons.search_rounded)),
          ),
          for (final e in byCat.entries) ...[
            SectionHeader(t('cat.${e.key}')),
            GlassCard(
              padding: const EdgeInsets.symmetric(horizontal: Tokens.sm, vertical: Tokens.xxs),
              child: Column(children: [
                for (final c in e.value)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(str(c['name']), style: const TextStyle(fontWeight: FontWeight.w700, fontFamily: 'monospace')),
                    subtitle: Text(str(c['description']), maxLines: 2, overflow: TextOverflow.ellipsis),
                    onTap: () => _showCommand(context, c),
                    trailing: Switch(
                      value: flag(c['enabled_for_me']),
                      onChanged: flag(c['enabled_global'])
                          ? (v) => act(context, ref, () => api.patch('/commands/${c['id']}', {'enabled': v}), reload: ['/commands'])
                          : null,
                    ),
                  ),
              ]),
            ),
          ],
        ]);
      }),
    );
  }

  void _showCommand(BuildContext context, Json c) {
    final t = ref.read(stringsProvider);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Tokens.bgElevated,
      isScrollControlled: true,
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Tokens.lg),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(str(c['name']), style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: Tokens.xs),
            Text(str(c['description'])),
            const SizedBox(height: Tokens.sm),
            SelectableText(str(c['syntax']), style: const TextStyle(fontFamily: 'monospace', color: Tokens.cyan)),
            if (asList(c['aliases']).isNotEmpty) ...[
              const SizedBox(height: Tokens.xs),
              Text('${t('cmd.aliases')}: ${asList(c['aliases']).join(', ')}', style: Theme.of(context).textTheme.bodySmall),
            ],
            const SizedBox(height: Tokens.sm),
            for (final ex in asList(c['examples']).take(4))
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text('$ex', style: const TextStyle(fontFamily: 'monospace')),
                trailing: const Icon(Icons.copy_rounded, size: 18),
                onTap: () => copyText(context, t, '$ex'),
              ),
            if (str(c['notes']).isNotEmpty) Text('ℹ️ ${c['notes']}', style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: Tokens.xs),
            Wrap(spacing: 6, runSpacing: 6, children: [
              Pill(str(c['min_plan']).toUpperCase(), color: Tokens.warning),
              Pill(t('cmd.where.${str(c['where'], 'any')}'), color: Tokens.cyan),
              for (final r in asList(c['rights'])) Pill(t('right.$r'), color: Tokens.violet),
            ]),
          ]),
        ),
      ),
    );
  }
}

class RemindersScreen extends ConsumerWidget {
  const RemindersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return AppScaffold(
      title: t('nav.reminders'),
      floating: FloatingActionButton.extended(
        key: const Key('reminder-add'),
        onPressed: () => showDialog<void>(context: context, builder: (_) => const _ReminderDialog()),
        icon: const Icon(Icons.add_alarm_rounded),
        label: Text(t('rem.add')),
      ),
      body: ApiView('/reminders', builder: (context, ref, d) {
        final items = asMaps(d['items']);
        final pending = items.where((r) => r['status'] == 'pending').toList();
        final done = items.where((r) => r['status'] != 'pending').toList();
        return ListView(padding: pagePadding, children: [
          GlassCard(child: Text(t('rem.hint'), style: Theme.of(context).textTheme.bodySmall)),
          SectionHeader(t('rem.pending', {'n': pending.length})),
          if (pending.isEmpty) GlassCard(child: EmptyView(t('rem.none'), icon: Icons.alarm_off_outlined)),
          for (final r in pending)
            GlassCard(
              child: Row(children: [
                Icon(r['kind'] == 'chat' ? Icons.forum_outlined : Icons.person_outline, color: Tokens.warning),
                const SizedBox(width: Tokens.sm),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(str(r['text'])),
                    Text(fmtTime(r['run_at']), style: Theme.of(context).textTheme.bodySmall),
                  ]),
                ),
                IconButton(
                  tooltip: t('common.delete'),
                  onPressed: () => act(context, ref, () => api.delete('/reminders/${r['id']}'), done: t('rem.deleted'), reload: ['/reminders']),
                  icon: const Icon(Icons.delete_outline),
                ),
              ]),
            ),
          if (done.isNotEmpty) ...[
            SectionHeader(t('rem.done')),
            GlassCard(
              child: Column(children: [
                for (final r in done.take(20))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(str(r['text'])),
                    subtitle: Text('${fmtTime(r['run_at'])} · ${t('rem.status.${str(r['status'])}')}'),
                  ),
              ]),
            ),
          ],
          const SizedBox(height: 72),
        ]);
      }),
    );
  }
}

class _ReminderDialog extends ConsumerStatefulWidget {
  const _ReminderDialog();

  @override
  ConsumerState<_ReminderDialog> createState() => _ReminderDialogState();
}

class _ReminderDialogState extends ConsumerState<_ReminderDialog> {
  final _text = TextEditingController();
  int _sec = 3600;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    return AlertDialog(
      title: Text(t('rem.add')),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(key: const Key('reminder-text'), controller: _text, maxLength: 1000, decoration: InputDecoration(hintText: t('rem.text'))),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final s in const [600, 1800, 3600, 10800, 86400, 604800])
            ChoiceChip(label: Text(fmtDuration(s)), selected: _sec == s, onSelected: (_) => setState(() => _sec = s)),
        ]),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: Text(t('common.cancel'))),
        FilledButton(
          key: const Key('reminder-save'),
          onPressed: () async {
            if (_text.text.trim().isEmpty) return;
            final ok = await act(context, ref, () => ref.read(apiProvider).post('/reminders', {'text': _text.text.trim(), 'in_sec': _sec}),
                done: t('rem.created'), reload: ['/reminders']);
            if (ok && context.mounted) Navigator.of(context).pop();
          },
          child: Text(t('common.save')),
        ),
      ],
    );
  }
}

/// No-code automation builder: trigger → (conditions) → actions, with a dry-run test before saving.
class AutomationScreen extends ConsumerWidget {
  const AutomationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return DefaultTabController(
      length: 3,
      child: AppScaffold(
        title: t('nav.automation'),
        floating: FloatingActionButton.extended(
          key: const Key('rule-new'),
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const RuleBuilderScreen())),
          icon: const Icon(Icons.add),
          label: Text(t('auto.new')),
        ),
        body: Column(children: [
          TabBar(tabs: [Tab(text: t('auto.rules')), Tab(text: t('auto.templates')), Tab(text: t('auto.log'))]),
          const Expanded(child: TabBarView(children: [_Rules(), _Templates(), _ExecLog()])),
        ]),
      ),
    );
  }
}

class _Rules extends ConsumerWidget {
  const _Rules();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final api = ref.read(apiProvider);
    return ApiView('/automation/rules', builder: (context, ref, d) {
      final items = asMaps(d['items']);
      return ListView(padding: pagePadding, children: [
        if (items.isEmpty) EmptyView(t('auto.no_rules'), icon: Icons.account_tree_outlined),
        for (final r in items)
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(str(r['name'], '#${r['id']}'), style: const TextStyle(fontWeight: FontWeight.w600))),
                Switch(
                  value: flag(r['enabled']),
                  onChanged: (v) => act(context, ref, () => api.patch('/automation/rules/${r['id']}', {'enabled': v}), reload: ['/automation/rules']),
                ),
              ]),
              Text('${t('auto.when')}: ${t('auto.trigger.${asMap(r['trigger'])['type']}')}', style: Theme.of(context).textTheme.bodySmall),
              Text('${t('auto.then')}: ${asMaps(r['actions']).map((a) => t('auto.action.${a['type']}')).join(' → ')}',
                  style: Theme.of(context).textTheme.bodySmall),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () async {
                    if (await confirmDialog(context, t, title: t('auto.delete'), body: str(r['name']), danger: true) && context.mounted) {
                      await act(context, ref, () => api.delete('/automation/rules/${r['id']}'), reload: ['/automation/rules']);
                    }
                  },
                  child: Text(t('common.delete'), style: const TextStyle(color: Tokens.danger)),
                ),
              ),
            ]),
          ),
        const SizedBox(height: 72),
      ]);
    });
  }
}

class _Templates extends ConsumerWidget {
  const _Templates();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return ApiView('/automation/templates', builder: (context, ref, d) {
      return ListView(padding: pagePadding, children: [
        for (final tpl in asMaps(d['items']))
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(str(tpl['title']), style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: Tokens.xxs),
              Text(str(tpl['description']), style: const TextStyle(color: Tokens.textSecondary)),
              const SizedBox(height: Tokens.xs),
              for (final r in asMaps(tpl['rules'])) Text('• ${str(r['name'])}', style: Theme.of(context).textTheme.bodySmall),
              Align(
                alignment: Alignment.centerRight,
                child: FilledButton.tonal(
                  onPressed: () => act(context, ref, () => ref.read(apiProvider).post('/automation/templates/${tpl['id']}/install'),
                      done: t('auto.installed'), reload: ['/automation/rules']),
                  child: Text(t('auto.install')),
                ),
              ),
            ]),
          ),
        const SizedBox(height: 72),
      ]);
    });
  }
}

class _ExecLog extends ConsumerWidget {
  const _ExecLog();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return ApiView('/automation/executions', builder: (context, ref, d) {
      final items = asMaps(d['items']);
      return ListView(padding: pagePadding, children: [
        if (items.isEmpty) EmptyView(t('auto.no_log'), icon: Icons.receipt_long_outlined),
        for (final e in items.take(100))
          GlassCard(
            child: Row(children: [
              Icon(e['status'] == 'ok' ? Icons.check_circle_outline : Icons.error_outline,
                  color: e['status'] == 'ok' ? Tokens.success : Tokens.warning),
              const SizedBox(width: Tokens.sm),
              Expanded(child: Text('#${e['rule_id']} · ${str(e['detail'], str(e['status']))}')),
              Text(fmtTime(e['created_at']), style: Theme.of(context).textTheme.bodySmall),
            ]),
          ),
      ]);
    });
  }
}

class RuleBuilderScreen extends ConsumerStatefulWidget {
  const RuleBuilderScreen({super.key});

  @override
  ConsumerState<RuleBuilderScreen> createState() => _RuleBuilderScreenState();
}

class _RuleBuilderScreenState extends ConsumerState<RuleBuilderScreen> {
  final _name = TextEditingController();
  String _trigger = 'keyword';
  final _keywords = TextEditingController();
  String _match = 'contains';
  final _at = TextEditingController(text: '09:00');
  int _minutes = 60;
  final Set<String> _media = {'voice'};
  String _aiLabel = 'question';
  String _action = 'reply';
  final _text = TextEditingController();
  int _cooldown = 600;
  final _sample = TextEditingController();
  String? _testResult;

  @override
  void dispose() {
    for (final c in [_name, _keywords, _at, _text, _sample]) {
      c.dispose();
    }
    super.dispose();
  }

  Json _rule() {
    final trigger = <String, dynamic>{'type': _trigger};
    switch (_trigger) {
      case 'keyword':
        trigger['keywords'] = _keywords.text.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
        trigger['match'] = _match;
      case 'time':
        trigger['at'] = _at.text.trim();
      case 'no_reply':
        trigger['minutes'] = _minutes;
      case 'media':
        trigger['types'] = _media.toList();
      case 'ai_class':
        trigger['label'] = _aiLabel;
    }
    final action = <String, dynamic>{'type': _action};
    if (_action == 'reply' || _action == 'notify') action['text'] = _text.text.trim();
    if (_action == 'afk_on' && _text.text.trim().isNotEmpty) action['reason'] = _text.text.trim();
    return {
      'name': _name.text.trim().isEmpty ? ref.read(stringsProvider)('auto.trigger.$_trigger') : _name.text.trim(),
      'trigger': trigger,
      'actions': [action],
      'cooldown_sec': _cooldown,
      'enabled': true,
    };
  }

  Future<void> _test() async {
    final t = ref.read(stringsProvider);
    try {
      final r = await ref.read(apiProvider).post('/automation/test', {'rule': _rule(), 'sample_text': _sample.text, 'is_new': _trigger == 'new_chat'});
      setState(() => _testResult = flag(r['would_fire'])
          ? t('auto.test_fires', {'n': asList(r['actions']).length})
          : flag(r['trigger_matched'])
              ? t('auto.test_conditions')
              : t('auto.test_no'));
    } on Object catch (e) {
      setState(() => _testResult = errorText(t, e));
    }
  }

  Future<void> _save() async {
    final ok = await act(context, ref, () => ref.read(apiProvider).post('/automation/rules', _rule()), reload: ['/automation/rules']);
    if (ok && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    return AppScaffold(
      title: t('auto.new'),
      body: ApiView('/automation/schema', builder: (context, ref, schema) {
        final triggers = asMap(schema['triggers']);
        final actions = asList(schema['actions']).map((e) => '$e').where((a) => const {'reply', 'notify', 'afk_on', 'afk_off', 'ai_reply', 'handoff', 'mark_read'}.contains(a)).toList();
        return ListView(padding: pagePadding, children: [
          TextField(controller: _name, maxLength: 60, decoration: InputDecoration(labelText: t('auto.name'))),
          SectionHeader(t('auto.when')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 6, runSpacing: 6, children: [
                for (final k in triggers.keys.where((k) => k != 'contact' && k != 'message'))
                  ChoiceChip(label: Text(str(triggers[k])), selected: _trigger == k, onSelected: (_) => setState(() => _trigger = k)),
              ]),
              const SizedBox(height: Tokens.sm),
              if (_trigger == 'keyword') ...[
                TextField(controller: _keywords, decoration: InputDecoration(labelText: t('auto.keywords'), hintText: t('auto.keywords_hint'))),
                const SizedBox(height: Tokens.xs),
                ChoiceRow(options: const ['contains', 'word', 'exact'], selected: _match, labels: (m) => t('auto.match.$m'), onSelected: (m) => setState(() => _match = m)),
              ],
              if (_trigger == 'time') TextField(controller: _at, decoration: InputDecoration(labelText: t('auto.at'), hintText: '23:00')),
              if (_trigger == 'no_reply')
                Wrap(spacing: 6, children: [
                  for (final m in const [15, 30, 60, 180])
                    ChoiceChip(label: Text(fmtDuration(m * 60)), selected: _minutes == m, onSelected: (_) => setState(() => _minutes = m)),
                ]),
              if (_trigger == 'media')
                Wrap(spacing: 6, runSpacing: 6, children: [
                  for (final m in asList(schema['media_types']).map((e) => '$e'))
                    FilterChip(
                      label: Text(m),
                      selected: _media.contains(m),
                      onSelected: (on) => setState(() => on ? _media.add(m) : _media.remove(m)),
                    ),
                ]),
              if (_trigger == 'ai_class')
                ChoiceRow(
                  options: asList(schema['ai_labels']).map((e) => '$e').toList(),
                  selected: _aiLabel,
                  labels: (l) => t('auto.label.$l'),
                  onSelected: (l) => setState(() => _aiLabel = l),
                ),
            ]),
          ),
          SectionHeader(t('auto.then')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              ChoiceRow(options: actions, selected: _action, labels: (a) => t('auto.action.$a'), onSelected: (a) => setState(() => _action = a)),
              if (_action == 'reply' || _action == 'notify' || _action == 'afk_on') ...[
                const SizedBox(height: Tokens.sm),
                TextField(
                  controller: _text,
                  maxLines: 3,
                  decoration: InputDecoration(labelText: _action == 'afk_on' ? t('afk.reason') : t('auto.text')),
                ),
              ],
              const SizedBox(height: Tokens.sm),
              Text(t('auto.cooldown'), style: const TextStyle(color: Tokens.textSecondary)),
              Wrap(spacing: 6, children: [
                for (final c in const [0, 300, 600, 3600, 86400])
                  ChoiceChip(label: Text(c == 0 ? '0' : fmtDuration(c)), selected: _cooldown == c, onSelected: (_) => setState(() => _cooldown = c)),
              ]),
            ]),
          ),
          SectionHeader(t('auto.test')),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              TextField(controller: _sample, decoration: InputDecoration(hintText: t('auto.sample'))),
              const SizedBox(height: Tokens.xs),
              OutlinedButton(key: const Key('rule-test'), onPressed: _test, child: Text(t('auto.run_test'))),
              if (_testResult != null) Padding(padding: const EdgeInsets.only(top: Tokens.xs), child: Text(_testResult!, key: const Key('rule-test-result'))),
            ]),
          ),
          FilledButton(key: const Key('rule-save'), onPressed: _save, child: Text(t('common.save'))),
        ]);
      }),
    );
  }
}

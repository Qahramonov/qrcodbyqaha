import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api.dart';
import 'i18n.dart';
import 'json.dart';
import 'session.dart';
import 'theme.dart';

const pagePadding = EdgeInsets.fromLTRB(Tokens.md, Tokens.xs, Tokens.md, Tokens.xxl);

/// Dark gradient with soft accent glows — the "liquid glass" backdrop every screen sits on.
class AppBackground extends StatelessWidget {
  const AppBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [Tokens.bgTop, Tokens.bgBottom], begin: Alignment.topCenter, end: Alignment.bottomCenter),
      ),
      child: Stack(children: [
        const Positioned(top: -120, left: -80, child: _Glow(color: Tokens.blue, size: 320)),
        const Positioned(bottom: -140, right: -100, child: _Glow(color: Tokens.violet, size: 380)),
        Positioned.fill(child: child),
      ]),
    );
  }
}

class _Glow extends StatelessWidget {
  const _Glow({required this.color, required this.size});

  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(colors: [color.withValues(alpha: 0.28), color.withValues(alpha: 0)]),
          ),
        ),
      );
}

class AppScaffold extends StatelessWidget {
  const AppScaffold({super.key, required this.title, required this.body, this.actions, this.floating});

  final String title;
  final Widget body;
  final List<Widget>? actions;
  final Widget? floating;

  @override
  Widget build(BuildContext context) {
    return AppBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(title: Text(title, overflow: TextOverflow.ellipsis), actions: actions),
        floatingActionButton: floating,
        body: SafeArea(top: false, child: body),
      ),
    );
  }
}

/// Frosted translucent card.
class GlassCard extends StatelessWidget {
  const GlassCard({super.key, required this.child, this.padding = const EdgeInsets.all(Tokens.md), this.onTap, this.margin});

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(Tokens.rLg);
    return Padding(
      padding: margin ?? const EdgeInsets.only(bottom: Tokens.sm),
      child: ClipRRect(
        borderRadius: radius,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: Tokens.glassBlur, sigmaY: Tokens.glassBlur),
          child: Material(
            color: Tokens.glassFill,
            shape: RoundedRectangleBorder(borderRadius: radius, side: const BorderSide(color: Tokens.glassBorder)),
            child: InkWell(onTap: onTap, borderRadius: radius, child: Padding(padding: padding, child: child)),
          ),
        ),
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.xxs, Tokens.md, Tokens.xxs, Tokens.xs),
        child: Row(children: [
          Expanded(
            child: Text(text.toUpperCase(),
                style: const TextStyle(fontSize: Tokens.caption, letterSpacing: 1.1, fontWeight: FontWeight.w600, color: Tokens.textSecondary)),
          ),
          ?trailing,
        ]),
      );
}

class StatTile extends StatelessWidget {
  const StatTile({super.key, required this.label, required this.value, this.icon, this.color = Tokens.blue});

  final String label;
  final String value;
  final IconData? icon;
  final Color color;

  @override
  Widget build(BuildContext context) => GlassCard(
        margin: EdgeInsets.zero,
        padding: const EdgeInsets.all(Tokens.sm),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (icon != null) Icon(icon, color: color, size: 20),
          const SizedBox(height: Tokens.xs),
          Text(value, style: const TextStyle(fontSize: Tokens.title, fontWeight: FontWeight.w700), maxLines: 1, overflow: TextOverflow.ellipsis),
          const SizedBox(height: Tokens.xxs),
          Text(label, style: Theme.of(context).textTheme.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
        ]),
      );
}

/// Two-column grid of stat tiles that adapts to the screen width.
class StatGrid extends StatelessWidget {
  const StatGrid(this.tiles, {super.key});

  final List<Widget> tiles;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        final cols = c.maxWidth > 560 ? 4 : 2;
        final w = (c.maxWidth - (cols - 1) * Tokens.sm) / cols;
        return Wrap(spacing: Tokens.sm, runSpacing: Tokens.sm, children: [for (final t in tiles) SizedBox(width: w, child: t)]);
      });
}

class KVRow extends StatelessWidget {
  const KVRow(this.label, this.value, {super.key, this.valueColor});

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: Tokens.xxs + 1),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(flex: 5, child: Text(label, style: const TextStyle(color: Tokens.textSecondary))),
          const SizedBox(width: Tokens.xs),
          Expanded(
            flex: 6,
            child: Text(value, textAlign: TextAlign.end, style: TextStyle(fontWeight: FontWeight.w600, color: valueColor)),
          ),
        ]),
      );
}

class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.color = Tokens.blue});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.xs + 2, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.18),
          borderRadius: BorderRadius.circular(Tokens.rPill),
          border: Border.all(color: color.withValues(alpha: 0.45)),
        ),
        child: Text(text, style: TextStyle(fontSize: Tokens.caption, color: color, fontWeight: FontWeight.w600)),
      );
}

/// Minimal bar chart for `[{"day": "...", "value": n}]` series.
class SparkBars extends StatelessWidget {
  const SparkBars(this.values, {super.key, this.color = Tokens.blue, this.height = 64});

  final List<double> values;
  final Color color;
  final double height;

  static List<double> fromSeries(Object? series) => asMaps(series).map((p) => number(p['value'])).toList();

  @override
  Widget build(BuildContext context) => SizedBox(
        height: height,
        width: double.infinity,
        child: CustomPaint(painter: _BarsPainter(values, color)),
      );
}

class _BarsPainter extends CustomPainter {
  _BarsPainter(this.values, this.color);

  final List<double> values;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    final maxV = values.fold<double>(0, (a, b) => b > a ? b : a);
    final gap = 3.0;
    final w = (size.width - gap * (values.length - 1)) / values.length;
    final paint = Paint()..color = color;
    final base = Paint()..color = Tokens.glassHighlight;
    for (var i = 0; i < values.length; i++) {
      final x = i * (w + gap);
      final h = maxV <= 0 ? 0.0 : (values[i] / maxV) * (size.height - 4);
      canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(x, size.height - 3, w, 3), const Radius.circular(2)), base);
      if (h > 0) {
        canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(x, size.height - h, w, h), const Radius.circular(3)), paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _BarsPainter old) => old.values != values || old.color != color;
}

class EmptyView extends StatelessWidget {
  const EmptyView(this.text, {super.key, this.icon = Icons.inbox_outlined});

  final String text;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: Tokens.xl),
        child: Column(children: [
          Icon(icon, size: 40, color: Tokens.textMuted),
          const SizedBox(height: Tokens.xs),
          Text(text, textAlign: TextAlign.center, style: const TextStyle(color: Tokens.textSecondary)),
        ]),
      );
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key});

  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(padding: EdgeInsets.all(Tokens.xxl), child: CircularProgressIndicator()),
      );
}

String errorText(T t, Object error) {
  if (error is ApiException) {
    if (error.isNetwork) return t('err.network');
    switch (error.status) {
      case 401:
        return t('err.unauthorized');
      case 404:
        return t('err.not_found');
      case 409:
        return '${t('err.conflict')}\n${error.message}';
      case 422:
        return '${t('err.validation')}\n${error.message}';
      case 429:
        return t('err.rate', {'s': error.retryAfter ?? 60});
      case 503:
        return '${t('err.unavailable')}\n${error.message}';
    }
    return error.message.isEmpty ? t('err.generic') : error.message;
  }
  return t('err.generic');
}

class ErrorView extends ConsumerWidget {
  const ErrorView(this.error, {super.key, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return Padding(
      padding: const EdgeInsets.all(Tokens.xl),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.cloud_off_rounded, size: 44, color: Tokens.danger),
        const SizedBox(height: Tokens.sm),
        Text(errorText(t, error), textAlign: TextAlign.center, key: const Key('error-text')),
        if (onRetry != null) ...[
          const SizedBox(height: Tokens.md),
          OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: Text(t('common.retry'))),
        ],
      ]),
    );
  }
}

/// Loads [path] and renders it; loading, error (with retry) and pull-to-refresh are handled here.
class ApiView extends ConsumerWidget {
  const ApiView(this.path, {super.key, required this.builder});

  final String path;
  final Widget Function(BuildContext context, WidgetRef ref, Json data) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(jsonProvider(path));
    return async.when(
      skipLoadingOnRefresh: true,
      skipLoadingOnReload: true,
      loading: () => const LoadingView(),
      error: (e, _) => Center(child: SingleChildScrollView(child: ErrorView(e, onRetry: () => ref.invalidate(jsonProvider(path))))),
      data: (data) => RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(jsonProvider(path));
          try {
            await ref.read(jsonProvider(path).future);
          } on Object {
            // the error state is rendered by the provider
          }
        },
        child: builder(context, ref, data),
      ),
    );
  }
}

class SwitchRow extends StatelessWidget {
  const SwitchRow({super.key, required this.title, required this.value, required this.onChanged, this.subtitle});

  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) => SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(title),
        subtitle: subtitle == null ? null : Text(subtitle!, style: Theme.of(context).textTheme.bodySmall),
        value: value,
        onChanged: onChanged,
      );
}

class ChoiceRow extends StatelessWidget {
  const ChoiceRow({super.key, required this.options, required this.selected, required this.onSelected, this.labels});

  final List<String> options;
  final String selected;
  final ValueChanged<String> onSelected;
  final String Function(String)? labels;

  @override
  Widget build(BuildContext context) => Wrap(spacing: Tokens.xs, runSpacing: Tokens.xs, children: [
        for (final o in options)
          ChoiceChip(label: Text(labels?.call(o) ?? o), selected: o == selected, onSelected: (_) => onSelected(o)),
      ]);
}

Future<bool> confirmDialog(BuildContext context, T t,
    {required String title, required String body, bool danger = false, String? confirmText}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (c) => AlertDialog(
      title: Text(title),
      content: Text(body),
      actions: [
        TextButton(onPressed: () => Navigator.of(c).pop(false), child: Text(t('common.cancel'))),
        FilledButton(
          style: danger ? FilledButton.styleFrom(backgroundColor: Tokens.danger) : null,
          onPressed: () => Navigator.of(c).pop(true),
          child: Text(confirmText ?? t('common.confirm')),
        ),
      ],
    ),
  );
  return ok ?? false;
}

Future<String?> promptText(BuildContext context, T t,
    {required String title, String initial = '', String? hint, int maxLines = 1, int? maxLength}) {
  final ctl = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (c) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: ctl,
        autofocus: true,
        maxLines: maxLines,
        maxLength: maxLength,
        decoration: InputDecoration(hintText: hint),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(c).pop(), child: Text(t('common.cancel'))),
        FilledButton(onPressed: () => Navigator.of(c).pop(ctl.text.trim()), child: Text(t('common.save'))),
      ],
    ),
  );
}

void toast(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}

/// Runs an API action with a success/error snackbar and reloads the given paths afterwards.
Future<bool> act(BuildContext context, WidgetRef ref, Future<void> Function() action,
    {String? done, List<String> reload = const []}) async {
  final t = ref.read(stringsProvider);
  try {
    await action();
    for (final p in reload) {
      ref.invalidate(jsonProvider(p));
    }
    if (context.mounted) toast(context, done ?? t('common.saved'));
    return true;
  } on Object catch (e) {
    if (context.mounted) toast(context, errorText(t, e));
    return false;
  }
}

Future<void> copyText(BuildContext context, T t, String text) async {
  await Clipboard.setData(ClipboardData(text: text));
  if (context.mounted) toast(context, t('common.copied'));
}

/// Tile in the home hub grid.
class HubTile extends StatelessWidget {
  const HubTile({super.key, required this.icon, required this.label, required this.onTap, this.color = Tokens.blue, this.badge});

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color color;
  final String? badge;

  @override
  Widget build(BuildContext context) => GlassCard(
        margin: EdgeInsets.zero,
        onTap: onTap,
        padding: const EdgeInsets.all(Tokens.sm),
        child: Row(children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(color: color.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(Tokens.rSm)),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(width: Tokens.sm),
          Expanded(child: Text(label, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600))),
          if (badge != null) Pill(badge!, color: Tokens.warning),
        ]),
      );
}

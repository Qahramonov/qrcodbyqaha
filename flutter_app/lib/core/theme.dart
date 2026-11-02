import 'package:flutter/material.dart';

/// Design tokens — mirrors design/tokens.json (test/theme_test.dart keeps both in sync).
class Tokens {
  // color.bg
  static const bgTop = Color(0xFF090C1C);
  static const bgBottom = Color(0xFF16102F);
  static const bgElevated = Color(0xFF141833);
  // color.accent
  static const blue = Color(0xFF3B82F6);
  static const violet = Color(0xFF8B5CF6);
  static const cyan = Color(0xFF22D3EE);
  // color.text
  static const textPrimary = Color(0xFFF0F3FF);
  static const textSecondary = Color(0xFFA6B0CE);
  static const textMuted = Color(0xFF6B7394);
  // color.glass (ARGB)
  static const glassFill = Color(0x0FFFFFFF);
  static const glassBorder = Color(0x1FFFFFFF);
  static const glassHighlight = Color(0x2EFFFFFF);
  // color.status
  static const success = Color(0xFF34D399);
  static const warning = Color(0xFFFBBF24);
  static const danger = Color(0xFFF87171);
  static const info = Color(0xFF60A5FA);
  // radius
  static const rSm = 10.0;
  static const rMd = 16.0;
  static const rLg = 24.0;
  static const rPill = 999.0;
  // space
  static const xxs = 4.0;
  static const xs = 8.0;
  static const sm = 12.0;
  static const md = 16.0;
  static const lg = 20.0;
  static const xl = 24.0;
  static const xxl = 32.0;
  // blur
  static const glassBlur = 18.0;
  // font
  static const fontFamily = 'Inter';
  static const fontFallback = ['Noto Color Emoji'];
  static const display = 28.0;
  static const title = 20.0;
  static const subtitle = 16.0;
  static const body = 14.0;
  static const caption = 12.0;

  static const accentGradient = LinearGradient(colors: [blue, violet], begin: Alignment.topLeft, end: Alignment.bottomRight);
}

ThemeData buildTheme() {
  const scheme = ColorScheme.dark(
    primary: Tokens.blue,
    secondary: Tokens.violet,
    tertiary: Tokens.cyan,
    surface: Tokens.bgElevated,
    error: Tokens.danger,
    onPrimary: Colors.white,
    onSecondary: Colors.white,
    onSurface: Tokens.textPrimary,
  );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, fontFamily: Tokens.fontFamily, brightness: Brightness.dark);
  // Overrides first, then Inter (+ emoji fallback) on every style — a TextStyle without a family would fall back to Roboto.
  final text = base.textTheme
      .apply(bodyColor: Tokens.textPrimary, displayColor: Tokens.textPrimary)
      .copyWith(
        headlineMedium: const TextStyle(fontSize: Tokens.display, fontWeight: FontWeight.w700, color: Tokens.textPrimary),
        titleLarge: const TextStyle(fontSize: Tokens.title, fontWeight: FontWeight.w700, color: Tokens.textPrimary),
        titleMedium: const TextStyle(fontSize: Tokens.subtitle, fontWeight: FontWeight.w600, color: Tokens.textPrimary),
        bodyMedium: const TextStyle(fontSize: Tokens.body, color: Tokens.textPrimary, height: 1.35),
        bodySmall: const TextStyle(fontSize: Tokens.caption, color: Tokens.textSecondary, height: 1.3),
      )
      .apply(fontFamily: Tokens.fontFamily, fontFamilyFallback: Tokens.fontFallback);
  return base.copyWith(
    scaffoldBackgroundColor: Colors.transparent,
    textTheme: text,
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(fontFamily: Tokens.fontFamily, fontSize: Tokens.title, fontWeight: FontWeight.w700, color: Tokens.textPrimary),
      foregroundColor: Tokens.textPrimary,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Tokens.glassFill,
      hintStyle: const TextStyle(color: Tokens.textMuted),
      labelStyle: const TextStyle(color: Tokens.textSecondary),
      contentPadding: const EdgeInsets.symmetric(horizontal: Tokens.md, vertical: Tokens.sm),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(Tokens.rMd), borderSide: const BorderSide(color: Tokens.glassBorder)),
      enabledBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(Tokens.rMd), borderSide: const BorderSide(color: Tokens.glassBorder)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(Tokens.rMd), borderSide: const BorderSide(color: Tokens.blue)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rMd)),
        textStyle: const TextStyle(fontFamily: Tokens.fontFamily, fontWeight: FontWeight.w600, fontSize: Tokens.subtitle),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        foregroundColor: Tokens.textPrimary,
        side: const BorderSide(color: Tokens.glassHighlight),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rMd)),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: Tokens.glassFill,
      selectedColor: Tokens.blue.withValues(alpha: 0.35),
      side: const BorderSide(color: Tokens.glassBorder),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rPill)),
      labelStyle: const TextStyle(color: Tokens.textPrimary, fontFamily: Tokens.fontFamily),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Colors.white : Tokens.textSecondary),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Tokens.blue : Tokens.glassHighlight),
      trackOutlineColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Colors.transparent : Tokens.glassBorder),
    ),
    dividerTheme: const DividerThemeData(color: Tokens.glassBorder, space: 1),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: Tokens.bgElevated,
      contentTextStyle: const TextStyle(color: Tokens.textPrimary, fontFamily: Tokens.fontFamily),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rMd)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Tokens.bgElevated,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Tokens.rLg)),
    ),
    listTileTheme: const ListTileThemeData(iconColor: Tokens.textSecondary, textColor: Tokens.textPrimary),
  );
}

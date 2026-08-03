import 'package:flutter/material.dart';

import 'tokens.dart';

/// Builds the light and dark [ThemeData] from the token palette.
///
/// The brand teal seeds a Material 3 scheme; the handoff's specific surface,
/// background, and outline values then override the seeded roles so cards,
/// backgrounds, and dividers match the design exactly.
class AppTheme {
  AppTheme._();

  static ThemeData light() => _build(Brightness.light);
  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final base = ColorScheme.fromSeed(
      seedColor: AppTokens.brandPrimary,
      brightness: brightness,
    );
    final scheme = base.copyWith(
      primary: AppTokens.brandPrimary,
      // Brand teal is dark enough for white foreground in both themes; the
      // seed-generated onPrimary is dark in dark mode and would render
      // low-contrast labels on filled buttons.
      onPrimary: Colors.white,
      primaryContainer: isDark
          ? AppTokens.brandPrimaryContainerDark
          : AppTokens.brandPrimaryContainerLight,
      onPrimaryContainer:
          isDark ? AppTokens.onBrandContainerDark : AppTokens.onBrandContainerLight,
      surface: isDark ? AppTokens.surfaceDark : AppTokens.surfaceLight,
      surfaceContainerLowest: isDark ? AppTokens.bgDark : AppTokens.bgLight,
      surfaceContainerHighest:
          isDark ? AppTokens.surfaceVariantDark : AppTokens.surfaceVariantLight,
      onSurface: isDark ? AppTokens.textPrimaryDark : AppTokens.textPrimaryLight,
      onSurfaceVariant:
          isDark ? AppTokens.textSecondaryDark : AppTokens.textSecondaryLight,
      outline: isDark ? AppTokens.borderDark : AppTokens.borderLight,
      outlineVariant: isDark ? AppTokens.borderDark : AppTokens.borderLight,
      error: AppTokens.destructive,
      scrim: isDark ? AppTokens.scrimBackdropDark : AppTokens.scrimBackdropLight,
    );

    final scaffoldBg = isDark ? AppTokens.bgDark : AppTokens.bgLight;

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scaffoldBg,
      fontFamily: 'Roboto',
      appBarTheme: AppBarTheme(
        backgroundColor: scaffoldBg,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontSize: 21,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface,
        ),
      ),
      cardTheme: CardThemeData(
        color: scheme.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppTokens.radiusCard),
          side: BorderSide(color: scheme.outline),
        ),
        margin: EdgeInsets.zero,
      ),
      chipTheme: ChipThemeData(
        side: BorderSide.none,
        shape: const StadiumBorder(),
        backgroundColor:
            isDark ? AppTokens.chipGrayBgDark : AppTokens.chipGrayBgLight,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(48),
          shape: const StadiumBorder(),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        indicatorColor: scheme.primaryContainer,
        elevation: 0,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(AppTokens.radiusSheet)),
        ),
      ),
      dividerTheme: DividerThemeData(color: scheme.outline, thickness: 1),
    );
  }
}

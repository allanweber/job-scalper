import 'package:flutter/material.dart';

/// Design tokens from the handoff (`design_handoff_job_scalper/README.md`).
///
/// Colors are kept as raw light/dark pairs here and assembled into a Material 3
/// [ColorScheme] in `app_theme.dart` — widgets read semantic scheme roles, not
/// these constants directly (only score bands and a few semantic chips reach in).
class AppTokens {
  AppTokens._();

  // Brand.
  static const brandPrimary = Color(0xFF006B5E);
  static const brandPrimaryContainerLight = Color(0xFFCCE8E2);
  static const brandPrimaryContainerDark = Color(0xFF17332B);
  static const onBrandContainerLight = Color(0xFF00382F);
  static const onBrandContainerDark = Color(0xFF7FE0C4);

  // Surfaces / background.
  static const bgLight = Color(0xFFF5FAF8);
  static const bgDark = Color(0xFF0F1513);
  static const surfaceLight = Color(0xFFFFFFFF);
  static const surfaceDark = Color(0xFF1B2320);
  static const surfaceVariantLight = Color(0xFFEEF3F1);
  static const surfaceVariantDark = Color(0xFF252D2A);
  static const scrimBackdropLight = Color(0xFFDFE5E2);
  static const scrimBackdropDark = Color(0xFF060D0B);

  // Lines.
  static const borderLight = Color(0xFFE4EAE7);
  static const borderDark = Color(0xFF333C39);

  // Text.
  static const textPrimaryLight = Color(0xFF171D1B);
  static const textPrimaryDark = Color(0xFFE4EAE7);
  static const textSecondaryLight = Color(0xFF3F4946);
  static const textSecondaryDark = Color(0xFFBCC5C1);
  static const textTertiaryLight = Color(0xFF6F7976);
  static const textTertiaryDark = Color(0xFF909A95);

  // Destructive.
  static const destructive = Color(0xFFBA1A1A);
  static const destructivePressed = Color(0xFF93000A);

  // Semantic chips (bg / text) for light and dark.
  static const chipGrayBgLight = Color(0xFFE2E9E6);
  static const chipGrayBgDark = Color(0xFF2A3230);
  static const chipBlueBgLight = Color(0xFFDBE7F6);
  static const chipBlueTextLight = Color(0xFF0D2B52);
  static const chipBlueBgDark = Color(0xFF16283F);
  static const chipBlueTextDark = Color(0xFF9DC3EE);
  static const chipRedBgLight = Color(0xFFFFE0DD);
  static const chipRedTextLight = Color(0xFF5C1512);
  static const chipRedBgDark = Color(0xFF3A1F1C);
  static const chipRedTextDark = Color(0xFFF0A89F);
  static const chipTanBgLight = Color(0xFFF6ECD8);
  static const chipTanTextLight = Color(0xFF7A4D00);
  static const chipTanBgDark = Color(0xFF3A2F18);
  static const chipTanTextDark = Color(0xFFE3BD7C);

  // Match-score ring bands (consistent across feed, detail, saved, drafts).
  static const scoreStrong = Color(0xFF006B5E); // >= 85
  static const scoreGood = Color(0xFF4C8A2F); //   70-84
  static const scoreFair = Color(0xFF9A6B00); //   55-69
  static const scoreWeak = Color(0xFF8A4A44); //   < 55

  /// The ring/label color for a 0-100 match score.
  static Color scoreColor(int score) {
    if (score >= 85) return scoreStrong;
    if (score >= 70) return scoreGood;
    if (score >= 55) return scoreFair;
    return scoreWeak;
  }

  // Shape / spacing.
  static const radiusCard = 16.0;
  static const radiusSheet = 22.0;
  static const screenPadding = 16.0;
  static const cardPadding = 16.0;
  static const listGap = 12.0;
}

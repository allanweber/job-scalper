import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// The application pipeline stages in funnel order (mirrors the backend's
/// APPLICATION_STATUSES). 'applied' is the entry point and 'offer' the success
/// end; 'ghosted' (no response) and 'rejected' (denied) are off-ramps. A null
/// stage means "not applied".
const kApplicationStages = <String>[
  'applied',
  'pre_screen',
  'interviewing',
  'offer',
  'ghosted',
  'rejected',
];

/// Human label for a stage string.
String applicationStageLabel(String status) => switch (status) {
      'applied' => 'Applied',
      'pre_screen' => 'Pre-Screen',
      'interviewing' => 'Interviewing',
      'offer' => 'Offer',
      'ghosted' => 'Ghosted',
      'rejected' => 'Rejected',
      _ => status,
    };

/// Theme-aware background + foreground colors for a stage chip/pill. Each stage
/// gets a visually distinct, legible pair drawn from the app's chip palette:
/// applied = blue, pre-screen = purple, interviewing = amber, offer = brand
/// green, ghosted = gray, rejected = red.
({Color bg, Color fg}) applicationStageColors(String status, bool dark) =>
    switch (status) {
      'applied' => (
          bg: dark ? AppTokens.chipBlueBgDark : AppTokens.chipBlueBgLight,
          fg: dark ? AppTokens.chipBlueTextDark : AppTokens.chipBlueTextLight,
        ),
      'pre_screen' => (
          bg: dark ? AppTokens.chipPurpleBgDark : AppTokens.chipPurpleBgLight,
          fg: dark ? AppTokens.chipPurpleTextDark : AppTokens.chipPurpleTextLight,
        ),
      'interviewing' => (
          bg: dark ? AppTokens.chipTanBgDark : AppTokens.chipTanBgLight,
          fg: dark ? AppTokens.chipTanTextDark : AppTokens.chipTanTextLight,
        ),
      'offer' => (
          bg: dark
              ? AppTokens.brandPrimaryContainerDark
              : AppTokens.brandPrimaryContainerLight,
          fg: dark ? AppTokens.onBrandContainerDark : AppTokens.onBrandContainerLight,
        ),
      'rejected' => (
          bg: dark ? AppTokens.chipRedBgDark : AppTokens.chipRedBgLight,
          fg: dark ? AppTokens.chipRedTextDark : AppTokens.chipRedTextLight,
        ),
      _ => (
          bg: dark ? AppTokens.chipGrayBgDark : AppTokens.chipGrayBgLight,
          fg: dark ? AppTokens.textSecondaryDark : AppTokens.textSecondaryLight,
        ),
    };

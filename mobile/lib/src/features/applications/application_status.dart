import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// The application pipeline stages in funnel order (mirrors the backend's
/// APPLICATION_STATUSES). 'rejected' is an off-ramp rather than a later stage.
/// A null stage means "not applied".
const kApplicationStages = <String>['applied', 'interviewing', 'offer', 'rejected'];

/// Human label for a stage string.
String applicationStageLabel(String status) => switch (status) {
      'applied' => 'Applied',
      'interviewing' => 'Interviewing',
      'offer' => 'Offer',
      'rejected' => 'Rejected',
      _ => status,
    };

/// Theme-aware background + foreground colors for a stage chip/pill. Each stage
/// gets a visually distinct, legible pair drawn from the app's chip palette:
/// applied = blue, interviewing = amber, offer = brand green, rejected = red.
({Color bg, Color fg}) applicationStageColors(String status, bool dark) =>
    switch (status) {
      'applied' => (
          bg: dark ? AppTokens.chipBlueBgDark : AppTokens.chipBlueBgLight,
          fg: dark ? AppTokens.chipBlueTextDark : AppTokens.chipBlueTextLight,
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

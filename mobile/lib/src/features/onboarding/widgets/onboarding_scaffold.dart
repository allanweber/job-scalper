import 'package:flutter/material.dart';

import '../../../theme/tokens.dart';

/// Common chrome for the form-like onboarding steps: a slim progress bar, an
/// optional back button, a title/subtitle, a scrollable body, and a pinned
/// primary CTA with busy + error states.
class OnboardingScaffold extends StatelessWidget {
  const OnboardingScaffold({
    super.key,
    required this.title,
    this.subtitle,
    required this.child,
    required this.primaryLabel,
    required this.onPrimary,
    this.primaryEnabled = true,
    this.busy = false,
    this.showBack = true,
    this.onBack,
    this.progress,
    this.error,
    this.secondary,
  });

  final String title;
  final String? subtitle;
  final Widget child;
  final String primaryLabel;
  final VoidCallback? onPrimary;
  final bool primaryEnabled;
  final bool busy;
  final bool showBack;
  final VoidCallback? onBack;

  /// 0..1 completion for the top bar; null hides it.
  final double? progress;
  final String? error;

  /// Optional secondary action rendered under the primary CTA (e.g. "Not now").
  final Widget? secondary;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            if (progress != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: progress,
                    minHeight: 4,
                    backgroundColor: scheme.surfaceContainerHighest,
                  ),
                ),
              ),
            Align(
              alignment: Alignment.centerLeft,
              child: showBack
                  ? IconButton(
                      onPressed: busy ? null : onBack,
                      icon: const Icon(Icons.arrow_back),
                    )
                  : const SizedBox(height: 48),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 4, 24, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(title,
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    if (subtitle != null) ...[
                      const SizedBox(height: 8),
                      Text(subtitle!,
                          style: TextStyle(
                              color: scheme.onSurfaceVariant, fontSize: 14, height: 1.4)),
                    ],
                    const SizedBox(height: 24),
                    child,
                  ],
                ),
              ),
            ),
            _Footer(
              primaryLabel: primaryLabel,
              onPrimary: onPrimary,
              enabled: primaryEnabled,
              busy: busy,
              error: error,
              secondary: secondary,
            ),
          ],
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer({
    required this.primaryLabel,
    required this.onPrimary,
    required this.enabled,
    required this.busy,
    required this.error,
    required this.secondary,
  });

  final String primaryLabel;
  final VoidCallback? onPrimary;
  final bool enabled;
  final bool busy;
  final String? error;
  final Widget? secondary;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (error != null) ...[
            Text(error!,
                style: const TextStyle(color: AppTokens.destructive, fontSize: 13)),
            const SizedBox(height: 12),
          ],
          SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: (!enabled || busy) ? null : onPrimary,
              child: busy
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                          strokeWidth: 2.2, color: Colors.white))
                  : Text(primaryLabel,
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.w700)),
            ),
          ),
          if (secondary != null) ...[
            const SizedBox(height: 8),
            secondary!,
          ],
        ],
      ),
    );
  }
}

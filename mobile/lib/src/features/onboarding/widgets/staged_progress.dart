import 'package:flutter/material.dart';

import '../onboarding_controller.dart';

/// Full-screen staged loader: a titled list of steps that fill in with a
/// checkmark as [currentStep] advances, with a spinner on the active row. Used
/// for the async profile build and feed build.
class StagedProgress extends StatelessWidget {
  const StagedProgress({
    super.key,
    required this.title,
    required this.subtitle,
    required this.steps,
    required this.currentStep,
    required this.phase,
  });

  final String title;
  final String subtitle;
  final List<String> steps;
  final int currentStep;
  final AsyncPhase phase;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 40, 24, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Spacer(),
            Text(title,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Text(subtitle,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14)),
            const SizedBox(height: 32),
            for (var i = 0; i < steps.length; i++)
              _StepRow(
                label: steps[i],
                state: _rowState(i),
              ),
            const Spacer(flex: 2),
          ],
        ),
      ),
    );
  }

  _RowState _rowState(int i) {
    if (phase == AsyncPhase.failed && i >= currentStep) return _RowState.pending;
    if (i < currentStep) return _RowState.done;
    if (i == currentStep && phase != AsyncPhase.done) return _RowState.active;
    return _RowState.done;
  }
}

enum _RowState { pending, active, done }

class _StepRow extends StatelessWidget {
  const _StepRow({required this.label, required this.state});

  final String label;
  final _RowState state;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    late final Widget leading;
    late final Color textColor;
    switch (state) {
      case _RowState.done:
        leading = Icon(Icons.check_circle_rounded, color: scheme.primary, size: 24);
        textColor = scheme.onSurface;
      case _RowState.active:
        leading = SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(strokeWidth: 2.4, color: scheme.primary),
        );
        textColor = scheme.onSurface;
      case _RowState.pending:
        leading = Icon(Icons.radio_button_unchecked,
            color: scheme.onSurfaceVariant.withValues(alpha: 0.4), size: 24);
        textColor = scheme.onSurfaceVariant;
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          SizedBox(width: 24, height: 24, child: Center(child: leading)),
          const SizedBox(width: 14),
          Expanded(
            child: Text(label,
                style: TextStyle(
                    fontSize: 15,
                    color: textColor,
                    fontWeight: state == _RowState.active
                        ? FontWeight.w600
                        : FontWeight.w400)),
          ),
        ],
      ),
    );
  }
}

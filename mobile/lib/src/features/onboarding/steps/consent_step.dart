import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../legal_text.dart';
import '../onboarding_controller.dart';
import '../widgets/onboarding_scaffold.dart';

/// Step 3 — consent. Two required checkable cards (Terms, Privacy); the text
/// links open bottom sheets with the full prose. The CTA (`POST
/// /me/legal/accept`) is disabled until both are checked.
class ConsentStep extends ConsumerStatefulWidget {
  const ConsentStep({super.key});

  @override
  ConsumerState<ConsentStep> createState() => _ConsentStepState();
}

class _ConsentStepState extends ConsumerState<ConsentStep> {
  bool _tos = false;
  bool _privacy = false;

  @override
  Widget build(BuildContext context) {
    final st = ref.watch(onboardingControllerProvider);
    final ctrl = ref.read(onboardingControllerProvider.notifier);
    return OnboardingScaffold(
      progress: _progress,
      title: 'A couple of agreements',
      subtitle:
          'Please review and accept these to continue. Tap a title to read the full text.',
      onBack: ctrl.back,
      busy: st.busy,
      error: st.error,
      primaryLabel: 'Agree & continue',
      primaryEnabled: _tos && _privacy,
      onPrimary: ctrl.acceptConsent,
      child: Column(
        children: [
          _ConsentCard(
            checked: _tos,
            onChanged: (v) => setState(() => _tos = v),
            title: 'Terms of Service',
            onOpen: () => showLegalSheet(context, LegalKind.terms),
          ),
          const SizedBox(height: 12),
          _ConsentCard(
            checked: _privacy,
            onChanged: (v) => setState(() => _privacy = v),
            title: 'Privacy Policy',
            onOpen: () => showLegalSheet(context, LegalKind.privacy),
          ),
        ],
      ),
    );
  }

  double get _progress => 3 / 8;
}

class _ConsentCard extends StatelessWidget {
  const _ConsentCard({
    required this.checked,
    required this.onChanged,
    required this.title,
    required this.onOpen,
  });

  final bool checked;
  final ValueChanged<bool> onChanged;
  final String title;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => onChanged(!checked),
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: checked ? scheme.primary : scheme.outlineVariant,
              width: checked ? 1.5 : 1),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Checkbox(
              value: checked,
              onChanged: (v) => onChanged(v ?? false),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('I agree to the',
                      style: TextStyle(
                          fontSize: 13, color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 2),
                  GestureDetector(
                    onTap: onOpen,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(title,
                            style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: scheme.primary,
                                decoration: TextDecoration.underline,
                                decorationColor: scheme.primary)),
                        const SizedBox(width: 4),
                        Icon(Icons.open_in_new, size: 14, color: scheme.primary),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

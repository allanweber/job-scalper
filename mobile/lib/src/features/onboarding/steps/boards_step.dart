import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../board_catalog.dart';
import '../onboarding_controller.dart';
import '../widgets/onboarding_scaffold.dart';

/// Step 8 — pick job boards. Select up to `maxAllowed` (3 on free); a 4th tap is
/// blocked with a toast. Saved with `PUT /account/sources`.
class BoardsStep extends ConsumerWidget {
  const BoardsStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(onboardingControllerProvider);
    final ctrl = ref.read(onboardingControllerProvider.notifier);
    final sources = st.sources;
    final scheme = Theme.of(context).colorScheme;
    final selectedCount = sources?.selected.length ?? 0;
    final max = sources?.maxAllowed ?? 3;

    return OnboardingScaffold(
      progress: 8 / 8,
      title: 'Choose your job boards',
      subtitle:
          'We scan these for you. Free plan scans up to $max — you can change '
          'them anytime.',
      onBack: ctrl.back,
      busy: st.busy,
      error: st.error,
      primaryLabel: 'Continue',
      primaryEnabled: selectedCount > 0,
      onPrimary: ctrl.saveBoardsAndContinue,
      child: sources == null
          ? const Padding(
              padding: EdgeInsets.only(top: 40),
              child: Center(child: CircularProgressIndicator()),
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('$selectedCount of $max selected',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: scheme.primary)),
                const SizedBox(height: 12),
                for (final slug in sources.available)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _BoardTile(
                      info: boardInfo(slug),
                      selected: sources.selected.contains(slug),
                      atCap: selectedCount >= max &&
                          !sources.selected.contains(slug),
                      onTap: () {
                        final ok = ctrl.toggleBoard(slug);
                        if (!ok) {
                          ScaffoldMessenger.of(context)
                            ..hideCurrentSnackBar()
                            ..showSnackBar(SnackBar(
                                content: Text(
                                    'Free plan scans up to $max boards'),
                                behavior: SnackBarBehavior.floating,
                                duration: const Duration(seconds: 2)));
                        }
                      },
                    ),
                  ),
              ],
            ),
    );
  }
}

class _BoardTile extends StatelessWidget {
  const _BoardTile({
    required this.info,
    required this.selected,
    required this.atCap,
    required this.onTap,
  });

  final BoardInfo info;
  final bool selected;
  final bool atCap;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final dim = atCap && !selected;
    return Opacity(
      opacity: dim ? 0.5 : 1,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: selected
                ? scheme.primaryContainer.withValues(alpha: 0.5)
                : scheme.surfaceContainerLow,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
                color: selected ? scheme.primary : scheme.outlineVariant,
                width: selected ? 1.5 : 1),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(info.name,
                        style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: scheme.onSurface)),
                    const SizedBox(height: 2),
                    Text(info.blurb,
                        style: TextStyle(
                            fontSize: 12.5, color: scheme.onSurfaceVariant)),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Icon(
                selected
                    ? Icons.check_circle_rounded
                    : Icons.circle_outlined,
                color: selected ? scheme.primary : scheme.outlineVariant,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../onboarding_controller.dart';
import '../widgets/chip_input.dart';
import '../widgets/onboarding_scaffold.dart';

/// Step 7 — review profile. A fully editable form pre-filled from the resume
/// build; saved with `PUT /account/profile`.
class ReviewProfileStep extends ConsumerStatefulWidget {
  const ReviewProfileStep({super.key});

  @override
  ConsumerState<ReviewProfileStep> createState() => _ReviewProfileStepState();
}

class _ReviewProfileStepState extends ConsumerState<ReviewProfileStep> {
  late final TextEditingController _salary;

  @override
  void initState() {
    super.initState();
    final p = ref.read(onboardingControllerProvider).profile;
    _salary = TextEditingController(
        text: p.salaryFloor > 0 ? p.salaryFloor.toStringAsFixed(0) : '');
  }

  @override
  void dispose() {
    _salary.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final st = ref.watch(onboardingControllerProvider);
    final ctrl = ref.read(onboardingControllerProvider.notifier);
    final p = st.profile;
    final scheme = Theme.of(context).colorScheme;

    return OnboardingScaffold(
      progress: 7 / 8,
      title: 'Review your profile',
      subtitle:
          'This is what we rank jobs against. Add or remove anything — you can '
          'edit it later in your account.',
      onBack: ctrl.back,
      busy: st.busy,
      error: st.error,
      primaryLabel: 'Looks good',
      onPrimary: () {
        FocusScope.of(context).unfocus();
        ctrl.saveProfileAndContinue();
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ChipInput(
            label: 'Target titles',
            hint: 'e.g. Backend Engineer',
            values: p.titles,
            onChanged: (v) => ctrl.updateProfile(p.copyWith(titles: v)),
          ),
          const SizedBox(height: 22),
          ChipInput(
            label: 'Required skills',
            hint: 'e.g. Python',
            values: p.requiredSkills,
            onChanged: (v) => ctrl.updateProfile(p.copyWith(requiredSkills: v)),
          ),
          const SizedBox(height: 22),
          ChipInput(
            label: 'Nice-to-have skills',
            hint: 'e.g. Kubernetes',
            values: p.niceToHaveSkills,
            onChanged: (v) =>
                ctrl.updateProfile(p.copyWith(niceToHaveSkills: v)),
          ),
          const SizedBox(height: 22),
          ChipInput(
            label: 'Keywords',
            hint: 'e.g. fintech',
            values: p.keywords,
            onChanged: (v) => ctrl.updateProfile(p.copyWith(keywords: v)),
          ),
          const SizedBox(height: 22),
          ChipInput(
            label: 'Exclude keywords',
            hint: 'e.g. on-site',
            values: p.excludeKeywords,
            onChanged: (v) => ctrl.updateProfile(p.copyWith(excludeKeywords: v)),
          ),
          const SizedBox(height: 22),
          LabeledField(
            label: 'Minimum salary (USD / year)',
            child: TextField(
              controller: _salary,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              style: const TextStyle(fontFamily: 'RobotoMono'),
              decoration: const InputDecoration(
                isDense: true,
                prefixText: '\$ ',
                hintText: '0',
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              ),
              onChanged: (v) => ctrl.updateProfile(
                  p.copyWith(salaryFloor: double.tryParse(v) ?? 0)),
            ),
          ),
          const SizedBox(height: 8),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('Remote only',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: scheme.onSurface)),
            subtitle: Text('Only show fully-remote roles',
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            value: p.remoteOnly,
            onChanged: (v) => ctrl.updateProfile(p.copyWith(remoteOnly: v)),
          ),
        ],
      ),
    );
  }
}

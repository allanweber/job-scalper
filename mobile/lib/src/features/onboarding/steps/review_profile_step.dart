import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../profile/widgets/profile_form_fields.dart';
import '../onboarding_controller.dart';
import '../widgets/onboarding_scaffold.dart';

/// Step 7 — review profile. A fully editable form pre-filled from the resume
/// build; saved with `PUT /me/profile`. The form itself is the shared
/// [ProfileFormFields], also used by the Profile → Search profile editor.
class ReviewProfileStep extends ConsumerWidget {
  const ReviewProfileStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(onboardingControllerProvider);
    final ctrl = ref.read(onboardingControllerProvider.notifier);

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
      child: ProfileFormFields(
        value: st.profile,
        onChanged: (p) => ctrl.updateProfile(p),
      ),
    );
  }
}

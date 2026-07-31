import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'onboarding_controller.dart';
import 'steps/boards_step.dart';
import 'steps/consent_step.dart';
import 'steps/notifications_step.dart';
import 'steps/resume_step.dart';
import 'steps/review_profile_step.dart';
import 'steps/signin_step.dart';
import 'steps/welcome_step.dart';
import 'widgets/staged_progress.dart';

/// The onboarding flow. A single route whose body is driven by
/// [OnboardingController]'s current [OnboardingStep]; the controller commits each
/// step to the backend and, on the final feed build, flips the session's
/// onboarding-complete flag (the router then redirects to the feed).
class OnboardingScreen extends ConsumerWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final step = ref.watch(onboardingControllerProvider.select((s) => s.step));
    return PopScope(
      // Back is handled inside each step via the controller.
      canPop: false,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 220),
        child: KeyedSubtree(
          key: ValueKey(step),
          child: _bodyFor(step),
        ),
      ),
    );
  }

  Widget _bodyFor(OnboardingStep step) => switch (step) {
        OnboardingStep.welcome => const WelcomeStep(),
        OnboardingStep.signIn => const SignInStep(),
        OnboardingStep.consent => const ConsentStep(),
        OnboardingStep.resume => const ResumeStep(),
        OnboardingStep.buildingProfile => const _BuildingProfile(),
        OnboardingStep.reviewProfile => const ReviewProfileStep(),
        OnboardingStep.boards => const BoardsStep(),
        OnboardingStep.notifications => const NotificationsStep(),
        OnboardingStep.buildingFeed => const _BuildingFeed(),
      };
}

class _BuildingProfile extends ConsumerWidget {
  const _BuildingProfile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(onboardingControllerProvider);
    return Scaffold(
      body: StagedProgress(
        title: 'Building your profile',
        subtitle: 'Reading your resume and extracting your skills…',
        steps: const [
          'Uploading resume',
          'Analyzing experience',
          'Extracting skills & keywords',
        ],
        currentStep: st.buildStepIndex,
        phase: st.buildPhase,
      ),
    );
  }
}

class _BuildingFeed extends ConsumerWidget {
  const _BuildingFeed();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(onboardingControllerProvider);
    return Scaffold(
      body: StagedProgress(
        title: 'Building your feed',
        subtitle: 'Scoring live postings against your new profile…',
        steps: const [
          'Gathering postings from your boards',
          'Scoring against your profile',
          'Ranking your best matches',
        ],
        currentStep: st.buildStepIndex,
        phase: st.buildPhase,
      ),
    );
  }
}

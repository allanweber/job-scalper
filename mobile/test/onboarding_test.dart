import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/onboarding_harness.dart';
import 'package:job_scalper/src/features/onboarding/onboarding_controller.dart';
import 'package:job_scalper/src/features/onboarding/onboarding_screen.dart';
import 'package:job_scalper/src/state/session.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Builds a ProviderContainer with the fake account repo, an in-memory
/// signed-in session, and the controller seeded onto [step].
Future<(ProviderContainer, FakeAccountRepository)> _container(
    OnboardingStep step,
    {FakeAccountRepository? repo, String? googleToken = 'fake-id-token'}) async {
  SharedPreferences.setMockInitialValues({
    'session.tokens':
        '{"access_token":"a","refresh_token":"r","expires_in":900}',
  });
  final prefs = await SharedPreferences.getInstance();
  final fake = repo ?? FakeAccountRepository();
  final container = ProviderContainer(overrides: [
    sharedPrefsProvider.overrideWithValue(prefs),
    accountRepositoryProvider.overrideWithValue(fake),
    googleAuthenticatorProvider
        .overrideWithValue(FakeGoogleAuthenticator(token: googleToken)),
    onboardingControllerProvider.overrideWith(
        () => SeededOnboardingController(seededState(step))),
  ]);
  addTearDown(container.dispose);
  return (container, fake);
}

Future<void> _pump(WidgetTester tester, ProviderContainer container) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: OnboardingScreen()),
  ));
  await tester.pump();
}

void main() {
  testWidgets('welcome shows first value-prop slide + Skip', (tester) async {
    final (container, _) = await _container(OnboardingStep.welcome);
    await _pump(tester, container);
    expect(find.text('Remote roles, already ranked'), findsOneWidget);
    expect(find.text('Skip'), findsOneWidget);
    expect(find.text('Next'), findsOneWidget);
  });

  testWidgets('cancelling Google sign-in stays on the sign-in step',
      (tester) async {
    final (container, _) = await _container(OnboardingStep.signIn,
        googleToken: null); // authenticator returns null == cancelled
    await _pump(tester, container);

    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();

    // No crash, no error, still on sign-in.
    expect(container.read(onboardingControllerProvider).step,
        OnboardingStep.signIn);
    expect(container.read(onboardingControllerProvider).error, isNull);
  });

  testWidgets('consent CTA is gated until both boxes are checked',
      (tester) async {
    final (container, fake) = await _container(OnboardingStep.consent);
    await _pump(tester, container);

    final cta = find.widgetWithText(FilledButton, 'Agree & continue');
    expect(tester.widget<FilledButton>(cta).onPressed, isNull);

    await tester.tap(find.byType(Checkbox).first);
    await tester.pump();
    expect(tester.widget<FilledButton>(cta).onPressed, isNull);

    await tester.tap(find.byType(Checkbox).last);
    await tester.pump();
    expect(tester.widget<FilledButton>(cta).onPressed, isNotNull);

    await tester.tap(cta);
    await tester.pumpAndSettle();
    expect(fake.legalAccepted, isTrue);
    // Advanced off the consent step.
    expect(container.read(onboardingControllerProvider).step,
        OnboardingStep.resume);
  });

  testWidgets('review profile is pre-filled and saves on continue',
      (tester) async {
    final (container, fake) = await _container(OnboardingStep.reviewProfile);
    await _pump(tester, container);

    expect(find.text('Backend Engineer'), findsOneWidget);
    expect(find.text('Python'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Looks good'));
    await tester.pumpAndSettle();

    expect(fake.savedProfile, isNotNull);
    expect(fake.savedProfile!.titles, contains('Backend Engineer'));
    expect(container.read(onboardingControllerProvider).step,
        OnboardingStep.boards);
  });

  testWidgets('board picker enforces the 3-board cap', (tester) async {
    final (container, _) = await _container(OnboardingStep.boards);
    await _pump(tester, container);

    final ctrl = container.read(onboardingControllerProvider.notifier);
    // Seeded with 2 selected; a 3rd is allowed, a 4th is blocked.
    expect(ctrl.toggleBoard('arbeitnow'), isTrue);
    expect(ctrl.toggleBoard('jobicy'), isFalse);
    expect(container.read(onboardingControllerProvider).sources!.selected.length,
        3);
  });

  testWidgets('notifications choice completes onboarding via feed build',
      (tester) async {
    final (container, _) = await _container(OnboardingStep.notifications);
    await _pump(tester, container);

    await tester.tap(find.text('Not now'));
    await tester.pump(); // enter buildingFeed
    expect(container.read(onboardingControllerProvider).step,
        OnboardingStep.buildingFeed);

    // Let the staged loader settle; onboarding-complete flips at the end.
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(container.read(sessionProvider).onboardingComplete, isTrue);
  });

  testWidgets('successful resume build pre-fills the review step',
      (tester) async {
    final (container, _) = await _container(OnboardingStep.resume);
    await _pump(tester, container);

    // Drive the build directly, bypassing the native file picker.
    unawaited(container
        .read(onboardingControllerProvider.notifier)
        .submitResume(bytes: [1], filename: 'cv.pdf', contentType: 'application/pdf'));
    await tester.pump(); // enter buildingProfile
    await tester.pump(const Duration(seconds: 3)); // staged loader settles
    await tester.pumpAndSettle();

    final st = container.read(onboardingControllerProvider);
    expect(st.step, OnboardingStep.reviewProfile);
    expect(st.error, isNull);
    expect(st.profile.titles, contains('Backend Engineer'));
  });

  testWidgets('failed resume build surfaces the job error on review',
      (tester) async {
    final fake = FakeAccountRepository(jobFails: true);
    final (container, _) = await _container(OnboardingStep.resume, repo: fake);
    await _pump(tester, container);

    unawaited(container
        .read(onboardingControllerProvider.notifier)
        .submitResume(bytes: [1], filename: 'cv.pdf', contentType: 'application/pdf'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();

    final st = container.read(onboardingControllerProvider);
    expect(st.step, OnboardingStep.reviewProfile);
    expect(st.buildPhase, AsyncPhase.failed);
    // The backend job's own error message is surfaced (not a silent empty form).
    expect(st.error, contains('unreadable resume'));
    expect(find.text(st.error!), findsOneWidget);
  });

  testWidgets('back from review skips the build loader and lands on resume',
      (tester) async {
    final (container, _) = await _container(OnboardingStep.reviewProfile);
    await _pump(tester, container);

    container.read(onboardingControllerProvider.notifier).back();
    // Must NOT strand the user on the non-rewindable buildingProfile loader.
    expect(container.read(onboardingControllerProvider).step,
        OnboardingStep.resume);
  });

  testWidgets('every step renders without error', (tester) async {
    for (final step in OnboardingStep.values) {
      final (container, _) = await _container(step);
      await _pump(tester, container);
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.takeException(), isNull, reason: 'step $step threw');
    }
  });
}

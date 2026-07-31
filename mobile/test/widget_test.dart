import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/app.dart';
import 'package:job_scalper/src/state/session.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> _pumpApp(WidgetTester tester,
    {Map<String, Object> seed = const {}}) async {
  SharedPreferences.setMockInitialValues(seed);
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      child: const JobScalperApp(),
    ),
  );
}

void main() {
  testWidgets('launch screen shows brand then routes to onboarding',
      (tester) async {
    await _pumpApp(tester);
    // Splash is visible immediately.
    expect(find.text('Job Scalper'), findsOneWidget);
    expect(find.text('Warming up…'), findsOneWidget);

    // After the splash delay, a signed-out first run lands on onboarding.
    await tester.pump(const Duration(milliseconds: 1700));
    await tester.pumpAndSettle();
    expect(find.text('Welcome to Job Scalper'), findsOneWidget);
    expect(find.text('Get started'), findsOneWidget);
  });

  testWidgets('restoring copy shows when a session is persisted',
      (tester) async {
    await _pumpApp(tester, seed: {
      'session.onboardingComplete': true,
      'session.tokens':
          '{"access_token":"a","refresh_token":"r","expires_in":900}',
    });
    expect(find.text('Restoring your session…'), findsOneWidget);
    // Let the splash timer fire so no timer leaks past teardown.
    await tester.pump(const Duration(milliseconds: 1700));
    await tester.pumpAndSettle();
  });

  testWidgets('session persists onboarding + theme mode', (tester) async {
    await _pumpApp(tester);
    final container = ProviderScope.containerOf(
        tester.element(find.byType(JobScalperApp)));
    final controller = container.read(sessionProvider.notifier);
    await controller.completeOnboarding();
    await controller.setThemeMode(ThemeMode.dark);
    expect(container.read(sessionProvider).onboardingComplete, isTrue);
    expect(container.read(sessionProvider).themeMode, ThemeMode.dark);
    // Drain the splash timer.
    await tester.pump(const Duration(milliseconds: 1700));
    await tester.pumpAndSettle();
  });
}

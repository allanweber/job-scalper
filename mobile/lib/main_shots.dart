import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'src/data/providers.dart';
import 'src/dev/onboarding_harness.dart';
import 'src/features/onboarding/onboarding_controller.dart';
import 'src/features/onboarding/onboarding_screen.dart';
import 'src/state/session.dart';
import 'src/theme/app_theme.dart';

/// Screenshot/QA entrypoint (NOT shipped) for the onboarding flow. Renders a
/// single seeded step chosen by the `?step=` query param, backed by the
/// in-memory fake so no server is needed. Theme follows platform brightness so
/// the capture tool can shoot light + dark by toggling prefers-color-scheme.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('session.tokens',
      '{"access_token":"demo","refresh_token":"demo","expires_in":900}');

  final name = Uri.base.queryParameters['step'] ?? 'welcome';
  final step = OnboardingStep.values.firstWhere(
    (s) => s.name == name,
    orElse: () => OnboardingStep.welcome,
  );

  runApp(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        accountRepositoryProvider.overrideWithValue(FakeAccountRepository()),
        googleAuthenticatorProvider
            .overrideWithValue(FakeGoogleAuthenticator()),
        onboardingControllerProvider
            .overrideWith(() => SeededOnboardingController(seededState(step))),
      ],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: ThemeMode.system,
        home: const OnboardingScreen(),
      ),
    ),
  );
}

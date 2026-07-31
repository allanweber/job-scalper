import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'src/app.dart';
import 'src/state/session.dart';

/// Screenshot/QA entrypoint (NOT shipped): seeds a signed-in, onboarding-complete
/// session with in-memory prefs so the nav shell renders without a backend or the
/// native Google flow. Theme follows the platform brightness, so a viewer can
/// screenshot light and dark by toggling prefers-color-scheme.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({
    'session.onboardingComplete': true,
    'session.themeMode': ThemeMode.system.index,
    'session.tokens':
        '{"access_token":"demo","refresh_token":"demo","expires_in":900}',
  });
  final prefs = await SharedPreferences.getInstance();
  runApp(
    ProviderScope(
      overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      child: const JobScalperApp(),
    ),
  );
}

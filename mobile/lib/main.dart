import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'src/app.dart';
import 'src/data/push_messaging.dart';
import 'src/state/session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Initialize Firebase so push works where it's configured (Android reads
  // google-services.json). If there's no config on this platform (e.g. iOS
  // before its APNs setup), push stays disabled and the app runs normally.
  try {
    await Firebase.initializeApp();
    firebaseAvailable = true;
  } catch (_) {
    firebaseAvailable = false;
  }
  final prefs = await SharedPreferences.getInstance();
  runApp(
    ProviderScope(
      overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      child: const JobScalperApp(),
    ),
  );
}

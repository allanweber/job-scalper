import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'data/providers.dart';
import 'data/push_messaging.dart';
import 'router/app_router.dart';
import 'state/push_registration.dart';
import 'state/session.dart';
import 'theme/app_theme.dart';

class JobScalperApp extends ConsumerStatefulWidget {
  const JobScalperApp({super.key});

  @override
  ConsumerState<JobScalperApp> createState() => _JobScalperAppState();
}

class _JobScalperAppState extends ConsumerState<JobScalperApp> {
  StreamSubscription<PushOpen>? _openSub;

  @override
  void initState() {
    super.initState();
    // Keep this device's push token registered while signed in.
    ref.read(pushRegistrationProvider);
    // Route notification taps into the app (no-op when push is unavailable).
    final messaging = ref.read(pushMessagingProvider);
    _openSub = messaging.onOpened.listen(_openFrom);
    messaging.initialOpen().then((open) {
      if (open != null) _openFrom(open);
    });
  }

  void _openFrom(PushOpen open) {
    if (!mounted) return;
    final router = ref.read(routerProvider);
    final pid = open.postingId;
    if (pid != null && pid.isNotEmpty) {
      router.go('/feed');
      router.push('/feed/job/$pid');
    } else {
      router.go('/feed');
    }
  }

  @override
  void dispose() {
    _openSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    final themeMode = ref.watch(sessionProvider.select((s) => s.themeMode));
    return MaterialApp.router(
      title: 'Job Scalper',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: themeMode,
      routerConfig: router,
    );
  }
}

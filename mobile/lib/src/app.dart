import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router/app_router.dart';
import 'state/session.dart';
import 'theme/app_theme.dart';

class JobScalperApp extends ConsumerWidget {
  const JobScalperApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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

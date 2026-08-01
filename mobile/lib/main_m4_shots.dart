import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/data/providers.dart';
import 'src/dev/feed_harness.dart';
import 'src/features/detail/job_detail_screen.dart';
import 'src/features/saved/saved_screen.dart';
import 'src/theme/app_theme.dart';

/// Screenshot/QA entrypoint (NOT shipped) for M4. `?screen=detail|saved` picks
/// the surface and `?state=ready|empty|error` the backing data; the real
/// screens run against the in-memory fake so no server is needed.
void main() {
  final params = Uri.base.queryParameters;
  final screen = params['screen'] ?? 'detail';
  final state = params['state'] ?? 'ready';

  final repo = switch (state) {
    'empty' => FakeFeedRepository(items: const []),
    'error' => FakeFeedRepository(fails: true),
    _ => FakeFeedRepository(),
  };

  final Widget home = screen == 'saved'
      ? const SavedScreen()
      : const JobDetailScreen(postingId: 'j1');

  runApp(
    ProviderScope(
      overrides: [feedRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: ThemeMode.system,
        home: home,
      ),
    ),
  );
}

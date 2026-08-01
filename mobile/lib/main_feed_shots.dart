import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/data/providers.dart';
import 'src/dev/feed_harness.dart';
import 'src/features/feed/feed_screen.dart';
import 'src/theme/app_theme.dart';

/// Screenshot/QA entrypoint (NOT shipped) for the Feed tab. Renders the real
/// [FeedScreen] backed by the in-memory fake so no server is needed; the
/// `?state=` query param selects ready / empty / error / loading.
void main() {
  final state = Uri.base.queryParameters['state'] ?? 'ready';
  final repo = switch (state) {
    'empty' => FakeFeedRepository(items: const []),
    'error' => FakeFeedRepository(fails: true),
    'loading' => FakeFeedRepository(delay: const Duration(minutes: 5)),
    _ => FakeFeedRepository(),
  };

  runApp(
    ProviderScope(
      overrides: [feedRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: ThemeMode.system,
        home: const FeedScreen(),
      ),
    ),
  );
}

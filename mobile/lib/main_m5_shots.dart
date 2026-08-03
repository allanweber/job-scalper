import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/data/providers.dart';
import 'src/dev/drafts_harness.dart';
import 'src/features/applications/applications_screen.dart';
import 'src/features/applications/draft_detail_screen.dart';
import 'src/theme/app_theme.dart';

/// Screenshot/QA entrypoint (NOT shipped) for M5. `?screen=applications|detail`
/// picks the surface and `?state=ready|empty|error` the backing data; the real
/// screens run against the in-memory fake so no server is needed.
void main() {
  final params = Uri.base.queryParameters;
  final screen = params['screen'] ?? 'applications';
  final state = params['state'] ?? 'ready';

  final repo = switch (state) {
    'empty' => FakeDraftsRepository(items: const []),
    'error' => FakeDraftsRepository(fails: true),
    _ => FakeDraftsRepository(),
  };

  final Widget home = screen == 'detail'
      ? DraftDetailScreen(draftId: 'd1', initial: demoDraftSummaries.first)
      : const ApplicationsScreen();

  runApp(
    ProviderScope(
      overrides: [draftsRepositoryProvider.overrideWithValue(repo)],
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

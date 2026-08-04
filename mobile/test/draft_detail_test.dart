import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:job_scalper/src/data/drafts_repository.dart';
import 'package:job_scalper/src/data/models/draft_models.dart';
import 'package:job_scalper/src/data/pdf_cache_repository.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/drafts_harness.dart';
import 'package:job_scalper/src/dev/feed_harness.dart';
import 'package:job_scalper/src/features/applications/draft_detail_screen.dart';
import 'package:job_scalper/src/features/detail/job_detail_screen.dart';

class _NoPdfCache extends PdfCacheRepository {
  @override
  Future<Uint8List?> get(String draftId, String docType) async => null;
  @override
  Future<void> put(String draftId, String docType, Uint8List bytes) async {}
  @override
  Future<void> invalidate(String draftId) async {}
}

ProviderContainer _container({DraftsRepository? repo}) {
  final container = ProviderContainer(overrides: [
    draftsRepositoryProvider.overrideWithValue(repo ?? FakeDraftsRepository()),
    pdfCacheRepositoryProvider.overrideWithValue(_NoPdfCache()),
  ]);
  addTearDown(container.dispose);
  return container;
}

Future<void> _pump(WidgetTester tester, ProviderContainer container,
    {String id = 'd1'}) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
      home: DraftDetailScreen(
        draftId: id,
        initial: demoDraftSummaries.firstWhere((d) => d.id == id),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('why-this-draft shows matched skills; regenerate picks a tone',
      (tester) async {
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final repo = FakeDraftsRepository();
    await _pump(tester, _container(repo: repo));

    // "Why this draft" surfaces the matched profile skills.
    expect(find.text('Why this draft'), findsOneWidget);
    expect(find.text('Python'), findsWidgets);

    // Regenerate opens the tone sheet; picking a tone calls the repo with it.
    await tester.tap(find.byTooltip('Regenerate'));
    await tester.pumpAndSettle();
    expect(find.text('Regenerate in a tone'), findsOneWidget);
    await tester.tap(find.text('Confident'));
    await tester.pumpAndSettle();
    expect(repo.regenerateCalls, hasLength(1));
    expect(repo.regenerateCalls.first.tone, 'confident');
  });

  testWidgets('shows resume by default and switches to the cover letter',
      (tester) async {
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pump(tester, _container());

    expect(find.text('Senior Backend Engineer'), findsOneWidget); // app bar
    expect(find.textContaining('Backend engineer with 6+ years'),
        findsOneWidget); // resume body

    // Header carries the job link + both PDF exports; the model line is gone.
    expect(find.text('View job posting'), findsOneWidget);
    expect(find.text('Resume PDF'), findsOneWidget);
    expect(find.text('Cover letter PDF'), findsOneWidget);
    expect(find.textContaining('claude-haiku'), findsNothing);

    await tester.tap(find.text('Cover letter'));
    await tester.pumpAndSettle();
    expect(find.textContaining('excited to apply'), findsOneWidget);
  });

  testWidgets('editing the resume PUTs the new markdown', (tester) async {
    final repo = FakeDraftsRepository();
    await _pump(tester, _container(repo: repo));

    await tester.tap(find.byIcon(Icons.edit_outlined));
    await tester.pumpAndSettle(); // full-screen editor opens

    await tester.enterText(find.byType(TextField), '# Edited resume');
    await tester.tap(find.widgetWithText(FilledButton, 'Save changes'));
    await tester.pumpAndSettle();

    expect(repo.edits, hasLength(1));
    expect(repo.edits.single.resumeMd, '# Edited resume');
    expect(find.text('Resume saved'), findsOneWidget); // snackbar
  });

  testWidgets('error state renders with retry', (tester) async {
    await _pump(tester, _container(repo: FakeDraftsRepository(fails: true)));
    expect(find.text("Couldn't load this draft"), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Retry'), findsOneWidget);
  });

  testWidgets('marking applied enters the pipeline and shows the stage control',
      (tester) async {
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final repo = FakeDraftsRepository();
    await _pump(tester, _container(repo: repo));

    // Starts un-applied: the call-to-action is shown.
    expect(find.text('Mark as applied'), findsOneWidget);

    await tester.tap(find.text('Mark as applied'));
    await tester.pumpAndSettle();

    // Enters the funnel at 'applied' via the status endpoint.
    expect(repo.statusCalls, hasLength(1));
    expect(repo.statusCalls.single.status, 'applied');
    // The CTA gives way to the stage picker.
    expect(find.text('Mark as applied'), findsNothing);
    expect(find.text('Application status'), findsOneWidget);
    expect(find.text('Remove'), findsOneWidget);
    expect(find.text('Updated to Applied'), findsOneWidget); // snackbar
  });

  testWidgets('advancing the stage and removing call the repo', (tester) async {
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final applied = DraftSummary(
      id: 'ds',
      postingId: 'js',
      jobSource: 'pool',
      keySource: 'platform',
      createdAt: DateTime.now().toIso8601String(),
      title: 'Staff Engineer',
      company: 'Acme',
      applied: true,
      applicationStatus: 'applied',
    );
    final repo = FakeDraftsRepository(items: [applied]);
    final container = _container(repo: repo);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: DraftDetailScreen(draftId: 'ds', initial: applied),
      ),
    ));
    await tester.pumpAndSettle();

    // Advance to a later stage.
    await tester.tap(find.text('Offer'));
    await tester.pumpAndSettle();
    expect(repo.statusCalls.last.status, 'offer');

    // Remove clears the stage and returns to the call-to-action.
    await tester.tap(find.text('Remove'));
    await tester.pumpAndSettle();
    expect(repo.statusCalls.last.status, isNull);
    expect(find.text('Mark as applied'), findsOneWidget);
  });

  testWidgets('Job analysis navigates to the nested job detail route',
      (tester) async {
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    // Mirror the real router nesting: job/:id lives under the draft route, so a
    // push must resolve to /applications/draft/:id/job/:id (absolute), not
    // /job/:id — the bug that produced "Page Not Found".
    final router = GoRouter(
      initialLocation: '/applications/draft/d1',
      routes: [
        GoRoute(
          path: '/applications/draft/:id',
          builder: (_, state) => DraftDetailScreen(
            draftId: state.pathParameters['id']!,
            initial: demoDraftSummaries
                .firstWhere((d) => d.id == state.pathParameters['id']),
          ),
          routes: [
            GoRoute(
              path: 'job/:postingId',
              builder: (_, state) => JobDetailScreen(
                  postingId: state.pathParameters['postingId']!),
            ),
          ],
        ),
      ],
    );
    final container = ProviderContainer(overrides: [
      draftsRepositoryProvider.overrideWithValue(FakeDraftsRepository()),
      pdfCacheRepositoryProvider.overrideWithValue(_NoPdfCache()),
      feedRepositoryProvider.overrideWithValue(FakeFeedRepository()),
    ]);
    addTearDown(container.dispose);

    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(routerConfig: router),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Job analysis'));
    await tester.pumpAndSettle();

    // Landed on the job detail (its 'Job' app bar), not the error page.
    expect(find.widgetWithText(AppBar, 'Job'), findsOneWidget);
    expect(find.textContaining('no routes for location'), findsNothing);
  });

  testWidgets('a draft in the pipeline shows the stage control, not the CTA',
      (tester) async {
    final applied = DraftSummary(
      id: 'da',
      postingId: 'ja',
      jobSource: 'pool',
      keySource: 'platform',
      createdAt: DateTime.now().toIso8601String(),
      title: 'Applied Role',
      company: 'Acme',
      applied: true,
      applicationStatus: 'interviewing',
    );
    final repo = FakeDraftsRepository(items: [applied]);
    final container = _container(repo: repo);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: DraftDetailScreen(draftId: 'da', initial: applied),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Application status'), findsOneWidget);
    expect(find.text('Mark as applied'), findsNothing);
    // The current stage is one of the selectable chips.
    expect(find.text('Interviewing'), findsWidgets);
  });

  testWidgets('a pending draft shows the drafting state, then the content',
      (tester) async {
    tester.view.physicalSize = const Size(1170, 5000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    // 'd1' comes back pending on the first fetch, ready afterwards.
    final container =
        _container(repo: FakeDraftsRepository(pendingOnce: {'d1'}));
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: DraftDetailScreen(
            draftId: 'd1', initial: demoDraftSummaries.first),
      ),
    ));
    // Let the initial load resolve (pending) — pump manually because the
    // drafting spinner never settles.
    await tester.pump();
    await tester.pump();
    expect(find.text('Drafting your application…'), findsOneWidget);
    expect(find.text('Mark as applied'), findsNothing); // actions disabled
    expect(find.byIcon(Icons.edit_outlined), findsNothing);

    // Advance past the poll interval; the second fetch returns the ready draft.
    await tester.pump(const Duration(milliseconds: 1600));
    await tester.pump();
    await tester.pump();
    expect(find.text('Drafting your application…'), findsNothing);
    expect(find.text('Mark as applied'), findsOneWidget); // actions enabled
    expect(find.textContaining('Backend engineer with'), findsOneWidget);
  });

  testWidgets('a failed draft shows the failure and its reason', (tester) async {
    final failed = DraftSummary(
      id: 'df',
      postingId: 'j1',
      jobSource: 'pool',
      keySource: 'platform',
      createdAt: DateTime.now().toIso8601String(),
      title: 'Broken Role',
      status: 'failed',
      error: 'no resume on file — upload a resume first',
    );
    final container = _container(repo: FakeDraftsRepository(items: [failed]));
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: DraftDetailScreen(draftId: 'df', initial: failed),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text("Couldn't finish this draft"), findsOneWidget);
    expect(find.textContaining('upload a resume first'), findsOneWidget);
    expect(find.text('Mark as applied'), findsNothing);
  });
}

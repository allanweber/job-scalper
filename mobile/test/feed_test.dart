import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:job_scalper/src/data/feed_repository.dart';
import 'package:job_scalper/src/data/models/feed_models.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/feed_harness.dart';
import 'package:job_scalper/src/features/feed/feed_controller.dart';
import 'package:job_scalper/src/features/feed/feed_screen.dart';
import 'package:job_scalper/src/features/feed/widgets/job_card.dart';

ProviderContainer _container({FeedRepository? repo}) {
  final container = ProviderContainer(overrides: [
    feedRepositoryProvider.overrideWithValue(repo ?? FakeFeedRepository()),
  ]);
  addTearDown(container.dispose);
  return container;
}

Future<void> _pump(WidgetTester tester, ProviderContainer container) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: FeedScreen()),
  ));
  await tester.pumpAndSettle();
}

/// Router-backed pump for the URL-import flow, whose success path navigates to
/// the imported posting's detail. The detail route is a stub so the test stays
/// focused on the feed screen and its dialog.
Future<void> _pumpRouter(WidgetTester tester, ProviderContainer container) async {
  final router = GoRouter(
    initialLocation: '/feed',
    routes: [
      GoRoute(path: '/feed', builder: (_, _) => const FeedScreen(), routes: [
        GoRoute(
          path: 'job/:id',
          builder: (_, s) =>
              Scaffold(body: Text('job ${s.pathParameters['id']}')),
        ),
      ]),
    ],
  );
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(routerConfig: router),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders ranked postings with the new-matches banner',
      (tester) async {
    final container = _container();
    await _pump(tester, container);

    // Full set is loaded (some cards are below the fold in the test viewport).
    expect(container.read(feedControllerProvider).items, hasLength(4));
    expect(find.byType(JobCard), findsWidgets);
    expect(find.text('Senior Backend Engineer'), findsOneWidget);
    expect(find.text('92'), findsOneWidget); // score ring
    expect(find.text('2 new matches since you last looked'), findsOneWidget);
  });

  testWidgets('score filter narrows the list to qualifying postings',
      (tester) async {
    final container = _container();
    await _pump(tester, container);
    expect(container.read(feedControllerProvider).items, hasLength(4));

    await tester.tap(find.text('85+'));
    await tester.pumpAndSettle();

    // Only the score-92 posting clears an 85 threshold.
    expect(container.read(feedControllerProvider).items, hasLength(1));
    expect(find.text('Senior Backend Engineer'), findsOneWidget);
  });

  testWidgets('tapping save persists optimistically', (tester) async {
    final repo = FakeFeedRepository();
    await _pump(tester, _container(repo: repo));

    // j1 (first card) is unsaved -> its heart is the outline variant.
    await tester.tap(find.byIcon(Icons.favorite_outline).first);
    await tester.pump();

    expect(repo.savedCalls, contains('j1'));
    // Optimistic: the filled heart appears immediately.
    expect(find.byIcon(Icons.favorite_rounded), findsWidgets);
  });

  testWidgets('empty state renders when nothing matches', (tester) async {
    await _pump(tester, _container(repo: FakeFeedRepository(items: const [])));
    expect(find.text('No matches yet'), findsOneWidget);
    expect(find.byType(JobCard), findsNothing);
  });

  testWidgets('empty state nudges to complete profile when none exists',
      (tester) async {
    await _pump(
        tester,
        _container(
            repo: FakeFeedRepository(
                items: const [],
                meta: const FeedMeta(hasProfile: false, sourcesCount: 1))));
    expect(find.text('Complete your profile'), findsOneWidget);
  });

  testWidgets('empty state nudges to add boards when there is room',
      (tester) async {
    await _pump(
        tester,
        _container(
            repo: FakeFeedRepository(
                items: const [],
                meta: const FeedMeta(sourcesCount: 1, poolSize: 0))));
    expect(find.text('Add job boards'), findsOneWidget);
  });

  testWidgets('a filtered-out feed offers to show all matches', (tester) async {
    final one = [
      FeedItem(
          postingId: 'j1',
          company: 'Linear',
          title: 'Senior Backend Engineer',
          url: 'https://example.com/j1',
          score: 60),
    ];
    final repo = FakeFeedRepository(
        items: one, meta: const FeedMeta(poolSize: 8, sourcesCount: 1));
    final container = _container(repo: repo);
    await _pump(tester, container);

    // Filter above the only posting's score -> empty, with a widening CTA.
    await tester.tap(find.text('85+'));
    await tester.pumpAndSettle();
    expect(find.byType(JobCard), findsNothing);
    expect(find.text('Show all matches'), findsOneWidget);

    // Tapping it drops the filter and the posting comes back.
    await tester.tap(find.text('Show all matches'));
    await tester.pumpAndSettle();
    expect(container.read(feedControllerProvider).minScore, 1);
    expect(find.byType(JobCard), findsOneWidget);
  });

  testWidgets('a short feed shows the add-boards footer', (tester) async {
    final one = [
      FeedItem(
          postingId: 'j1',
          company: 'Linear',
          title: 'Senior Backend Engineer',
          url: 'https://example.com/j1',
          score: 92),
    ];
    await _pump(
        tester,
        _container(
            repo: FakeFeedRepository(
                items: one, meta: const FeedMeta(sourcesCount: 1))));
    expect(find.text('Add boards'), findsOneWidget);
    expect(find.byType(JobCard), findsOneWidget);
  });

  testWidgets('error state renders and Retry re-requests', (tester) async {
    await _pump(tester, _container(repo: FakeFeedRepository(fails: true)));
    expect(find.text('Couldn’t load your feed'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.text('Couldn’t load your feed'), findsOneWidget); // still failing
  });

  testWidgets('cards scrolled into view are marked seen', (tester) async {
    final repo = FakeFeedRepository();
    await _pump(tester, _container(repo: repo));
    expect(repo.seen, contains('j1'));
  });

  testWidgets('sorting by newest reorders the feed by publish date',
      (tester) async {
    final now = DateTime.now();
    // A strong-but-old posting and a weak-but-recent one, so score order and
    // newest order disagree.
    final items = [
      FeedItem(
          postingId: 'strong-old',
          company: 'A',
          title: 'Strong Old',
          url: 'https://example.com/1',
          score: 92,
          publishedAt:
              now.subtract(const Duration(days: 10)).toIso8601String()),
      FeedItem(
          postingId: 'weak-new',
          company: 'B',
          title: 'Weak New',
          url: 'https://example.com/2',
          score: 55,
          publishedAt:
              now.subtract(const Duration(hours: 1)).toIso8601String()),
    ];
    final container = _container(repo: FakeFeedRepository(items: items));
    await _pump(tester, container);
    // Default (score) order: the higher-scoring posting leads.
    expect(container.read(feedControllerProvider).items.first.postingId,
        'strong-old');

    await tester.tap(find.byIcon(Icons.sort_rounded));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Newest').last);
    await tester.pumpAndSettle();

    final state = container.read(feedControllerProvider);
    expect(state.sort, FeedSort.newest);
    expect(state.items.first.postingId, 'weak-new'); // most recent leads now
  });

  testWidgets('add-from-URL imports the link and opens its detail',
      (tester) async {
    final repo = FakeFeedRepository();
    await _pumpRouter(tester, _container(repo: repo));

    await tester.tap(find.byIcon(Icons.add_link_rounded));
    await tester.pumpAndSettle();
    expect(find.text('Add a job'), findsOneWidget);

    await tester.enterText(
        find.byKey(const Key('import-url-field')), 'https://jobs.example.com/123');
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();

    // The URL was imported and we navigated to the new posting's detail.
    expect(repo.importedUrls, contains('https://jobs.example.com/123'));
    expect(find.text('job imported-1'), findsOneWidget);
  });

  testWidgets('add-from-text pastes a description and opens its detail',
      (tester) async {
    final repo = FakeFeedRepository();
    await _pumpRouter(tester, _container(repo: repo));

    await tester.tap(find.byIcon(Icons.add_link_rounded));
    await tester.pumpAndSettle();

    // Switch to the paste-text mode and paste a full description.
    await tester.tap(find.text('Paste text'));
    await tester.pumpAndSettle();
    const jd = 'Senior Backend Engineer building distributed payment systems '
        'in Python. Remote role, you will own services end to end.';
    await tester.enterText(find.byKey(const Key('import-text-field')), jd);
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();

    expect(repo.importedTexts, contains(jd));
    expect(find.text('job text-imported-1'), findsOneWidget);
  });

  testWidgets('add-from-text rejects a too-short paste without a network call',
      (tester) async {
    final repo = FakeFeedRepository();
    await _pumpRouter(tester, _container(repo: repo));

    await tester.tap(find.byIcon(Icons.add_link_rounded));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Paste text'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('import-text-field')), 'too short');
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();

    // Client-side guard: no import attempted, dialog stays open with a hint.
    expect(repo.importedTexts, isEmpty);
    expect(find.text('Paste the full job description.'), findsOneWidget);
  });

  testWidgets('add-from-URL surfaces a failure without leaving the dialog',
      (tester) async {
    // fails:true makes the feed error out, but the app-bar action still works;
    // the import itself throws, so the dialog stays open with the message.
    final repo = FakeFeedRepository(fails: true);
    await _pumpRouter(tester, _container(repo: repo));

    await tester.tap(find.byIcon(Icons.add_link_rounded));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const Key('import-url-field')), 'https://bad.example.com');
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();

    expect(find.text('Add a job'), findsOneWidget); // still open
    // The message shows inside the dialog (the feed behind it also errored).
    expect(
        find.descendant(
            of: find.byType(AlertDialog),
            matching: find.textContaining('Failed host lookup')),
        findsOneWidget);
  });

  testWidgets('an applied posting shows the APPLIED badge', (tester) async {
    final items = [
      FeedItem(
        postingId: 'j1',
        company: 'Linear',
        title: 'Senior Backend Engineer',
        url: 'https://example.com/j1',
        score: 92,
        drafted: true,
        applied: true,
      ),
    ];
    await _pump(tester, _container(repo: FakeFeedRepository(items: items)));

    // Applied wins over the drafted badge on the card header.
    expect(find.text('APPLIED'), findsOneWidget);
    expect(find.text('DRAFTED'), findsNothing);
  });
}

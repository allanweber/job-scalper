import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
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

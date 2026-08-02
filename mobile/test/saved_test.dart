import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/feed_repository.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/feed_harness.dart';
import 'package:job_scalper/src/features/feed/widgets/job_card.dart';
import 'package:job_scalper/src/features/saved/saved_controller.dart';
import 'package:job_scalper/src/features/saved/saved_screen.dart';

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
    child: const MaterialApp(home: SavedScreen()),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lists only saved postings', (tester) async {
    final container = _container();
    await _pump(tester, container);

    // Of the demo set only j2 (Stripe) is saved.
    expect(container.read(savedControllerProvider).items, hasLength(1));
    expect(find.text('Platform Engineer, Payments'), findsOneWidget);
    expect(find.text('Senior Backend Engineer'), findsNothing);
  });

  testWidgets('unsaving removes the card and calls the API', (tester) async {
    final repo = FakeFeedRepository();
    final container = _container(repo: repo);
    await _pump(tester, container);
    expect(find.byType(JobCard), findsOneWidget);

    await tester.tap(find.byIcon(Icons.favorite_rounded));
    await tester.pumpAndSettle();

    expect(repo.unsavedCalls, contains('j2'));
    expect(find.text('Nothing saved yet'), findsOneWidget);
  });

  testWidgets('empty state when nothing is saved', (tester) async {
    await _pump(tester, _container(repo: FakeFeedRepository(items: const [])));
    expect(find.text('Nothing saved yet'), findsOneWidget);
    expect(find.byType(JobCard), findsNothing);
  });

  testWidgets('a job saved elsewhere appears immediately via the override',
      (tester) async {
    final container = _container();
    await _pump(tester, container);
    // j1 (Senior Backend Engineer) starts unsaved, so it isn't listed.
    expect(find.text('Senior Backend Engineer'), findsNothing);

    // Simulate saving j1 from the feed/detail: the shared override flips before
    // any reload, and the Saved tab should surface it at once.
    container.read(savedOverridesProvider.notifier).set('j1', true);
    await tester.pumpAndSettle();
    expect(find.text('Senior Backend Engineer'), findsOneWidget);
  });

  testWidgets('unsaving elsewhere drops it from the saved list immediately',
      (tester) async {
    final container = _container();
    await _pump(tester, container);
    expect(find.text('Platform Engineer, Payments'), findsOneWidget);

    container.read(savedOverridesProvider.notifier).set('j2', false);
    await tester.pumpAndSettle();
    expect(find.text('Platform Engineer, Payments'), findsNothing);
    expect(find.text('Nothing saved yet'), findsOneWidget);
  });
}

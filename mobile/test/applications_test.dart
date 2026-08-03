import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/drafts_repository.dart';
import 'package:job_scalper/src/data/models/draft_models.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/drafts_harness.dart';
import 'package:job_scalper/src/features/applications/applications_controller.dart';
import 'package:job_scalper/src/features/applications/applications_screen.dart';

ProviderContainer _container({DraftsRepository? repo}) {
  final container = ProviderContainer(overrides: [
    draftsRepositoryProvider.overrideWithValue(repo ?? FakeDraftsRepository()),
  ]);
  addTearDown(container.dispose);
  return container;
}

Future<void> _pump(WidgetTester tester, ProviderContainer container) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: ApplicationsScreen()),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lists the user drafts with title + company', (tester) async {
    final container = _container();
    await _pump(tester, container);

    expect(container.read(applicationsControllerProvider).items, hasLength(3));
    expect(find.text('Senior Backend Engineer'), findsOneWidget);
    expect(find.text('Platform Engineer, Payments'), findsOneWidget);
    // Company appears in the card subtitle.
    expect(find.textContaining('Linear'), findsWidgets);
  });

  testWidgets('empty state when there are no drafts', (tester) async {
    await _pump(tester, _container(repo: FakeDraftsRepository(items: const [])));
    expect(find.text('No applications yet'), findsOneWidget);
  });

  testWidgets('error state renders with retry', (tester) async {
    await _pump(tester, _container(repo: FakeDraftsRepository(fails: true)));
    expect(find.text('Couldn’t load your applications'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Retry'), findsOneWidget);
  });

  testWidgets('a pending draft shows the Drafting… pill', (tester) async {
    final items = [
      DraftSummary(
        id: 'p1',
        postingId: 'j9',
        jobSource: 'pool',
        keySource: 'platform',
        createdAt: DateTime.now().toIso8601String(),
        title: 'New Role',
        company: 'Zed',
        status: 'pending',
      ),
    ];
    // Inline container (not the shared helper) so we can dispose it inside the
    // test body — a pending row schedules a background poll timer, and the
    // framework's end-of-test timer check runs before addTearDown fires.
    final container = ProviderContainer(overrides: [
      draftsRepositoryProvider
          .overrideWithValue(FakeDraftsRepository(items: items)),
    ]);
    // A pending row shows an indeterminate spinner, so pump manually rather
    // than settling.
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ApplicationsScreen()),
    ));
    await tester.pump();
    await tester.pump();
    expect(find.text('New Role'), findsOneWidget);
    expect(find.text('Drafting…'), findsOneWidget);
    container.dispose(); // cancels the poll timer before the teardown check
  });

  testWidgets('a failed draft shows the Failed pill', (tester) async {
    final items = [
      DraftSummary(
        id: 'f1',
        postingId: 'j9',
        jobSource: 'pool',
        keySource: 'platform',
        createdAt: DateTime.now().toIso8601String(),
        title: 'Broken Role',
        company: 'Zed',
        status: 'failed',
        error: 'no resume on file',
      ),
    ];
    await _pump(tester, _container(repo: FakeDraftsRepository(items: items)));
    expect(find.text('Broken Role'), findsOneWidget);
    expect(find.text('Failed'), findsOneWidget);
  });
}

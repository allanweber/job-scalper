import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:job_scalper/src/data/feed_repository.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/feed_harness.dart';
import 'package:job_scalper/src/features/detail/job_detail_screen.dart';

ProviderContainer _container({FeedRepository? repo}) {
  final container = ProviderContainer(overrides: [
    feedRepositoryProvider.overrideWithValue(repo ?? FakeFeedRepository()),
  ]);
  addTearDown(container.dispose);
  return container;
}

Future<void> _pump(WidgetTester tester, ProviderContainer container,
    {String postingId = 'j1'}) async {
  // A minimal router so "Draft application" can navigate to the draft detail;
  // the target is a stub so this test stays focused on the job-detail screen.
  final router = GoRouter(
    initialLocation: '/feed/job/$postingId',
    routes: [
      GoRoute(
        path: '/feed/job/:id',
        builder: (_, s) => JobDetailScreen(postingId: s.pathParameters['id']!),
      ),
      GoRoute(
        path: '/applications/draft/:id',
        builder: (_, _) => const Scaffold(body: Text('draft detail stub')),
      ),
    ],
  );
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(routerConfig: router),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders the full posting with breakdown and actions',
      (tester) async {
    // Tall surface so the full description (bottom of the scroll) is laid out.
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pump(tester, _container());

    expect(find.text('Senior Backend Engineer'), findsOneWidget);
    expect(find.text('Why this ranks'), findsOneWidget);
    expect(find.textContaining('scale our core platform'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Apply'), findsOneWidget);
    expect(find.text('Draft application'), findsOneWidget);
  });

  testWidgets('shows skills missing from the résumé', (tester) async {
    tester.view.physicalSize = const Size(1170, 7000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pump(tester, _container());

    // The section label is upper-cased by _Label; the description is verbatim.
    expect(find.textContaining('not in your résumé'), findsOneWidget);
    // The gap terms from the harness detail render as chips.
    expect(find.text('Terraform'), findsOneWidget);
    expect(find.text('GraphQL'), findsOneWidget);
  });

  testWidgets('save toggle from the app bar persists', (tester) async {
    final repo = FakeFeedRepository();
    await _pump(tester, _container(repo: repo)); // j1 is unsaved

    await tester.tap(find.byIcon(Icons.favorite_outline));
    await tester.pump();
    expect(repo.savedCalls, contains('j1'));
  });

  testWidgets('draft application creates a draft and navigates to it',
      (tester) async {
    final repo = FakeFeedRepository();
    await _pump(tester, _container(repo: repo));

    await tester.tap(find.text('Draft application'));
    await tester.pumpAndSettle();

    // The draft is requested and we navigate straight to the (pending) detail.
    expect(repo.draftCalls, contains('j1'));
    expect(find.text('draft detail stub'), findsOneWidget);
  });

  testWidgets('error state renders with retry', (tester) async {
    await _pump(tester, _container(repo: FakeFeedRepository(fails: true)));
    expect(find.text("Couldn't load this job"), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Retry'), findsOneWidget);
  });
}

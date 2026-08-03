import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:job_scalper/src/data/drafts_repository.dart';
import 'package:job_scalper/src/data/models/draft_models.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/drafts_harness.dart';
import 'package:job_scalper/src/features/applications/application_flow_chart.dart';
import 'package:job_scalper/src/features/applications/application_insights_screen.dart';
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
    child: const MaterialApp(home: ApplicationInsightsScreen()),
  ));
  await tester.pumpAndSettle();
}

// A representative funnel modelled on the reference Sankey.
final _funnel = FakeDraftsRepository(
  insights: const ApplicationInsights(total: 124, counts: {
    'applied': 0,
    'pre_screen': 3,
    'interviewing': 4,
    'offer': 1,
    'ghosted': 93,
    'rejected': 29,
  }),
);

void main() {
  testWidgets('renders the funnel total, chart and headline rates',
      (tester) async {
    await _pump(tester, _container(repo: _funnel));

    expect(find.text('124 applications'), findsOneWidget);
    expect(find.byType(ApplicationFlowChart), findsOneWidget);

    // Headline tiles: interviews (interviewing + offer = 5), offers (1),
    // ghost rate (93/124 = 75%).
    expect(find.text('Interviews'), findsOneWidget);
    expect(find.text('5'), findsOneWidget);
    expect(find.text('Offers'), findsOneWidget);
    expect(find.text('75%'), findsOneWidget);
  });

  testWidgets('empty state when there are no applications', (tester) async {
    await _pump(
        tester,
        _container(
            repo: FakeDraftsRepository(
                items: const [],
                insights: const ApplicationInsights(total: 0, counts: {}))));
    expect(find.text('No applications yet'), findsOneWidget);
    expect(find.byType(ApplicationFlowChart), findsNothing);
  });

  testWidgets('error state renders with retry', (tester) async {
    await _pump(tester, _container(repo: FakeDraftsRepository(fails: true)));
    expect(find.text("Couldn't load your insights"), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Retry'), findsOneWidget);
  });

  testWidgets('the Insights icon on Applications opens the flow chart',
      (tester) async {
    final router = GoRouter(
      initialLocation: '/applications',
      routes: [
        GoRoute(
          path: '/applications',
          builder: (_, _) => const ApplicationsScreen(),
          routes: [
            GoRoute(
              path: 'insights',
              builder: (_, _) => const ApplicationInsightsScreen(),
            ),
          ],
        ),
      ],
    );
    // Default demo drafts: 3 applications, all in 'applied'.
    final container = _container();
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(routerConfig: router),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Insights'));
    await tester.pumpAndSettle();

    expect(find.text('3 applications'), findsOneWidget);
    expect(find.byType(ApplicationFlowChart), findsOneWidget);
  });
}

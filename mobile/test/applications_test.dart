import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/drafts_repository.dart';
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
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/drafts_repository.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/drafts_harness.dart';
import 'package:job_scalper/src/features/applications/draft_detail_screen.dart';

ProviderContainer _container({DraftsRepository? repo}) {
  final container = ProviderContainer(overrides: [
    draftsRepositoryProvider.overrideWithValue(repo ?? FakeDraftsRepository()),
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
}

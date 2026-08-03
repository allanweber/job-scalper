import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/onboarding_harness.dart';
import 'package:job_scalper/src/features/profile/notifications_controller.dart';
import 'package:job_scalper/src/features/profile/notifications_screen.dart';

ProviderContainer _container(FakeAccountRepository repo) {
  final container = ProviderContainer(overrides: [
    accountRepositoryProvider.overrideWithValue(repo),
  ]);
  addTearDown(container.dispose);
  return container;
}

Future<void> _pump(WidgetTester tester, ProviderContainer container) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: NotificationsScreen()),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders prefs and toggling alerts persists', (tester) async {
    final repo = FakeAccountRepository();
    final container = _container(repo);
    await _pump(tester, container);

    expect(find.text('New match alerts'), findsOneWidget);
    expect(find.textContaining('Notify me at 90+'), findsOneWidget);

    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();

    expect((await repo.getNotificationPrefs()).matchAlerts, false);
  });

  testWidgets('changing the threshold persists and updates the label',
      (tester) async {
    final repo = FakeAccountRepository();
    final container = _container(repo);
    await _pump(tester, container);

    container.read(notificationsControllerProvider.notifier).setMinScore(80);
    await tester.pumpAndSettle();

    expect(find.textContaining('Notify me at 80+'), findsOneWidget);
    expect((await repo.getNotificationPrefs()).minScore, 80);
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/dev/onboarding_harness.dart';
import 'package:job_scalper/src/features/profile/boards_screen.dart';
import 'package:job_scalper/src/features/profile/delete_account_screen.dart';
import 'package:job_scalper/src/features/profile/llm_key_screen.dart';
import 'package:job_scalper/src/features/profile/profile_edit_screen.dart';
import 'package:job_scalper/src/features/profile/profile_screen.dart';
import 'package:job_scalper/src/features/profile/usage_screen.dart';
import 'package:job_scalper/src/state/session.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A signed-in in-memory session + the fake account repo, so profile screens
/// render against seedable state without a server.
Future<(ProviderContainer, FakeAccountRepository)> _container(
    {FakeAccountRepository? repo, bool signedIn = true}) async {
  SharedPreferences.setMockInitialValues({
    // Signed-in fixtures carry a token pair; the delete test omits it so
    // `signOut()` skips its (networked) logout call and stays hermetic.
    if (signedIn)
      'session.tokens':
          '{"access_token":"a","refresh_token":"r","expires_in":900}',
  });
  final prefs = await SharedPreferences.getInstance();
  final fake = repo ?? FakeAccountRepository();
  final container = ProviderContainer(overrides: [
    sharedPrefsProvider.overrideWithValue(prefs),
    accountRepositoryProvider.overrideWithValue(fake),
  ]);
  addTearDown(container.dispose);
  return (container, fake);
}

Future<void> _pump(
    WidgetTester tester, ProviderContainer container, Widget screen) async {
  tester.view.physicalSize = const Size(1170, 6000);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('profile hub lists the account sections', (tester) async {
    final (container, _) = await _container();
    await _pump(tester, container, const ProfileScreen());

    expect(find.text('Search profile'), findsOneWidget);
    expect(find.text('Resume'), findsOneWidget);
    expect(find.text('Job boards'), findsOneWidget);
    expect(find.text('Your API key'), findsOneWidget);
    expect(find.text('Usage'), findsOneWidget);
    expect(find.text('Appearance'), findsOneWidget);
    expect(find.text('Sign out'), findsOneWidget);
    expect(find.text('Delete account'), findsOneWidget);
  });

  testWidgets('sign out asks for confirmation before signing out',
      (tester) async {
    final (container, _) = await _container();
    await _pump(tester, container, const ProfileScreen());

    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    // The confirmation dialog appears; the session is untouched until confirmed.
    expect(find.text('Sign out?'), findsOneWidget);
    expect(container.read(sessionProvider).isSignedIn, isTrue);
  });

  testWidgets('search-profile Save is gated on a change and persists',
      (tester) async {
    final (container, fake) = await _container();
    await _pump(tester, container, const ProfileEditScreen());

    // Nothing edited yet → Save disabled.
    final saveButton =
        tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save changes'));
    expect(saveButton.onPressed, isNull);

    // Toggle "Remote only" to make the form dirty.
    await tester.tap(find.text('Remote only'));
    await tester.pumpAndSettle();
    final saveAfter =
        tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save changes'));
    expect(saveAfter.onPressed, isNotNull);

    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();
    expect(fake.savedProfile, isNotNull);
    expect(fake.savedProfile!.remoteOnly, isFalse);
  });

  testWidgets('adding an LLM key persists it and flips the provider to set',
      (tester) async {
    final (container, fake) = await _container();
    await _pump(tester, container, const LlmKeyScreen());

    expect(find.text('Anthropic'), findsOneWidget);
    expect(find.text('OpenAI'), findsOneWidget);
    expect(find.text('Not set'), findsNWidgets(2));

    // Open the entry dialog on the Anthropic card and save a key.
    await tester.tap(find.widgetWithText(OutlinedButton, 'Add key').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'sk-ant-123');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(fake.savedKeys, contains(('anthropic', 'sk-ant-123')));
    expect(find.text('Set · validated'), findsOneWidget);
  });

  testWidgets('delete account is gated until DELETE is typed', (tester) async {
    final (container, fake) = await _container(signedIn: false);
    await _pump(tester, container, const DeleteAccountScreen());

    final before = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Delete my account'));
    expect(before.onPressed, isNull);

    await tester.enterText(find.byType(TextField), 'DELETE');
    await tester.pumpAndSettle();
    final after = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Delete my account'));
    expect(after.onPressed, isNotNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Delete my account'));
    // The button shows an (indefinite) spinner while deleting, so pump a couple
    // of frames rather than settling.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(fake.accountDeletions, 1);
    expect(container.read(sessionProvider).isSignedIn, isFalse);
  });

  testWidgets('job boards disables further picks once the cap is reached',
      (tester) async {
    final (container, _) = await _container();
    await _pump(tester, container, const BoardsScreen());

    // The fake starts with none selected and a cap of 3. Select three boards.
    for (final name in ['Remotive', 'RemoteOK', 'We Work Remotely']) {
      await tester.tap(find.widgetWithText(CheckboxListTile, name));
      await tester.pumpAndSettle();
    }

    // A fourth, unselected board is now disabled…
    final fourth = tester.widget<CheckboxListTile>(
        find.widgetWithText(CheckboxListTile, 'Arbeitnow'));
    expect(fourth.onChanged, isNull);
    // …while an already-selected board can still be toggled off.
    final selected = tester.widget<CheckboxListTile>(
        find.widgetWithText(CheckboxListTile, 'Remotive'));
    expect(selected.onChanged, isNotNull);
  });

  testWidgets('usage screen renders the plan metrics', (tester) async {
    final (container, _) = await _container();
    await _pump(tester, container, const UsageScreen());

    expect(find.text('Application drafts'), findsOneWidget);
    expect(find.text('Profile rebuilds'), findsOneWidget);
    expect(find.textContaining('7 / 20'), findsOneWidget);
  });
}

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/env.dart';
import '../state/session.dart';
import 'account_repository.dart';
import 'api_client.dart';
import 'drafts_repository.dart';
import 'feed_repository.dart';
import 'google_authenticator.dart';
import 'pdf_cache_repository.dart';

/// The shared, token-aware HTTP client (owned by the session controller).
final apiClientProvider =
    Provider<ApiClient>((ref) => ref.watch(sessionProvider.notifier).api);

/// The account/profile/sources repository. Overridden with an in-memory fake in
/// widget tests and the screenshot harness.
final accountRepositoryProvider = Provider<AccountRepository>(
    (ref) => HttpAccountRepository(ref.watch(apiClientProvider)));

/// The ranked-feed repository. Overridden with an in-memory fake in widget
/// tests and the screenshot harness.
final feedRepositoryProvider = Provider<FeedRepository>(
    (ref) => HttpFeedRepository(ref.watch(apiClientProvider)));

/// The drafts/applications repository. Overridden with an in-memory fake in
/// widget tests and the screenshot harness.
final draftsRepositoryProvider = Provider<DraftsRepository>(
    (ref) => HttpDraftsRepository(ref.watch(apiClientProvider)));

/// Source of Google ID tokens: native Google Sign-In in normal builds, or the
/// dev stand-in when `DEV_LOGIN=true` (web verification / screenshots).
/// Overridden with a fake in tests.
final googleAuthenticatorProvider = Provider<GoogleAuthenticator>((ref) =>
    Env.devLogin ? DevGoogleAuthenticator() : GoogleSignInAuthenticator());

/// On-device PDF cache. Singleton — one DB file for the app lifetime.
final pdfCacheRepositoryProvider =
    Provider<PdfCacheRepository>((_) => PdfCacheRepository());

/// Posting IDs that the user drafted in this session, before the feed
/// refreshes. Used to show the "Drafted" badge on feed cards immediately
/// after drafting from the job detail screen.
final draftedPostingIdsProvider =
    NotifierProvider<DraftedPostingIds, Set<String>>(DraftedPostingIds.new);

class DraftedPostingIds extends Notifier<Set<String>> {
  @override
  Set<String> build() => const {};

  void add(String postingId) => state = {...state, postingId};
}

/// Session-local "applied" overrides keyed by posting id. Set when the user
/// marks/unmarks a posting applied from the draft detail screen, so the feed,
/// saved list, and job detail reflect it immediately — before the next refresh
/// re-reads the server-side flag. A value wins over the model's `applied`.
final appliedOverridesProvider =
    NotifierProvider<AppliedOverrides, Map<String, bool>>(AppliedOverrides.new);

class AppliedOverrides extends Notifier<Map<String, bool>> {
  @override
  Map<String, bool> build() => const {};

  void set(String postingId, bool applied) =>
      state = {...state, postingId: applied};
}

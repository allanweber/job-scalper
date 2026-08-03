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

/// Session-local application-stage overrides keyed by posting id. Written
/// optimistically when the user changes a stage (applied → interviewing →
/// offer → rejected, or clears it) from the draft detail, so the Applications
/// list reflects the new stage immediately, before the next reload. The value
/// is the stage string, or null when cleared; a posting present in the map wins
/// over the model's own `applicationStatus`.
final applicationStatusOverridesProvider =
    NotifierProvider<ApplicationStatusOverrides, Map<String, String?>>(
        ApplicationStatusOverrides.new);

class ApplicationStatusOverrides extends Notifier<Map<String, String?>> {
  @override
  Map<String, String?> build() => const {};

  void set(String postingId, String? status) =>
      state = {...state, postingId: status};
}

/// Session-local "saved" overrides keyed by posting id. Written optimistically
/// the instant the user taps the heart anywhere — feed, saved list, or job
/// detail — and read by both the feed and saved lists, so a save/unsave shows
/// on every surface immediately, before the network round-trip. Reverted if the
/// request fails. A value here wins over the model's own `saved` flag.
final savedOverridesProvider =
    NotifierProvider<SavedOverrides, Map<String, bool>>(SavedOverrides.new);

class SavedOverrides extends Notifier<Map<String, bool>> {
  @override
  Map<String, bool> build() => const {};

  void set(String postingId, bool saved) =>
      state = {...state, postingId: saved};
}

/// Bumped whenever a posting's saved state is toggled from the feed or job
/// detail screens. The Saved tab watches this and reloads itself in the
/// background, so its server-side list reconciles after the optimistic override
/// has already updated the UI.
final savedRevisionProvider =
    NotifierProvider<SavedRevision, int>(SavedRevision.new);

class SavedRevision extends Notifier<int> {
  @override
  int build() => 0;

  void bump() => state = state + 1;
}

/// Bumped when a draft is created or transitions (pending → ready/failed). The
/// Applications tab watches this and reloads, so a newly requested draft shows
/// up as 'pending' at once and updates when the worker finishes.
final draftsRevisionProvider =
    NotifierProvider<DraftsRevision, int>(DraftsRevision.new);

class DraftsRevision extends Notifier<int> {
  @override
  int build() => 0;

  void bump() => state = state + 1;
}

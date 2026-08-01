import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/env.dart';
import '../state/session.dart';
import 'account_repository.dart';
import 'api_client.dart';
import 'drafts_repository.dart';
import 'feed_repository.dart';
import 'google_authenticator.dart';

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

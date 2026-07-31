import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/session.dart';
import 'account_repository.dart';
import 'api_client.dart';

/// The shared, token-aware HTTP client (owned by the session controller).
final apiClientProvider =
    Provider<ApiClient>((ref) => ref.watch(sessionProvider.notifier).api);

/// The account/profile/sources repository. Overridden with an in-memory fake in
/// widget tests and the screenshot harness.
final accountRepositoryProvider = Provider<AccountRepository>(
    (ref) => HttpAccountRepository(ref.watch(apiClientProvider)));

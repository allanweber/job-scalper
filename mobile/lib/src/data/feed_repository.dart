import 'api_client.dart';
import 'models/feed_models.dart';

/// The ranked-feed surface used by the Feed and Saved tabs.
///
/// An interface so widget tests and the screenshot harness can inject an
/// in-memory fake; the app runs [HttpFeedRepository] against the FastAPI backend.
abstract class FeedRepository {
  /// The ranked feed (`GET /feed`), optionally filtered by a minimum score.
  Future<Feed> getFeed({int limit = 100, int minScore = 1});

  /// Save / unsave a posting (`POST` / `DELETE /feed/{id}/save`).
  Future<void> save(String postingId);
  Future<void> unsave(String postingId);

  /// Record that a posting scrolled into view (`POST /feed/{id}/seen`).
  Future<void> markSeen(String postingId);
}

class HttpFeedRepository implements FeedRepository {
  HttpFeedRepository(this._api);

  final ApiClient _api;

  @override
  Future<Feed> getFeed({int limit = 100, int minScore = 1}) async {
    final r = await _api.get<Map<String, dynamic>>('/feed',
        query: {'limit': limit, 'min_score': minScore});
    return Feed.fromJson(r.data!);
  }

  @override
  Future<void> save(String postingId) =>
      _api.post<Map<String, dynamic>>('/feed/$postingId/save');

  @override
  Future<void> unsave(String postingId) =>
      _api.delete<Map<String, dynamic>>('/feed/$postingId/save');

  @override
  Future<void> markSeen(String postingId) =>
      _api.post<Map<String, dynamic>>('/feed/$postingId/seen');
}

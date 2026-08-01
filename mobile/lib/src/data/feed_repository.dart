import 'api_client.dart';
import 'models/feed_models.dart';

/// The ranked-feed surface used by the Feed and Saved tabs.
///
/// An interface so widget tests and the screenshot harness can inject an
/// in-memory fake; the app runs [HttpFeedRepository] against the FastAPI backend.
abstract class FeedRepository {
  /// The ranked feed (`GET /feed`), optionally filtered by a minimum score.
  Future<Feed> getFeed({int limit = 100, int minScore = 1});

  /// A single posting's full detail (`GET /postings/{id}`).
  Future<PostingDetail> getPosting(String postingId);

  /// Save / unsave a posting (`POST` / `DELETE /feed/{id}/save`).
  Future<void> save(String postingId);
  Future<void> unsave(String postingId);

  /// Record that a posting scrolled into view (`POST /feed/{id}/seen`).
  Future<void> markSeen(String postingId);

  /// Kick off an async application draft (`POST /drafts`); returns the job id.
  Future<String> createDraft(String postingId);
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
  Future<PostingDetail> getPosting(String postingId) async {
    final r = await _api.get<Map<String, dynamic>>('/postings/$postingId');
    return PostingDetail.fromJson(r.data!);
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

  @override
  Future<String> createDraft(String postingId) async {
    final r = await _api.post<Map<String, dynamic>>('/drafts',
        data: {'posting_id': postingId});
    return r.data!['job_id'] as String;
  }
}

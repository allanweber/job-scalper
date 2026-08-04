import 'dart:typed_data';

import 'package:dio/dio.dart';

import 'api_client.dart';
import 'models/draft_models.dart';

/// The drafts/applications surface used by the Applications tab.
///
/// An interface so widget tests and the screenshot harness can inject an
/// in-memory fake; the app runs [HttpDraftsRepository] against the FastAPI
/// backend.
abstract class DraftsRepository {
  /// All of the user's drafts, newest first (`GET /drafts`).
  Future<List<DraftSummary>> listDrafts();

  /// One draft's full content (`GET /drafts/{id}`).
  Future<Draft> getDraft(String id);

  /// Re-run drafting for an existing draft, optionally in a new [tone]
  /// (`POST /drafts/{id}/regenerate`). Returns the draft (back in 'pending');
  /// poll [getDraft] until it's ready.
  Future<Draft> regenerateDraft(String id, {String? tone});

  /// Persist edited resume and/or cover-letter markdown (`PUT /drafts/{id}`).
  Future<Draft> updateDraft(String id, {String? resumeMd, String? coverLetterMd});

  /// Mark (or unmark) this draft's posting as applied
  /// (`PUT /drafts/{id}/applied`). Returns the updated draft.
  Future<Draft> setApplied(String id, bool applied);

  /// Set (or clear) this draft's application pipeline stage
  /// (`PUT /drafts/{id}/status`). [status] is 'applied' | 'interviewing' |
  /// 'offer' | 'rejected', or null to clear back to not-applied.
  Future<Draft> setApplicationStatus(String id, String? status);

  /// Fetch a rendered PDF from the server (`GET /drafts/{id}/{which}.pdf`).
  /// [which] is `"resume"` or `"cover_letter"`.
  Future<Uint8List> getDraftPdf(String id, String which);

  /// The application funnel aggregate for the Insights flow chart
  /// (`GET /drafts/insights`).
  Future<ApplicationInsights> getInsights();
}

class HttpDraftsRepository implements DraftsRepository {
  HttpDraftsRepository(this._api);

  final ApiClient _api;

  @override
  Future<List<DraftSummary>> listDrafts() async {
    final r = await _api.get<List<dynamic>>('/drafts');
    return (r.data ?? const [])
        .map((e) => DraftSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<Draft> getDraft(String id) async {
    final r = await _api.get<Map<String, dynamic>>('/drafts/$id');
    return Draft.fromJson(r.data!);
  }

  @override
  Future<Draft> regenerateDraft(String id, {String? tone}) async {
    final r = await _api.post<Map<String, dynamic>>('/drafts/$id/regenerate',
        data: {'tone': tone});
    return Draft.fromJson(r.data!);
  }

  @override
  Future<Draft> updateDraft(String id,
      {String? resumeMd, String? coverLetterMd}) async {
    final body = <String, dynamic>{};
    if (resumeMd != null) body['resume_md'] = resumeMd;
    if (coverLetterMd != null) body['cover_letter_md'] = coverLetterMd;
    final r = await _api.put<Map<String, dynamic>>('/drafts/$id', data: body);
    return Draft.fromJson(r.data!);
  }

  @override
  Future<Draft> setApplied(String id, bool applied) async {
    final r = await _api.put<Map<String, dynamic>>('/drafts/$id/applied',
        data: {'applied': applied});
    return Draft.fromJson(r.data!);
  }

  @override
  Future<Draft> setApplicationStatus(String id, String? status) async {
    final r = await _api.put<Map<String, dynamic>>('/drafts/$id/status',
        data: {'status': status});
    return Draft.fromJson(r.data!);
  }

  @override
  Future<Uint8List> getDraftPdf(String id, String which) async {
    final r = await _api.raw.get<List<int>>(
      '/drafts/$id/$which.pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    return Uint8List.fromList(r.data!);
  }

  @override
  Future<ApplicationInsights> getInsights() async {
    final r = await _api.get<Map<String, dynamic>>('/drafts/insights');
    return ApplicationInsights.fromJson(r.data!);
  }
}

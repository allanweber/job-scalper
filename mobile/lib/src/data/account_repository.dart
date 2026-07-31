import 'package:dio/dio.dart';

import 'api_client.dart';
import 'models/account_models.dart';
import 'models/api_models.dart';

/// The account/profile/sources surface used by onboarding and the Account tab.
///
/// Declared as an interface so the QA/screenshot harness and widget tests can
/// inject an in-memory fake; the app always runs [HttpAccountRepository] against
/// the real FastAPI backend.
abstract class AccountRepository {
  /// Accept ToS + Privacy (`POST /account/legal/accept`); returns the updated user.
  Future<ApiUser> acceptLegal();

  Future<Profile> getProfile();
  Future<Profile> saveProfile(Profile profile);

  /// Kick off an async resume-driven profile build; returns the job id to poll.
  Future<String> buildProfileFromResume();

  /// Upload the resume bytes (`PUT /account/resume`, multipart).
  Future<ResumeInfo> uploadResume({
    required List<int> bytes,
    required String filename,
    String? contentType,
  });

  /// The stored resume metadata, or null if none uploaded yet.
  Future<ResumeInfo?> getResume();

  Future<SourcesInfo> getSources();
  Future<SourcesInfo> saveSources(List<String> sources);

  /// Poll an async job (`GET /jobs/{id}`).
  Future<JobRecord> getJob(String jobId);
}

class HttpAccountRepository implements AccountRepository {
  HttpAccountRepository(this._api);

  final ApiClient _api;

  @override
  Future<ApiUser> acceptLegal() async {
    final r = await _api.post<Map<String, dynamic>>('/account/legal/accept');
    return ApiUser.fromJson(r.data!);
  }

  @override
  Future<Profile> getProfile() async {
    final r = await _api.get<Map<String, dynamic>>('/account/profile');
    return Profile.fromJson(r.data!);
  }

  @override
  Future<Profile> saveProfile(Profile profile) async {
    final r = await _api.put<Map<String, dynamic>>('/account/profile',
        data: profile.toFields());
    return Profile.fromJson(r.data!);
  }

  @override
  Future<String> buildProfileFromResume() async {
    final r =
        await _api.post<Map<String, dynamic>>('/account/profile/from-resume');
    return r.data!['job_id'] as String;
  }

  @override
  Future<ResumeInfo> uploadResume({
    required List<int> bytes,
    required String filename,
    String? contentType,
  }) async {
    final form = FormData.fromMap({
      'file': MultipartFile.fromBytes(
        bytes,
        filename: filename,
        contentType: contentType == null ? null : DioMediaType.parse(contentType),
      ),
    });
    // Content-Type must be multipart here, not the client-default JSON.
    final r = await _api.raw.put<Map<String, dynamic>>(
      '/account/resume',
      data: form,
      options: Options(contentType: 'multipart/form-data'),
    );
    return ResumeInfo.fromJson(r.data!);
  }

  @override
  Future<ResumeInfo?> getResume() async {
    try {
      final r = await _api.get<Map<String, dynamic>>('/account/resume');
      return ResumeInfo.fromJson(r.data!);
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) return null;
      rethrow;
    }
  }

  @override
  Future<SourcesInfo> getSources() async {
    final r = await _api.get<Map<String, dynamic>>('/account/sources');
    return SourcesInfo.fromJson(r.data!);
  }

  @override
  Future<SourcesInfo> saveSources(List<String> sources) async {
    final r = await _api.put<Map<String, dynamic>>('/account/sources',
        data: {'sources': sources});
    return SourcesInfo.fromJson(r.data!);
  }

  @override
  Future<JobRecord> getJob(String jobId) async {
    final r = await _api.get<Map<String, dynamic>>('/jobs/$jobId');
    return JobRecord.fromJson(r.data!);
  }
}

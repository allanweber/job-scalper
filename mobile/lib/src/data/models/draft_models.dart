// Wire models for the drafts/applications surface
// (`scalper/service/schemas.py`: DraftSummary, DraftResponse).

/// A row in the Applications list (`GET /drafts`). Joined to its pool posting
/// server-side, so [title]/[company] are present unless the posting was purged.
class DraftSummary {
  const DraftSummary({
    required this.id,
    required this.postingId,
    required this.jobSource,
    required this.keySource,
    required this.createdAt,
    this.title,
    this.company,
  });

  final String id;
  final String? postingId;
  final String jobSource;
  final String? keySource;
  final String createdAt;
  final String? title;
  final String? company;

  /// A human label for the application even when the posting metadata is gone.
  String get displayTitle => title ?? 'Application';

  factory DraftSummary.fromJson(Map<String, dynamic> j) => DraftSummary(
        id: j['id'] as String,
        postingId: j['posting_id'] as String?,
        jobSource: (j['job_source'] as String?) ?? 'pool',
        keySource: j['key_source'] as String?,
        createdAt: (j['created_at'] as String?) ?? '',
        title: j['title'] as String?,
        company: j['company'] as String?,
      );
}

/// A full draft (`GET /drafts/{id}`): the tailored resume + cover letter markdown
/// plus the optional "stretch claims" note the model surfaces for review.
class Draft {
  const Draft({
    required this.id,
    required this.postingId,
    required this.jobSource,
    this.resumeMd,
    this.coverLetterMd,
    this.stretchClaimsMd,
    this.provider,
    this.model,
    this.keySource,
    required this.createdAt,
  });

  final String id;
  final String? postingId;
  final String jobSource;
  final String? resumeMd;
  final String? coverLetterMd;
  final String? stretchClaimsMd;
  final String? provider;
  final String? model;
  final String? keySource;
  final String createdAt;

  Draft copyWith({String? resumeMd, String? coverLetterMd}) => Draft(
        id: id,
        postingId: postingId,
        jobSource: jobSource,
        resumeMd: resumeMd ?? this.resumeMd,
        coverLetterMd: coverLetterMd ?? this.coverLetterMd,
        stretchClaimsMd: stretchClaimsMd,
        provider: provider,
        model: model,
        keySource: keySource,
        createdAt: createdAt,
      );

  factory Draft.fromJson(Map<String, dynamic> j) => Draft(
        id: j['id'] as String,
        postingId: j['posting_id'] as String?,
        jobSource: (j['job_source'] as String?) ?? 'pool',
        resumeMd: j['resume_md'] as String?,
        coverLetterMd: j['cover_letter_md'] as String?,
        stretchClaimsMd: j['stretch_claims_md'] as String?,
        provider: j['provider'] as String?,
        model: j['model'] as String?,
        keySource: j['key_source'] as String?,
        createdAt: (j['created_at'] as String?) ?? '',
      );
}

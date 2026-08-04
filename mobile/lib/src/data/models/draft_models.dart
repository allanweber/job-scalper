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
    this.url,
    this.applied = false,
    this.applicationStatus,
    this.status = 'ready',
    this.error,
  });

  final String id;
  final String? postingId;
  final String jobSource;
  final String? keySource;
  final String createdAt;
  final String? title;
  final String? company;
  final String? url;
  final bool applied;

  /// The application pipeline stage: 'applied' | 'interviewing' | 'offer' |
  /// 'rejected', or null when not applied. `applied` is derived from this.
  final String? applicationStatus;

  /// Lifecycle: 'pending' while drafting, 'ready' when done, 'failed' on error.
  final String status;
  final String? error;

  bool get isPending => status == 'pending';
  bool get isReady => status == 'ready';
  bool get isFailed => status == 'failed';

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
        url: j['url'] as String?,
        applied: (j['applied'] as bool?) ?? false,
        applicationStatus: j['application_status'] as String?,
        status: (j['status'] as String?) ?? 'ready',
        error: j['error'] as String?,
      );
}

/// Aggregate application funnel (`GET /drafts/insights`) for the Insights flow
/// chart. [total] is the number of applications; [counts] maps each pipeline
/// stage to how many sit there now (the counts sum to [total]).
class ApplicationInsights {
  const ApplicationInsights({required this.total, required this.counts});

  final int total;
  final Map<String, int> counts;

  int stage(String s) => counts[s] ?? 0;

  factory ApplicationInsights.fromJson(Map<String, dynamic> j) =>
      ApplicationInsights(
        total: (j['total'] as num?)?.toInt() ?? 0,
        counts: {
          for (final e
              in ((j['counts'] as Map?) ?? const {}).entries)
            e.key as String: (e.value as num).toInt(),
        },
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
    this.applied = false,
    this.applicationStatus,
    this.status = 'ready',
    this.error,
    this.tone,
    this.matchedSkills = const [],
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
  final bool applied;

  /// The application pipeline stage: 'applied' | 'interviewing' | 'offer' |
  /// 'rejected', or null when not applied. `applied` is derived from this.
  final String? applicationStatus;

  /// Lifecycle: 'pending' while drafting, 'ready' when done, 'failed' on error.
  final String status;
  final String? error;

  /// The voice this draft was generated in (null = professional).
  final String? tone;

  /// Profile skills the posting matched — shown as "why this draft".
  final List<String> matchedSkills;

  bool get isPending => status == 'pending';
  bool get isReady => status == 'ready';
  bool get isFailed => status == 'failed';

  /// Sentinel so [copyWith] can tell "leave applicationStatus unchanged" apart
  /// from "clear it to null" (removing the applied stage).
  static const _unset = Object();

  Draft copyWith({
    String? resumeMd,
    String? coverLetterMd,
    bool? applied,
    Object? applicationStatus = _unset,
    String? status,
    String? error,
  }) =>
      Draft(
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
        applied: applied ?? this.applied,
        applicationStatus: applicationStatus == _unset
            ? this.applicationStatus
            : applicationStatus as String?,
        status: status ?? this.status,
        error: error ?? this.error,
        tone: tone,
        matchedSkills: matchedSkills,
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
        applied: (j['applied'] as bool?) ?? false,
        applicationStatus: j['application_status'] as String?,
        status: (j['status'] as String?) ?? 'ready',
        error: j['error'] as String?,
        tone: j['tone'] as String?,
        matchedSkills: (j['matched_skills'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
      );
}

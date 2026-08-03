// Wire models for the account/profile/sources/jobs surface
// (`scalper/service/schemas.py`: ProfileFields, ProfileResponse,
// ResumeResponse, SourcesResponse, JobResponse).

/// The user's match profile — the chip-input fields the feed is ranked against.
class Profile {
  const Profile({
    this.name = 'default',
    this.titles = const [],
    this.requiredSkills = const [],
    this.niceToHaveSkills = const [],
    this.keywords = const [],
    this.excludeKeywords = const [],
    this.remoteOnly = true,
    this.salaryFloor = 0,
    this.excludeNonLatin = true,
    this.id,
    this.origin,
  });

  final String name;
  final List<String> titles;
  final List<String> requiredSkills;
  final List<String> niceToHaveSkills;
  final List<String> keywords;
  final List<String> excludeKeywords;
  final bool remoteOnly;
  final double salaryFloor;
  final bool excludeNonLatin;
  final String? id;
  final String? origin;

  /// True once the profile carries any user-meaningful content (used to decide
  /// whether an async resume build actually produced something).
  bool get isEmpty =>
      titles.isEmpty &&
      requiredSkills.isEmpty &&
      niceToHaveSkills.isEmpty &&
      keywords.isEmpty &&
      excludeKeywords.isEmpty;

  Profile copyWith({
    String? name,
    List<String>? titles,
    List<String>? requiredSkills,
    List<String>? niceToHaveSkills,
    List<String>? keywords,
    List<String>? excludeKeywords,
    bool? remoteOnly,
    double? salaryFloor,
    bool? excludeNonLatin,
    String? id,
    String? origin,
  }) =>
      Profile(
        name: name ?? this.name,
        titles: titles ?? this.titles,
        requiredSkills: requiredSkills ?? this.requiredSkills,
        niceToHaveSkills: niceToHaveSkills ?? this.niceToHaveSkills,
        keywords: keywords ?? this.keywords,
        excludeKeywords: excludeKeywords ?? this.excludeKeywords,
        remoteOnly: remoteOnly ?? this.remoteOnly,
        salaryFloor: salaryFloor ?? this.salaryFloor,
        excludeNonLatin: excludeNonLatin ?? this.excludeNonLatin,
        id: id ?? this.id,
        origin: origin ?? this.origin,
      );

  static List<String> _strList(Object? v) =>
      (v as List?)?.map((e) => e.toString()).toList() ?? const [];

  factory Profile.fromJson(Map<String, dynamic> j) => Profile(
        name: (j['name'] as String?) ?? 'default',
        titles: _strList(j['titles']),
        requiredSkills: _strList(j['required_skills']),
        niceToHaveSkills: _strList(j['nice_to_have_skills']),
        keywords: _strList(j['keywords']),
        excludeKeywords: _strList(j['exclude_keywords']),
        remoteOnly: (j['remote_only'] as bool?) ?? true,
        salaryFloor: (j['salary_floor'] as num?)?.toDouble() ?? 0,
        excludeNonLatin: (j['exclude_non_latin'] as bool?) ?? true,
        id: j['id'] as String?,
        origin: j['origin'] as String?,
      );

  /// The `ProfileFields` body for `PUT /me/profile`.
  Map<String, dynamic> toFields() => {
        'name': name,
        'titles': titles,
        'required_skills': requiredSkills,
        'nice_to_have_skills': niceToHaveSkills,
        'keywords': keywords,
        'exclude_keywords': excludeKeywords,
        'remote_only': remoteOnly,
        'salary_floor': salaryFloor,
        'exclude_non_latin': excludeNonLatin,
      };
}

/// Metadata about the user's stored resume (`GET/PUT /me/resume`).
class ResumeInfo {
  const ResumeInfo({
    this.filename,
    this.contentType,
    required this.sizeBytes,
    required this.textChars,
    required this.updatedAt,
  });

  final String? filename;
  final String? contentType;
  final int sizeBytes;
  final int textChars;
  final String updatedAt;

  factory ResumeInfo.fromJson(Map<String, dynamic> j) => ResumeInfo(
        filename: j['filename'] as String?,
        contentType: j['content_type'] as String?,
        sizeBytes: (j['size_bytes'] as num?)?.toInt() ?? 0,
        textChars: (j['text_chars'] as num?)?.toInt() ?? 0,
        updatedAt: (j['updated_at'] as String?) ?? '',
      );
}

/// The job-board selection state (`GET/PUT /me/sources`).
class SourcesInfo {
  const SourcesInfo({
    required this.selected,
    required this.available,
    required this.maxAllowed,
  });

  final List<String> selected;
  final List<String> available;
  final int maxAllowed;

  factory SourcesInfo.fromJson(Map<String, dynamic> j) => SourcesInfo(
        selected: Profile._strList(j['sources']),
        available: Profile._strList(j['available']),
        maxAllowed: (j['max_allowed'] as num?)?.toInt() ?? 3,
      );
}

/// A single bring-your-own LLM key's stored state (`GET /me/keys`). The key
/// itself is write-only server-side and never returned — only whether one is on
/// file and whether it has been validated.
class LlmKeyInfo {
  const LlmKeyInfo({
    required this.provider,
    required this.valid,
    this.lastValidatedAt,
  });

  final String provider; // 'anthropic' | 'openai'
  final bool valid;
  final String? lastValidatedAt;

  /// True once the backend has validated the stored key at least once.
  bool get validated => lastValidatedAt != null;

  factory LlmKeyInfo.fromJson(Map<String, dynamic> j) => LlmKeyInfo(
        provider: j['provider'] as String,
        valid: (j['valid'] as bool?) ?? false,
        lastValidatedAt: j['last_validated_at'] as String?,
      );
}

/// The set of stored BYO keys (`GET/PUT/DELETE /me/keys`).
class LlmKeysInfo {
  const LlmKeysInfo({this.keys = const []});

  final List<LlmKeyInfo> keys;

  /// The stored key for [provider], or null if none is on file.
  LlmKeyInfo? forProvider(String provider) {
    for (final k in keys) {
      if (k.provider == provider) return k;
    }
    return null;
  }

  factory LlmKeysInfo.fromJson(Map<String, dynamic> j) => LlmKeysInfo(
        keys: ((j['keys'] as List?) ?? const [])
            .map((e) => LlmKeyInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

/// One usage metric within the quota (`GET /me/quota`).
class QuotaMetricInfo {
  const QuotaMetricInfo({
    required this.metric,
    required this.limit,
    required this.used,
    required this.remaining,
    required this.unlimited,
  });

  final String metric;
  final int limit;
  final int used;
  final int remaining;
  final bool unlimited;

  factory QuotaMetricInfo.fromJson(Map<String, dynamic> j) => QuotaMetricInfo(
        metric: j['metric'] as String,
        limit: (j['limit'] as num?)?.toInt() ?? 0,
        used: (j['used'] as num?)?.toInt() ?? 0,
        remaining: (j['remaining'] as num?)?.toInt() ?? 0,
        unlimited: (j['unlimited'] as bool?) ?? false,
      );
}

/// The user's plan usage for the current period (`GET /me/quota`).
class QuotaInfo {
  const QuotaInfo({
    required this.plan,
    required this.period,
    required this.byoKey,
    this.metrics = const [],
  });

  final String plan;
  final String period;
  final bool byoKey;
  final List<QuotaMetricInfo> metrics;

  factory QuotaInfo.fromJson(Map<String, dynamic> j) => QuotaInfo(
        plan: (j['plan'] as String?) ?? 'free',
        period: (j['period'] as String?) ?? '',
        byoKey: (j['byo_key'] as bool?) ?? false,
        metrics: ((j['metrics'] as List?) ?? const [])
            .map((e) => QuotaMetricInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

/// An async job record (`GET /jobs/{id}`), polled while a resume-driven profile
/// build runs.
class JobRecord {
  const JobRecord({
    required this.id,
    required this.kind,
    required this.status,
    this.result,
    this.error,
  });

  final String id;
  final String kind;
  final String status; // queued | running | succeeded | failed
  final Map<String, dynamic>? result;
  final String? error;

  bool get isDone => status == 'succeeded' || status == 'failed';
  bool get isFailed => status == 'failed';

  factory JobRecord.fromJson(Map<String, dynamic> j) => JobRecord(
        id: j['id'] as String,
        kind: (j['kind'] as String?) ?? '',
        status: (j['status'] as String?) ?? 'queued',
        result: j['result'] as Map<String, dynamic>?,
        error: j['error'] as String?,
      );
}

/// Notification preferences (`GET/PUT /me/notifications`): whether to send
/// new-match alerts and the minimum match score that triggers one.
class NotificationPrefs {
  const NotificationPrefs({required this.matchAlerts, required this.minScore});

  final bool matchAlerts;
  final int minScore;

  NotificationPrefs copyWith({bool? matchAlerts, int? minScore}) =>
      NotificationPrefs(
        matchAlerts: matchAlerts ?? this.matchAlerts,
        minScore: minScore ?? this.minScore,
      );

  factory NotificationPrefs.fromJson(Map<String, dynamic> j) => NotificationPrefs(
        matchAlerts: (j['match_alerts'] as bool?) ?? true,
        minScore: (j['min_score'] as num?)?.toInt() ?? 90,
      );
}

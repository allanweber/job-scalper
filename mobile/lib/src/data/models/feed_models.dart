// Wire models for the ranked feed (`scalper/service/schemas.py`:
// FeedItemResponse, FeedResponse).

/// One ranked posting in the feed. `score` is 0–100; `matchedSkills` /
/// `missingSkills` explain the score against the user's profile.
class FeedItem {
  const FeedItem({
    required this.postingId,
    required this.company,
    required this.title,
    required this.url,
    this.location,
    this.remote = true,
    this.salaryMin,
    this.salaryMax,
    this.salaryCurrency,
    this.publishedAt,
    this.score = 0,
    this.matchedSkills = const [],
    this.missingSkills = const [],
    this.matchedKeywords = const [],
    this.sources = const [],
    this.isNew = false,
    this.saved = false,
    this.drafted = false,
    this.applied = false,
    this.breakdown = const {},
  });

  final String postingId;
  final String company;
  final String title;
  final String url;
  final String? location;
  final bool remote;
  final double? salaryMin;
  final double? salaryMax;
  final String? salaryCurrency;
  final String? publishedAt;
  final int score;
  final List<String> matchedSkills;
  final List<String> missingSkills;
  final List<String> matchedKeywords;
  final List<String> sources;
  final bool isNew;
  final bool saved;
  final bool drafted;
  final bool applied;
  final Map<String, double> breakdown;

  FeedItem copyWith({bool? saved, bool? drafted, bool? applied}) => FeedItem(
        postingId: postingId,
        company: company,
        title: title,
        url: url,
        location: location,
        remote: remote,
        salaryMin: salaryMin,
        salaryMax: salaryMax,
        salaryCurrency: salaryCurrency,
        publishedAt: publishedAt,
        score: score,
        matchedSkills: matchedSkills,
        missingSkills: missingSkills,
        matchedKeywords: matchedKeywords,
        sources: sources,
        isNew: isNew,
        saved: saved ?? this.saved,
        drafted: drafted ?? this.drafted,
        applied: applied ?? this.applied,
        breakdown: breakdown,
      );

  static List<String> _strList(Object? v) =>
      (v as List?)?.map((e) => e.toString()).toList() ?? const [];

  factory FeedItem.fromJson(Map<String, dynamic> j) => FeedItem(
        postingId: j['posting_id'] as String,
        company: (j['company'] as String?) ?? '',
        title: (j['title'] as String?) ?? '',
        url: (j['url'] as String?) ?? '',
        location: j['location'] as String?,
        remote: (j['remote'] as bool?) ?? true,
        salaryMin: (j['salary_min'] as num?)?.toDouble(),
        salaryMax: (j['salary_max'] as num?)?.toDouble(),
        salaryCurrency: j['salary_currency'] as String?,
        publishedAt: j['published_at'] as String?,
        score: (j['score'] as num?)?.toInt() ?? 0,
        matchedSkills: _strList(j['matched_skills']),
        missingSkills: _strList(j['missing_skills']),
        matchedKeywords: _strList(j['matched_keywords']),
        sources: _strList(j['sources']),
        isNew: (j['is_new'] as bool?) ?? false,
        saved: (j['saved'] as bool?) ?? false,
        drafted: (j['drafted'] as bool?) ?? false,
        applied: (j['applied'] as bool?) ?? false,
        breakdown: (j['breakdown'] as Map?)?.map(
                (k, v) => MapEntry(k.toString(), (v as num).toDouble())) ??
            const {},
      );
}

/// A single posting's full detail (`GET /postings/{id}`): everything the feed
/// item carries plus the full description and timezone.
class PostingDetail {
  const PostingDetail({
    required this.postingId,
    required this.company,
    required this.title,
    required this.url,
    required this.description,
    this.location,
    this.remote = true,
    this.timezone,
    this.salaryMin,
    this.salaryMax,
    this.salaryCurrency,
    this.publishedAt,
    this.score = 0,
    this.matchedSkills = const [],
    this.missingSkills = const [],
    this.matchedKeywords = const [],
    this.resumeGap = const [],
    this.sources = const [],
    this.isNew = false,
    this.saved = false,
    this.drafted = false,
    this.applied = false,
    this.breakdown = const {},
  });

  final String postingId;
  final String company;
  final String title;
  final String url;
  final String description;
  final String? location;
  final bool remote;
  final String? timezone;
  final double? salaryMin;
  final double? salaryMax;
  final String? salaryCurrency;
  final String? publishedAt;
  final int score;
  final List<String> matchedSkills;
  final List<String> missingSkills;
  final List<String> matchedKeywords;

  /// Skills/keywords the posting emphasises that the user's résumé doesn't show.
  final List<String> resumeGap;
  final List<String> sources;
  final bool isNew;
  final bool saved;
  final bool drafted;
  final bool applied;
  final Map<String, double> breakdown;

  PostingDetail copyWith({bool? saved, bool? drafted, bool? applied}) =>
      PostingDetail(
        postingId: postingId,
        company: company,
        title: title,
        url: url,
        description: description,
        location: location,
        remote: remote,
        timezone: timezone,
        salaryMin: salaryMin,
        salaryMax: salaryMax,
        salaryCurrency: salaryCurrency,
        publishedAt: publishedAt,
        score: score,
        matchedSkills: matchedSkills,
        missingSkills: missingSkills,
        matchedKeywords: matchedKeywords,
        resumeGap: resumeGap,
        sources: sources,
        isNew: isNew,
        saved: saved ?? this.saved,
        drafted: drafted ?? this.drafted,
        applied: applied ?? this.applied,
        breakdown: breakdown,
      );

  factory PostingDetail.fromJson(Map<String, dynamic> j) => PostingDetail(
        postingId: j['posting_id'] as String,
        company: (j['company'] as String?) ?? '',
        title: (j['title'] as String?) ?? '',
        url: (j['url'] as String?) ?? '',
        description: (j['description'] as String?) ?? '',
        location: j['location'] as String?,
        remote: (j['remote'] as bool?) ?? true,
        timezone: j['timezone'] as String?,
        salaryMin: (j['salary_min'] as num?)?.toDouble(),
        salaryMax: (j['salary_max'] as num?)?.toDouble(),
        salaryCurrency: j['salary_currency'] as String?,
        publishedAt: j['published_at'] as String?,
        score: (j['score'] as num?)?.toInt() ?? 0,
        matchedSkills: FeedItem._strList(j['matched_skills']),
        missingSkills: FeedItem._strList(j['missing_skills']),
        matchedKeywords: FeedItem._strList(j['matched_keywords']),
        resumeGap: FeedItem._strList(j['resume_gap']),
        sources: FeedItem._strList(j['sources']),
        isNew: (j['is_new'] as bool?) ?? false,
        saved: (j['saved'] as bool?) ?? false,
        drafted: (j['drafted'] as bool?) ?? false,
        applied: (j['applied'] as bool?) ?? false,
        breakdown: (j['breakdown'] as Map?)?.map(
                (k, v) => MapEntry(k.toString(), (v as num).toDouble())) ??
            const {},
      );
}

/// Thin-feed context (`FeedResponse.meta`) that lets the Feed screen explain
/// *why* a feed is empty or thin and offer the one action that widens it —
/// lower the score filter, or add more boards.
class FeedMeta {
  const FeedMeta({
    this.poolSize = 0,
    this.sourcesCount = 0,
    this.sourcesMax = 3,
    this.hasProfile = true,
  });

  /// Postings visible from the user's boards, before scoring/filtering. When
  /// this is > 0 but the feed is empty, the score filter is what's hiding them.
  final int poolSize;

  /// Boards currently feeding the user, and the free-tier cap. Room to add more
  /// boards (`sourcesCount < sourcesMax`) is the other lever on a thin feed.
  final int sourcesCount;
  final int sourcesMax;

  /// Whether the user has a scoring profile yet.
  final bool hasProfile;

  /// True when the user could widen results by adding another board.
  bool get canAddBoards => sourcesCount < sourcesMax;

  factory FeedMeta.fromJson(Map<String, dynamic> j) => FeedMeta(
        poolSize: (j['pool_size'] as num?)?.toInt() ?? 0,
        sourcesCount: (j['sources_count'] as num?)?.toInt() ?? 0,
        sourcesMax: (j['sources_max'] as num?)?.toInt() ?? 3,
        hasProfile: (j['has_profile'] as bool?) ?? true,
      );
}

/// A page of ranked feed items (`GET /feed`).
class Feed {
  const Feed({
    required this.items,
    required this.count,
    this.meta = const FeedMeta(),
  });

  final List<FeedItem> items;
  final int count;
  final FeedMeta meta;

  int get newCount => items.where((i) => i.isNew).length;

  factory Feed.fromJson(Map<String, dynamic> j) => Feed(
        items: ((j['items'] as List?) ?? const [])
            .map((e) => FeedItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        count: (j['count'] as num?)?.toInt() ?? 0,
        meta: j['meta'] is Map<String, dynamic>
            ? FeedMeta.fromJson(j['meta'] as Map<String, dynamic>)
            : const FeedMeta(),
      );
}

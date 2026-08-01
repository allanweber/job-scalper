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
  final Map<String, double> breakdown;

  FeedItem copyWith({bool? saved, bool? drafted}) => FeedItem(
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
        breakdown: (j['breakdown'] as Map?)?.map(
                (k, v) => MapEntry(k.toString(), (v as num).toDouble())) ??
            const {},
      );
}

/// A page of ranked feed items (`GET /feed`).
class Feed {
  const Feed({required this.items, required this.count});

  final List<FeedItem> items;
  final int count;

  int get newCount => items.where((i) => i.isNew).length;

  factory Feed.fromJson(Map<String, dynamic> j) => Feed(
        items: ((j['items'] as List?) ?? const [])
            .map((e) => FeedItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        count: (j['count'] as num?)?.toInt() ?? 0,
      );
}

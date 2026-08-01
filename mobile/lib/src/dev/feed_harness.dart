import '../data/feed_repository.dart';
import '../data/models/feed_models.dart';

/// Dev/QA-only support (NOT used by `main.dart`): an in-memory feed backend and
/// demo postings, shared by the widget tests and the screenshot entrypoint so
/// both exercise the real [FeedController] without a server.

final demoFeedItems = <FeedItem>[
  FeedItem(
    postingId: 'j1',
    company: 'Linear',
    title: 'Senior Backend Engineer',
    url: 'https://example.com/j1',
    remote: true,
    salaryMin: 150000,
    salaryMax: 190000,
    salaryCurrency: 'USD',
    publishedAt: DateTime.now().subtract(const Duration(hours: 5)).toIso8601String(),
    score: 92,
    matchedSkills: ['Python', 'PostgreSQL', 'AWS', 'Docker'],
    missingSkills: ['Kubernetes'],
    matchedKeywords: ['API', 'fintech'],
    sources: ['remotive', 'weworkremotely'],
    isNew: true,
  ),
  FeedItem(
    postingId: 'j2',
    company: 'Stripe',
    title: 'Platform Engineer, Payments',
    url: 'https://example.com/j2',
    remote: true,
    location: 'Remote (US)',
    salaryMin: 140000,
    salaryMax: 175000,
    salaryCurrency: 'USD',
    publishedAt: DateTime.now().subtract(const Duration(days: 1)).toIso8601String(),
    score: 78,
    matchedSkills: ['Python', 'AWS', 'Go'],
    missingSkills: ['Terraform', 'gRPC'],
    sources: ['remoteok'],
    isNew: true,
    saved: true,
  ),
  FeedItem(
    postingId: 'j3',
    company: 'Arbeitnow GmbH',
    title: 'Backend Developer (Django)',
    url: 'https://example.com/j3',
    remote: true,
    location: 'Berlin / Remote',
    salaryMin: 70000,
    salaryMax: 85000,
    salaryCurrency: 'EUR',
    publishedAt: DateTime.now().subtract(const Duration(days: 3)).toIso8601String(),
    score: 64,
    matchedSkills: ['Python', 'PostgreSQL'],
    missingSkills: ['Django', 'Celery'],
    sources: ['arbeitnow'],
    drafted: true,
  ),
  FeedItem(
    postingId: 'j4',
    company: 'Nomad Labs',
    title: 'Full-Stack Engineer',
    url: 'https://example.com/j4',
    remote: true,
    salaryMin: 90000,
    salaryCurrency: 'USD',
    publishedAt: DateTime.now().subtract(const Duration(days: 6)).toIso8601String(),
    score: 51,
    matchedSkills: ['Docker'],
    missingSkills: ['React', 'TypeScript', 'Node'],
    sources: ['jobicy', 'workingnomads'],
  ),
];

/// In-memory [FeedRepository]. Filters by score like the real endpoint, records
/// saves/seen for assertions, and can simulate a slow load or a failure.
class FakeFeedRepository implements FeedRepository {
  FakeFeedRepository({
    List<FeedItem>? items,
    this.fails = false,
    this.delay,
  }) : _items = items ?? demoFeedItems;

  final List<FeedItem> _items;
  final bool fails;
  final Duration? delay;

  final List<String> savedCalls = [];
  final List<String> unsavedCalls = [];
  final Set<String> seen = {};

  @override
  Future<Feed> getFeed({int limit = 100, int minScore = 1}) async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    final filtered = _items.where((i) => i.score >= minScore).toList();
    return Feed(items: filtered, count: filtered.length);
  }

  @override
  Future<void> save(String postingId) async => savedCalls.add(postingId);

  @override
  Future<void> unsave(String postingId) async => unsavedCalls.add(postingId);

  @override
  Future<void> markSeen(String postingId) async {
    seen.add(postingId);
  }
}

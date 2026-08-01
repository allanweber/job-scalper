import '../data/drafts_repository.dart';
import '../data/models/draft_models.dart';

/// Dev/QA-only support (NOT used by `main.dart`): an in-memory drafts backend
/// and demo applications, shared by the widget tests and the screenshot
/// entrypoint so both exercise the real controllers without a server.

final demoDraftSummaries = <DraftSummary>[
  DraftSummary(
    id: 'd1',
    postingId: 'j1',
    jobSource: 'pool',
    keySource: 'platform',
    createdAt: DateTime.now().subtract(const Duration(hours: 2)).toIso8601String(),
    title: 'Senior Backend Engineer',
    company: 'Linear',
  ),
  DraftSummary(
    id: 'd2',
    postingId: 'j2',
    jobSource: 'pool',
    keySource: 'byo',
    createdAt: DateTime.now().subtract(const Duration(days: 1)).toIso8601String(),
    title: 'Platform Engineer, Payments',
    company: 'Stripe',
  ),
  DraftSummary(
    id: 'd3',
    postingId: 'j3',
    jobSource: 'pool',
    keySource: 'platform',
    createdAt: DateTime.now().subtract(const Duration(days: 4)).toIso8601String(),
    title: 'Backend Developer (Django)',
    company: 'Arbeitnow GmbH',
  ),
];

Draft _demoDraft(DraftSummary s) => Draft(
      id: s.id,
      postingId: s.postingId,
      jobSource: s.jobSource,
      resumeMd: _demoResume,
      coverLetterMd: _demoCoverLetter,
      stretchClaimsMd: s.id == 'd1'
          ? 'Framed “led a team” — you mentored two engineers; confirm the '
              'framing fits before sending.'
          : null,
      provider: 'anthropic',
      model: s.keySource == 'byo' ? 'claude-sonnet-4-6' : 'claude-haiku-4-5',
      keySource: s.keySource,
      createdAt: s.createdAt,
    );

/// In-memory [DraftsRepository]. Serves the demo drafts, records edits for
/// assertions, and can simulate a slow load or a failure.
class FakeDraftsRepository implements DraftsRepository {
  FakeDraftsRepository({
    List<DraftSummary>? items,
    this.fails = false,
    this.delay,
  }) : _items = items ?? demoDraftSummaries;

  final List<DraftSummary> _items;
  final bool fails;
  final Duration? delay;

  final List<({String id, String? resumeMd, String? coverLetterMd})> edits = [];
  final Map<String, Draft> _overrides = {};

  @override
  Future<List<DraftSummary>> listDrafts() async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    return List.unmodifiable(_items);
  }

  @override
  Future<Draft> getDraft(String id) async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    if (_overrides.containsKey(id)) return _overrides[id]!;
    final s = _items.firstWhere((e) => e.id == id, orElse: () => _items.first);
    return _demoDraft(s);
  }

  @override
  Future<Draft> updateDraft(String id,
      {String? resumeMd, String? coverLetterMd}) async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    edits.add((id: id, resumeMd: resumeMd, coverLetterMd: coverLetterMd));
    final base = _overrides[id] ??
        _demoDraft(_items.firstWhere((e) => e.id == id,
            orElse: () => _items.first));
    final updated =
        base.copyWith(resumeMd: resumeMd, coverLetterMd: coverLetterMd);
    _overrides[id] = updated;
    return updated;
  }
}

const _demoResume = '''
# Jane Doe
Senior Backend Engineer · jane@example.com

## Summary
Backend engineer with 6+ years building high-throughput Python services and
owning PostgreSQL at scale. Tailored for the Senior Backend Engineer role.

## Experience
### Acme — Staff Engineer (2021–present)
- Scaled the payments API to 12k req/s on AWS + Docker.
- Cut p99 latency 40% via query and index redesign.

### Beta — Backend Engineer (2018–2021)
- Built event-driven ingestion in Python and PostgreSQL.

## Skills
Python · PostgreSQL · AWS · Docker · REST APIs
''';

const _demoCoverLetter = '''
Dear Hiring Team,

I'm excited to apply for the Senior Backend Engineer role. Scaling reliable,
high-throughput Python services is exactly the work I've spent the last six
years doing — most recently taking a payments API to 12k requests per second
while cutting p99 latency by 40%.

Your emphasis on PostgreSQL performance and clean API design maps directly to
my day-to-day, and I'd love to bring that to your team.

Best,
Jane Doe
''';

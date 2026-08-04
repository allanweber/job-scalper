import 'dart:typed_data';

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
    url: 'https://example.com/jobs/j1',
  ),
  DraftSummary(
    id: 'd2',
    postingId: 'j2',
    jobSource: 'pool',
    keySource: 'byo',
    createdAt: DateTime.now().subtract(const Duration(days: 1)).toIso8601String(),
    title: 'Platform Engineer, Payments',
    company: 'Stripe',
    url: 'https://example.com/jobs/j2',
  ),
  DraftSummary(
    id: 'd3',
    postingId: 'j3',
    jobSource: 'pool',
    keySource: 'platform',
    createdAt: DateTime.now().subtract(const Duration(days: 4)).toIso8601String(),
    title: 'Backend Developer (Django)',
    company: 'Arbeitnow GmbH',
    url: 'https://example.com/jobs/j3',
  ),
];

Draft _demoDraft(DraftSummary s) => Draft(
      id: s.id,
      postingId: s.postingId,
      jobSource: s.jobSource,
      // Pending/failed drafts have no content yet.
      resumeMd: s.isReady ? _demoResume : null,
      coverLetterMd: s.isReady ? _demoCoverLetter : null,
      stretchClaimsMd: s.id == 'd1' && s.isReady
          ? 'Framed “led a team” — you mentored two engineers; confirm the '
              'framing fits before sending.'
          : null,
      provider: 'anthropic',
      model: s.keySource == 'byo' ? 'claude-sonnet-4-6' : 'claude-haiku-4-5',
      keySource: s.keySource,
      createdAt: s.createdAt,
      applied: s.applied,
      applicationStatus: s.applicationStatus,
      status: s.status,
      error: s.error,
      matchedSkills:
          s.isReady ? const ['Python', 'PostgreSQL', 'AWS'] : const [],
    );

/// In-memory [DraftsRepository]. Serves the demo drafts, records edits for
/// assertions, and can simulate a slow load or a failure.
class FakeDraftsRepository implements DraftsRepository {
  FakeDraftsRepository({
    List<DraftSummary>? items,
    this.fails = false,
    this.delay,
    this.insights,
    Set<String>? pendingOnce,
  })  : _items = items ?? demoDraftSummaries,
        _pendingOnce = pendingOnce ?? const {};

  final List<DraftSummary> _items;
  final bool fails;
  final Duration? delay;

  /// Optional explicit funnel for [getInsights]; when null it's computed from
  /// the items (each item = one application, null stage folds into 'applied').
  final ApplicationInsights? insights;

  /// Draft ids that return a 'pending' draft on the first getDraft call and a
  /// ready one afterwards — used to exercise the poll-until-ready flow.
  final Set<String> _pendingOnce;
  final Map<String, int> _getCalls = {};

  final List<({String id, String? resumeMd, String? coverLetterMd})> edits = [];
  final List<({String id, bool applied})> appliedCalls = [];
  final List<({String id, String? status})> statusCalls = [];
  final List<({String id, String? tone})> regenerateCalls = [];
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
    final calls = (_getCalls[id] ?? 0) + 1;
    _getCalls[id] = calls;
    if (_pendingOnce.contains(id) && calls < 2) {
      return Draft(
        id: id,
        postingId: s.postingId,
        jobSource: s.jobSource,
        createdAt: s.createdAt,
        status: 'pending',
      );
    }
    return _demoDraft(s);
  }

  @override
  Future<Draft> regenerateDraft(String id, {String? tone}) async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    regenerateCalls.add((id: id, tone: tone));
    final s = _items.firstWhere((e) => e.id == id, orElse: () => _items.first);
    final draft = _demoDraft(s).copyWith(status: 'ready');
    return Draft(
      id: draft.id, postingId: draft.postingId, jobSource: draft.jobSource,
      resumeMd: draft.resumeMd, coverLetterMd: draft.coverLetterMd,
      stretchClaimsMd: draft.stretchClaimsMd, provider: draft.provider,
      model: draft.model, keySource: draft.keySource, createdAt: draft.createdAt,
      applied: draft.applied, applicationStatus: draft.applicationStatus,
      status: 'ready', tone: tone, matchedSkills: draft.matchedSkills,
    );
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

  @override
  Future<Draft> setApplied(String id, bool applied) async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    appliedCalls.add((id: id, applied: applied));
    final base = _overrides[id] ??
        _demoDraft(_items.firstWhere((e) => e.id == id,
            orElse: () => _items.first));
    final updated = base.copyWith(
        applied: applied, applicationStatus: applied ? 'applied' : null);
    _overrides[id] = updated;
    return updated;
  }

  @override
  Future<Draft> setApplicationStatus(String id, String? status) async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    statusCalls.add((id: id, status: status));
    final base = _overrides[id] ??
        _demoDraft(_items.firstWhere((e) => e.id == id,
            orElse: () => _items.first));
    final updated =
        base.copyWith(applied: status != null, applicationStatus: status);
    _overrides[id] = updated;
    return updated;
  }

  @override
  Future<Uint8List> getDraftPdf(String id, String which) async {
    if (delay != null) await Future.delayed(delay!);
    // In tests the PDF service is not running — always throw so the screen
    // falls through to on-device generation.
    throw Exception('pdf service not available in tests');
  }

  @override
  Future<ApplicationInsights> getInsights() async {
    if (delay != null) await Future.delayed(delay!);
    if (fails) throw Exception('Failed host lookup');
    if (insights != null) return insights!;
    // Mirror the backend: every item is one application; a null stage folds
    // into 'applied'.
    final counts = <String, int>{};
    for (final d in _items) {
      final stage = d.applicationStatus ?? 'applied';
      counts[stage] = (counts[stage] ?? 0) + 1;
    }
    return ApplicationInsights(total: _items.length, counts: counts);
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

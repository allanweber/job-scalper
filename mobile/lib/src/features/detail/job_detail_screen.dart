import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/feed_models.dart';
import '../../theme/tokens.dart';
import '../../util/format.dart';
import '../feed/widgets/score_ring.dart';
import 'job_detail_controller.dart';

/// Full posting view: match breakdown, skills, full description, and the
/// apply / save / draft actions. [initial] (the feed item that was tapped)
/// renders the header instantly while the full detail loads.
class JobDetailScreen extends ConsumerStatefulWidget {
  const JobDetailScreen({super.key, required this.postingId, this.initial});

  final String postingId;
  final FeedItem? initial;

  @override
  ConsumerState<JobDetailScreen> createState() => _JobDetailScreenState();
}

class _JobDetailScreenState extends ConsumerState<JobDetailScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref
        .read(jobDetailControllerProvider.notifier)
        .load(widget.postingId));
  }

  @override
  Widget build(BuildContext context) {
    final initial = widget.initial;
    final state = ref.watch(jobDetailControllerProvider);
    final ctrl = ref.read(jobDetailControllerProvider.notifier);
    final detail = state.detail;
    final saved = detail?.saved ?? initial?.saved ?? false;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Job'),
        actions: [
          IconButton(
            onPressed: detail == null ? null : ctrl.toggleSave,
            tooltip: saved ? 'Saved' : 'Save',
            icon: Icon(saved ? Icons.favorite_rounded : Icons.favorite_outline),
          ),
        ],
      ),
      body: switch (state.status) {
        DetailStatus.error when detail == null => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh,
          ),
        _ => _Body(state: state, initial: initial),
      },
      bottomNavigationBar: (detail ?? initial) == null
          ? null
          : _ActionBar(
              url: detail?.url ?? initial?.url ?? '',
              drafted: detail?.drafted ?? initial?.drafted ?? false,
              draftPhase: state.draftPhase,
              onDraft: () => _draft(ctrl),
            ),
    );
  }

  Future<void> _draft(JobDetailController ctrl) async {
    await ctrl.draft();
    if (!mounted) return;
    final s = ref.read(jobDetailControllerProvider);
    final messenger = ScaffoldMessenger.of(context);
    if (s.draftPhase == DraftPhase.done) {
      messenger.showSnackBar(const SnackBar(
          content: Text('Draft started — find it in Applications shortly.')));
    } else if (s.draftPhase == DraftPhase.failed) {
      messenger.showSnackBar(SnackBar(
          content: Text(s.draftError ?? 'Couldn’t start the draft.')));
    }
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.state, required this.initial});
  final JobDetailState state;
  final FeedItem? initial;

  @override
  Widget build(BuildContext context) {
    final d = state.detail;
    // Header renders from the loaded detail, or the tapped item while loading.
    final company = d?.company ?? initial?.company ?? '';
    final title = d?.title ?? initial?.title ?? '';
    final score = d?.score ?? initial?.score ?? 0;
    final isNew = d?.isNew ?? initial?.isNew ?? false;

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppTokens.screenPadding, 16,
          AppTokens.screenPadding, 24),
      children: [
        _Header(company: company, title: title, score: score, isNew: isNew),
        const SizedBox(height: 16),
        _Meta(detail: d, initial: initial),
        if (d == null) ...[
          const SizedBox(height: 40),
          const Center(child: CircularProgressIndicator()),
        ] else ...[
          if (d.breakdown.isNotEmpty) ...[
            const SizedBox(height: 20),
            _Breakdown(breakdown: d.breakdown, score: d.score),
          ],
          if (d.matchedSkills.isNotEmpty || d.missingSkills.isNotEmpty) ...[
            const SizedBox(height: 20),
            _SkillsSection(detail: d),
          ],
          const SizedBox(height: 24),
          _Description(text: d.description),
        ],
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.company,
    required this.title,
    required this.score,
    required this.isNew,
  });
  final String company;
  final String title;
  final int score;
  final bool isNew;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ScoreRing(score: score, size: 64),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Flexible(
                    child: Text(company,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontSize: 13.5,
                            fontWeight: FontWeight.w600,
                            color: scheme.onSurfaceVariant)),
                  ),
                  if (isNew) ...[
                    const SizedBox(width: 8),
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                          color: scheme.primary,
                          borderRadius: BorderRadius.circular(6)),
                      child: Text('NEW',
                          style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.5,
                              color: scheme.onPrimary)),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 3),
              Text(title,
                  style: TextStyle(
                      fontSize: 20,
                      height: 1.2,
                      fontWeight: FontWeight.w800,
                      color: scheme.onSurface)),
            ],
          ),
        ),
      ],
    );
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.detail, required this.initial});
  final PostingDetail? detail;
  final FeedItem? initial;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final remote = detail?.remote ?? initial?.remote ?? false;
    final location = detail?.location ?? initial?.location;
    final tz = detail?.timezone;
    final salary = formatSalary(
      min: detail?.salaryMin ?? initial?.salaryMin,
      max: detail?.salaryMax ?? initial?.salaryMax,
      currency: detail?.salaryCurrency ?? initial?.salaryCurrency,
    );
    final published = relativeTime(detail?.publishedAt ?? initial?.publishedAt);
    TextStyle style() => TextStyle(fontSize: 13, color: scheme.onSurfaceVariant);

    return Wrap(
      spacing: 14,
      runSpacing: 8,
      children: [
        if (remote) _MetaItem(icon: Icons.public, label: 'Remote', style: style()),
        if (location != null && location.isNotEmpty)
          _MetaItem(icon: Icons.place_outlined, label: location, style: style()),
        if (tz != null && tz.isNotEmpty)
          _MetaItem(icon: Icons.schedule, label: tz, style: style()),
        if (salary != null)
          _MetaItem(
              icon: Icons.payments_outlined, label: salary, style: style()),
        if (published != null)
          _MetaItem(
              icon: Icons.calendar_today_outlined,
              label: published,
              style: style()),
      ],
    );
  }
}

class _MetaItem extends StatelessWidget {
  const _MetaItem(
      {required this.icon, required this.label, required this.style});
  final IconData icon;
  final String label;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: style.color),
        const SizedBox(width: 5),
        Text(label, style: style),
      ],
    );
  }
}

class _Breakdown extends StatelessWidget {
  const _Breakdown({required this.breakdown, required this.score});
  final Map<String, double> breakdown;
  final int score;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = breakdown.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final max = entries.first.value == 0 ? 1.0 : entries.first.value;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppTokens.radiusCard),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Why this ranks',
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: scheme.onSurface)),
              Text('$score / 100',
                  style: TextStyle(
                      fontFamily: 'RobotoMono',
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: AppTokens.scoreColor(score))),
            ],
          ),
          const SizedBox(height: 12),
          for (final e in entries) ...[
            _BreakdownRow(label: e.key, value: e.value, max: max),
            const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow(
      {required this.label, required this.value, required this.max});
  final String label;
  final double value;
  final double max;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pretty = label.isEmpty
        ? label
        : label[0].toUpperCase() + label.substring(1);
    return Row(
      children: [
        SizedBox(
          width: 84,
          child: Text(pretty,
              style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (value / max).clamp(0.0, 1.0),
              minHeight: 7,
              backgroundColor: scheme.surfaceContainerHighest,
              valueColor: AlwaysStoppedAnimation(scheme.primary),
            ),
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 36,
          child: Text('${(value * 100).round()}%',
              textAlign: TextAlign.right,
              style: TextStyle(
                  fontFamily: 'RobotoMono',
                  fontSize: 12,
                  color: scheme.onSurfaceVariant)),
        ),
      ],
    );
  }
}

class _SkillsSection extends StatelessWidget {
  const _SkillsSection({required this.detail});
  final PostingDetail detail;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (detail.matchedSkills.isNotEmpty) ...[
          _Label('You match'),
          const SizedBox(height: 8),
          _Chips(
            labels: detail.matchedSkills,
            bg: scheme.primaryContainer,
            fg: scheme.onPrimaryContainer,
            icon: Icons.check_rounded,
          ),
        ],
        if (detail.missingSkills.isNotEmpty) ...[
          const SizedBox(height: 16),
          _Label('Gaps'),
          const SizedBox(height: 8),
          _Chips(
            labels: detail.missingSkills,
            bg: scheme.surfaceContainerHighest,
            fg: scheme.onSurfaceVariant,
            icon: Icons.remove_rounded,
          ),
        ],
        if (detail.matchedKeywords.isNotEmpty) ...[
          const SizedBox(height: 16),
          _Label('Keywords'),
          const SizedBox(height: 8),
          _Chips(
            labels: detail.matchedKeywords,
            bg: AppTokens.chipBlueBgLight,
            fg: AppTokens.chipBlueTextLight,
            icon: Icons.tag,
          ),
        ],
      ],
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text.toUpperCase(),
        style: TextStyle(
            fontSize: 11.5,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.6,
            color: Theme.of(context).colorScheme.onSurfaceVariant));
  }
}

class _Chips extends StatelessWidget {
  const _Chips({
    required this.labels,
    required this.bg,
    required this.fg,
    required this.icon,
  });
  final List<String> labels;
  final Color bg;
  final Color fg;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final l in labels)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration:
                BoxDecoration(color: bg, borderRadius: BorderRadius.circular(8)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 13, color: fg),
                const SizedBox(width: 4),
                Text(l,
                    style: TextStyle(
                        fontSize: 12.5, fontWeight: FontWeight.w600, color: fg)),
              ],
            ),
          ),
      ],
    );
  }
}

class _Description extends StatelessWidget {
  const _Description({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _Label('Job description'),
        const SizedBox(height: 10),
        SelectableText(
          text.trim().isEmpty ? 'No description provided.' : text.trim(),
          style: TextStyle(
              fontSize: 14, height: 1.5, color: scheme.onSurface),
        ),
      ],
    );
  }
}

class _ActionBar extends StatelessWidget {
  const _ActionBar({
    required this.url,
    required this.drafted,
    required this.draftPhase,
    required this.onDraft,
  });
  final String url;
  final bool drafted;
  final DraftPhase draftPhase;
  final VoidCallback onDraft;

  @override
  Widget build(BuildContext context) {
    final running = draftPhase == DraftPhase.running;
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: Row(
        children: [
          Expanded(
            child: SizedBox(
              height: 50,
              child: OutlinedButton.icon(
                onPressed: (running || drafted) ? null : onDraft,
                icon: running
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : Icon(drafted
                        ? Icons.check_rounded
                        : Icons.auto_awesome_outlined),
                label: Text(drafted ? 'Drafted' : 'Draft application'),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SizedBox(
              height: 50,
              child: FilledButton.icon(
                onPressed: () => _open(context),
                icon: const Icon(Icons.open_in_new_rounded, size: 18),
                label: const Text('Apply'),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _open(BuildContext context) async {
    final uri = Uri.tryParse(url);
    var ok = false;
    if (uri != null) {
      ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Couldn’t open the posting.')));
    }
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded,
                size: 48, color: scheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text('Couldn’t load this job',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurface)),
            const SizedBox(height: 8),
            Text(message,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 20),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

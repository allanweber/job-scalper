import 'package:flutter/material.dart';

import '../../../data/models/feed_models.dart';
import '../../../theme/tokens.dart';
import '../../../util/format.dart';
import 'score_ring.dart';

/// A single ranked posting in the feed: score ring, title/company, match
/// summary (matched vs missing skills), meta (remote/location/salary), the
/// source boards it came from, and a save toggle.
class JobCard extends StatelessWidget {
  const JobCard({
    super.key,
    required this.item,
    required this.onToggleSave,
    this.onTap,
  });

  final FeedItem item;
  final VoidCallback onToggleSave;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(AppTokens.radiusCard),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppTokens.radiusCard),
        child: Container(
          padding: const EdgeInsets.all(AppTokens.cardPadding),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppTokens.radiusCard),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ScoreRing(score: item.score),
                  const SizedBox(width: 12),
                  Expanded(child: _Header(item: item)),
                  _SaveButton(saved: item.saved, onTap: onToggleSave),
                ],
              ),
              const SizedBox(height: 12),
              _MetaRow(item: item),
              if (item.matchedSkills.isNotEmpty ||
                  item.missingSkills.isNotEmpty) ...[
                const SizedBox(height: 12),
                _Skills(item: item),
              ],
              if (item.sources.isNotEmpty) ...[
                const SizedBox(height: 12),
                _Sources(sources: item.sources, drafted: item.drafted),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.item});
  final FeedItem item;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Flexible(
              child: Text(item.company,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: scheme.onSurfaceVariant)),
            ),
            if (item.isNew) ...[
              const SizedBox(width: 8),
              const _NewBadge(),
            ],
          ],
        ),
        const SizedBox(height: 2),
        Text(item.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
                fontSize: 16,
                height: 1.2,
                fontWeight: FontWeight.w700,
                color: scheme.onSurface)),
      ],
    );
  }
}

class _NewBadge extends StatelessWidget {
  const _NewBadge();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: scheme.primary,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text('NEW',
          style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.5,
              color: scheme.onPrimary)),
    );
  }
}

class _SaveButton extends StatelessWidget {
  const _SaveButton({required this.saved, required this.onTap});
  final bool saved;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return IconButton(
      onPressed: onTap,
      visualDensity: VisualDensity.compact,
      tooltip: saved ? 'Saved' : 'Save',
      icon: Icon(
        saved ? Icons.favorite_rounded : Icons.favorite_outline,
        color: saved ? scheme.primary : scheme.onSurfaceVariant,
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.item});
  final FeedItem item;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final salary = formatSalary(
        min: item.salaryMin, max: item.salaryMax, currency: item.salaryCurrency);
    return Wrap(
      spacing: 8,
      runSpacing: 6,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (item.remote) const _MetaChip(icon: Icons.public, label: 'Remote'),
        if (item.location != null && item.location!.isNotEmpty)
          _MetaChip(icon: Icons.place_outlined, label: item.location!),
        if (salary != null) _MetaChip(icon: Icons.payments_outlined, label: salary),
        if (relativeTime(item.publishedAt) case final t?)
          Text(t, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
      ],
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: scheme.onSurfaceVariant),
        const SizedBox(width: 4),
        Text(label,
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
      ],
    );
  }
}

class _Skills extends StatelessWidget {
  const _Skills({required this.item});
  final FeedItem item;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final s in item.matchedSkills.take(6))
          _SkillChip(
            label: s,
            bg: scheme.primaryContainer,
            fg: scheme.onPrimaryContainer,
            icon: Icons.check_rounded,
          ),
        for (final s in item.missingSkills.take(3))
          _SkillChip(
            label: s,
            bg: scheme.surfaceContainerHighest,
            fg: scheme.onSurfaceVariant,
            icon: Icons.remove_rounded,
          ),
      ],
    );
  }
}

class _SkillChip extends StatelessWidget {
  const _SkillChip({
    required this.label,
    required this.bg,
    required this.fg,
    required this.icon,
  });
  final String label;
  final Color bg;
  final Color fg;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(8)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: fg),
          const SizedBox(width: 4),
          Text(label,
              style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.w600, color: fg)),
        ],
      ),
    );
  }
}

class _Sources extends StatelessWidget {
  const _Sources({required this.sources, required this.drafted});
  final List<String> sources;
  final bool drafted;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Expanded(
          child: Text(
            sources.map(prettySource).join(' · '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
          ),
        ),
        if (drafted) ...[
          const SizedBox(width: 8),
          Icon(Icons.description_rounded, size: 14, color: scheme.primary),
          const SizedBox(width: 3),
          Text('Drafted',
              style: TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w600,
                  color: scheme.primary)),
        ],
      ],
    );
  }
}


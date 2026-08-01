// Small display formatters shared by the feed card and the job detail view.

/// A compact salary range, e.g. `$120k–$160k`, `€70k+`, `up to $90k`.
String? formatSalary({double? min, double? max, String? currency}) {
  final sym = switch (currency) {
    'USD' || null => r'$',
    'EUR' => '€',
    'GBP' => '£',
    final c => '$c ',
  };
  String k(double v) {
    if (v >= 1000) {
      final n = v / 1000;
      return '$sym${n == n.roundToDouble() ? n.toStringAsFixed(0) : n.toStringAsFixed(1)}k';
    }
    return '$sym${v.toStringAsFixed(0)}';
  }

  if (min != null && max != null && max > 0) return '${k(min)}–${k(max)}';
  if (min != null && min > 0) return '${k(min)}+';
  if (max != null && max > 0) return 'up to ${k(max)}';
  return null;
}

/// A coarse "time ago" label from an ISO timestamp, or null if unparseable.
String? relativeTime(String? iso) {
  if (iso == null || iso.isEmpty) return null;
  final t = DateTime.tryParse(iso);
  if (t == null) return null;
  final d = DateTime.now().difference(t);
  if (d.inDays >= 30) return '${(d.inDays / 30).floor()}mo ago';
  if (d.inDays >= 1) return '${d.inDays}d ago';
  if (d.inHours >= 1) return '${d.inHours}h ago';
  return 'just now';
}

/// A human label for a source-board slug.
String prettySource(String slug) => switch (slug) {
      'remotive' => 'Remotive',
      'remoteok' => 'RemoteOK',
      'weworkremotely' => 'We Work Remotely',
      'arbeitnow' => 'Arbeitnow',
      'jobicy' => 'Jobicy',
      'himalayas' => 'Himalayas',
      'workingnomads' => 'Working Nomads',
      'themuse' => 'The Muse',
      _ => slug.isEmpty ? slug : slug[0].toUpperCase() + slug.substring(1),
    };

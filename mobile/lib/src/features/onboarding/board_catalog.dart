/// Human-friendly names + one-liners for job-board source slugs returned by
/// `GET /me/sources`. Unknown slugs fall back to a title-cased label.
class BoardInfo {
  const BoardInfo(this.name, this.blurb);
  final String name;
  final String blurb;
}

const _catalog = <String, BoardInfo>{
  'remotive': BoardInfo('Remotive', 'Curated remote roles across tech.'),
  'remoteok': BoardInfo('RemoteOK', 'High-volume remote job aggregator.'),
  'weworkremotely':
      BoardInfo('We Work Remotely', 'One of the largest remote communities.'),
  'arbeitnow': BoardInfo('Arbeitnow', 'Remote & EU roles, English-friendly.'),
  'jobicy': BoardInfo('Jobicy', 'Remote jobs with a global talent focus.'),
  'himalayas': BoardInfo('Himalayas', 'Remote roles with rich company data.'),
  'workingnomads':
      BoardInfo('Working Nomads', 'Hand-picked remote listings by category.'),
  'themuse': BoardInfo('The Muse', 'Roles from vetted companies with culture info.'),
  'adzuna': BoardInfo('Adzuna', 'Broad job-search aggregator.'),
  'jobspresso': BoardInfo('Jobspresso', 'Curated remote tech & marketing jobs.'),
  'remoteco': BoardInfo('Remote.co', 'Remote roles across disciplines.'),
};

BoardInfo boardInfo(String slug) {
  final known = _catalog[slug];
  if (known != null) return known;
  final pretty = slug
      .split(RegExp(r'[_\-\s]+'))
      .where((w) => w.isNotEmpty)
      .map((w) => w[0].toUpperCase() + w.substring(1))
      .join(' ');
  return BoardInfo(pretty.isEmpty ? slug : pretty, 'Remote job board.');
}

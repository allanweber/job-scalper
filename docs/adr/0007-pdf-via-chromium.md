# Resume/cover-letter PDFs render via headless Chromium, not a PDF library

Application Draft PDFs are produced by rendering markdown → HTML (Jinja, as reports
already do) → PDF with headless Chromium's print-to-PDF, reusing the Playwright browser
helper the scrape sources already use. Chromium lives behind a new optional `pdf` extra
and is fail-soft: if it is not installed, the markdown is still written and a hint is
printed, mirroring how the hard sources degrade.

## Considered options

- **WeasyPrint** — pure md→HTML→PDF with no browser, but pulls a new system-library
  family (cairo/pango) that is a known install headache across platforms.
- **ReportLab / fpdf** — no HTML step, but layout is hand-built in Python; poor typography
  for a resume and far more code.
- **Headless Chromium via Playwright (chosen)** — best CSS/font fidelity (needed to match
  the user's existing Word-made `backend.pdf` layout: centred header, caps sections,
  right-aligned dates, justified body) and no new dependency family, since Playwright is
  already an optional dep for scraping.

## Consequences

Faithful PDFs require a structured resume template the model fills, and the markdown stays
the source of truth (PDFs are always re-derivable via `scalper render`). The cost is the
`playwright install chromium` step — already documented for the scrape sources — and that
PDF output is unavailable until the `pdf` extra is installed.

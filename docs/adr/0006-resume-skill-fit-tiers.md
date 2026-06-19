# Tailored resumes bridge adjacent skills, ledgered as Stretch Claims

When drafting a complete tailored resume (Application Draft), the model rephrases the
user's real resume into a posting's language and may **bridge** a missing required skill
into the resume when it is genuinely adjacent to a real one with a named foundation the
user already has (e.g. Docker → Kubernetes). It must never claim a skill with no honest
bridge (e.g. Java → Go), and never invent employers, dates, titles, or credentials. Every
bridge is recorded in a Stretch Claims ledger so the user knows exactly which claims they
cannot yet defend cold.

## Considered options

- **Pure-honest** — only state skills literally present. Safest, but loses easy
  keyword-match the user genuinely qualifies for under a different name.
- **Pure-keyword** — inject all required skills to maximise match. Produces a resume that
  fails the first technical screen and burns credibility.
- **Bridged + ledgered (chosen)** — the middle: re-label real adjacent skills in the
  posting's terms, block unrelated ones, and surface every bridge for the user to vet.

## Consequences

The draft prompt enforces a three-tier rule (present / adjacent / unrelated). The resume
stays clean and sendable; the `stretch_claims.md` ledger exists only when at least one
bridge was made and then lists all of them. The honesty boundary lives in the prompt, so
it is only as strong as the model's adherence — the ledger is the user's backstop.

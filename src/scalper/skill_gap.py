"""Résumé gap: skills/keywords a posting emphasises that the résumé doesn't show.

Distinct from `scoring.missing_skills` (which is *profile* required-skills the posting
lacks). This looks the other way — terms present in the **posting** but absent from
the user's **résumé text** — so the detail screen can tell the user, concretely, what
this job asks for that their résumé doesn't yet mention.

Deterministic and LLM-free: a curated vocabulary of common tech skills/tools/keywords
(plus any extra terms the caller passes, e.g. the user's own profile skills) is matched
against the posting; anything found there but not in the résumé is a gap. Word-boundary
matching (shared with scoring) keeps short tokens like ``go`` or ``r`` honest.
"""

from __future__ import annotations

import re

from scalper.scoring import _contains_term

#: Curated skills/tools/keywords worth flagging. Display casing is preserved (the
#: matcher is case-insensitive) so labels render nicely in the UI. Kept broad but
#: not exhaustive — the caller can union in the user's own profile terms.
SKILL_VOCAB: tuple[str, ...] = (
    # languages
    "Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Swift", "Go", "Rust",
    "Ruby", "PHP", "C++", "C#", "Scala", "Elixir", "Clojure", "Dart", "R", "SQL",
    "Bash", "PowerShell",
    # frontend
    "React", "React Native", "Vue", "Angular", "Svelte", "Next.js", "Nuxt",
    "Redux", "Tailwind", "HTML", "CSS", "SASS", "Flutter", "Jetpack Compose",
    "SwiftUI", "Webpack", "Vite",
    # backend / frameworks
    "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring", "Spring Boot",
    "Rails", "Laravel", ".NET", "GraphQL", "gRPC", "REST API", "Microservices",
    # data / ml
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
    "DynamoDB", "Snowflake", "BigQuery", "Kafka", "Spark", "Airflow", "dbt",
    "Pandas", "NumPy", "PyTorch", "TensorFlow", "scikit-learn", "Machine Learning",
    "Deep Learning", "NLP", "LLM", "Data Engineering", "ETL",
    # cloud / devops
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Ansible",
    "Jenkins", "CI/CD", "GitHub Actions", "GitLab", "Prometheus", "Grafana",
    "Datadog", "Linux", "Nginx", "Serverless", "Lambda",
    # practices / roles
    "Agile", "Scrum", "TDD", "Microservice", "Distributed Systems", "System Design",
    "Observability", "SRE", "DevOps", "Security", "OAuth", "SAML", "Accessibility",
    "Unit Testing", "Integration Testing", "Playwright", "Cypress", "Selenium",
    "Figma", "Product Management",
)


def resume_gap(posting_text: str, resume_text: str | None,
               extra_terms: list[str] | None = None, *, limit: int = 12) -> list[str]:
    """Terms present in the posting but absent from the résumé, posting-order.

    ``posting_text`` is matched as-is (scoring lowercases it already); ``resume_text``
    is lowercased here. Returns at most ``limit`` terms, ordered by first appearance in
    the posting so the most prominent asks lead. Empty when there's no résumé to compare
    against (nothing to call "missing").
    """
    if not resume_text or not resume_text.strip():
        return []
    resume = resume_text.lower()
    vocab: list[str] = list(SKILL_VOCAB)
    seen_lower = {t.lower() for t in vocab}
    for extra in extra_terms or []:
        low = extra.strip().lower()
        if low and low not in seen_lower:
            seen_lower.add(low)
            vocab.append(extra.strip())

    hits: list[tuple[int, str]] = []
    for term in vocab:
        if _contains_term(posting_text, term) and not _contains_term(resume, term):
            m = re.search(rf"\b{re.escape(term.lower())}\b", posting_text)
            hits.append((m.start() if m else 1 << 30, term))
    hits.sort(key=lambda h: h[0])
    return [term for _, term in hits[:limit]]

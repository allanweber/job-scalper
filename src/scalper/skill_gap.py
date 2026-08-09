"""Résumé gap: skills/keywords a posting emphasises that the résumé doesn't show.

Distinct from `scoring.missing_skills` (which is *profile* required-skills the posting
lacks). This looks the other way — terms present in the **posting** but absent from
the user's **résumé text** — so the detail screen can tell the user, concretely, what
this job asks for that their résumé doesn't yet mention.

Deterministic and LLM-free: a comprehensive gazetteer of tech skills/tools/keywords
(plus any extra terms the caller passes, e.g. the user's own profile skills) is matched
against the posting; anything found there but not in the résumé is a gap. Word-boundary
matching (shared with scoring) keeps short tokens honest. Bare single letters (``c``,
``r``) and other prose-colliding tokens are intentionally omitted — their false-positive
rate outweighs their value; the multi-char aliases (``C++``, ``C#``, ``R (language)``)
cover them where they matter.
"""

from __future__ import annotations

import re

from scalper.scoring import _contains_term

#: Comprehensive gazetteer of skills/tools/keywords worth flagging. Display casing is
#: preserved (the matcher is case-insensitive) so labels render nicely in the UI. Broad
#: by design so the gap genuinely reflects the posting rather than a tiny hand-list; the
#: caller can still union in the user's own profile terms for anything niche.
SKILL_VOCAB: tuple[str, ...] = (
    # --- languages ---
    "Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Swift", "Objective-C",
    "Go", "Golang", "Rust", "Ruby", "PHP", "C++", "C#", "Scala", "Elixir", "Erlang",
    "Clojure", "Haskell", "Dart", "Perl", "Lua", "Groovy", "F#", "OCaml", "Julia",
    "MATLAB", "Solidity", "Assembly", "COBOL", "Fortran", "VBA", "Bash", "Shell",
    "PowerShell", "SQL", "PL/SQL", "T-SQL", "GraphQL", "HTML", "CSS", "SASS", "SCSS",
    "LESS", "XML", "YAML", "JSON", "Markdown",
    # --- frontend ---
    "React", "React Native", "Vue", "Vue.js", "Angular", "AngularJS", "Svelte",
    "SvelteKit", "Next.js", "Nuxt", "Remix", "Gatsby", "Redux", "MobX", "RxJS",
    "jQuery", "Bootstrap", "Tailwind", "Material UI", "Chakra UI", "Storybook",
    "Webpack", "Vite", "Babel", "ESLint", "Prettier", "Three.js", "D3.js", "WebGL",
    "WebSockets", "WebAssembly", "PWA", "SPA", "SSR", "Responsive Design",
    # --- mobile ---
    "Flutter", "SwiftUI", "UIKit", "Jetpack Compose", "Android", "iOS", "Xamarin",
    "Ionic", "Cordova", "Expo", "Fastlane",
    # --- backend / frameworks ---
    "Node.js", "Express", "NestJS", "Deno", "Bun", "Django", "Flask", "FastAPI",
    "Tornado", "Celery", "Spring", "Spring Boot", "Micronaut", "Quarkus", "Rails",
    "Ruby on Rails", "Sinatra", "Laravel", "Symfony", "ASP.NET", ".NET", ".NET Core",
    "Phoenix", "Gin", "Fiber", "Actix", "gRPC", "REST", "REST API", "SOAP",
    "Microservices", "Message Queue", "RabbitMQ", "GraphQL API", "OpenAPI", "Swagger",
    # --- databases / data stores ---
    "PostgreSQL", "MySQL", "MariaDB", "SQLite", "SQL Server", "Oracle", "MongoDB",
    "Redis", "Memcached", "Cassandra", "DynamoDB", "Couchbase", "Neo4j", "CouchDB",
    "Elasticsearch", "OpenSearch", "Solr", "InfluxDB", "TimescaleDB", "Snowflake",
    "BigQuery", "Redshift", "Databricks", "ClickHouse", "Firebase", "Firestore",
    "Supabase", "Prisma", "SQLAlchemy", "Hibernate", "TypeORM",
    # --- data / ML / AI ---
    "Kafka", "Spark", "PySpark", "Hadoop", "Flink", "Airflow", "dbt", "Dagster",
    "Luigi", "Pandas", "NumPy", "SciPy", "Polars", "Dask", "PyTorch", "TensorFlow",
    "Keras", "scikit-learn", "XGBoost", "Hugging Face", "LangChain", "OpenAI",
    "Machine Learning", "Deep Learning", "Reinforcement Learning", "NLP",
    "Computer Vision", "LLM", "LLMs", "Generative AI", "MLOps", "Data Engineering",
    "Data Science", "Data Analysis", "ETL", "ELT", "Data Warehouse", "Data Pipeline",
    "Data Modeling", "Tableau", "Power BI", "Looker", "Metabase", "Superset",
    "Jupyter", "R (language)",
    # --- cloud / infra / devops ---
    "AWS", "GCP", "Google Cloud", "Azure", "DigitalOcean", "Heroku", "Vercel",
    "Netlify", "Cloudflare", "EC2", "S3", "Lambda", "ECS", "EKS", "RDS", "CloudFront",
    "Docker", "Kubernetes", "Helm", "OpenShift", "Terraform", "Pulumi", "Ansible",
    "Chef", "Puppet", "Vagrant", "Packer", "Jenkins", "CircleCI", "Travis CI",
    "GitHub Actions", "GitLab CI", "ArgoCD", "Spinnaker", "CI/CD", "Prometheus",
    "Grafana", "Datadog", "New Relic", "Splunk", "ELK", "Sentry", "PagerDuty",
    "Nginx", "Apache", "HAProxy", "Envoy", "Istio", "Consul", "Vault", "Serverless",
    "Linux", "Unix", "Bash Scripting", "Networking", "TCP/IP", "DNS", "Load Balancing",
    # --- version control / tooling ---
    "Git", "GitHub", "GitLab", "Bitbucket", "SVN", "Jira", "Confluence", "Notion",
    "Figma", "Sketch", "Adobe XD", "Postman", "Insomnia",
    # --- testing / quality ---
    "Unit Testing", "Integration Testing", "End-to-End Testing", "TDD", "BDD",
    "Playwright", "Cypress", "Selenium", "Jest", "Vitest", "Mocha", "Chai",
    "Pytest", "JUnit", "TestNG", "RSpec", "Cucumber", "Appium", "Load Testing",
    # --- architecture / practices ---
    "Microservice", "Monorepo", "Event-Driven", "Domain-Driven Design",
    "Distributed Systems", "System Design", "Design Patterns", "Clean Architecture",
    "SOLID", "Scalability", "High Availability", "Observability", "SRE", "DevOps",
    "DevSecOps", "Platform Engineering", "API Design", "OAuth", "OpenID", "SAML",
    "JWT", "SSO", "Encryption", "Security", "Penetration Testing", "OWASP",
    "Accessibility", "WCAG", "SEO", "Performance Optimization", "Caching",
    "Concurrency", "Multithreading", "Functional Programming",
    "Object-Oriented Programming",
    # --- methodologies / soft / role ---
    "Agile", "Scrum", "Kanban", "Waterfall", "SAFe", "Product Management",
    "Project Management", "Stakeholder Management", "Technical Leadership",
    "Mentoring", "Code Review", "Pair Programming", "Cross-Functional",
    "Communication", "Problem Solving",
    # --- domains ---
    "Fintech", "Healthcare", "E-commerce", "SaaS", "B2B", "B2C", "Blockchain",
    "Web3", "Cybersecurity", "IoT", "AR/VR", "Gaming", "Ad Tech", "MarTech",
    "Embedded Systems", "Robotics",
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

    # Suppress a term when a longer matched term already contains it as whole
    # words (e.g. drop "GitHub" when "GitHub Actions" matched) so the chips don't
    # show a general term next to the specific one that subsumes it.
    matched = [t for _, t in hits]
    kept = [
        (pos, term) for pos, term in hits
        if not any(other != term and len(other) > len(term)
                   and _contains_term(other.lower(), term.lower())
                   for other in matched)
    ]
    return [term for _, term in kept[:limit]]

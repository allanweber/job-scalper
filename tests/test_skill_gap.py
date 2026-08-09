"""Unit tests for the résumé-gap helper (`scalper.skill_gap`)."""

from scalper.skill_gap import resume_gap


def test_gap_is_posting_minus_resume():
    posting = "We use Python, Kubernetes, Docker and Terraform on AWS."
    resume = "Backend engineer with Python and Docker experience."
    gap = resume_gap(posting.lower(), resume)
    # In the posting, not in the résumé.
    assert "Kubernetes" in gap and "Terraform" in gap and "AWS" in gap
    # In both -> not a gap.
    assert "Python" not in gap and "Docker" not in gap


def test_no_resume_means_no_gap():
    # Nothing to call "missing" without a résumé to compare against.
    assert resume_gap("python kubernetes aws", None) == []
    assert resume_gap("python kubernetes aws", "   ") == []


def test_extra_terms_widen_the_vocabulary():
    # A term outside the curated vocab is still caught when passed as extra.
    posting = "Experience with contentful and headless cms required."
    gap = resume_gap(posting, "unrelated résumé text", extra_terms=["Contentful"])
    assert "Contentful" in gap


def test_word_boundary_avoids_substring_false_positives():
    # 'Go' must not match inside 'category'; 'R' must not match inside 'refactor'.
    posting = "Strong in category management and refactoring legacy code."
    assert resume_gap(posting, "unrelated") == []


def test_gazetteer_catches_varied_terms():
    # A broad posting: many distinct tools, none in the résumé -> all flagged.
    posting = ("Build data pipelines with Kafka, Snowflake and Airflow; deploy on "
               "AWS with Terraform and Ansible.").lower()
    gap = resume_gap(posting, "Generalist engineer.", limit=20)
    for term in ["Kafka", "Snowflake", "Airflow", "AWS", "Terraform", "Ansible"]:
        assert term in gap, term


def test_bare_single_letters_are_not_flagged():
    # Prose-colliding single letters are deliberately absent from the gazetteer.
    posting = "We value clarity in c and r style thinking and product strategy."
    assert resume_gap(posting, "unrelated résumé") == []


def test_result_is_capped_and_posting_ordered():
    posting = ("kubernetes first, then terraform, then aws, then docker, "
               "then react, then graphql")
    gap = resume_gap(posting, "python only", limit=3)
    assert len(gap) == 3
    assert gap[0] == "Kubernetes"  # first mentioned leads

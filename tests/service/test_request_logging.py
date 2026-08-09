from __future__ import annotations

import logging


def test_request_logging_emits_structured_line(client, auth_headers, caplog):
    """A normal request emits one scalper.request line with core fields, and the
    request id is echoed back to the caller."""
    # A successful request logs at DEBUG (kept quiet at the default INFO level).
    with caplog.at_level(logging.DEBUG, logger="scalper.request"):
        r = client.get("/me", headers=auth_headers)
    assert r.status_code == 200

    rid = r.headers.get("X-Request-ID")
    assert rid, "response should carry the request id header"

    records = [rec for rec in caplog.records if rec.name == "scalper.request"]
    assert records, "expected a request log line"
    rec = records[-1]
    assert rec.method == "GET"
    assert rec.route == "/me"          # route template, not just the raw path
    assert rec.status == 200
    assert rec.request_id == rid       # same id in the log and the response header
    assert rec.user_id                 # attributed to the authenticated user
    assert isinstance(rec.latency_ms, float)

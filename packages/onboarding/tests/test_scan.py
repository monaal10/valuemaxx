"""Tests for the AST codebase scanner (SCAN).

The scanner is read-only: it parses source with :mod:`ast` and never writes. Every
captured string is redacted, so a planted secret never appears in the result. It
classifies sites (run boundary, status setter, mark_*, ORM write, external write,
webhook handler), records durable entity ids, and marks which external systems echo
injected metadata back.
"""

from __future__ import annotations

from pathlib import Path

from valuemaxx.onboarding.scan import ECHOING_SYSTEMS, scan_codebase

_APP_SOURCE = '''
"""A toy support app to scan."""
import stripe
import salesforce


def run_agent(ticket_id, customer_id):
    """The agent run boundary."""
    client = Anthropic(api_key="sk-ant-api03-PLANTEDSECRETvalue0123456789abcdef")
    result = client.complete(ticket_id)
    return result


def mark_resolved(ticket):
    ticket.status = "resolved"
    db.session.commit()


def close_ticket(ticket):
    ticket.save()


def charge_customer(customer_id, amount):
    stripe.PaymentIntent.create(amount=amount, metadata={"customer": customer_id})


def push_to_salesforce(lead):
    salesforce.Lead.create(name=lead.name)


def handle_webhook(request):
    """A webhook handler."""
    payload = request.json
    return payload
'''

_PLANTED_SECRET = "sk-ant-api03-PLANTEDSECRETvalue0123456789abcdef"


def _write_app(tmp_path: Path) -> Path:
    src = tmp_path / "app.py"
    src.write_text(_APP_SOURCE)
    return tmp_path


def test_scan_finds_run_boundary(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    symbols = {s.symbol for s in result.run_boundaries}
    assert "run_agent" in symbols


def test_scan_finds_status_setter(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    setters = [s for s in result.outcome_sites if s.kind == "status_setter"]
    assert any(s.symbol == "mark_resolved" for s in setters)


def test_scan_finds_orm_write(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    assert any(s.kind == "orm_write" for s in result.outcome_sites)


def test_scan_finds_webhook_handler(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    assert any(s.kind == "webhook_handler" for s in result.outcome_sites)


def test_scan_finds_external_write_with_echo_true_for_stripe(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    stripe_sites = [
        s for s in result.outcome_sites if s.kind == "external_write" and s.system == "stripe"
    ]
    assert stripe_sites, "no stripe external write found"
    assert all(s.echoes_metadata is True for s in stripe_sites)


def test_scan_marks_salesforce_as_non_echoing(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    sf_sites = [
        s for s in result.outcome_sites if s.kind == "external_write" and s.system == "salesforce"
    ]
    assert sf_sites, "no salesforce external write found"
    assert all(s.echoes_metadata is False for s in sf_sites)


def test_scan_captures_entity_ids(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    assert "ticket_id" in result.entity_ids
    assert "customer_id" in result.entity_ids


def test_scan_never_emits_planted_secret(tmp_path: Path) -> None:
    result = scan_codebase(_write_app(tmp_path))
    dump = result.model_dump_json()
    assert _PLANTED_SECRET not in dump
    # deep-dump every captured string field
    blob = repr(result)
    assert _PLANTED_SECRET not in blob


def test_scan_is_read_only(tmp_path: Path) -> None:
    root = _write_app(tmp_path)
    src = root / "app.py"
    before = src.stat().st_mtime_ns
    before_text = src.read_text()
    scan_codebase(root)
    assert src.stat().st_mtime_ns == before
    assert src.read_text() == before_text


def test_echoing_systems_allowlist_known_members() -> None:
    assert "stripe" in ECHOING_SYSTEMS
    assert "hubspot" in ECHOING_SYSTEMS
    assert "zendesk" in ECHOING_SYSTEMS
    assert "salesforce" not in ECHOING_SYSTEMS


def test_scan_skips_unparseable_files_with_warning(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("def mark_done(t):\n    t.status = 'done'\n")
    (tmp_path / "broken.py").write_text("def oops(:\n")  # syntax error
    result = scan_codebase(tmp_path)
    assert any(s.symbol == "mark_done" for s in result.outcome_sites)
    assert any("broken.py" in w for w in result.warnings)

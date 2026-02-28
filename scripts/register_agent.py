#!/usr/bin/env python3
"""
register_agent.py — CLI script to register agents/tools via the Agent Marketplace API
and display the AI governance review results.

Usage:
    python scripts/register_agent.py                  # registers all demo payloads
    python scripts/register_agent.py --agent-only     # agents only
    python scripts/register_agent.py --tool-only      # tools only
    python scripts/register_agent.py --url http://localhost:8500

The script registers purposefully flawed payloads so you can see the AI governance
agent catch real issues (missing masking, unverified PCI claims, over-broad access, etc.)

Requirements:
    pip install httpx python-dotenv
    Marketplace must be running: python app.py  (http://localhost:8500)
"""

import sys
import json
import argparse
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Try to load .env from project root (parent of scripts/)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[env] Loaded {env_path}")
    else:
        load_dotenv()  # search up from cwd
except ImportError:
    pass  # python-dotenv optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Demo payloads — designed to exercise the governance agent
# ---------------------------------------------------------------------------

# Payload 1: Card authorization agent — handles raw PANs, claims PCI compliance,
# but source code shows it logs raw card numbers. Should trigger multiple flags.
CARD_AUTH_AGENT = {
    "agent_id": "card_authorization_agent",
    "agent_type": "payments",
    "endpoint": "http://localhost:8200/receive",
    "capabilities": [
        "authorize_card",
        "void_transaction",
        "capture_payment",
        "get_raw_pan",          # suspicious — exposes raw PAN
    ],
    "owner_team": "Core Payments",
    "compliance": ["PCI-Scoped", "Production-Ready"],  # self-reported — will be validated
    "docs_url": "https://wiki.internal/agents/card-auth",
    "source_repo": "https://github.com/payments-platform/card-auth-agent",
    "description": (
        "Handles card authorization requests end-to-end. Accepts raw PAN, CVV, and "
        "expiry directly from callers. Logs full card numbers to the transaction audit "
        "log for debugging purposes. Returns raw PAN in API response for downstream "
        "processing. Auth is optional — set auth_required=false for internal services. "
        "Supports get_raw_pan capability for reconciliation use cases."
    ),
    "auth_required": False,     # auth off — governance agent should flag this
    "auth_type": "",
}

# Payload 2: Customer data analytics agent — handles PII but claims 'PII-Safe',
# shares data with third-party analytics, no consent mentioned.
CUSTOMER_ANALYTICS_AGENT = {
    "agent_id": "customer_data_analytics_agent",
    "agent_type": "analytics",
    "endpoint": "http://localhost:8201/receive",
    "capabilities": [
        "profile_customer",
        "segment_by_spend",
        "export_to_partner",    # red flag: sends PII to partner
        "track_device",         # collects device IDs linked to individuals
    ],
    "owner_team": "Growth Analytics",
    "compliance": ["PII-Safe", "Production-Ready"],  # claimed but doubtful
    "docs_url": "",
    "source_repo": "",
    "description": (
        "Customer behavioral analytics agent. Profiles customers using full name, email, "
        "phone number, home address, DOB, and device fingerprint. Segments users by spend "
        "patterns. The export_to_partner capability sends enriched customer profiles (with "
        "PII) to our third-party marketing analytics vendor. No consent workflow is "
        "implemented — assumes opt-in at account creation."
    ),
    "auth_required": True,
    "auth_type": "bearer",
}

# Payload 3: A well-behaved, clearly-scoped settlement tool — should get a cleaner review
SETTLEMENT_REPORT_AGENT = {
    "agent_id": "settlement_report_agent",
    "agent_type": "reporting",
    "endpoint": "http://localhost:8202/receive",
    "capabilities": [
        "generate_daily_settlement",
        "reconcile_batch",
        "export_csv",
    ],
    "owner_team": "Finance & Settlement",
    "compliance": ["Internal-Only"],
    "docs_url": "https://wiki.internal/agents/settlement",
    "source_repo": "https://github.com/payments-platform/settlement-report-agent",
    "description": (
        "Generates daily settlement reports and batch reconciliation files. Operates on "
        "aggregated transaction totals — no raw card data, no PAN, no CVV. Produces "
        "CSV exports of net settlement amounts by merchant and currency. "
        "Restricted to the Finance team via role-based access control."
    ),
    "auth_required": True,
    "auth_type": "bearer",
}

AGENT_PAYLOADS = [
    ("Card Authorization Agent (expect issues)", CARD_AUTH_AGENT),
    ("Customer Analytics Agent (expect issues)", CUSTOMER_ANALYTICS_AGENT),
    ("Settlement Report Agent (should be cleaner)", SETTLEMENT_REPORT_AGENT),
]

# ---------------------------------------------------------------------------
# Tool payloads
# ---------------------------------------------------------------------------

# Tool 1: Raw PAN lookup — very high-risk tool
PAN_LOOKUP_TOOL = {
    "tool_id": "raw_pan_lookup",
    "description": (
        "Looks up the raw PAN (Primary Account Number) for a given token or transaction ID. "
        "Returns the full 16-digit card number in plaintext. Used by the reconciliation "
        "team for chargeback evidence gathering. No masking applied. Response includes "
        "PAN, expiry, cardholder name, and billing address."
    ),
    "owner_team": "Disputes & Chargebacks",
    "compliance": ["PCI-Scoped"],
    "docs_url": "",
    "source_repo": "https://github.com/payments-platform/pan-lookup-tool",
    "source_agent": "",
    "endpoint": "http://localhost:8080/tools/raw_pan_lookup",
    "auth_required": True,
    "auth_type": "bearer",
    "example_request": {
        "token": "tok_4111xxxx1111",
        "reason": "chargeback_evidence"
    },
}

# Tool 2: Safe currency conversion — should get a clean review
FX_RATE_TOOL = {
    "tool_id": "fx_rate_lookup",
    "description": (
        "Returns the current mid-market exchange rate between two ISO-4217 currency codes. "
        "No PII or card data involved. Rates are sourced from ECB and updated hourly. "
        "No authentication required — public rate data."
    ),
    "owner_team": "FX & Treasury",
    "compliance": [],
    "docs_url": "",
    "source_repo": "https://github.com/payments-platform/fx-rate-tool",
    "source_agent": "",
    "endpoint": "http://localhost:8080/tools/fx_rate_lookup",
    "auth_required": False,
    "auth_type": "",
    "example_request": {
        "from_currency": "USD",
        "to_currency": "EUR"
    },
}

TOOL_PAYLOADS = [
    ("Raw PAN Lookup Tool (expect HIGH risk flags)", PAN_LOOKUP_TOOL),
    ("FX Rate Lookup Tool (should be clean)", FX_RATE_TOOL),
]


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
DIM    = "\033[2m"


def _color(text, code):
    return f"{code}{text}{RESET}"


def _header(text):
    bar = "=" * 70
    print(f"\n{_color(bar, CYAN)}")
    print(_color(f"  {text}", BOLD))
    print(_color(bar, CYAN))


def _section(label, value):
    print(f"\n  {_color(label, BOLD)}")
    if isinstance(value, list):
        if not value:
            print(f"    {_color('(none)', DIM)}")
        for v in value:
            print(f"    • {v}")
    else:
        wrapped = textwrap.fill(str(value), width=65, subsequent_indent="    ")
        print(f"    {wrapped}")


def _badge(label, value):
    color = {
        "confirmed": RED, "possible": YELLOW, "none": GREEN,
        "high": RED, "medium": YELLOW, "low": GREEN,
        True: RED, False: GREEN,
    }.get(value, RESET)
    return f"{_color(label, BOLD)}: {_color(str(value).upper(), color)}"


def print_review(label, response_json):
    """Pretty-print the full registration + governance review response."""
    status = response_json.get("status", "?")
    item_id = response_json.get("agent_id") or response_json.get("tool_id", "?")
    review = response_json.get("ai_review")

    status_color = GREEN if status in ("registered", "updated") else RED
    status_note = " (already existed — enrichment updated)" if status == "updated" else ""
    print(f"\n  {_color('Registration status', BOLD)}: {_color(status, status_color)}{status_note}")
    print(f"  {_color('ID', BOLD)}: {item_id}")

    if not review:
        print(f"\n  {_color('⚠ No AI review returned', YELLOW)}")
        print(f"  {_color('(Is GOOGLE_CLOUD_PROJECT / GCP_PROJECT_ID set? Is the marketplace running?)', DIM)}")
        return

    # Summary
    _section("Summary", review.get("summary", ""))

    # Scope badges
    print(f"\n  {_badge('PCI Scope', review.get('pci_scope', '?'))}   "
          f"{_badge('PII Scope', review.get('pii_scope', '?'))}   "
          f"{_badge('Duplicate Risk', review.get('duplicate_risk', '?'))}")
    print(f"\n  {_badge('Requires Human Review', review.get('requires_human_review', '?'))}   "
          f"{_color('Confidence', BOLD)}: {review.get('confidence', '?').upper()}")

    # Auth assessment
    _section("Auth Assessment", review.get("auth_assessment", ""))

    # Risk flags
    flags = review.get("risk_flags", [])
    if flags:
        print(f"\n  {_color('Risk Flags', BOLD)} {_color('(🔴 issues found)', RED)}")
        for f in flags:
            print(f"    {_color('🔴', RED)} {f}")
    else:
        print(f"\n  {_color('✅ No risk flags', GREEN)}")

    # Unverified claims
    unverified = review.get("unverified_claims", [])
    if unverified:
        print(f"\n  {_color('Unverified Compliance Claims', BOLD)} {_color('(🟡 claimed but not evidenced)', YELLOW)}")
        for u in unverified:
            print(f"    {_color('🟡', YELLOW)} {u}")

    # Detected compliance
    detected = review.get("detected_compliance", [])
    if detected:
        print(f"\n  {_color('Detected Compliance (AI-verified)', BOLD)} {_color('(🟢 supported by evidence)', GREEN)}")
        for d in detected:
            print(f"    {_color('🟢', GREEN)} {d}")

    # Recommendations
    recs = review.get("recommendations", [])
    if recs:
        _section("Recommendations", recs)


# ---------------------------------------------------------------------------
# Registration calls
# ---------------------------------------------------------------------------

def register_agent(base_url: str, label: str, payload: dict) -> dict | None:
    _header(f"AGENT: {label}")
    print(f"\n  {_color('Payload summary', DIM)}")
    print(f"    agent_id   : {payload['agent_id']}")
    print(f"    owner_team : {payload['owner_team']}")
    print(f"    capabilities: {', '.join(payload.get('capabilities', []))}")
    print(f"    compliance : {payload.get('compliance', [])}")
    print(f"    auth       : {payload.get('auth_required')} / {payload.get('auth_type', 'none')}")
    print(f"\n  {_color('Calling POST /api/register/agent ...', DIM)}")
    print(f"  {_color('(AI governance review may take 10-30s)', DIM)}")

    try:
        resp = httpx.post(
            f"{base_url}/api/register/agent",
            json=payload,
            timeout=90.0,
        )
        resp.raise_for_status()
        data = resp.json()
        print_review(label, data)
        return data
    except httpx.ConnectError:
        print(f"\n  {_color('ERROR: Cannot connect to marketplace at ' + base_url, RED)}")
        print(f"  {_color('Start it with: python app.py', DIM)}")
        return None
    except httpx.HTTPStatusError as e:
        print(f"\n  {_color(f'HTTP {e.response.status_code}: {e.response.text}', RED)}")
        return None
    except Exception as e:
        print(f"\n  {_color(f'Error: {e}', RED)}")
        return None


def register_tool(base_url: str, label: str, payload: dict) -> dict | None:
    _header(f"TOOL: {label}")
    print(f"\n  {_color('Payload summary', DIM)}")
    print(f"    tool_id    : {payload['tool_id']}")
    print(f"    owner_team : {payload['owner_team']}")
    print(f"    compliance : {payload.get('compliance', [])}")
    print(f"    auth       : {payload.get('auth_required')} / {payload.get('auth_type', 'none')}")
    print(f"\n  {_color('Calling POST /api/register/tool ...', DIM)}")
    print(f"  {_color('(AI governance review may take 10-30s)', DIM)}")

    try:
        resp = httpx.post(
            f"{base_url}/api/register/tool",
            json=payload,
            timeout=90.0,
        )
        resp.raise_for_status()
        data = resp.json()
        print_review(label, data)
        return data
    except httpx.ConnectError:
        print(f"\n  {_color('ERROR: Cannot connect to marketplace at ' + base_url, RED)}")
        print(f"  {_color('Start it with: python app.py', DIM)}")
        return None
    except httpx.HTTPStatusError as e:
        print(f"\n  {_color(f'HTTP {e.response.status_code}: {e.response.text}', RED)}")
        return None
    except Exception as e:
        print(f"\n  {_color(f'Error: {e}', RED)}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def check_governance(base_url: str) -> bool:
    """Call /api/governance/status and print a clear message. Returns True if ready."""
    try:
        resp = httpx.get(f"{base_url}/api/governance/status", timeout=5.0)
        data = resp.json()
    except httpx.ConnectError:
        print(f"\n  {_color('ERROR: Marketplace not reachable at ' + base_url, RED)}")
        print(f"  {_color('Start it with: cd c:/work/projects/agent-marketplace && python app.py', DIM)}")
        return False
    except Exception as e:
        print(f"\n  {_color(f'Could not check governance status: {e}', YELLOW)}")
        return True  # proceed anyway

    if data.get("ready"):
        print(f"  {_color('✅ Governance AI', GREEN)}: {data.get('model')}  "
              f"project={data.get('project')}  region={data.get('region')}")
        return True
    else:
        print(f"\n  {_color('⚠ Governance AI is NOT configured', YELLOW)}")
        print(f"  {_color('project', DIM)}: {data.get('project')}")
        print(f"  {_color('region', DIM)} : {data.get('region')}")
        print(f"\n  {_color('Fix:', BOLD)} add these to {_color('agent-marketplace/.env', CYAN)}:")
        print(f"    GCP_PROJECT_ID=your-gcp-project-id")
        print(f"    GCP_LOCATION=us-central1")
        print(f"\n  Then restart the marketplace and re-run this script.")
        print(f"\n  {_color('Also ensure ADC is set up:', DIM)}")
        print(f"    gcloud auth application-default login")
        print(f"\n  Registrations will proceed but WITHOUT AI governance review.\n")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Register agents/tools via the Agent Marketplace API and display AI governance review."
    )
    parser.add_argument("--url", default="http://localhost:8500", help="Marketplace base URL (default: http://localhost:8500)")
    parser.add_argument("--agent-only", action="store_true", help="Register agents only")
    parser.add_argument("--tool-only",  action="store_true", help="Register tools only")
    parser.add_argument("--json",       action="store_true", help="Print raw JSON responses instead of formatted output")
    args = parser.parse_args()

    print(f"\n{_color('Agent Marketplace — Registration & Governance Review Script', BOLD)}")
    print(f"{_color('=' * 70, DIM)}")
    print(f"  Target : {args.url}")
    print(f"  Payloads: {len(AGENT_PAYLOADS)} agents, {len(TOOL_PAYLOADS)} tools")

    # Pre-flight: check governance agent before starting registrations
    print(f"\n{_color('Pre-flight check', BOLD)}")
    check_governance(args.url)

    run_agents = not args.tool_only
    run_tools  = not args.agent_only

    results = []

    if run_agents:
        print(f"\n{_color('━' * 70, BOLD)}")
        print(_color("  AGENT REGISTRATIONS", BOLD))
        for label, payload in AGENT_PAYLOADS:
            result = register_agent(args.url, label, payload)
            if args.json and result:
                print(f"\n  {_color('Raw JSON:', DIM)}")
                print(json.dumps(result, indent=2))
            results.append(result)

    if run_tools:
        print(f"\n{_color('━' * 70, BOLD)}")
        print(_color("  TOOL REGISTRATIONS", BOLD))
        for label, payload in TOOL_PAYLOADS:
            result = register_tool(args.url, label, payload)
            if args.json and result:
                print(f"\n  {_color('Raw JSON:', DIM)}")
                print(json.dumps(result, indent=2))
            results.append(result)

    # Summary
    print(f"\n{_color('=' * 70, CYAN)}")
    print(_color("  SUMMARY", BOLD))
    print(_color("=" * 70, CYAN))

    had_review = [r for r in results if r and r.get("ai_review")]
    needs_human = [
        r for r in had_review
        if r["ai_review"].get("requires_human_review") is True
    ]
    high_pci = [
        r for r in had_review
        if r["ai_review"].get("pci_scope") == "confirmed"
    ]

    print(f"\n  Registered   : {len([r for r in results if r])} / {len(results)}")
    print(f"  AI Reviews   : {len(had_review)}")
    print(f"  Need Human ↗ : {_color(str(len(needs_human)), RED if needs_human else GREEN)}")
    print(f"  PCI Confirmed: {_color(str(len(high_pci)), RED if high_pci else GREEN)}")

    if needs_human:
        print(f"\n  {_color('Items flagged for human review:', YELLOW)}")
        for r in needs_human:
            iid = r.get("agent_id") or r.get("tool_id", "?")
            rev = r["ai_review"]
            print(f"    • {iid}  [{rev.get('pci_scope','?')} PCI / {rev.get('pii_scope','?')} PII]")

    print(f"\n  View in marketplace UI: {args.url}\n")


if __name__ == "__main__":
    main()

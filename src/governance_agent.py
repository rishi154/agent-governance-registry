"""
GovernanceAgent: AI-powered governance review of marketplace registrations.

Uses Claude via Google Vertex AI (native vertexai SDK — same library as rsagenticai).
No Anthropic API key needed — uses Application Default Credentials.

Requires:
  - GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT env var
  - GCP_LOCATION or VERTEX_REGION env var  (default: us-east5)
  - VERTEX_CLAUDE_MODEL env var            (default: claude-opus-4-5@20251101)
  - gcloud auth application-default login  (for ADC credentials)
"""

import os
import json
import logging
import re
import httpx

logger = logging.getLogger(__name__)

# Support both naming conventions:
# - GCP_PROJECT_ID / GCP_LOCATION  (user's .env convention from rsagenticai)
# - GOOGLE_CLOUD_PROJECT / VERTEX_REGION  (standard Google SDK convention)
GOOGLE_CLOUD_PROJECT = (
    os.getenv("GCP_PROJECT_ID")
    or os.getenv("GOOGLE_CLOUD_PROJECT", "")
)
VERTEX_REGION = (
    os.getenv("GCP_LOCATION")
    or os.getenv("VERTEX_REGION", "us-east5")
)
VERTEX_CLAUDE_MODEL  = os.getenv("VERTEX_CLAUDE_MODEL", "claude-opus-4-5@20251101")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a Governance Review Agent for a payment processor's AI Agent Marketplace.
Your role is to INDEPENDENTLY assess agent/tool registrations — not rubber-stamp them.

## Your Analysis Must Cover:

### 1. PCI-DSS Scope Detection
Look for handling of: card numbers (PANs), CVV/CVC codes, cardholder data, track data,
authorization codes, raw transaction data tied to identifiable cards.
- pci_scope = "confirmed": clear evidence card data is processed/stored/transmitted
- pci_scope = "possible": description suggests it might, but unclear
- pci_scope = "none": clearly no card data involved

### 2. PII Scope Detection
Look for: SSNs, full names, addresses, email, phone numbers, DOB, government IDs,
biometrics, device IDs, IP addresses linked to individuals.
- pii_scope = "confirmed" / "possible" / "none"

### 3. Compliance Claim Validation — Be SKEPTICAL
Self-reported compliance badges need evidence:
- "PCI-Scoped" without masking/tokenization controls = unverified claim
- "Production-Ready" without evidence of testing = unverified claim
- auth_required=true but no auth code shown = unverified claim
Put unverified claims in the unverified_claims array.

### 4. Risk Flags — Be Specific
Flag concrete issues such as:
- Handles card/PAN data but no masking or tokenization mentioned
- Returns raw sensitive data in API response
- Auth claimed but not evidenced in code
- Capabilities broader than what the team should access
- Sensitive data in logs or error messages

### 5. Duplicate Detection
Compare against existing catalog:
- "none": clearly different capabilities
- "low": some overlap, different purpose
- "medium": partial overlap, may create redundancy
- "high": near-identical to an existing item

## Output Format
Return ONLY a valid JSON object — no markdown fences, no explanation text:
{
  "summary": "<2-3 sentence plain-English assessment>",
  "detected_compliance": ["<tags AI independently detected>"],
  "unverified_claims": ["<tags claimed but not evidenced>"],
  "risk_flags": ["<specific concrete risks found>"],
  "recommendations": ["<actionable fixes>"],
  "requires_human_review": true or false,
  "confidence": "low" or "medium" or "high",
  "pci_scope": "none" or "possible" or "confirmed",
  "pii_scope": "none" or "possible" or "confirmed",
  "auth_assessment": "<one sentence on auth enforcement>",
  "duplicate_risk": "none" or "low" or "medium" or "high"
}

Be direct. Name exact fields or capabilities that raise concerns.
Do not fabricate evidence for or against compliance."""


class GovernanceAgent:
    """Reviews agent/tool registrations using Claude on Vertex AI (native SDK)."""

    def __init__(self):
        if not GOOGLE_CLOUD_PROJECT:
            logger.warning(
                "GOOGLE_CLOUD_PROJECT not set — AI governance review unavailable. "
                "Set it or run: gcloud auth application-default login"
            )
            self.model = None
            return

        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, GenerationConfig

            vertexai.init(project=GOOGLE_CLOUD_PROJECT, location=VERTEX_REGION)

            self.model = GenerativeModel(
                VERTEX_CLAUDE_MODEL,
                system_instruction=SYSTEM_PROMPT,
            )
            self.GenerationConfig = GenerationConfig
            logger.info(
                f"GovernanceAgent ready — model: {VERTEX_CLAUDE_MODEL}, region: {VERTEX_REGION}"
            )
        except ImportError:
            logger.warning(
                "vertexai package not installed — run: pip install google-cloud-aiplatform"
            )
            self.model = None
        except Exception as e:
            logger.warning(f"GovernanceAgent init failed: {e}")
            self.model = None

    async def review(
        self,
        item_id: str,
        item_type: str,
        payload: dict,
        existing_catalog: list[dict],
        source_code: str | None = None,
    ) -> dict | None:
        """
        Run AI governance review on a registration.
        Returns a review dict, or None if Vertex AI is unavailable.
        """
        if self.model is None:
            return None

        catalog_lines = [
            f"- {item['id']} ({item['item_type']}): {item.get('description', '')} "
            f"| compliance: {item.get('compliance', [])}"
            for item in existing_catalog[:20]
        ]
        catalog_summary = "\n".join(catalog_lines) or "Empty catalog"

        code_section = ""
        if source_code:
            # Truncate to keep prompt size reasonable. Source code is untrusted input.
            safe_code = source_code[:4000]
            code_section = f"\n\n## Source Code (fetched from source_repo)\n```\n{safe_code}\n```"

        user_message = f"""Review this {item_type} registration for our payment processor's Agent Marketplace.

## Registration Details
- **ID**: {item_id}
- **Type**: {item_type}
- **Description**: {payload.get('description', 'Not provided')}
- **Capabilities**: {payload.get('capabilities', payload.get('tool_id', 'Not specified'))}
- **Owner Team**: {payload.get('owner_team', 'Unknown')}
- **Claimed Compliance**: {payload.get('compliance', [])}
- **Auth Required**: {payload.get('auth_required', False)}
- **Auth Type**: {payload.get('auth_type', 'None')}
- **Source Repo**: {payload.get('source_repo', 'Not provided')}
- **Endpoint**: {payload.get('endpoint', 'Not provided')}
{code_section}

## Existing Catalog
{catalog_summary}

Return ONLY a JSON object as described in your instructions."""

        try:
            response = await self.model.generate_content_async(
                user_message,
                generation_config=self.GenerationConfig(
                    max_output_tokens=2000,
                    temperature=0.1,
                ),
            )
            text = response.text.strip()
            # Strip markdown code fences if Claude wrapped the JSON
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)

        except Exception as e:
            logger.error(f"Governance review failed for {item_id}: {e}")
            return None

    async def fetch_source_code(self, source_repo: str) -> str | None:
        """Try to fetch README from a GitHub repo URL for code analysis."""
        if not source_repo or "github.com" not in source_repo:
            return None
        try:
            parts = source_repo.rstrip("/").split("github.com/")
            if len(parts) < 2:
                return None
            raw_url = f"https://raw.githubusercontent.com/{parts[1]}/main/README.md"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(raw_url)
                if resp.status_code == 200:
                    return resp.text
        except Exception as e:
            logger.debug(f"Could not fetch source from {source_repo}: {e}")
        return None


governance_agent = GovernanceAgent()

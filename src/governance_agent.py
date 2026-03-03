"""
GovernanceAgent: Comprehensive AI-powered governance review.

Enhanced with 15 critical AI governance checks:
1. PCI-DSS Scope Detection
2. PII Scope Detection
3. Compliance Claim Validation
4. Risk Flags
5. Duplicate Detection
6. LLM/Model Usage Detection (NEW)
7. Data Retention & Privacy (NEW)
8. Rate Limiting & DoS Protection (NEW)
9. Model Output Validation (NEW)
10. Agent Chaining & Loops (NEW)
11. Cost & Token Tracking (NEW)
12. Authentication & Authorization (NEW)
13. Dependency Vulnerabilities (NEW)
14. Observability & Monitoring (NEW)
15. Input Validation & Sanitization (NEW)
"""

import os
import json
import logging
import re
import httpx

logger = logging.getLogger(__name__)

GOOGLE_CLOUD_PROJECT = (
    os.getenv("GCP_PROJECT_ID")
    or os.getenv("GOOGLE_CLOUD_PROJECT", "")
)
VERTEX_REGION = (
    os.getenv("GCP_LOCATION")
    or os.getenv("VERTEX_REGION", "us-east5")
)
VERTEX_CLAUDE_MODEL = os.getenv("VERTEX_CLAUDE_MODEL", "claude-opus-4-5@20251101")

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

### 4. Risk Flags — Be Specific
Flag concrete issues such as:
- Handles card/PAN data but no masking or tokenization mentioned
- Returns raw sensitive data in API response
- Auth claimed but not evidenced in code
- Sensitive data in logs or error messages

### 5. Duplicate Detection
Compare against existing catalog:
- "none": clearly different capabilities
- "low": some overlap, different purpose
- "medium": partial overlap, may create redundancy
- "high": near-identical to an existing item

### 6. LLM/Model Usage Detection (CRITICAL)
Scan source code for:
- **LLM Provider Imports**: openai, anthropic, google.generativeai, vertexai, boto3 (bedrock)
- **Model Identifiers**: "gpt-4", "gpt-3.5", "claude-3", "claude-opus", "gemini", "bedrock"
- **API Key Handling**: 
  - GOOD: os.getenv("OPENAI_API_KEY"), AWS IAM, secrets manager
  - BAD: api_key = "sk-...", hardcoded keys
- **Prompt Injection Risks**:
  - HIGH: f"User query: {user_input}" without sanitization
  - HIGH: prompt = request.body (direct user input)
  - MEDIUM: Some validation but insufficient
  - LOW: Input sanitized, separate system/user contexts
- **Token/Cost Management**:
  - Check for: tiktoken, token counting, max_tokens limits
  - Flag: Unbounded context windows, no cost tracking

Output:
- llm_provider: "openai" | "anthropic" | "google" | "aws" | "multiple" | "none" | "unknown"
- model_version: detected model string or "unknown"
- api_key_handling: "environment_variable" | "hardcoded" | "secrets_manager" | "iam_role" | "unknown"
- prompt_injection_risk: "high" | "medium" | "low" | "none"
- token_management: "implemented" | "partial" | "none"

### 7. Data Retention & Privacy (CRITICAL)
Check for:
- **PII/PCI Logging**: logger.info(f"Card: {card_number}"), print(user_data)
- **External Data Transmission**: Sending PII/PCI to LLM APIs, analytics, logs
- **Data Deletion**: GDPR right-to-delete, data retention policies
- **Log Retention**: Logs stored indefinitely, no rotation
- **Redaction**: PII/PCI logged without masking

Risk flags:
- "Logs PII/PCI data without redaction"
- "Sends sensitive data to external LLM API"
- "No GDPR data deletion mechanism"
- "No log retention policy"

### 8. Rate Limiting & DoS Protection (HIGH)
Check for:
- **Endpoint Protection**: No @limiter decorator, no rate limiting
- **Timeouts**: httpx.get(url) without timeout parameter
- **Recursive Calls**: Agent A → Agent B → Agent A (cycle detection)
- **Unbounded Loops**: while True without break, no max iterations

Risk flags:
- "No rate limiting on endpoints"
- "External calls without timeout"
- "Recursive agent calls without cycle detection"
- "Unbounded loops detected"

### 9. Model Output Validation (HIGH)
Check for:
- **Code Execution**: eval(llm_response), exec(llm_response)
- **Schema Validation**: No Pydantic validation on LLM output
- **Hallucination Handling**: No fallback if LLM returns invalid data
- **SQL Injection**: LLM output used in SQL queries

Risk flags:
- "Executes LLM output directly (eval/exec)"
- "No schema validation on model responses"
- "No fallback for LLM hallucinations"
- "LLM output used in SQL without sanitization"

### 10. Agent Chaining & Loops (MEDIUM)
Check for:
- **Agent-to-Agent Calls**: httpx.post to other agent endpoints
- **Cycle Detection**: No visited agents tracking
- **Max Depth**: No hop_count or max_depth limit
- **Synchronous Chaining**: Blocking calls causing cascading failures

Risk flags:
- "Agent chains without cycle detection"
- "No maximum chain depth limit"
- "Synchronous chaining causes cascading failures"

### 11. Cost & Token Tracking (MEDIUM)
Check for:
- **Token Counting**: No tiktoken or token counting before calls
- **Cost Estimation**: No cost calculation
- **Budget Limits**: No max_tokens, no cost alerts
- **Context Window**: Unbounded context growth

Recommendations:
- "Implement token counting before LLM calls"
- "Set max_tokens limit"
- "Track costs per team for chargeback"

### 12. Authentication & Authorization (HIGH)
Check for:
- **Endpoint Auth**: No authentication on sensitive endpoints
- **API Key Exposure**: API keys in logs, error messages
- **Authorization**: No role-based access control
- **Token Validation**: No JWT validation, weak tokens

Risk flags:
- "No authentication on sensitive endpoints"
- "API keys exposed in logs"
- "No authorization checks"

### 13. Dependency Vulnerabilities (MEDIUM)
Parse requirements.txt / package.json:
- **Unpinned Versions**: requests instead of requests==2.31.0
- **Known Vulnerabilities**: Flag if you recognize vulnerable packages
- **Outdated Dependencies**: Very old versions

Recommendations:
- "Pin all dependency versions"
- "Update vulnerable dependencies"

### 14. Observability & Monitoring (LOW)
Check for:
- **Structured Logging**: print() instead of logger, no JSON logs
- **Metrics**: No Prometheus metrics, no performance tracking
- **Tracing**: No OpenTelemetry, no distributed tracing
- **Health Checks**: No /health endpoint

Recommendations:
- "Use structured logging with JSON format"
- "Add metrics for latency, error rate, token usage"
- "Add health check endpoint"

### 15. Input Validation & Sanitization (HIGH)
Check for:
- **SQL Injection**: User input in SQL queries
- **Command Injection**: User input in os.system(), subprocess
- **Path Traversal**: User input in file paths
- **XSS**: User input in HTML without escaping
- **Schema Validation**: No Pydantic models for input

Risk flags:
- "SQL injection vulnerability"
- "Command injection risk"
- "Path traversal vulnerability"
- "No input validation"

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
  "duplicate_risk": "none" or "low" or "medium" or "high",
  
  "llm_usage": {
    "provider": "openai" | "anthropic" | "google" | "aws" | "multiple" | "none" | "unknown",
    "model_version": "<detected model or unknown>",
    "api_key_handling": "environment_variable" | "hardcoded" | "secrets_manager" | "iam_role" | "unknown",
    "prompt_injection_risk": "high" | "medium" | "low" | "none",
    "token_management": "implemented" | "partial" | "none"
  },
  
  "data_privacy": {
    "logs_sensitive_data": true or false,
    "sends_data_to_external_apis": true or false,
    "has_data_deletion": true or false,
    "log_retention_policy": "defined" | "undefined" | "unknown",
    "issues": ["<specific privacy issues>"]
  },
  
  "security": {
    "rate_limiting": "implemented" | "partial" | "none",
    "has_timeouts": true or false,
    "input_validation": "comprehensive" | "partial" | "none",
    "output_validation": "implemented" | "none",
    "authentication": "strong" | "weak" | "none",
    "vulnerabilities": ["<specific security issues>"]
  },
  
  "agent_behavior": {
    "calls_other_agents": true or false,
    "has_cycle_detection": true or false,
    "max_chain_depth": "<number or unlimited>",
    "issues": ["<agent chaining issues>"]
  },
  
  "cost_management": {
    "tracks_tokens": true or false,
    "has_cost_limits": true or false,
    "has_budget_alerts": true or false,
    "issues": ["<cost management issues>"]
  },
  
  "observability": {
    "structured_logging": true or false,
    "has_metrics": true or false,
    "has_tracing": true or false,
    "has_health_check": true or false
  },
  
  "dependencies": {
    "versions_pinned": true or false,
    "known_vulnerabilities": ["<package@version: issue>"],
    "outdated_packages": ["<package@version>"]
  }
}

Be direct. Name exact fields or capabilities that raise concerns.
Do not fabricate evidence for or against compliance."""


class GovernanceAgent:
    """Reviews agent/tool registrations using Claude on Vertex AI with comprehensive checks."""

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
        Run comprehensive AI governance review on a registration.
        Returns a review dict with 15 categories of checks, or None if Vertex AI is unavailable.
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
            # Truncate to keep prompt size reasonable
            safe_code = source_code[:8000]  # Increased for better analysis
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

Perform comprehensive governance review covering all 15 categories.
Return ONLY a JSON object as described in your instructions."""

        try:
            response = await self.model.generate_content_async(
                user_message,
                generation_config=self.GenerationConfig(
                    max_output_tokens=3000,  # Increased for comprehensive output
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

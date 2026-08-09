#!/usr/bin/env python3
"""Generate an offline capability report for AI-provider limits.

This utility is deliberately static and read-only with respect to providers: it
does not load .env, inspect API keys, make network requests, or invoke models.
The evidence catalogue is updated manually from official documentation.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

AS_OF = date(2026, 8, 9).isoformat()
STATUSES = {"Yes", "No", "Partial", "Unknown", "N/A"}
SOURCES = {"API", "Response Headers", "Documentation", "Dashboard", "Unknown"}

CAPABILITIES = (
    ("quota_rate_limits_api", "Quota/rate-limits API"),
    ("rpm", "RPM/RPS"),
    ("tpm", "TPM"),
    ("concurrency", "Concurrency"),
    ("usage", "Usage"),
    ("billing_quota", "Billing quota/balance"),
    ("endpoint_count", "API endpoint catalogue/count"),
    ("multiple_api_keys", "Official multiple API keys"),
    ("limit_increase", "Limit increase"),
)


def c(status: str, source: str, note: str) -> dict[str, str]:
    if status not in STATUSES or source not in SOURCES:
        raise ValueError(f"Invalid capability value: {status=}, {source=}")
    return {"status": status, "source": source, "note": note}


def p(name: str, refs: list[str], **caps: dict[str, str]) -> dict[str, Any]:
    missing = {key for key, _ in CAPABILITIES} - caps.keys()
    extra = caps.keys() - {key for key, _ in CAPABILITIES}
    if missing or extra:
        raise ValueError(f"Invalid capability set for {name}: {missing=}, {extra=}")
    return {"provider": name, "capabilities": caps, "references": refs}


PROVIDERS = [
    p("OpenAI", ["https://developers.openai.com/api/docs/guides/rate-limits", "https://platform.openai.com/settings/organization/limits", "https://platform.openai.com/docs/api-reference/usage"],
      quota_rate_limits_api=c("Partial", "API", "Organization usage/cost APIs exist, but the live RPM/TPM ceiling is primarily exposed through headers and the Limits page."),
      rpm=c("Yes", "Response Headers", "Request limit, remaining requests and reset time are returned in x-ratelimit-* headers."),
      tpm=c("Yes", "Response Headers", "Token limit, remaining tokens and reset time are returned in x-ratelimit-* headers."),
      concurrency=c("Partial", "Documentation", "Some products expose concurrent-session or queue constraints; there is no single universal concurrency value."),
      usage=c("Yes", "API", "Organization Usage API and Usage dashboard are available."),
      billing_quota=c("Yes", "API", "Organization Costs API and billing/limits dashboard expose spend information."),
      endpoint_count=c("Yes", "Documentation", "The versioned API reference is the authoritative endpoint catalogue; its count changes over time."),
      multiple_api_keys=c("Yes", "Dashboard", "Projects, users and service accounts can have separately managed keys; project/org limits still apply."),
      limit_increase=c("Yes", "Dashboard", "Usage tiers can rise automatically; eligible organizations can request higher limits.")),
    p("Gemini", ["https://ai.google.dev/gemini-api/docs/rate-limits", "https://ai.google.dev/gemini-api/docs/billing", "https://ai.google.dev/gemini-api/docs/api-key"],
      quota_rate_limits_api=c("Partial", "Dashboard", "Current project limits are shown in AI Studio; no single Gemini Developer API endpoint returns the full limit matrix."),
      rpm=c("Yes", "Documentation", "Per-project/model RPM is documented and the active value is shown in AI Studio."),
      tpm=c("Yes", "Documentation", "Per-project/model TPM is documented and the active value is shown in AI Studio."),
      concurrency=c("Partial", "Documentation", "Batch/enqueued-token constraints exist, but no universal online concurrency number is published."),
      usage=c("Yes", "Dashboard", "AI Studio/Google Cloud surfaces project usage."),
      billing_quota=c("Yes", "Dashboard", "Billing setup and spend controls are managed in AI Studio/Google Cloud."),
      endpoint_count=c("Yes", "Documentation", "The official Gemini API reference is the versioned endpoint catalogue."),
      multiple_api_keys=c("Yes", "Dashboard", "Google AI Studio supports keys across projects; quotas are generally enforced per project, not multiplied safely by keys."),
      limit_increase=c("Yes", "Documentation", "Paid tiers grow with spend and eligible projects can request a rate-limit increase.")),
    p("BytePlus", ["https://docs.byteplus.com/en/docs/ModelArk/1593702", "https://docs.byteplus.com/en/docs/ModelArk/1099455"],
      quota_rate_limits_api=c("No", "Documentation", "ModelArk documents limits and console configuration; no public account-wide limits-discovery API is documented."),
      rpm=c("Yes", "Documentation", "Model and endpoint request-rate limits are documented/configured in ModelArk."),
      tpm=c("Yes", "Documentation", "Token throughput limits apply to supported text endpoints and are documented by model/endpoint."),
      concurrency=c("Partial", "Documentation", "Media-model concurrency and provisioned endpoint capacity are model/deployment specific."),
      usage=c("Yes", "Dashboard", "Usage and endpoint monitoring are available in the BytePlus console."),
      billing_quota=c("Yes", "Dashboard", "Account balance, billing and resource quotas are console-managed."),
      endpoint_count=c("Yes", "Dashboard", "Created inference endpoints can be enumerated in ModelArk console; API-method inventory is in the reference."),
      multiple_api_keys=c("Partial", "Dashboard", "Multiple IAM credentials can be managed, but limits remain account/project/resource scoped."),
      limit_increase=c("Yes", "Dashboard", "Capacity can be adjusted through provisioned endpoints, quota applications or support.")),
    p("Qwen", ["https://www.alibabacloud.com/help/en/model-studio/rate-limit", "https://www.alibabacloud.com/help/en/model-studio/new-free-quota"],
      quota_rate_limits_api=c("No", "Documentation", "Model Studio publishes limits and console monitoring, not a general live quota-discovery API."),
      rpm=c("Yes", "Documentation", "Per-model RPM is documented."),
      tpm=c("Yes", "Documentation", "Per-model TPM is documented."),
      concurrency=c("Partial", "Documentation", "Some asynchronous/media or dedicated deployments use concurrency/capacity limits rather than a universal value."),
      usage=c("Yes", "Dashboard", "Hourly monitoring and usage are available in the Model Studio console."),
      billing_quota=c("Yes", "Dashboard", "Free quota and billing consumption are shown in the console."),
      endpoint_count=c("Yes", "Documentation", "The API reference/deployment console provides the versioned endpoint catalogue."),
      multiple_api_keys=c("Yes", "Documentation", "Multiple keys are supported, but documented limits aggregate at account level across keys."),
      limit_increase=c("Yes", "Dashboard", "Temporary increases, dedicated capacity and support options are available depending on model/region.")),
    p("Kling", ["https://app.klingai.com/global/dev/document-api/quickStart/productIntroduction/overview"],
      quota_rate_limits_api=c("Unknown", "Unknown", "No public account quota-discovery endpoint was found in the official developer reference."),
      rpm=c("Unknown", "Unknown", "No stable public RPM value was found; inspect the developer console/contract."),
      tpm=c("N/A", "Documentation", "The media API is not documented with token-per-minute accounting."),
      concurrency=c("Partial", "Dashboard", "Plan/account task capacity may be visible in the developer console, but no universal public value is documented."),
      usage=c("Yes", "Dashboard", "Task and resource consumption are available in the Kling developer console."),
      billing_quota=c("Yes", "Dashboard", "Package/balance information is console-managed."),
      endpoint_count=c("Yes", "Documentation", "The official developer reference is the endpoint catalogue; exact count is version-sensitive."),
      multiple_api_keys=c("Unknown", "Unknown", "Official public material reviewed does not clearly promise multiple active keys per account."),
      limit_increase=c("Partial", "Dashboard", "Higher commercial capacity is handled through plans or business support.")),
    p("Runway", ["https://docs.dev.runwayml.com/usage/tiers/", "https://docs.dev.runwayml.com/api/"],
      quota_rate_limits_api=c("No", "Documentation", "Tier limits are documented/dashboard-based; no limits-discovery endpoint is published."),
      rpm=c("N/A", "Documentation", "Runway states there is no requests-per-minute maximum; concurrency and daily generation limits govern capacity."),
      tpm=c("N/A", "Documentation", "Runway media generation is not governed by TPM."),
      concurrency=c("Yes", "Documentation", "Maximum concurrent generations are published by tier/model/modality."),
      usage=c("Yes", "Dashboard", "Organization usage is visible in the developer dashboard."),
      billing_quota=c("Yes", "Dashboard", "Monthly spend caps and tier usage are dashboard-managed."),
      endpoint_count=c("Yes", "Documentation", "The API reference is a versioned endpoint catalogue."),
      multiple_api_keys=c("Partial", "Dashboard", "Organization key management is available; keys do not create independent organization capacity."),
      limit_increase=c("Yes", "Documentation", "Tiers increase with usage; enterprise/custom concurrency is available through support.")),
    p("ElevenLabs", ["https://elevenlabs.io/docs/overview/models", "https://elevenlabs.io/docs/api-reference/user/subscription/get", "https://elevenlabs.io/docs/overview/administration/workspaces/api-keys"],
      quota_rate_limits_api=c("Yes", "API", "GET /v1/user/subscription returns tier, usage and credit/character limits."),
      rpm=c("Partial", "Documentation", "Endpoint rate limiting exists, but ElevenLabs emphasizes plan/model concurrency rather than one universal RPM."),
      tpm=c("N/A", "Documentation", "Speech/media quotas use credits, characters and concurrency, not TPM."),
      concurrency=c("Yes", "Response Headers", "current-concurrent-requests and maximum-concurrent-requests headers expose live concurrency."),
      usage=c("Yes", "API", "Subscription response exposes consumed and available units; dashboard provides breakdowns."),
      billing_quota=c("Yes", "API", "Subscription response exposes credit/character limits and overage-related fields."),
      endpoint_count=c("Yes", "Documentation", "The official API reference is the versioned endpoint catalogue."),
      multiple_api_keys=c("Yes", "Documentation", "Multiple user/service-account keys are officially supported with scopes and per-key credit caps."),
      limit_increase=c("Yes", "Documentation", "Upgrade plans or request enterprise concurrency through an account manager.")),
    p("HeyGen", ["https://docs.heygen.com/reference/limits", "https://docs.heygen.com/reference/overview"],
      quota_rate_limits_api=c("Unknown", "Unknown", "No general authenticated endpoint returning all current account limits was found."),
      rpm=c("Partial", "Documentation", "Rate limits are product/plan specific; 429 responses signal exhaustion, without one universal RPM."),
      tpm=c("N/A", "Documentation", "HeyGen video/avatar APIs do not publish TPM accounting."),
      concurrency=c("Yes", "Documentation", "Concurrent-generation/session limits are plan and product specific."),
      usage=c("Partial", "Dashboard", "Credits and plan usage are available in the account dashboard."),
      billing_quota=c("Yes", "Dashboard", "Credits and subscription limits are dashboard-managed."),
      endpoint_count=c("Yes", "Documentation", "The API reference is the versioned endpoint catalogue."),
      multiple_api_keys=c("Unknown", "Unknown", "Public documentation reviewed does not clearly guarantee multiple active production keys."),
      limit_increase=c("Yes", "Dashboard", "Higher API plans and enterprise/contact-sales capacity are available.")),
    p("Luma", ["https://docs.lumalabs.ai/docs/rate-limits", "https://docs.lumalabs.ai/reference/getcredits"],
      quota_rate_limits_api=c("Partial", "API", "GET /dream-machine/v1/credits returns balance, but it does not return the complete rate-limit matrix."),
      rpm=c("Yes", "Documentation", "Create requests per minute are published by model/tier."),
      tpm=c("N/A", "Documentation", "Dream Machine image/video capacity is not token-per-minute based."),
      concurrency=c("Yes", "Documentation", "Concurrent generations are published by model/tier."),
      usage=c("Partial", "Dashboard", "Usage is visible in the platform; the credits endpoint exposes remaining balance rather than a full usage ledger."),
      billing_quota=c("Yes", "API", "The credits endpoint returns API credit balance; monthly usage limits are documented."),
      endpoint_count=c("Yes", "Documentation", "The API reference is the versioned endpoint catalogue."),
      multiple_api_keys=c("Unknown", "Unknown", "Official public docs reviewed do not clearly state multi-key policy."),
      limit_increase=c("Yes", "Documentation", "The Scale plan/support provides higher concurrency and monthly usage limits.")),
    p("Recraft", ["https://www.recraft.ai/docs", "https://www.recraft.ai/pricing"],
      quota_rate_limits_api=c("Unknown", "Unknown", "No public endpoint returning the account's rate-limit configuration was found."),
      rpm=c("Partial", "Documentation", "Rate limiting is documented for API access, but exact account values may depend on the commercial plan."),
      tpm=c("N/A", "Documentation", "Image generation is credit/request based, not TPM based."),
      concurrency=c("Unknown", "Unknown", "No universal public concurrency value was found."),
      usage=c("Yes", "Dashboard", "API usage and credits are visible in the Recraft account/dashboard."),
      billing_quota=c("Yes", "Dashboard", "Credits and billing are dashboard-managed."),
      endpoint_count=c("Yes", "Documentation", "The official API reference enumerates endpoints; count changes with versions."),
      multiple_api_keys=c("Unknown", "Unknown", "Multi-key entitlement is not clearly documented publicly."),
      limit_increase=c("Yes", "Dashboard", "Higher plans or enterprise contact can provide additional capacity.")),
    p("Ideogram", ["https://developer.ideogram.ai/ideogram-api/api-overview", "https://developer.ideogram.ai/ideogram-api/api-setup"],
      quota_rate_limits_api=c("No", "Documentation", "No limits-discovery endpoint is published."),
      rpm=c("N/A", "Documentation", "The published default is 10 in-flight requests, not a universal RPM figure."),
      tpm=c("N/A", "Documentation", "Image API limits are not token-per-minute based."),
      concurrency=c("Yes", "Documentation", "The default limit is 10 in-flight requests."),
      usage=c("Yes", "Dashboard", "API balance/usage is managed in the API dashboard."),
      billing_quota=c("Yes", "Dashboard", "Balance, automatic top-up and thresholds are configurable in the dashboard."),
      endpoint_count=c("Yes", "Documentation", "The official API reference enumerates endpoints."),
      multiple_api_keys=c("Yes", "Documentation", "Multiple keys are explicitly supported and billed under the same plan."),
      limit_increase=c("Yes", "Documentation", "Larger-scale capacity is available by contacting Ideogram partnerships.")),
    p("Flux (Black Forest Labs)", ["https://docs.bfl.ai/", "https://docs.bfl.ai/quick_start/pricing"],
      quota_rate_limits_api=c("Unknown", "Unknown", "No public account limits-discovery endpoint was found."),
      rpm=c("Unknown", "Unknown", "No single public RPM value applies across hosted FLUX endpoints."),
      tpm=c("N/A", "Documentation", "Image generation is request/credit based, not TPM based."),
      concurrency=c("Unknown", "Unknown", "Current account concurrency is not publicly exposed as a universal value."),
      usage=c("Partial", "Dashboard", "Usage/credits are available through the BFL account console."),
      billing_quota=c("Yes", "Dashboard", "Credits and billing balance are dashboard-managed."),
      endpoint_count=c("Yes", "Documentation", "The BFL API reference enumerates the current endpoints."),
      multiple_api_keys=c("Unknown", "Unknown", "Official public documentation reviewed does not clearly state multi-key entitlement."),
      limit_increase=c("Partial", "Dashboard", "Capacity depends on account/commercial arrangements; contact support for production scale.")),
    p("Hedra", ["https://www.hedra.com/docs", "https://www.hedra.com/api"],
      quota_rate_limits_api=c("Unknown", "Unknown", "No public quota-discovery endpoint was found."),
      rpm=c("Unknown", "Unknown", "No stable universal RPM is publicly documented."),
      tpm=c("N/A", "Documentation", "Media generation is not documented with TPM accounting."),
      concurrency=c("Partial", "Dashboard", "Task concurrency/capacity is account-plan dependent."),
      usage=c("Yes", "Dashboard", "Credits and generation usage are visible in the Hedra account."),
      billing_quota=c("Yes", "Dashboard", "Plan credits and billing are dashboard-managed."),
      endpoint_count=c("Yes", "Documentation", "The official API reference enumerates endpoints."),
      multiple_api_keys=c("Unknown", "Unknown", "Public documentation reviewed does not establish a multiple-key policy."),
      limit_increase=c("Yes", "Dashboard", "Higher commercial capacity is available through plan upgrades/contact sales.")),
    p("Higgsfield", ["https://docs.higgsfield.ai/", "https://higgsfield.ai/api"],
      quota_rate_limits_api=c("Unknown", "Unknown", "No public API returning quota or live limits was found."),
      rpm=c("Unknown", "Unknown", "No universal public RPM value was found."),
      tpm=c("N/A", "Documentation", "Media generation is not documented with TPM accounting."),
      concurrency=c("Unknown", "Unknown", "Account concurrency is not publicly documented as a stable universal value."),
      usage=c("Partial", "Dashboard", "Account credits/usage are dashboard based."),
      billing_quota=c("Yes", "Dashboard", "Plans and credits are managed in the account dashboard."),
      endpoint_count=c("Yes", "Documentation", "The official API documentation is the endpoint catalogue."),
      multiple_api_keys=c("Unknown", "Unknown", "No clear official public multi-key policy was found."),
      limit_increase=c("Partial", "Dashboard", "Production capacity is handled through plan upgrades or business support.")),
    p("FASHN", ["https://docs.fashn.ai/api-overview/api-fundamentals", "https://docs.fashn.ai/api-reference/credits"],
      quota_rate_limits_api=c("Partial", "API", "Credit information is available by API; the full live rate-limit configuration is documented rather than returned by one endpoint."),
      rpm=c("Yes", "Documentation", "Defaults: /v1/run 50 per 60 seconds and /v1/status 50 per 10 seconds."),
      tpm=c("N/A", "Documentation", "FASHN uses credits and requests, not token throughput."),
      concurrency=c("Yes", "Documentation", "Default concurrency is documented as 6 processing requests."),
      usage=c("Yes", "Response Headers", "x-fashn-credits-used reports credits consumed for a prediction; dashboard/API provide balance context."),
      billing_quota=c("Yes", "API", "Credits/balance can be queried using the documented credits API."),
      endpoint_count=c("Yes", "Documentation", "The official reference enumerates endpoint/model lifecycle and cost."),
      multiple_api_keys=c("Unknown", "Unknown", "The public docs reviewed do not clearly establish multiple-key entitlement."),
      limit_increase=c("Yes", "Documentation", "FASHN explicitly invites justified rate-limit increase requests via support.")),
    p("Grok (xAI)", ["https://docs.x.ai/developers/rate-limits", "https://docs.x.ai/developers/management-api", "https://console.x.ai/"],
      quota_rate_limits_api=c("Partial", "Dashboard", "Personalized per-model limits are shown in Console; no single public inference endpoint returns the complete matrix."),
      rpm=c("Yes", "Documentation", "Per-model RPS is published and derived from RPM; personalized values are in Console."),
      tpm=c("Yes", "Documentation", "Per-model TPM is published for token models."),
      concurrency=c("Partial", "Documentation", "Voice/session products publish concurrency; text/image/video mainly publish RPS/TPM."),
      usage=c("Yes", "Dashboard", "Team usage and cost tracking are available in Console."),
      billing_quota=c("Yes", "Dashboard", "Prepaid credits, invoices and spend-tier information are console-managed."),
      endpoint_count=c("Yes", "Documentation", "The REST/API references enumerate versioned endpoints."),
      multiple_api_keys=c("Yes", "Dashboard", "Teams can manage multiple keys; team/model limits remain shared."),
      limit_increase=c("Yes", "Documentation", "Spend tiers upgrade automatically; increases and enterprise capacity can be requested.")),
]


def validate() -> None:
    if len(PROVIDERS) != 16 or len({item["provider"] for item in PROVIDERS}) != 16:
        raise ValueError("Provider catalogue must contain 16 unique providers")
    for provider in PROVIDERS:
        for key, _ in CAPABILITIES:
            item = provider["capabilities"][key]
            if item["status"] not in STATUSES or item["source"] not in SOURCES:
                raise ValueError(f"Invalid entry: {provider['provider']} / {key}")


def build_payload() -> dict[str, Any]:
    validate()
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_as_of": AS_OF,
        "mode": "offline_static_evidence",
        "safety": {
            "network_requests": False,
            "environment_loaded": False,
            "api_keys_used": False,
            "generations_performed": False,
            "paid_credits_spent": False,
        },
        "status_values": sorted(STATUSES),
        "source_values": sorted(SOURCES),
        "notes": [
            "Unknown means the reviewed official public material did not establish the capability.",
            "Partial means only part of the requested metric is exposed, or availability varies by product/model/plan.",
            "Endpoint count means an authoritative catalogue/list is available; exact numeric totals are version-sensitive.",
            "Multiple keys do not imply multiplied limits; providers commonly enforce quota at project, team, workspace or account level.",
        ],
        "providers": PROVIDERS,
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AI provider limits diagnostics",
        "",
        f"Evidence reviewed as of **{payload['evidence_as_of']}**. This report was generated offline; no API key was read, no provider was called, and no paid generation was performed.",
        "",
        "Legend: `Yes` = available; `Partial` = product/plan dependent or incomplete; `No` = explicitly not exposed; `N/A` = metric does not apply; `Unknown` = not established by reviewed official public material.",
        "",
        "## Summary",
        "",
        "| Provider | Limits API | RPM/RPS | TPM | Concurrency | Usage | Billing | Endpoints | Multi-key | Increase |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    keys = [key for key, _ in CAPABILITIES]
    for provider in payload["providers"]:
        vals = [provider["capabilities"][key]["status"] for key in keys]
        lines.append("| " + " | ".join([provider["provider"], *vals]) + " |")
    lines += ["", "## Detailed evidence", ""]
    for provider in payload["providers"]:
        lines += [f"### {provider['provider']}", ""]
        for key, label in CAPABILITIES:
            item = provider["capabilities"][key]
            lines.append(f"- **{label}: {item['status']}** — source: `{item['source']}`. {item['note']}")
        lines += ["", "Official references:", ""]
        lines += [f"- {url}" for url in provider["references"]]
        lines.append("")
    lines += [
        "## Interpretation notes", "",
        *[f"- {note}" for note in payload["notes"]], "",
        "This is a capability/evidence inventory, not a guarantee of the limits assigned to a particular account. Check the provider dashboard and contract before configuring production concurrency.", "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd(), help="Report directory (default: current directory)")
    parser.add_argument("--json-name", default="provider_limits_report.json")
    parser.add_argument("--markdown-name", default="provider_limits_report.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    json_path = args.output_dir / args.json_name
    markdown_path = args.output_dir / args.markdown_name
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown(payload), encoding="utf-8")
    print(f"providers={len(payload['providers'])}")
    print(f"json={json_path.resolve()}")
    print(f"markdown={markdown_path.resolve()}")
    print("network_requests=0 paid_generations=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# AI provider limits diagnostics

Evidence reviewed as of **2026-08-09**. This report was generated offline; no API key was read, no provider was called, and no paid generation was performed.

Legend: `Yes` = available; `Partial` = product/plan dependent or incomplete; `No` = explicitly not exposed; `N/A` = metric does not apply; `Unknown` = not established by reviewed official public material.

## Summary

| Provider | Limits API | RPM/RPS | TPM | Concurrency | Usage | Billing | Endpoints | Multi-key | Increase |
|---|---|---|---|---|---|---|---|---|---|
| OpenAI | Partial | Yes | Yes | Partial | Yes | Yes | Yes | Yes | Yes |
| Gemini | Partial | Yes | Yes | Partial | Yes | Yes | Yes | Yes | Yes |
| BytePlus | No | Yes | Yes | Partial | Yes | Yes | Yes | Partial | Yes |
| Qwen | No | Yes | Yes | Partial | Yes | Yes | Yes | Yes | Yes |
| Kling | Unknown | Unknown | N/A | Partial | Yes | Yes | Yes | Unknown | Partial |
| Runway | No | N/A | N/A | Yes | Yes | Yes | Yes | Partial | Yes |
| ElevenLabs | Yes | Partial | N/A | Yes | Yes | Yes | Yes | Yes | Yes |
| HeyGen | Unknown | Partial | N/A | Yes | Partial | Yes | Yes | Unknown | Yes |
| Luma | Partial | Yes | N/A | Yes | Partial | Yes | Yes | Unknown | Yes |
| Recraft | Unknown | Partial | N/A | Unknown | Yes | Yes | Yes | Unknown | Yes |
| Ideogram | No | N/A | N/A | Yes | Yes | Yes | Yes | Yes | Yes |
| Flux (Black Forest Labs) | Unknown | Unknown | N/A | Unknown | Partial | Yes | Yes | Unknown | Partial |
| Hedra | Unknown | Unknown | N/A | Partial | Yes | Yes | Yes | Unknown | Yes |
| Higgsfield | Unknown | Unknown | N/A | Unknown | Partial | Yes | Yes | Unknown | Partial |
| FASHN | Partial | Yes | N/A | Yes | Yes | Yes | Yes | Unknown | Yes |
| Grok (xAI) | Partial | Yes | Yes | Partial | Yes | Yes | Yes | Yes | Yes |

## Detailed evidence

### OpenAI

- **Quota/rate-limits API: Partial** — source: `API`. Organization usage/cost APIs exist, but the live RPM/TPM ceiling is primarily exposed through headers and the Limits page.
- **RPM/RPS: Yes** — source: `Response Headers`. Request limit, remaining requests and reset time are returned in x-ratelimit-* headers.
- **TPM: Yes** — source: `Response Headers`. Token limit, remaining tokens and reset time are returned in x-ratelimit-* headers.
- **Concurrency: Partial** — source: `Documentation`. Some products expose concurrent-session or queue constraints; there is no single universal concurrency value.
- **Usage: Yes** — source: `API`. Organization Usage API and Usage dashboard are available.
- **Billing quota/balance: Yes** — source: `API`. Organization Costs API and billing/limits dashboard expose spend information.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The versioned API reference is the authoritative endpoint catalogue; its count changes over time.
- **Official multiple API keys: Yes** — source: `Dashboard`. Projects, users and service accounts can have separately managed keys; project/org limits still apply.
- **Limit increase: Yes** — source: `Dashboard`. Usage tiers can rise automatically; eligible organizations can request higher limits.

Official references:

- https://developers.openai.com/api/docs/guides/rate-limits
- https://platform.openai.com/settings/organization/limits
- https://platform.openai.com/docs/api-reference/usage

### Gemini

- **Quota/rate-limits API: Partial** — source: `Dashboard`. Current project limits are shown in AI Studio; no single Gemini Developer API endpoint returns the full limit matrix.
- **RPM/RPS: Yes** — source: `Documentation`. Per-project/model RPM is documented and the active value is shown in AI Studio.
- **TPM: Yes** — source: `Documentation`. Per-project/model TPM is documented and the active value is shown in AI Studio.
- **Concurrency: Partial** — source: `Documentation`. Batch/enqueued-token constraints exist, but no universal online concurrency number is published.
- **Usage: Yes** — source: `Dashboard`. AI Studio/Google Cloud surfaces project usage.
- **Billing quota/balance: Yes** — source: `Dashboard`. Billing setup and spend controls are managed in AI Studio/Google Cloud.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official Gemini API reference is the versioned endpoint catalogue.
- **Official multiple API keys: Yes** — source: `Dashboard`. Google AI Studio supports keys across projects; quotas are generally enforced per project, not multiplied safely by keys.
- **Limit increase: Yes** — source: `Documentation`. Paid tiers grow with spend and eligible projects can request a rate-limit increase.

Official references:

- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/billing
- https://ai.google.dev/gemini-api/docs/api-key

### BytePlus

- **Quota/rate-limits API: No** — source: `Documentation`. ModelArk documents limits and console configuration; no public account-wide limits-discovery API is documented.
- **RPM/RPS: Yes** — source: `Documentation`. Model and endpoint request-rate limits are documented/configured in ModelArk.
- **TPM: Yes** — source: `Documentation`. Token throughput limits apply to supported text endpoints and are documented by model/endpoint.
- **Concurrency: Partial** — source: `Documentation`. Media-model concurrency and provisioned endpoint capacity are model/deployment specific.
- **Usage: Yes** — source: `Dashboard`. Usage and endpoint monitoring are available in the BytePlus console.
- **Billing quota/balance: Yes** — source: `Dashboard`. Account balance, billing and resource quotas are console-managed.
- **API endpoint catalogue/count: Yes** — source: `Dashboard`. Created inference endpoints can be enumerated in ModelArk console; API-method inventory is in the reference.
- **Official multiple API keys: Partial** — source: `Dashboard`. Multiple IAM credentials can be managed, but limits remain account/project/resource scoped.
- **Limit increase: Yes** — source: `Dashboard`. Capacity can be adjusted through provisioned endpoints, quota applications or support.

Official references:

- https://docs.byteplus.com/en/docs/ModelArk/1593702
- https://docs.byteplus.com/en/docs/ModelArk/1099455

### Qwen

- **Quota/rate-limits API: No** — source: `Documentation`. Model Studio publishes limits and console monitoring, not a general live quota-discovery API.
- **RPM/RPS: Yes** — source: `Documentation`. Per-model RPM is documented.
- **TPM: Yes** — source: `Documentation`. Per-model TPM is documented.
- **Concurrency: Partial** — source: `Documentation`. Some asynchronous/media or dedicated deployments use concurrency/capacity limits rather than a universal value.
- **Usage: Yes** — source: `Dashboard`. Hourly monitoring and usage are available in the Model Studio console.
- **Billing quota/balance: Yes** — source: `Dashboard`. Free quota and billing consumption are shown in the console.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The API reference/deployment console provides the versioned endpoint catalogue.
- **Official multiple API keys: Yes** — source: `Documentation`. Multiple keys are supported, but documented limits aggregate at account level across keys.
- **Limit increase: Yes** — source: `Dashboard`. Temporary increases, dedicated capacity and support options are available depending on model/region.

Official references:

- https://www.alibabacloud.com/help/en/model-studio/rate-limit
- https://www.alibabacloud.com/help/en/model-studio/new-free-quota

### Kling

- **Quota/rate-limits API: Unknown** — source: `Unknown`. No public account quota-discovery endpoint was found in the official developer reference.
- **RPM/RPS: Unknown** — source: `Unknown`. No stable public RPM value was found; inspect the developer console/contract.
- **TPM: N/A** — source: `Documentation`. The media API is not documented with token-per-minute accounting.
- **Concurrency: Partial** — source: `Dashboard`. Plan/account task capacity may be visible in the developer console, but no universal public value is documented.
- **Usage: Yes** — source: `Dashboard`. Task and resource consumption are available in the Kling developer console.
- **Billing quota/balance: Yes** — source: `Dashboard`. Package/balance information is console-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official developer reference is the endpoint catalogue; exact count is version-sensitive.
- **Official multiple API keys: Unknown** — source: `Unknown`. Official public material reviewed does not clearly promise multiple active keys per account.
- **Limit increase: Partial** — source: `Dashboard`. Higher commercial capacity is handled through plans or business support.

Official references:

- https://app.klingai.com/global/dev/document-api/quickStart/productIntroduction/overview

### Runway

- **Quota/rate-limits API: No** — source: `Documentation`. Tier limits are documented/dashboard-based; no limits-discovery endpoint is published.
- **RPM/RPS: N/A** — source: `Documentation`. Runway states there is no requests-per-minute maximum; concurrency and daily generation limits govern capacity.
- **TPM: N/A** — source: `Documentation`. Runway media generation is not governed by TPM.
- **Concurrency: Yes** — source: `Documentation`. Maximum concurrent generations are published by tier/model/modality.
- **Usage: Yes** — source: `Dashboard`. Organization usage is visible in the developer dashboard.
- **Billing quota/balance: Yes** — source: `Dashboard`. Monthly spend caps and tier usage are dashboard-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The API reference is a versioned endpoint catalogue.
- **Official multiple API keys: Partial** — source: `Dashboard`. Organization key management is available; keys do not create independent organization capacity.
- **Limit increase: Yes** — source: `Documentation`. Tiers increase with usage; enterprise/custom concurrency is available through support.

Official references:

- https://docs.dev.runwayml.com/usage/tiers/
- https://docs.dev.runwayml.com/api/

### ElevenLabs

- **Quota/rate-limits API: Yes** — source: `API`. GET /v1/user/subscription returns tier, usage and credit/character limits.
- **RPM/RPS: Partial** — source: `Documentation`. Endpoint rate limiting exists, but ElevenLabs emphasizes plan/model concurrency rather than one universal RPM.
- **TPM: N/A** — source: `Documentation`. Speech/media quotas use credits, characters and concurrency, not TPM.
- **Concurrency: Yes** — source: `Response Headers`. current-concurrent-requests and maximum-concurrent-requests headers expose live concurrency.
- **Usage: Yes** — source: `API`. Subscription response exposes consumed and available units; dashboard provides breakdowns.
- **Billing quota/balance: Yes** — source: `API`. Subscription response exposes credit/character limits and overage-related fields.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official API reference is the versioned endpoint catalogue.
- **Official multiple API keys: Yes** — source: `Documentation`. Multiple user/service-account keys are officially supported with scopes and per-key credit caps.
- **Limit increase: Yes** — source: `Documentation`. Upgrade plans or request enterprise concurrency through an account manager.

Official references:

- https://elevenlabs.io/docs/overview/models
- https://elevenlabs.io/docs/api-reference/user/subscription/get
- https://elevenlabs.io/docs/overview/administration/workspaces/api-keys

### HeyGen

- **Quota/rate-limits API: Unknown** — source: `Unknown`. No general authenticated endpoint returning all current account limits was found.
- **RPM/RPS: Partial** — source: `Documentation`. Rate limits are product/plan specific; 429 responses signal exhaustion, without one universal RPM.
- **TPM: N/A** — source: `Documentation`. HeyGen video/avatar APIs do not publish TPM accounting.
- **Concurrency: Yes** — source: `Documentation`. Concurrent-generation/session limits are plan and product specific.
- **Usage: Partial** — source: `Dashboard`. Credits and plan usage are available in the account dashboard.
- **Billing quota/balance: Yes** — source: `Dashboard`. Credits and subscription limits are dashboard-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The API reference is the versioned endpoint catalogue.
- **Official multiple API keys: Unknown** — source: `Unknown`. Public documentation reviewed does not clearly guarantee multiple active production keys.
- **Limit increase: Yes** — source: `Dashboard`. Higher API plans and enterprise/contact-sales capacity are available.

Official references:

- https://docs.heygen.com/reference/limits
- https://docs.heygen.com/reference/overview

### Luma

- **Quota/rate-limits API: Partial** — source: `API`. GET /dream-machine/v1/credits returns balance, but it does not return the complete rate-limit matrix.
- **RPM/RPS: Yes** — source: `Documentation`. Create requests per minute are published by model/tier.
- **TPM: N/A** — source: `Documentation`. Dream Machine image/video capacity is not token-per-minute based.
- **Concurrency: Yes** — source: `Documentation`. Concurrent generations are published by model/tier.
- **Usage: Partial** — source: `Dashboard`. Usage is visible in the platform; the credits endpoint exposes remaining balance rather than a full usage ledger.
- **Billing quota/balance: Yes** — source: `API`. The credits endpoint returns API credit balance; monthly usage limits are documented.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The API reference is the versioned endpoint catalogue.
- **Official multiple API keys: Unknown** — source: `Unknown`. Official public docs reviewed do not clearly state multi-key policy.
- **Limit increase: Yes** — source: `Documentation`. The Scale plan/support provides higher concurrency and monthly usage limits.

Official references:

- https://docs.lumalabs.ai/docs/rate-limits
- https://docs.lumalabs.ai/reference/getcredits

### Recraft

- **Quota/rate-limits API: Unknown** — source: `Unknown`. No public endpoint returning the account's rate-limit configuration was found.
- **RPM/RPS: Partial** — source: `Documentation`. Rate limiting is documented for API access, but exact account values may depend on the commercial plan.
- **TPM: N/A** — source: `Documentation`. Image generation is credit/request based, not TPM based.
- **Concurrency: Unknown** — source: `Unknown`. No universal public concurrency value was found.
- **Usage: Yes** — source: `Dashboard`. API usage and credits are visible in the Recraft account/dashboard.
- **Billing quota/balance: Yes** — source: `Dashboard`. Credits and billing are dashboard-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official API reference enumerates endpoints; count changes with versions.
- **Official multiple API keys: Unknown** — source: `Unknown`. Multi-key entitlement is not clearly documented publicly.
- **Limit increase: Yes** — source: `Dashboard`. Higher plans or enterprise contact can provide additional capacity.

Official references:

- https://www.recraft.ai/docs
- https://www.recraft.ai/pricing

### Ideogram

- **Quota/rate-limits API: No** — source: `Documentation`. No limits-discovery endpoint is published.
- **RPM/RPS: N/A** — source: `Documentation`. The published default is 10 in-flight requests, not a universal RPM figure.
- **TPM: N/A** — source: `Documentation`. Image API limits are not token-per-minute based.
- **Concurrency: Yes** — source: `Documentation`. The default limit is 10 in-flight requests.
- **Usage: Yes** — source: `Dashboard`. API balance/usage is managed in the API dashboard.
- **Billing quota/balance: Yes** — source: `Dashboard`. Balance, automatic top-up and thresholds are configurable in the dashboard.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official API reference enumerates endpoints.
- **Official multiple API keys: Yes** — source: `Documentation`. Multiple keys are explicitly supported and billed under the same plan.
- **Limit increase: Yes** — source: `Documentation`. Larger-scale capacity is available by contacting Ideogram partnerships.

Official references:

- https://developer.ideogram.ai/ideogram-api/api-overview
- https://developer.ideogram.ai/ideogram-api/api-setup

### Flux (Black Forest Labs)

- **Quota/rate-limits API: Unknown** — source: `Unknown`. No public account limits-discovery endpoint was found.
- **RPM/RPS: Unknown** — source: `Unknown`. No single public RPM value applies across hosted FLUX endpoints.
- **TPM: N/A** — source: `Documentation`. Image generation is request/credit based, not TPM based.
- **Concurrency: Unknown** — source: `Unknown`. Current account concurrency is not publicly exposed as a universal value.
- **Usage: Partial** — source: `Dashboard`. Usage/credits are available through the BFL account console.
- **Billing quota/balance: Yes** — source: `Dashboard`. Credits and billing balance are dashboard-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The BFL API reference enumerates the current endpoints.
- **Official multiple API keys: Unknown** — source: `Unknown`. Official public documentation reviewed does not clearly state multi-key entitlement.
- **Limit increase: Partial** — source: `Dashboard`. Capacity depends on account/commercial arrangements; contact support for production scale.

Official references:

- https://docs.bfl.ai/
- https://docs.bfl.ai/quick_start/pricing

### Hedra

- **Quota/rate-limits API: Unknown** — source: `Unknown`. No public quota-discovery endpoint was found.
- **RPM/RPS: Unknown** — source: `Unknown`. No stable universal RPM is publicly documented.
- **TPM: N/A** — source: `Documentation`. Media generation is not documented with TPM accounting.
- **Concurrency: Partial** — source: `Dashboard`. Task concurrency/capacity is account-plan dependent.
- **Usage: Yes** — source: `Dashboard`. Credits and generation usage are visible in the Hedra account.
- **Billing quota/balance: Yes** — source: `Dashboard`. Plan credits and billing are dashboard-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official API reference enumerates endpoints.
- **Official multiple API keys: Unknown** — source: `Unknown`. Public documentation reviewed does not establish a multiple-key policy.
- **Limit increase: Yes** — source: `Dashboard`. Higher commercial capacity is available through plan upgrades/contact sales.

Official references:

- https://www.hedra.com/docs
- https://www.hedra.com/api

### Higgsfield

- **Quota/rate-limits API: Unknown** — source: `Unknown`. No public API returning quota or live limits was found.
- **RPM/RPS: Unknown** — source: `Unknown`. No universal public RPM value was found.
- **TPM: N/A** — source: `Documentation`. Media generation is not documented with TPM accounting.
- **Concurrency: Unknown** — source: `Unknown`. Account concurrency is not publicly documented as a stable universal value.
- **Usage: Partial** — source: `Dashboard`. Account credits/usage are dashboard based.
- **Billing quota/balance: Yes** — source: `Dashboard`. Plans and credits are managed in the account dashboard.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official API documentation is the endpoint catalogue.
- **Official multiple API keys: Unknown** — source: `Unknown`. No clear official public multi-key policy was found.
- **Limit increase: Partial** — source: `Dashboard`. Production capacity is handled through plan upgrades or business support.

Official references:

- https://docs.higgsfield.ai/
- https://higgsfield.ai/api

### FASHN

- **Quota/rate-limits API: Partial** — source: `API`. Credit information is available by API; the full live rate-limit configuration is documented rather than returned by one endpoint.
- **RPM/RPS: Yes** — source: `Documentation`. Defaults: /v1/run 50 per 60 seconds and /v1/status 50 per 10 seconds.
- **TPM: N/A** — source: `Documentation`. FASHN uses credits and requests, not token throughput.
- **Concurrency: Yes** — source: `Documentation`. Default concurrency is documented as 6 processing requests.
- **Usage: Yes** — source: `Response Headers`. x-fashn-credits-used reports credits consumed for a prediction; dashboard/API provide balance context.
- **Billing quota/balance: Yes** — source: `API`. Credits/balance can be queried using the documented credits API.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The official reference enumerates endpoint/model lifecycle and cost.
- **Official multiple API keys: Unknown** — source: `Unknown`. The public docs reviewed do not clearly establish multiple-key entitlement.
- **Limit increase: Yes** — source: `Documentation`. FASHN explicitly invites justified rate-limit increase requests via support.

Official references:

- https://docs.fashn.ai/api-overview/api-fundamentals
- https://docs.fashn.ai/api-reference/credits

### Grok (xAI)

- **Quota/rate-limits API: Partial** — source: `Dashboard`. Personalized per-model limits are shown in Console; no single public inference endpoint returns the complete matrix.
- **RPM/RPS: Yes** — source: `Documentation`. Per-model RPS is published and derived from RPM; personalized values are in Console.
- **TPM: Yes** — source: `Documentation`. Per-model TPM is published for token models.
- **Concurrency: Partial** — source: `Documentation`. Voice/session products publish concurrency; text/image/video mainly publish RPS/TPM.
- **Usage: Yes** — source: `Dashboard`. Team usage and cost tracking are available in Console.
- **Billing quota/balance: Yes** — source: `Dashboard`. Prepaid credits, invoices and spend-tier information are console-managed.
- **API endpoint catalogue/count: Yes** — source: `Documentation`. The REST/API references enumerate versioned endpoints.
- **Official multiple API keys: Yes** — source: `Dashboard`. Teams can manage multiple keys; team/model limits remain shared.
- **Limit increase: Yes** — source: `Documentation`. Spend tiers upgrade automatically; increases and enterprise capacity can be requested.

Official references:

- https://docs.x.ai/developers/rate-limits
- https://docs.x.ai/developers/management-api
- https://console.x.ai/

## Interpretation notes

- Unknown means the reviewed official public material did not establish the capability.
- Partial means only part of the requested metric is exposed, or availability varies by product/model/plan.
- Endpoint count means an authoritative catalogue/list is available; exact numeric totals are version-sensitive.
- Multiple keys do not imply multiplied limits; providers commonly enforce quota at project, team, workspace or account level.

This is a capability/evidence inventory, not a guarantee of the limits assigned to a particular account. Check the provider dashboard and contract before configuring production concurrency.

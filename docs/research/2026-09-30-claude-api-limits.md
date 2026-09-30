# Claude API Rate Limits and Headless Session Costs

**Date:** 2026-09-30
**Topic:** Claude API rate limits, costs, and subscription tiers for 7 parallel headless turns.

## Executive Summary
Running 7 parallel headless turns continuously will quickly stress standard API limits depending on the organization's tier. While prompt caching helps mitigate cost and ITPM (Input Tokens Per Minute) pressure, organizations scaling headless agents typically need to reach the **Scale** or **Custom** tier to sustain such workloads without encountering `429 Too Many Requests` errors.

## 1. Usage Tiers & Monthly Caps
Anthropic enforces organization-level tiers that govern monthly spend limits and API throughput ([Source: Anthropic API Limits Documentation](https://platform.claude.com/docs/en/api/rate-limits)):

*   **Start Tier**: ~$500/month cap. Ideal for initial development.
*   **Build Tier**: ~$1,000/month cap. For growing applications.
*   **Scale Tier**: ~$200,000/month cap. For high-volume production.
*   **Custom Tier**: No cap, negotiated limits via sales.

*Finding: 7 continuous headless agents (assuming ~24/7 operation) will rapidly exhaust the $1,000 Build tier cap. A Scale tier is mandatory for viable budget caps.*

## 2. Rate Limits (Throughput)
Limits are measured across three dimensions per model class:
*   **RPM (Requests Per Minute)**
*   **ITPM (Input Tokens Per Minute)**
*   **OTPM (Output Tokens Per Minute)**

**Caching impact**: Cached tokens from prompt caching **do not** count toward ITPM limits, which significantly increases effective throughput for context-heavy headless sessions ([Source: Anthropic Prompt Caching Specs](https://platform.claude.com/docs/en/api/prompt-caching)).

**7 Parallel Turns Analysis**:
*   If a turn takes 20 seconds, 7 parallel agents generate ~21 RPM.
*   Most standard Build/Scale tiers support >= 50 RPM, so RPM is unlikely to be the bottleneck.
*   However, if each turn generates a large amount of code, OTPM could become the primary bottleneck. Exceeding any metric triggers a `429 Too Many Requests` error requiring exponential backoff.

## 3. Token Pricing (As of Sept 2026)
Pricing per 1 Million Tokens (MTok) varies by model ([Source: Anthropic Pricing Page](https://anthropic.com/pricing)):
*   **Claude Sonnet 5.5**: $2 Input / $10 Output
*   **Claude Haiku 4.5**: $1 Input / $5 Output
*   **Claude Opus 5.5**: $4 Input / $20 Output
*   **Prompt Caching**: significantly reduces standard input costs for repeated context (e.g., Opus 5.5 cache reads are $0.20/MTok).

*Recommendation: To support 7 parallel headless turns continuously, use Sonnet 5.5 or Haiku 4.5 with maximal Prompt Caching, ensure your organization is at the **Scale Tier** (for adequate ITPM/OTPM and the $200k monthly cap), and implement robust exponential backoff + jitter for 429 and 529 errors.*

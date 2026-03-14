# Testing Methodology: Evaluation Workflows for Investment-Grade LLM Systems

**Document:** `testing-methodology.md`
**Suite:** Doomsday Prep Platform — Prompt Engineering Case Study
**Author framing:** Senior Prompt Engineer, investment-grade system design
**Primary axes:** Auditability · Output Reliability
**Secondary axis:** Cost control

---

## Design Philosophy

When I talk about "testing" an LLM-integrated system in the context of an investment-grade application, I mean something fundamentally different from unit testing a deterministic function. A prompt cannot have 100% code coverage in the traditional sense. A model cannot be mocked in a way that reflects real inference behaviour. And the failure modes — semantically correct but directionally inverted outputs, confident but hallucinated country codes, valid JSON with logically inconsistent field combinations — cannot be caught by type checks or assertion equality.

My testing methodology for this system is built around three convictions:

1. **Evaluation is a pipeline, not an event.** I do not test prompts once and ship them. I designed a continuous evaluation workflow where every prompt change passes through a structured review gate before reaching the production model routing layer.

2. **Human review is mandatory for high-stakes signal paths.** Automated evaluation can catch format violations and distribution anomalies. It cannot catch semantic drift — a `nuclear_posture` signal quietly being scored as `arms_control` because of a prompt reframing. That requires a human reviewer with domain knowledge, working from a structured rubric.

3. **The audit trail is the test infrastructure.** I designed the audit fields (`retry_count`, `fallback_used`, `model_used`, `processed_signals`, `capped_delta`) not only for runtime observability but as the data substrate for offline evaluation. Every production call emits the evidence needed to reconstruct, score, and compare any historical LLM decision.

---

## Evaluation Architecture Overview

The testing methodology operates across four stages:

```
Stage 1: Prompt Regression Harness (automated)
    ↓ Schema validity, field coverage, boundary compliance
Stage 2: Semantic Consistency Suite (automated + deterministic scoring)
    ↓ Signal direction audit, confidence calibration, category coverage
Stage 3: Human Review Panel (structured rubric, domain experts)
    ↓ Lineage sign-off for production promotion
Stage 4: Production Shadow Mode (live traffic, offline comparison)
    ↓ Drift detection, cost monitoring, alert triggers
```

Each stage produces a structured output that feeds the next. No stage is optional for a prompt change that affects the analysis system prompt or the user prompt template. Guide generation prompts follow a reduced workflow (Stages 1 and 3 only, no shadow mode required) because their outputs are not safety-critical — a poorly phrased water storage tip does not affect the risk score.

---

## Stage 1 — Prompt Regression Harness

### What I Test

The regression harness is a deterministic test suite that runs each prompt variant against a fixed corpus of synthetic news articles and validates the output structure. I designed the corpus to include:

- **Clean-signal articles:** Unambiguous military escalation, clear ceasefire announcements, explicit nuclear-posture statements. These should produce high-confidence outputs in the expected category with no ambiguity.
- **Ambiguous-signal articles:** Articles where the signal category is genuinely unclear — economic sanctions with military undertones, diplomatic language that could be read as either progress or stalling. These stress-test confidence calibration.
- **Out-of-scope articles:** Sports results, celebrity news, domestic crime. These should produce either an `other` category signal at low confidence, or an empty signal list with `analysis_notes` acknowledging the absence of relevant content.
- **Adversarial articles:** Deliberately crafted inputs that probe for prompt injection, JSON boundary violations, and category hallucination — a North Korea diplomatic meeting described in language that resembles a military mobilisation.

### What Constitutes a Regression

A prompt change causes a regression if any of the following holds on the fixed corpus:

| Condition | Threshold | Severity |
|---|---|---|
| JSON parse failure rate | > 0% on clean-signal articles | **Blocking** |
| 3-tier extraction fallback rate | > 5% of responses require Tier 3 | **Blocking** |
| Schema field missing rate | Any required field absent | **Blocking** |
| Category mismatch on clean articles | > 10% | **High** |
| Confidence out of [0.0, 1.0] range | Any instance | **Blocking** |
| `affected_country_codes` not ISO-3166-1 alpha-3 | > 2% | **High** |
| Out-of-scope article produces `raw_score > 5.0` | Any instance | **Medium** |

The blocking thresholds exist because any of those conditions propagate invalid data into the `DoomsdayScoringEngine`. The scoring engine's formula (`contribution = (raw_score / 10) * SIGNAL_SCALE_FACTOR * direction * cat_weight * country_modifier * confidence`) is deterministic — it will faithfully multiply a hallucinated `raw_score=9.8` into a large clock delta without raising an exception.

### Anchoring to Real Extraction Code

The regression harness exercises the exact extraction path used in production. I do not mock `_extract_json_from_response`. I run it:

```python
# backend/app/services/llm/base.py — lines 92–119 (verbatim)
# The 3-tier extraction cascade tested against every prompt variant:

def _extract_json_from_response(text: str) -> dict[str, Any]:
    """
    Robustly extract JSON from LLM response text.
    Handles markdown code fences and extra prose.
    """
    # Tier 1: direct parse — the expected happy path
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Tier 2: markdown code fence extraction
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Tier 3: outermost brace extraction — most permissive, last resort
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]!r}")
```

> **Annotation:** Testing against the real extraction function rather than a simplified version is critical. A prompt change that causes the model to wrap its output in prose ("Here is my analysis: {...}") would pass a test that only checks `json.loads(response)`. But Tier 1 would fail, Tier 2 would fail (no code fence), and only Tier 3 would recover the JSON — degrading extraction quality and adding latency. The regression harness surface this degradation as a Tier-3 rate increase before it reaches production.

### Regression Harness Output Format

Every harness run produces a machine-readable report:

```json
{
  "run_id": "prompt-v2.3.1-20260314T143200Z",
  "prompt_version": "2.3.1",
  "corpus_size": 45,
  "results": {
    "tier1_parse_success_rate": 0.91,
    "tier2_parse_success_rate": 0.07,
    "tier3_parse_success_rate": 0.02,
    "total_parse_failure_rate": 0.00,
    "schema_violations": [],
    "category_mismatch_rate": 0.04,
    "confidence_out_of_range": 0,
    "blocking_regressions": [],
    "high_severity_findings": []
  },
  "verdict": "PASS",
  "promoted_to": "stage_2"
}
```

The `run_id` uses the prompt version plus a UTC timestamp. This report is stored alongside the prompt text it evaluated and forms part of the promotion audit trail. No prompt advances to Stage 2 without a `"verdict": "PASS"` entry in the run log.

---

## Stage 2 — Semantic Consistency Suite

### The Problem Automated Harnesses Cannot Solve

Stage 1 validates structure. It cannot validate meaning. A prompt variant might produce perfectly valid JSON in which every `nuclear_posture` article is re-categorised as `diplomatic_breakdown` — because a reframing of the role description shifted the model's categorical intuitions. The JSON parses. The schema validates. The scoring engine runs. The clock deltas are completely wrong.

I designed Stage 2 to detect semantic drift using a cross-validation strategy:

**Baseline locking:** When I promote a prompt to production, I record the model's outputs on the full corpus as a **semantic baseline** — the ground-truth signal distribution for that prompt version. Category frequencies, average confidence per category, and directional distribution (escalating/de-escalating/neutral ratios per signal category) are all stored.

**Delta comparison:** A candidate prompt variant must produce a semantic distribution within defined tolerance bands of the baseline:

| Metric | Tolerance |
|---|---|
| Category frequency shift (any category) | ≤ 15% relative |
| Average confidence per category | ≤ 0.10 absolute |
| Sentiment direction ratio (escalating vs. de-escalating) | ≤ 20% relative |
| Mean `raw_score` per category | ≤ 1.0 absolute |

These tolerances are not arbitrary. They reflect the sensitivity of the downstream scoring formula. A 20% shift in escalating/de-escalating ratios across all signals translates directly into a directional bias in clock delta, which compounds across cycles.

### Cross-Provider Consistency Check

Because the system supports multiple LLM providers (Ollama for self-hosted, Anthropic for production), I run Stage 2 against all active providers simultaneously. Outputs are compared for:

- **Category agreement rate:** Do both providers categorise the same article the same way? I target ≥ 80% agreement on clean-signal articles.
- **Score magnitude correlation:** Do provider-specific `raw_score` distributions track each other? I use Spearman rank correlation; target ρ ≥ 0.75.
- **Confidence calibration alignment:** If Provider A reports 0.9 confidence on an article and Provider B reports 0.4, one of them is miscalibrated for this prompt. Articles with > 0.5 inter-provider confidence gap are flagged for human review in Stage 3.

This cross-provider check is operationally important because the `factory.py` routing layer selects providers based on availability and cost thresholds. A prompt that works for Anthropic but degrades Ollama's output quality would silently degrade system performance during Anthropic outages — exactly the scenario where reliability matters most.

---

## Stage 3 — Human Review Panel

### Why Human Review Is Non-Negotiable

Stages 1 and 2 are fast, cheap, and scale to thousands of articles. But they evaluate LLM outputs against their own past outputs — they cannot evaluate whether those outputs are *correct* against the world. For a system that influences risk scores read by end users as factual assessments of geopolitical risk, I consider human review of the signal categorisation non-negotiable before any production promotion.

I designed a structured review process with three roles:

| Role | Responsibility |
|---|---|
| **Prompt Author** | Submits the prompt change with written rationale, expected behaviour changes, and corpus diffs from Stage 2 |
| **Domain Reviewer** | Evaluates whether LLM signal categorisations are semantically correct — does this article genuinely warrant `nuclear_posture` or should it be `military_escalation`? Requires geopolitical domain knowledge, not ML expertise |
| **System Reliability Reviewer** | Evaluates whether the change degrades any reliability property — does it increase Tier-3 extraction rates, does it narrow the model's fallback behaviour, does it introduce any prompt injection surface? |

All three roles must sign off before promotion. The sign-off is recorded in the audit trail as a named event with the reviewer's identity, timestamp, and a structured verdict.

### The Review Rubric

The domain reviewer works from a standardised rubric applied to a sampled subset of the Stage 2 corpus results. The rubric covers:

**Categorisation accuracy:**
- Does the assigned `signal_category` match the article's primary risk dimension?
- Is the category the *most specific* applicable, or has the model over-generalised to `other`?
- Are multi-signal articles producing appropriately separated signal records, or is the model collapsing distinct signals into one?

**Scoring calibration:**
- Does the `raw_score` reflect genuine escalation magnitude, or is the model compressing to a narrow mid-range (3–7) to avoid strong claims?
- Are de-escalatory articles scoring ≤ 3.0? Are catastrophic-risk articles scoring ≥ 8.0?
- Is `confidence` inversely correlated with article ambiguity, as it should be?

**Reasoning quality:**
- Does the `reasoning` field (max 500 chars) accurately summarise the evidence basis for the score?
- Is it self-consistent with the numerical values — a high-confidence `raw_score=9.0` with reasoning that hedges heavily is a calibration failure?

**Country code accuracy:**
- Are `affected_country_codes` limited to ISO-3166-1 alpha-3 codes for countries substantively mentioned as parties to the risk?
- Is the requesting country always included (enforced downstream, but the prompt should not create hostile outputs that require correction)?

The domain reviewer records a verdict per sampled article: **APPROVE**, **FLAG**, or **REJECT**. A Flag triggers a written note with specific correction guidance. A Reject blocks promotion and requires a prompt revision cycle.

### Audit Record of the Review Process

Every human review produces a structured record stored with the prompt version:

```json
{
  "review_id": "review-v2.3.1-20260314T160000Z",
  "prompt_version": "2.3.1",
  "stage2_run_id": "prompt-v2.3.1-20260314T143200Z",
  "reviewers": {
    "prompt_author": {
      "name": "Senior PE",
      "verdict": "APPROVED",
      "timestamp": "2026-03-14T15:45:00Z",
      "rationale": "Role reframing reduces diplomatic_breakdown over-assignment on military articles"
    },
    "domain_reviewer": {
      "name": "Geopolitical Analyst",
      "verdict": "APPROVED",
      "timestamp": "2026-03-14T16:00:00Z",
      "sample_size": 15,
      "approve_count": 14,
      "flag_count": 1,
      "reject_count": 0,
      "flags": [
        {
          "article_id": "art_089",
          "note": "Sanctions article scored as military_escalation — should be sanctions_economic"
        }
      ]
    },
    "reliability_reviewer": {
      "name": "Systems Engineer",
      "verdict": "APPROVED",
      "timestamp": "2026-03-14T16:05:00Z",
      "tier3_rate_delta": "+0.01",
      "fallback_rate_delta": "0.00",
      "note": "Marginal Tier-3 rate increase is acceptable; no reliability regression"
    }
  },
  "overall_verdict": "APPROVED_WITH_FLAG",
  "promotion_target": "production"
}
```

The `APPROVED_WITH_FLAG` verdict records that the flag was acknowledged and accepted — the minor categorisation issue in `art_089` does not block promotion but is logged for monitoring in Stage 4. This creates a continuous improvement loop: flagged items accumulate into the next corpus revision.

---

## Stage 4 — Production Shadow Mode

### Comparing Old and New Prompt in Live Traffic

When I promote a new prompt version, I do not cut over immediately. I run both versions simultaneously against live traffic in shadow mode for a minimum of 72 hours:

- **Primary path:** Current production prompt version, scoring engine runs on its output.
- **Shadow path:** Candidate prompt version, scoring engine runs on its output in a separate ledger. The shadow score is **not** written to the user-facing database.

At the end of the shadow window, I compare the two ledgers:

| Comparison Metric | Alert Threshold |
|---|---|
| Mean `raw_score` delta (candidate vs. production) | > 0.5 per category |
| Clock delta distribution shift | > 10% change in mean delta magnitude |
| `fallback_used` rate (candidate) | > production rate by > 2 percentage points |
| `retry_count > 0` rate (candidate) | > production rate by > 5 percentage points |
| Token count per call (cost proxy) | > 10% increase |

If any alert threshold is breached, the shadow run is flagged. Automatic promotion does not occur. A follow-up review gate determines whether the delta is expected (a deliberate behaviour change that is working as intended) or anomalous (an unintended side effect of the prompt change).

### Using the Audit Trail as Shadow Infrastructure

The production audit trail I designed — `retry_count`, `fallback_used`, `model_used`, `processed_signals`, `capped_delta`, `raw_delta` — provides all the fields needed for shadow comparison without additional instrumentation. I collect identical envelope fields from both paths:

```python
# backend/app/services/llm/base.py — lines 185–218
# Success path audit fields (same structure for both production and shadow ledger):

return LLMAnalysisResponse(
    country_code=country_code,
    signals=signals,
    analysis_notes=payload.get("analysis_notes"),
    model_used=self.provider_name,    # ← identifies which prompt version served this call
    retry_count=attempt - 1,          # ← cost and reliability indicator
    fallback_used=False,              # ← degradation indicator
)
```

```python
# backend/app/services/clock/scoring_engine.py — lines 231–243
# Scoring output audit fields persist the full formula trace:

return ScoringOutput(
    country_code=inp.country_code,
    previous_score=inp.previous_score,
    raw_delta=round(raw_delta, 4),      # ← un-capped formula result
    capped_delta=round(capped_delta, 4), # ← actual applied delta
    new_score=round(new_score, 3),      # ← final bounded score
    signal_count=len(processed_signals),
    dominant_signal_category=dominant_category,
    fallback_used=False,
    processed_signals=processed_signals, # ← full per-signal audit record
)
```

> **Annotation:** The presence of `raw_delta` alongside `capped_delta` in every scoring record is specifically designed to support shadow comparison. A candidate prompt that consistently generates `raw_delta` values that hit the ±5s cap more frequently than the production prompt is applying too much force to the clock — a signal that its scoring distribution is shifted upward. I can detect this pattern from the stored `ScoringOutput` records without replaying any LLM calls.

---

## Investment-Grade Audit Trail Requirements

For a system used by financial decision-makers or operated under regulatory audit, I define the following minimum audit trail requirements. These are not aspirational — they describe what the current system already emits, by design.

### Per-Call Requirements

Every LLM call — whether successful, retried, or fully failed — must record:

| Field | Source | Purpose |
|---|---|---|
| `model_used` | `LLMAnalysisResponse.model_used` | Provider attribution for cost and liability |
| `retry_count` | `LLMAnalysisResponse.retry_count` | Reliability indicator; cost multiplier |
| `fallback_used` | `LLMAnalysisResponse.fallback_used` | Degraded operation flag |
| `country_code` | `LLMAnalysisResponse.country_code` | Scope of analysis |
| Timestamp | Application layer | Call timing for rate and latency analysis |
| `analysis_notes` | `LLMAnalysisResponse.analysis_notes` | Optional model narrative, preserved verbatim |

### Per-Signal Requirements

Every signal extracted from an LLM response must be stored as a `SignalRecord` with the full formula inputs, not just the output:

```python
# backend/app/schemas/doomsday.py — SignalRecord structure
# (as used in scoring_engine.py lines 176–186)

signal_record = SignalRecord(
    country_code=inp.country_code,
    signal_category=llm_signal.signal_category,   # LLM assignment
    raw_score=llm_signal.raw_score,               # LLM value [0.0, 10.0]
    sentiment=llm_signal.sentiment,               # LLM direction
    confidence=llm_signal.confidence,             # LLM confidence [0.0, 1.0]
    reasoning=llm_signal.reasoning,               # LLM text, preserved verbatim
    category_weight=cat_weight,                   # Deterministic registry lookup
    country_modifier=country_modifier,            # Deterministic registry lookup
    weighted_delta_contribution=round(contribution, 4),  # Formula output
)
```

> **Annotation:** I store both the LLM's raw values (`raw_score`, `confidence`, `sentiment`) and the deterministic weights applied to them (`category_weight`, `country_modifier`). This separation is essential for auditability: if a regulator or auditor challenges a clock score, I can show that the LLM contributed *these specific raw values*, and the scoring engine applied *these specific deterministic weights*, producing *this specific contribution*. Neither the LLM behaviour nor the formula weights are hidden behind an aggregate. Every operand in the formula is recoverable from stored data.

### Per-Cycle Requirements

Every scan cycle — the automated process that fetches news, runs LLM analysis, and updates country scores — must record an aggregate record that enables operational monitoring without querying individual signal records:

| Field | Type | Purpose |
|---|---|---|
| `cycle_id` | UUID | Unique cycle identifier |
| `started_at` | UTC datetime | Cycle start for latency tracking |
| `completed_at` | UTC datetime | Cycle duration |
| `countries_processed` | int | Scope |
| `llm_calls_attempted` | int | Total call volume |
| `llm_calls_succeeded` | int | Success rate denominator |
| `llm_fallback_used` | bool | Any fallback in this cycle |
| `total_signals_extracted` | int | LLM output volume |
| `scores_updated` | int | Downstream effect |

### Retention and Immutability Requirements

For investment-grade operation:

- **Signal records are append-only.** Once a `SignalRecord` is written, it is never modified. Score corrections are applied as new `ScoringOutput` records with a `correction_of` reference, not as in-place updates.
- **Guide versions follow the same principle.** The `GuideVersion` model stores versioned snapshots with explicit `version_number` and `rollback_available` flags. Rollback is implemented as a pointer change (`guide.current_version_id`), never as a content deletion:

```python
# backend/app/services/content/guide_service.py — lines 336–358
# Rollback is a read of the previous version, not a deletion:

async def rollback_guide_version(user: User, region: str, db: AsyncSession) -> dict:
    """Rollback to previous guide version. CLI: rollback --region=PT --to=previous"""
    ...
    previous = sorted_versions[-2]
    guide.current_version_id = previous.id    # pointer change only
    await db.commit()

    return {
        "rolled_back_to_version": previous.version_number,
        "region": region,
        "content_date": previous.created_at.isoformat(),
    }
```

> **Annotation:** I use pointer-based rollback rather than content restoration because it preserves the full version history as an immutable ledger. Both the "current" and "previous" versions remain in the database after rollback. An auditor can reconstruct the exact content that was served to any user at any point in time by querying `GuideVersion` ordered by `version_number`. This is the same principle used by event-sourced financial systems: the state is always reconstructable from the history.

- **Audit records are retained for a minimum of 90 days** in the base deployment. This covers one full quarterly audit cycle and satisfies most financial regulatory review windows. For higher-compliance deployments, the retention window is configurable at the infrastructure layer without code changes.

---

## Evaluation Workflow Summary

The following table maps each testing stage to its inputs, outputs, and the auditability artefact it produces:

| Stage | Input | Output | Audit Artefact |
|---|---|---|---|
| 1: Regression Harness | Prompt candidate + fixed corpus | Pass/Fail verdict + tier rates | `run_id` + JSON report, stored with prompt |
| 2: Semantic Suite | Stage 1 output + baseline distribution | Distribution delta report + provider agreement | Comparison JSON with per-metric deltas |
| 3: Human Review | Stage 2 output + review rubric | Named verdicts (Approve/Flag/Reject) | `review_id` JSON with reviewer identities and rationale |
| 4: Shadow Mode | Live traffic + both prompt versions | Shadow score ledger + alert flags | 72-hour comparison report with threshold analysis |

No prompt enters production without a complete lineage: Stage 1 run record → Stage 2 comparison record → Stage 3 review record → Stage 4 shadow report. The `prompt_version` string links all four records. An auditor who asks "why did the clock score change after the March 14 deployment?" can trace from the deployment timestamp to the prompt version, from the prompt version to the review record, and from the review record to the specific flag that was accepted into production.

This lineage is the testing methodology. It is not documentation of what I plan to build — it is a description of the audit infrastructure that already exists by virtue of the system design I made from the beginning.

---

## Cost Control Implications of the Testing Methodology

Shadow mode requires running two LLM provider calls per live news article for 72 hours. For the current traffic volume, this is the most expensive testing operation in the pipeline. I designed the shadow window to be configurable — 72 hours is the minimum; 24 hours is acceptable for low-risk prompt changes (system prompt wording only, no category list modifications); 96 hours is required for changes that modify the signal category taxonomy.

The evaluation corpus for Stages 1 and 2 is intentionally small (45 articles) and static, keeping per-run costs bounded and reproducible. Running against a dynamic or large corpus would introduce variability that makes Stage 2 delta comparisons unreliable — and would cost more per run, reducing the incentive to run the harness frequently.

Prompt regression testing is cheap precisely because I designed it to be cheap. The 45-article corpus was sized to cover all 10 signal categories with at least 3 articles each (30 targeted) plus 15 ambiguous and adversarial articles. Coverage is qualitative, not statistical — I am testing prompt *behaviour*, not estimating signal *prevalence*.

---

*Document ends. Cross-references: `audit-trail.md` (runtime audit fields), `reliability-engineering.md` (3-tier extraction cascade), `deterministic-fallback.md` (fallback scoring behaviour).*

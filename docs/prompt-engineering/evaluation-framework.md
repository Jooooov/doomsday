# Evaluation Framework: Model Selection Rubrics, Prompt Quality Gates, and Risk-Based Scoring Criteria

**Document:** `evaluation-framework.md`
**Suite:** Doomsday Prep Platform — Prompt Engineering Case Study
**Author framing:** Senior Prompt Engineer, investment-grade system design
**Primary axes:** Auditability · Output Reliability
**Secondary axis:** Cost control

---

## Why Evaluation Must Be a Design Artefact, Not a Post-Hoc Activity

In most LLM integrations I have reviewed, evaluation is treated as something that happens after a prompt is written — a round of manual spot-checks, perhaps a small benchmark dataset, and a subjective "it looks good" before deployment. That approach is not appropriate for a system where LLM output influences a risk score that end users read as authoritative.

I designed the evaluation framework for the Doomsday Prep Platform as a **first-class architectural concern**. Every metric I evaluate against is observable from the audit fields already embedded in the production schemas — `retry_count`, `fallback_used`, `signal_count`, `raw_delta`, `capped_delta`, `weighted_delta_contribution`. The evaluation framework does not require a separate test harness, a golden dataset, or manual review cycles for routine operation. It is a set of defined criteria and threshold rules applied to data the system produces as a natural by-product of serving production traffic.

This document describes the three components of that framework: the **model selection rubric** I use to choose between providers, the **prompt quality gates** I apply before a prompt change reaches production, and the **risk-based scoring criteria** that determine whether the LLM's output is having a calibrated, auditable effect on the clock.

---

## Part 1 — Model Selection Rubric

### The Selection Problem

The system supports two LLM providers: a locally-hosted Ollama instance and the Anthropic API. The provider is selected via `LLM_PROVIDER` environment variable and resolved at startup through the factory:

```python
# backend/app/services/llm/factory.py (verbatim)

@lru_cache(maxsize=1)
def get_llm() -> BaseLLM:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "ollama":
        from app.services.llm.ollama import OllamaLLM
        return OllamaLLM()
    elif provider == "anthropic":
        from app.services.llm.anthropic_llm import AnthropicLLM
        return AnthropicLLM()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use 'ollama' or 'anthropic'.")
```

> **Annotation:** `@lru_cache(maxsize=1)` means the provider is instantiated once per process lifetime. Provider selection is a deployment-time decision, not a request-time decision. Switching providers requires an environment variable change and a process restart — both of which are auditable events in any deployment log. This constraint shapes the selection rubric: I am not choosing a provider per-call; I am choosing one for a deployment epoch.

The rubric I apply to select between providers has four axes, each observable from production data and each grounded in a concrete system requirement.

---

### Rubric Axis 1 — JSON Compliance Rate

**Definition:** The fraction of LLM calls for which `_extract_json_from_response()` succeeds on **Tier 1** (direct `json.loads()` without regex fallback).

**Why Tier 1 specifically:** I designed the 3-tier extraction cascade to tolerate non-compliant responses, but each tier below Tier 1 is a signal of degraded output quality. A provider whose responses routinely require Tier 2 (markdown fence stripping) or Tier 3 (brace-boundary extraction) is consuming more CPU, more diagnostic attention, and — critically — introducing a higher probability of Tier 3 failure leading to retry:

```python
# backend/app/services/llm/base.py — lines 97–119 (verbatim)

def _extract_json_from_response(text: str) -> dict[str, Any]:
    # Tier 1 — direct parse: zero overhead, zero ambiguity
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Tier 2 — markdown fence extraction: recovery for chat-tuned models
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Tier 3 — brace-boundary extraction: last resort
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]!r}")
```

**Observable proxy:** `retry_count` on `LLMAnalysisResponse`. A `retry_count > 0` on a successful call means at least one prior attempt raised a `ValueError` from the extraction cascade — the call was re-issued at full token cost. The `retry_count` distribution across a scan cycle is the closest available proxy for Tier 1 compliance rate without instrumenting the extraction function's internal tier transitions.

**Selection threshold I apply:** A provider producing more than 5% of calls with `retry_count > 0` across consecutive scan cycles is under review. More than 10% triggers provider switch evaluation.

**Why I do not fabricate measured numbers:** The 5% and 10% figures above are the design thresholds I chose based on the cost model — not measured baselines from a completed run. At 3 retries maximum and a 6-hour cycle cadence, a 5% retry rate on a 20-country scan means roughly 1 additional LLM call per cycle. At 10%, it is 2 additional calls. Both are within tolerance. Above 10%, the cost-quality trade-off shifts. The actual measured rates are established during the first sustained production run; this framework describes what I will measure and what actions the measurements trigger.

---

### Rubric Axis 2 — Schema Validity Rate

**Definition:** The fraction of signals that pass `_parse_signals()` validation without being skipped.

```python
# backend/app/services/llm/base.py — lines 226–254 (annotated)

def _parse_signals(
    self, payload: dict[str, Any], country_code: str
) -> list[LLMSignalOutput]:
    raw_signals = payload.get("signals", [])
    if not isinstance(raw_signals, list):
        logger.warning("LLM returned non-list 'signals' field for %s", country_code)
        return []

    validated: list[LLMSignalOutput] = []
    for i, raw in enumerate(raw_signals):
        try:
            signal = LLMSignalOutput.model_validate(raw)     # ← Pydantic validation
            if country_code not in signal.affected_country_codes:
                signal.affected_country_codes.append(country_code)
            validated.append(signal)
        except Exception as exc:
            logger.warning(
                "Skipping invalid signal %d for %s: %s — data: %s",
                i, country_code, exc, raw,
            )

    return validated
```

> **Annotation:** Pydantic's `model_validate()` enforces the `LLMSignalOutput` schema, including field presence, type coercion, and range constraints (e.g. `raw_score: float = Field(..., ge=0.0, le=10.0)`). A signal that passes JSON extraction but fails schema validation is silently skipped with a WARNING log. It does not cause a retry — I designed it this way because partial signal lists are preferable to zero-signal fallbacks. But a provider that regularly produces structurally invalid signal fields (wrong types, out-of-range scores, missing required fields) represents a prompt-model alignment failure worth investigating.

**Selection threshold I apply:** A skip rate exceeding 15% of signals across a scan cycle indicates the model is producing structurally malformed fields — out-of-range scores, wrong sentiment enum values, or missing required keys. This warrants prompt revision before provider revision; the cause is more likely a model-prompt fit issue than a model quality issue.

---

### Rubric Axis 3 — Signal Yield Rate

**Definition:** The fraction of LLM calls that produce at least one valid signal (`signal_count > 0`).

**Observable proxy:** `signal_count` and `fallback_used` on `ScoringOutput`, and `llm_calls_succeeded / llm_calls_attempted` on `ScanCycleResult`:

```python
# backend/app/schemas/doomsday.py — lines 148–161 (verbatim)

class ScanCycleResult(BaseModel):
    scan_run_id: uuid.UUID
    started_at: datetime
    completed_at: datetime
    status: str
    country_results: list[CountryDeltaResult]
    total_articles_fetched: int
    total_signals_generated: int
    llm_calls_attempted: int        # ← total calls issued
    llm_calls_succeeded: int        # ← calls that returned ≥1 valid signal
    llm_fallback_used: bool         # ← True if any country used empty-signal fallback
```

**Selection threshold I apply:** `llm_calls_succeeded / llm_calls_attempted` below 0.85 across three consecutive scan cycles indicates a systemic provider problem. Below 0.70, I consider it an outage condition and switch providers via environment variable restart.

**Why this threshold does not depend on benchmark scores:** The yield rate threshold is a **reliability requirement**, not a performance claim. A system that fails to produce usable signals for more than 30% of countries in a cycle is no longer providing LLM-informed risk assessment — it is running on mean-reversion for a third of its coverage. That is a meaningful degradation in the system's intended capability, regardless of whether any benchmark dataset exists.

---

### Rubric Axis 4 — Operational Cost per Signal

**Definition:** The amortised token cost of producing one valid signal, accounting for retries.

**Formula:**

```
cost_per_signal = (total_input_tokens + total_output_tokens) × price_per_token
                  ÷ total_signals_generated
```

This is a secondary axis. I include it explicitly because cost control is a real constraint in a production system, and it interacts with the primary reliability axes in a non-obvious way. A provider with a higher per-call token price may be cheaper per-signal if its JSON compliance rate is significantly higher — because fewer retries means fewer redundant calls at full input token cost.

The **retry cost multiplier** is bounded by the retry loop design:

```python
# backend/app/services/llm/base.py — lines 163–204

for attempt in range(1, self.max_retries + 1):   # max_retries = 3
    try:
        raw_text = await self._call_llm(...)
        payload = _extract_json_from_response(raw_text)
        ...
        return LLMAnalysisResponse(..., retry_count=attempt - 1, ...)

    except Exception as exc:
        last_error = exc
        if attempt < self.max_retries:
            await asyncio.sleep(2 ** attempt)      # 2s, 4s backoff
```

Maximum retry cost on total failure: 3× the input token cost for one country call. For a 20-country scan cycle with 100% failure rate, total cost would be 3× what a perfectly compliant provider would cost. This upper bound — 3× nominal cost — is the cost containment guarantee provided by the `max_retries=3` ceiling. The `LLM_MAX_RETRIES` setting is externalised precisely so this ceiling can be tightened in cost-sensitive deployments without code changes.

**Article-level cost control** further bounds input token cost by truncating article content at 800 characters before prompt assembly:

```python
# backend/app/services/llm/base.py — _build_articles_text (lines 78–89)

f"{art.content[:800]}"   # ← hard truncation: token budget ceiling per article
```

The 800-character ceiling is a deliberate cost-accuracy tradeoff grounded in journalistic structure: the primary claim, parties, and scale descriptor of a news article almost always appear in the opening two paragraphs. The tail adds interpretive nuance that rarely changes `signal_category` or `sentiment` direction — but does add tokens to every call. I set this at 800 characters to capture the essential signal while capping per-article token cost.

---

### Model Selection Decision Matrix

When evaluating a provider change, I apply the four rubric axes in order:

| Rubric axis | Measurement source | Pass threshold | Action on fail |
|---|---|---|---|
| JSON Compliance Rate | `retry_count` distribution across cycle | `retry_count > 0` for < 5% of calls | Investigate prompt-model fit; consider provider switch |
| Schema Validity Rate | WARNING log skip rate vs. payload signal count | Skip rate < 15% of signals | Prompt revision first; provider switch if persists |
| Signal Yield Rate | `llm_calls_succeeded / llm_calls_attempted` | Ratio ≥ 0.85 sustained | Provider switch below 0.70; investigation between 0.70–0.85 |
| Cost per Signal | Token counts × rate card ÷ signals | New provider ≤ 120% of incumbent cost per signal | Cost premium requires corresponding reliability gain |

**I do not include subjective quality assessments in this matrix.** A provider is selected or retained based on observable, queryable data from the production audit trail — not on the impressiveness of its reasoning text or its marketing claims. This is the correct approach for an investment-grade system: selection criteria that cannot be operationalised into measurements are not selection criteria.

---

## Part 2 — Prompt Quality Gates

### What "Prompt Quality" Means in This System

A prompt is production-quality in this system if and only if it satisfies four gates. Not aspirational properties — gates, meaning conditions that must hold before a prompt change is deployed to production.

I define these gates operationally, not aesthetically. A prompt is not "good" because it is well-written or comprehensive; it is good because the system can demonstrate specific, observable properties when using it.

---

### Gate 1 — Schema Contract Integrity

**Requirement:** The system prompt must contain the full, verbatim JSON output contract. Named schema references are not acceptable.

The production `ANALYSIS_SYSTEM_PROMPT` satisfies this gate:

```python
# backend/app/services/llm/base.py — lines 53–66 (verbatim)

Respond ONLY with valid JSON matching this exact schema:
{
  "signals": [
    {
      "signal_category": "string",
      "raw_score": 0.0,
      "sentiment": "escalating|de-escalating|neutral",
      "confidence": 0.0,
      "reasoning": "string",
      "affected_country_codes": ["ISO3"]
    }
  ],
  "analysis_notes": "optional overall summary"
}
```

> **Annotation:** The phrase "Respond ONLY with valid JSON" is not a suggestion. The "ONLY" is load-bearing — it eliminates the model's latitude to add conversational framing, analysis preambles, or caveats. Without "ONLY", models fine-tuned on chat data default to prose-then-JSON, which forces the extraction cascade to Tier 2 or Tier 3 on every call. The schema is reproduced inline rather than referenced by name because the model must see the exact structure it is expected to produce at inference time.

**Gate evaluation procedure:** After any change to `ANALYSIS_SYSTEM_PROMPT`, I issue ten test calls against the target model with representative article inputs covering mixed geopolitical topics. Tier 1 extraction must succeed on all ten. If any call requires Tier 2 or Tier 3, the prompt change does not proceed to production — the schema contract phrasing is revised until Tier 1 compliance reaches 10/10.

**Gate 1 for `GUIDE_SYSTEM_PROMPT`:** The guide system prompt uses a minimalist design with a single terminal instruction:

```python
# backend/app/services/content/guide_service.py — lines 26–30 (verbatim)

GUIDE_SYSTEM_PROMPT = """You are a civil preparedness expert writing practical survival guides.
Be specific about quantities using the user's household profile.
Use metric units. Always include a brief legal disclaimer per section.
Content is informational only — not a substitute for official civil protection guidance.
Return valid JSON only."""
```

For this prompt, Gate 1 evaluates whether the user-prompt-embedded JSON schema template (the `Return JSON: { "title": str, ... }` block) is structurally matched by the model's output. The schema contract is split across system and user prompts — a deliberate architectural choice described in `prompt-decomposition.md` — but the gate condition remains identical: schema match rate = 100% on a test corpus before deployment.

---

### Gate 2 — Signal Category Coverage

**Requirement:** The prompt must produce signals across at least 4 distinct signal categories when given a mixed-topic article batch covering diverse geopolitical events.

The `ANALYSIS_SYSTEM_PROMPT` defines 10 signal categories:

```python
# backend/app/services/llm/base.py — lines 42–51 (verbatim)

Signal categories:
- military_escalation: Troop movements, weapons deployments, active combat
- nuclear_posture: Nuclear alerts, doctrine changes, test launches, arsenals
- cyber_attack: State-sponsored cyberattacks on critical infrastructure
- sanctions_economic: Economic warfare, trade blocks, financial weapons
- diplomatic_breakdown: Ambassador recalls, treaty withdrawals, failed negotiations
- civilian_impact: Humanitarian crises, refugee flows, civilian casualties
- peace_talks: Negotiations, ceasefires, diplomatic progress
- arms_control: Arms control agreements, disarmament, treaties
- propaganda: State propaganda, information warfare, narratives
- other: Any other relevant signals
```

**Why coverage matters for gate quality:** A model that maps all signals to `military_escalation` regardless of article content is not performing risk classification — it is applying a single label. The `dominant_signal_category` field on `ScoringOutput` makes this detectable at the cycle level. But detecting it after deployment is not acceptable; this gate tests for the failure mode before deployment.

**Gate evaluation procedure:** I run a calibration batch of 20 article inputs, explicitly spanning articles that should produce `diplomatic_breakdown`, `peace_talks`, `nuclear_posture`, `sanctions_economic`, `cyber_attack`, and `civilian_impact` signals. The output must include at least 4 distinct `signal_category` values across the batch. Fewer than 4 indicates category collapse — the model-prompt combination fails this gate.

**Why 4, not 10:** I do not require all 10 categories to appear in a 20-article batch. Some categories (`arms_control`, `propaganda`) require specific article types that may not all appear in a given test corpus. The gate tests that the model's taxonomy is functional across the most common categories, not that it covers every edge case on a fixed test set.

---

### Gate 3 — Score Range Utilisation

**Requirement:** The `raw_score` values produced by the prompt-model combination must span a minimum of 4.0 units across a calibration batch.

The scoring engine normalises `raw_score` as the primary LLM-to-delta conversion:

```python
# backend/app/services/clock/scoring_engine.py — lines 166–173 (annotated)

contribution = (
    (llm_signal.raw_score / 10.0)   # ← normalise to 0.0–1.0
    * SIGNAL_SCALE_FACTOR
    * direction
    * cat_weight
    * country_modifier
    * llm_signal.confidence
)
```

**Why score range matters:** If the model consistently returns `raw_score` values in the 7.0–9.0 range regardless of article content, the scoring engine produces a biased distribution of `capped_delta` values — one that is systematically negative (escalating) rather than reflecting the actual news mix. The `raw_delta` versus `capped_delta` pair reveals whether this is happening:

```python
# backend/app/services/clock/scoring_engine.py — line 25 (verbatim)
# Note: capped_delta is the ACTUAL change stored in DB (audit trail).
```

If `raw_delta` is consistently larger than `capped_delta` — the ±5-second cap is binding on most cycles — the model is over-scoring.

**Gate evaluation procedure:** Across a calibration batch of 20 calls spanning explicitly escalatory, de-escalatory, and neutral article batches:
1. Range condition: `max(raw_score) - min(raw_score) ≥ 4.0`
2. De-escalation presence: at least 3 calls producing a `raw_score ≤ 3.5` (genuine de-escalation or neutral content)
3. High-confidence escalation: at least 3 calls producing a `raw_score ≥ 7.0` with `sentiment = "escalating"`

A model-prompt combination that cannot produce low `raw_score` values cannot model de-escalation. A system that cannot model de-escalation cannot represent world events accurately — it can only push the clock toward midnight, never away from it.

---

### Gate 4 — Confidence Variance

**Requirement:** The `confidence` field must vary by at least 0.15 between high-quality article batches and low-quality/vague article batches.

`confidence` is not decorative in this system. It gates the weight of every signal in the scoring formula:

```python
# backend/app/services/clock/scoring_engine.py — line 173 (verbatim)

contribution = (
    (llm_signal.raw_score / 10.0)
    * SIGNAL_SCALE_FACTOR
    * direction
    * cat_weight
    * country_modifier
    * llm_signal.confidence          # ← gates impact proportional to model certainty
)
```

A model that returns `confidence=0.9` on every signal regardless of article quality is functionally equivalent to removing the confidence multiplier from the formula. All signals receive full weight; ambiguous events are treated as certain events.

**Gate evaluation procedure:** I construct two batches:
- **High-quality batch:** Clear, specific, attributed articles reporting direct geopolitical actions (troop deployments with named units, diplomatic communiqués with named parties, sanctions with cited legal mechanisms)
- **Low-quality batch:** Speculative opinion pieces, vague regional-tension reports, social media summaries with no primary source attribution

`mean(confidence, high-quality batch) - mean(confidence, low-quality batch)` must be ≥ 0.15. This gap ensures the `confidence` field is functioning as a quality signal in the contribution formula, not as a constant.

**Why 0.15:** At `confidence=0.9` versus `confidence=0.75`, the contribution difference is 17% — meaningful enough to materially affect whether a signal's contribution crosses a threshold in the context of the ±5-second cap. Below a 0.15 gap, the `confidence` field's variation is noise rather than a quality discriminator.

---

### Prompt Quality Gate Summary

| Gate | Condition | Pass criterion | Failure consequence |
|---|---|---|---|
| **Gate 1 — Schema Contract** | All test calls reach Tier 1 extraction | 10/10 calls: direct `json.loads()` succeeds | Prompt phrasing revision; no deployment |
| **Gate 2 — Category Coverage** | Output spans minimum distinct categories | ≥ 4 distinct `signal_category` values in 20-call batch | Prompt taxonomy revision; no deployment |
| **Gate 3 — Score Range** | LLM uses full scoring scale | Range ≥ 4.0; de-escalation presence confirmed | Prompt calibration instruction revision; no deployment |
| **Gate 4 — Confidence Variance** | Confidence discriminates article quality | High-low quality gap ≥ 0.15 | Prompt confidence instruction revision; no deployment |

All four gates must pass before any prompt change enters production. There is no waiver process. A prompt that passes three of four gates is not "almost ready" — it has a specific failure mode that will degrade the system in a specific way, and that failure mode must be resolved.

---

## Part 3 — Risk-Based Scoring Criteria

### What Scoring Criteria Govern

The audit fields described in `audit-trail.md` produce three categories of quality signal for the scoring system. I organise my ongoing system health assessment around these categories: **reliability criteria** (is the LLM producing usable output?), **calibration criteria** (are the outputs having appropriate magnitude effects on the clock?), and **coverage criteria** (is the clock's movement reflecting the actual diversity of world events?). Each criterion has specific, queryable database fields that evidence its current state.

---

### Scoring Criterion 1 — Reliability: LLM Layer Uptime

**Fields:** `fallback_used` (on `ScoringOutput`, `CountryDeltaResult`, `ClockSnapshotResponse`), `retry_count` (on `LLMAnalysisResponse`), `llm_calls_succeeded / llm_calls_attempted` (on `ScanCycleResult`).

**Risk classification:**

| Condition | Risk level | Response |
|---|---|---|
| `fallback_used = FALSE` for all countries; `retry_count = 0` for ≥ 95% of calls | Green — normal operation | No action |
| `retry_count > 0` for 5–10% of calls; no fallback | Amber — extraction pressure | Investigate prompt-model fit; check provider error logs |
| `fallback_used = TRUE` for any country in a cycle | Amber — partial degradation | Review `analysis_notes` for error type; assess whether affected countries are geopolitically significant this cycle |
| `fallback_used = TRUE` for > 30% of countries in a cycle | Red — systemic degradation | Provider switch evaluation; check `model_used` to confirm scope |
| `llm_calls_succeeded = 0` for a full cycle | Red — complete LLM outage | Switch `LLM_PROVIDER` via environment variable; restart service |

**Why `fallback_used` is the primary reliability indicator, not an error log:**

The scoring engine's `_score_fallback()` path is a designed degraded operating mode — the clock continues running on mean-reversion, not frozen. An operator needs to know whether any given historical snapshot was driven by LLM analysis or by mean-reversion, and that information must be in the data record, not in a log file:

```python
# backend/app/services/clock/scoring_engine.py — lines 331–358 (verbatim)

def _score_fallback(self, inp: ScoringInput, regional_anchor: float) -> ScoringOutput:
    """
    Fallback scoring when the LLM returned no signals.
    Mean-reversion rate: 10% of the gap per cycle, capped at ±MAX_DELTA.
    """
    gap = regional_anchor - inp.previous_score
    raw_delta = gap * 0.10
    capped_delta = self._apply_delta_cap(raw_delta)
    new_score = self._apply_score_bounds(inp.previous_score + capped_delta)

    return ScoringOutput(
        ...
        raw_delta=round(raw_delta, 4),
        capped_delta=round(capped_delta, 4),
        new_score=round(new_score, 3),
        signal_count=0,
        dominant_signal_category=None,
        fallback_used=True,          # ← audit flag: mean-reversion applied
        processed_signals=[],
    )
```

> **Annotation:** The audit query that surfaces reliability state is: `SELECT country_code, snapshot_ts, fallback_used, signal_count FROM clock_snapshots WHERE fallback_used = TRUE ORDER BY snapshot_ts DESC`. This query requires no log access, no external tool, and no post-hoc reconstruction. It is available to any analyst with read access to the database. I designed the schema this way because in a financial system context, auditability means answering compliance questions from data, not from logs.

**The two distinct fallback modes and their audit distinction:**

The scoring engine implements two fallback modes. Both produce `fallback_used=True`, but their `raw_delta` values differ — and that difference is auditable:

```python
# backend/app/services/clock/scoring_engine.py — lines 374–388 (verbatim)

def _score_error_fallback(self, inp: ScoringInput) -> ScoringOutput:
    """Emergency fallback on exception — zero delta, keep previous score."""
    return ScoringOutput(
        ...
        raw_delta=0.0,       # ← zero: emergency stop, not mean-reversion
        capped_delta=0.0,
        new_score=round(self._apply_score_bounds(inp.previous_score), 3),
        fallback_used=True,
        processed_signals=[],
    )
```

**Audit query to distinguish modes:** `WHERE fallback_used = TRUE AND raw_delta != 0.0` returns mean-reversion records (LLM unavailable, graceful degradation). `WHERE fallback_used = TRUE AND raw_delta = 0.0` returns exception records (scoring engine error, emergency stop). Both are auditable; both are distinct; neither is silent.

---

### Scoring Criterion 2 — Calibration: Delta Cap Activation Rate

**Fields:** `raw_delta` and `capped_delta` on `ScoringOutput` and `ClockSnapshotResponse`.

The hard ±5-second cap is applied in the scoring engine before writing the final score:

```python
# backend/app/services/clock/scoring_engine.py — lines 194–200 (verbatim)

raw_delta = sum(s.weighted_delta_contribution for s in processed_signals)

# ── Cap ───────────────────────────────────────────────────────────────────
capped_delta = self._apply_delta_cap(raw_delta)

# ── Compute new score ─────────────────────────────────────────────────────
new_score = self._apply_score_bounds(inp.previous_score + capped_delta)
```

```python
# backend/app/services/clock/scoring_engine.py — lines 323–325 (verbatim)

def _apply_delta_cap(self, raw_delta: float) -> float:
    """Clamp raw_delta to ±MAX_DELTA_PER_CYCLE (hard constraint)."""
    return max(-self.max_delta, min(self.max_delta, raw_delta))
```

Both values are persisted to the database. The scoring engine module docstring explicitly identifies `capped_delta` as an audit trail field:

```python
# backend/app/services/clock/scoring_engine.py — line 25 (verbatim)
# Note: capped_delta is the ACTUAL change stored in DB (audit trail).
```

**Risk classification:**

| Condition | Interpretation | Action |
|---|---|---|
| `abs(raw_delta - capped_delta) < 0.01` for ≥ 95% of cycles | Cap not binding — scoring weights well-calibrated | No action |
| `abs(raw_delta) > abs(capped_delta)` for 10–25% of cycles | Cap occasionally binding — normal in high-intensity news periods | Monitor; acceptable |
| `abs(raw_delta) > abs(capped_delta)` for > 25% of cycles | Cap chronically binding — `SIGNAL_SCALE_FACTOR` or category weights too aggressive | Scoring weight recalibration review |
| `abs(raw_delta) < 0.05` for > 80% of cycles | Systematic under-scoring — model returning low scores or model output dominated by `neutral` sentiment | Prompt review; confidence-calibration check |

**Calibration audit query:** `SELECT country_code, snapshot_ts, raw_delta, delta_applied, (raw_delta - delta_applied) AS cap_absorption FROM clock_snapshots WHERE ABS(raw_delta - delta_applied) > 0.01 ORDER BY ABS(cap_absorption) DESC`. Any row in this result represents a cycle where the hard cap was binding. The distribution of `cap_absorption` values across time is the primary diagnostic for whether scoring weights need adjustment.

**Why storing both `raw_delta` and `capped_delta` is not redundant:** The distinction is material for scoring system auditability. If `raw_delta = 8.3` and `capped_delta = 5.0`, a reviewer can see exactly how much the LLM signals wanted to move the clock versus how much the deterministic safety bounds allowed. Storing only `capped_delta` would hide whether the cap was binding — making it impossible to distinguish a 5.0-second movement that was exactly the right magnitude from one that was constrained from 8.3 by the safety boundary.

---

### Scoring Criterion 3 — Coverage: Signal Category Distribution

**Fields:** `dominant_signal_category` on `ScoringOutput` and `CountryDeltaResult`; `signal_category` on individual `SignalRecord` entries in `processed_signals`.

**Risk classification:**

| Condition | Interpretation | Action |
|---|---|---|
| Dominant category varies across countries and cycles | Healthy — model responding to content, not applying a fixed label | No action |
| Same dominant category for > 70% of all countries in one cycle | Possible genuine clustering — may reflect a specific news period | Cross-reference against article corpus to distinguish real clustering from model failure |
| Same dominant category for > 70% of countries across 3+ consecutive cycles | Likely category collapse — model not discriminating between signal types | Prompt revision targeting category specificity; re-run Gate 2 |
| `signal_category = "other"` for > 30% of signals in a cycle | Taxonomy mapping failure — model not mapping articles to defined categories | Review signal category definitions in `ANALYSIS_SYSTEM_PROMPT`; consider adding discriminating examples |

**Coverage audit query:** `SELECT dominant_signal_category, COUNT(*) AS cycle_count, COUNT(DISTINCT country_code) AS country_coverage FROM scoring_outputs GROUP BY dominant_signal_category ORDER BY cycle_count DESC`. If one category dominates this distribution across time, it is a signal that either the news environment is genuinely dominated by one event type or the model has collapsed its taxonomy.

**The context check — distinguishing real clustering from model failure:** Before treating category clustering as a model failure, I cross-reference `dominant_signal_category` against the actual article corpus processed in those cycles. If the world is genuinely experiencing a period of high `nuclear_posture` news, clustering in that category is correct classification, not a model failure. The distinction between correct clustering and taxonomy collapse is only resolvable by examining the article corpus — not by examining model outputs alone. This is why I designed the `processed_signals` audit field to carry `article_title` and `article_url` provenance on every `SignalRecord`: post-hoc verification is a database query, not an investigation.

```python
# backend/app/schemas/doomsday.py — SignalRecord provenance fields (verbatim)

class SignalRecord(BaseModel):
    ...
    # Article provenance
    article_url: str | None = None
    article_title: str | None = None
    article_published_at: datetime | None = None
    article_source: str | None = None
```

---

## How the Three Parts Compose

The evaluation framework is a sequential assessment protocol, not three independent tools:

```
Before any prompt change is deployed:
  Gate 1 (schema contract) → Gate 2 (category coverage) → Gate 3 (score range) → Gate 4 (confidence variance)
  All four gates must pass. Any gate failure blocks deployment and specifies the revision needed.

Before any provider change is made:
  Rubric Axis 1 (JSON compliance) + Axis 2 (schema validity) + Axis 3 (signal yield) + Axis 4 (cost per signal)
  Assessed across ≥ 2 weeks of production data. Decision recorded with measured values as evidence.

After each production scan cycle (ongoing):
  Criterion 1 (reliability) → Criterion 2 (calibration) → Criterion 3 (coverage)
  Assessed from ScanCycleResult and ScoringOutput records. Risk-classified and acted on per the tables above.
```

The architecture of this evaluation framework reflects a deliberate choice: **the audit fields that serve operations serve evaluation.** I did not design a separate evaluation layer with separate metrics. The same `retry_count`, `fallback_used`, `raw_delta`, `capped_delta`, `signal_count`, and `dominant_signal_category` fields that an on-call operator queries to diagnose a score anomaly are the fields I query to assess whether the prompt and model are performing within specification.

This unification is the appropriate design for an investment-grade system. A separate evaluation layer that tracks different metrics from what is persisted in production would create the possibility of the evaluation claiming one thing while the database records another. By grounding evaluation entirely in production schema fields, I ensure the evaluation framework and the audit trail are the same artefact — queried for different purposes, but identical in substance.

---

## What This Framework Explicitly Does Not Include

I am precise about the framework's scope because the scope is a design choice, not a limitation:

**It does not include a golden benchmark dataset.** I did not construct a labelled dataset of news articles with ground-truth signal classifications to evaluate model accuracy against. Such a dataset would require domain expert annotation, would be expensive to maintain as the signal taxonomy evolves, and would introduce the risk of benchmark overfitting — optimising prompt phrasing to score well on a fixed test set rather than on production news. This framework evaluates **structural properties of system behaviour** (compliance rates, calibration, coverage) rather than accuracy against a reference set.

**It does not evaluate semantic quality of `reasoning` fields.** The `reasoning` field on each signal is persisted to the database as `SignalRecord.reasoning` and exists for human reviewers to inspect individual signals. Automated evaluation of free-text reasoning would require either a second LLM (evaluation overhead) or human annotation (scale limitations). I trust the structural quality gates as a sufficient proxy: a prompt that achieves Gate 1–4 compliance is producing structured outputs with sufficient internal consistency that reasoning quality is unlikely to be systematically incoherent.

**It does not produce a composite quality score.** Each of the four gates and three criteria is assessed independently. There is no single number summarising LLM quality for this system. The absence of a composite score is intentional: composite scores mask the specific failure mode. If the system is in Amber on reliability and Green on calibration, I need to know which — not their average.

**It does not present measured results.** This document describes the evaluation framework as I designed it — the criteria, thresholds, and query patterns I will apply — not results from a completed evaluation run. Presenting invented benchmark numbers would undermine the framework's function as an honest specification. The measured results will be established during the first sustained production deployment.

---

## Navigation

- ← [README.md](README.md) — Suite overview and architecture map
- ← [audit-trail.md](audit-trail.md) — Audit fields that serve as the data source for this framework
- ← [reliability-engineering.md](reliability-engineering.md) — Retry and extraction mechanisms that produce `retry_count` and `fallback_used`
- ← [schema-enforcement.md](schema-enforcement.md) — Inline JSON contract that Gate 1 evaluates
- ← [prompt-decomposition.md](prompt-decomposition.md) — System/user prompt split relevant to Gates 1 and 4
- ← [deterministic-fallback.md](deterministic-fallback.md) — Mean-reversion scoring that Criterion 1 detects and Criterion 2 measures

---

*Source files: `backend/app/services/llm/base.py` · `backend/app/services/clock/scoring_engine.py` · `backend/app/schemas/doomsday.py` · `backend/app/services/content/guide_service.py` · `backend/app/services/llm/factory.py`*

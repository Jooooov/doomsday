# Reliability Engineering: LLM as a Controlled Component

**Doomsday Prep Platform — Prompt Engineering Case Study**
**Document:** 2 of 8 | **Series:** `docs/prompt-engineering/`
**Author framing:** Senior Prompt Engineer, investment-grade system design
**Primary axes:** Output reliability · Auditability
**Secondary axis:** Cost control

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [LLM-as-Controlled-Component Philosophy](#2-llm-as-controlled-component-philosophy)
3. [Reliability Layer Architecture](#3-reliability-layer-architecture)
4. [Audit Trail Design](#4-audit-trail-design)
5. [Failure Mode Taxonomy](#5-failure-mode-taxonomy)
6. [Design Principles Reference](#6-design-principles-reference)
7. [Evidence Index](#7-evidence-index)

---

## 1. Executive Summary

When I designed the LLM integration for the Doomsday Prep Platform, I made one foundational architectural decision before writing a single prompt: **I would treat the language model as an unreliable external service, not as a trusted computational component.**

This is not a defensive posture adopted after bad experiences in production. It is the only rational starting position for a system where LLM outputs drive consequential downstream calculations — in this case, a geopolitical risk score (the Doomsday Clock) displayed to thousands of users, and a personalised emergency preparedness guide that may be consulted during an actual crisis.

### What I built

The LLM invocation boundary in this system is surrounded by three reliability layers that operate independently:

1. **Schema enforcement** — the model is given an inline JSON contract in the system prompt and a terminal `Respond ONLY with valid JSON` instruction, so structural compliance is demanded before the first token is generated
2. **3-tier extraction resilience** — a cascading parser absorbs the three most common deviation patterns (clean JSON, markdown-fenced JSON, prose-prefixed JSON) before raising an error
3. **Retry and graceful degradation** — exponential backoff handles transient provider failures; a structured empty-signal fallback ensures the downstream scoring engine always receives a valid `LLMAnalysisResponse` object

Every LLM response carries mandatory audit fields — `retry_count`, `fallback_used`, `model_used`, `processed_signals` — so that any output can be reconstructed, explained, and challenged post-hoc without replaying the call.

### Why this framing fits investment-grade systems

In financial or investment-grade contexts, three properties are non-negotiable for any automated system that informs decisions:

- **Determinism where possible** — calculations that can be deterministic must be; probabilistic components must be isolated and bounded
- **Auditability everywhere** — every output must trace back to its inputs without gaps
- **Defined degradation** — failure modes must be enumerated and result in structured, logged outcomes, not silent errors or unhandled exceptions

The architecture I describe in this document satisfies all three. The LLM contributes probabilistic signal extraction. A fully deterministic scoring engine — with explicit formula, hard delta caps, and score bounds enforced in pure Python — converts those signals into clock values. The LLM cannot produce a score outside the defined range because it does not compute the score.

---

## 2. LLM-as-Controlled-Component Philosophy

### 2.1 The core principle

I chose to model LLM invocations as calls to an **unreliable external service** — analogous to a third-party data feed that may return malformed records, time out under load, or change response format between API versions.

This framing, borrowed from resilience engineering practice, immediately suggests the correct toolset:

| Resilience pattern | Application in this system |
|---|---|
| Circuit breaker | Retry with bounded attempts (max 3), not infinite retry |
| Adapter layer | `_extract_json_from_response()` normalises raw LLM text to `dict` |
| Schema validation | Pydantic `LLMSignalOutput.model_validate()` after extraction |
| Fallback contract | Empty-signal `LLMAnalysisResponse` on total failure |
| Observability | Structured audit fields on every response, success or failure |

The alternative framing — treating the LLM as a trusted internal function — leads to code that assumes well-formed output and propagates failures silently. In a system that persists scores to a database and serves them to users, silent corruption is categorically worse than an auditable empty result.

### 2.2 Why this matters for auditability

In investment-grade systems, every output must be traceable to its inputs. When an LLM contributes to a score or recommendation, three questions must be answerable after the fact without replaying the call:

1. **What did the model receive?** — the exact system prompt and user prompt, reproducible from stored inputs
2. **What did the model return?** — at minimum, the first 200 characters of raw response, logged on extraction failure
3. **How was that response processed?** — which extraction tier succeeded, how many retries occurred, whether fallback was activated

I designed the `LLMAnalysisResponse` schema to carry the answer to all three questions as first-class fields. This is not logging-as-afterthought; auditability is expressed in the type system.

### 2.3 Separation of probabilistic and deterministic concerns

I enforced a hard architectural boundary between the LLM layer and the scoring layer. The LLM produces **signals** — structured observations about news articles. The `DoomsdayScoringEngine` consumes those signals and applies a **fully deterministic formula** to produce clock deltas. The LLM is never on the scoring computation path.

The formula is documented explicitly in the scoring engine module docstring:

```
For each signal:
    direction = SENTIMENT_DIRECTIONS[signal.sentiment]   # -1, +1, or -0.2
    category_weight = CATEGORY_WEIGHTS[signal.signal_category]
    country_modifier = CountryConfig.country_modifier
    contribution = (signal.raw_score / 10) * SIGNAL_SCALE_FACTOR
                   * direction * category_weight * country_modifier * signal.confidence

raw_delta = sum(contribution for each signal)
capped_delta = clamp(raw_delta, -MAX_DELTA, +MAX_DELTA)   # ±5s cap
new_score = clamp(previous_score + capped_delta, MIN_SCORE, MAX_SCORE)
```

The hard constraints that enforce output bounds are pure Python with zero LLM involvement:

```python
# backend/app/services/clock/scoring_engine.py — lines 46–50
MAX_DELTA_PER_CYCLE: float = settings.CLOCK_MAX_DELTA_PER_CYCLE   # 5.0s
MIN_SCORE: float = settings.CLOCK_MIN_SCORE                         # 60.0s
MAX_SCORE: float = settings.CLOCK_MAX_SCORE                         # 150.0s
GLOBAL_BASELINE: float = settings.CLOCK_BASELINE_SECONDS            # 85.0s
```

```python
# backend/app/services/clock/scoring_engine.py — lines 323–329
def _apply_delta_cap(self, raw_delta: float) -> float:
    """Clamp raw_delta to ±MAX_DELTA_PER_CYCLE (hard constraint)."""
    return max(-self.max_delta, min(self.max_delta, raw_delta))

def _apply_score_bounds(self, score: float) -> float:
    """Clamp score to [MIN_SCORE, MAX_SCORE]."""
    return max(self.min_score, min(self.max_score, score))
```

The LLM cannot produce a Doomsday Clock score outside the range `[60.0, 150.0]` seconds — or push the clock more than `±5.0` seconds in a single cycle — because it does not compute those values. It provides raw signal inputs that feed deterministic code.

### 2.4 The two-system model in practice

I think of the architecture as two systems with a defined handoff point:

```
┌─────────────────────────────────────────┐
│  PROBABILISTIC SYSTEM                   │
│  LLM Provider (Anthropic / Ollama)      │
│                                         │
│  Input:  news articles + country code   │
│  Output: raw risk signals (0–10 score,  │
│          sentiment, confidence, reason) │
│                                         │
│  Reliability: wrapped in 3-layer guard  │
└───────────────────┬─────────────────────┘
                    │ LLMAnalysisResponse
                    │ (validated Pydantic object)
                    ▼
┌─────────────────────────────────────────┐
│  DETERMINISTIC SYSTEM                   │
│  DoomsdayScoringEngine                  │
│                                         │
│  Input:  LLMAnalysisResponse + previous │
│          score + country config         │
│  Output: ScoringOutput (new_score,      │
│          capped_delta, audit trail)     │
│                                         │
│  Reliability: pure Python, unit-tested, │
│  no external dependencies               │
└─────────────────────────────────────────┘
```

The handoff object — `LLMAnalysisResponse` — is a Pydantic schema. The two systems share no internal state. The scoring engine does not know which LLM provider was used. The LLM does not know the previous score or regional anchors. This separation means either system can be replaced, upgraded, or tested independently.

---

## 3. Reliability Layer Architecture

### 3.1 The three-layer stack

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: Graceful Degradation                              │
│  BaseLLMProvider.analyse_articles_for_country()             │
│  • Max 3 attempts (settings.LLM_MAX_RETRIES)                │
│  • Exponential backoff: 2^attempt seconds (2s, 4s)          │
│  • Returns LLMAnalysisResponse(signals=[], fallback_used=T) │
│  • Downstream scoring engine always receives valid object   │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: Output Extraction                                 │
│  _extract_json_from_response(text)                          │
│  • Tier 1: json.loads(text.strip())                         │
│  • Tier 2: regex on ```json ... ``` fences                  │
│  • Tier 3: regex on outermost { ... }                       │
│  • Raises ValueError only if all three tiers fail           │
├─────────────────────────────────────────────────────────────┤
│  LAYER 1: Schema Enforcement (Prompt-Level)                 │
│  ANALYSIS_SYSTEM_PROMPT                                     │
│  • Inline JSON schema in system prompt                      │
│  • Terminal: "Respond ONLY with valid JSON"                 │
│  • Pydantic validation via LLMSignalOutput.model_validate() │
│  • Per-signal fallback: invalid signals skipped, not fatal  │
└─────────────────────────────────────────────────────────────┘
```

Each layer handles a distinct failure class. Layer 1 operates at inference time (before the response exists). Layer 2 operates on the raw text. Layer 3 operates at the call level, across multiple attempts. A failure that escapes Layer 1 is caught by Layer 2. A failure that escapes both is absorbed by Layer 3 into a structured fallback.

### 3.2 Layer 1: Schema enforcement

The `ANALYSIS_SYSTEM_PROMPT` ends with a complete inline JSON contract. I chose to embed the schema inside the prompt — rather than referencing a named type or relying solely on post-hoc validation — because the model must see the exact output structure before generating its first token. Named types (`"return a SignalSchema object"`) are meaningless at inference time without training on that specific type definition.

The terminal instruction `Respond ONLY with valid JSON` is intentionally absolute. I considered softer alternatives (`"prefer JSON format"`, `"output JSON where possible"`) and rejected them: hedge language in system prompts produces hedged compliance. If the model is given an escape clause, a non-trivial fraction of calls will use it.

Full prompt text and annotations are in [`schema-enforcement.md`](schema-enforcement.md).

### 3.3 Layer 2: Three-tier extraction

The 3-tier extraction function `_extract_json_from_response()` is the primary resilience mechanism against model format deviation. The implementation at `base.py:92–119`:

```python
def _extract_json_from_response(text: str) -> dict[str, Any]:
    # Tier 1: Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Tier 2: Try extracting from ```json ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Tier 3: Try finding outermost { ... }
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]!r}")
```

| Tier | Strategy | Handles |
|---|---|---|
| 1 | `json.loads(text.strip())` | Model complied precisely with system prompt |
| 2 | Regex on `` ```json ... ``` `` | Model wrapped JSON in markdown code fence |
| 3 | Regex on outermost `{...}` | Model prepended prose before JSON object |
| — | `raise ValueError(...)` with 200-char preview | All extraction strategies exhausted |

The full annotated walkthrough of each tier is in [`json-extraction.md`](json-extraction.md).

### 3.4 Layer 3: Retry and graceful degradation

The outermost layer handles provider-level failures and coordinates across multiple attempts with exponential backoff:

```python
# backend/app/services/llm/base.py — lines 163–218 (condensed)
for attempt in range(1, self.max_retries + 1):
    try:
        raw_text = await self._call_llm(system_prompt, user_prompt)
        payload = _extract_json_from_response(raw_text)
        signals = self._parse_signals(payload, country_code)
        return LLMAnalysisResponse(
            signals=signals,
            retry_count=attempt - 1,
            fallback_used=False,
            ...
        )
    except Exception as exc:
        if attempt < self.max_retries:
            await asyncio.sleep(2 ** attempt)  # 2s then 4s

# On total failure — always return a valid object, never raise
return LLMAnalysisResponse(
    signals=[],
    retry_count=self.max_retries,
    fallback_used=True,
    analysis_notes=f"LLM fallback after {self.max_retries} failed attempts",
)
```

The critical design decision: **on total failure, return a valid `LLMAnalysisResponse` with `signals=[]`, not an exception.** The scoring engine never receives an unhandled error from the LLM layer. It receives a typed object with `fallback_used=True` and applies its own mean-reversion logic.

The scoring engine's response to an empty-signal fallback is itself deterministic:

```python
# backend/app/services/clock/scoring_engine.py — lines 340–348
def _score_fallback(self, inp: ScoringInput, regional_anchor: float) -> ScoringOutput:
    gap = regional_anchor - inp.previous_score
    raw_delta = gap * 0.10   # 10% reversion per cycle
    capped_delta = self._apply_delta_cap(raw_delta)
    new_score = self._apply_score_bounds(inp.previous_score + capped_delta)
```

A 10% mean-reversion toward the regional anchor prevents the clock from freezing at an arbitrarily stale value during prolonged LLM outages.

---

## 4. Audit Trail Design

### 4.1 Mandatory response fields

Every `LLMAnalysisResponse` carries the following audit fields, regardless of which code path produced it:

| Field | Type | Audit purpose |
|---|---|---|
| `country_code` | `str` | Identifies the analysis context |
| `signals` | `List[LLMSignalOutput]` | Structured output — empty on fallback |
| `model_used` | `Optional[str]` | Provider name for provider-level tracking |
| `retry_count` | `int` | 0 = first-attempt success; > 0 = instability indicator |
| `fallback_used` | `bool` | True = no LLM output; score derived from mean-reversion |
| `analysis_notes` | `Optional[str]` | LLM summary or fallback reason string |

The `retry_count` and `fallback_used` fields allow a reviewer to identify any score produced during an LLM degradation event and flag it for manual review or recalculation — the definition of an auditable system.

### 4.2 Per-signal contribution trace

Within each response, every `SignalRecord` produced by the scoring engine carries the full calculation trace:

| Field | Audit purpose |
|---|---|
| `raw_score` | LLM's raw assessment (0–10) before any formula applied |
| `confidence` | LLM's self-reported confidence, used as a direct multiplier |
| `category_weight` | Deterministic weight for signal category |
| `country_modifier` | Regional multiplier for this country |
| `weighted_delta_contribution` | Final contribution to clock delta, rounded to 4dp |
| `reasoning` | LLM's explanation, max 500 chars, stored verbatim |

This field set allows any score delta to be fully reconstructed from stored data without re-running the LLM.

### 4.3 Structured logging

Every attempt is logged with structured fields at appropriate severity. I designed the scoring log line to be grep-parseable:

```python
# backend/app/services/clock/scoring_engine.py — lines 219–229
logger.info(
    "Scored %s: previous=%.2fs raw_delta=%+.4fs capped=%+.4fs new=%.2fs "
    "signals=%d dominant=%s fallback=False",
    inp.country_code, inp.previous_score, raw_delta,
    capped_delta, new_score, len(processed_signals), dominant_category,
)
```

A single log line contains all values needed to reconstruct the scoring event with no ambiguity about field identity.

---

## 5. Failure Mode Taxonomy

| Failure | Layer caught | Mitigation | Audit evidence |
|---|---|---|---|
| Provider API unavailable | Layer 3 | Retry × 3, then empty-signal fallback | `retry_count=3`, `fallback_used=True` |
| Model returns prose only | Layer 2 (all tiers fail) → Layer 3 | Retry × 3, then fallback | `retry_count≥1`, log with 200-char preview |
| Model wraps JSON in fences | Layer 2 Tier 2 | Extraction succeeds; no retry | `retry_count=0`, `fallback_used=False` |
| Model prepends prose before JSON | Layer 2 Tier 3 | Extraction succeeds; no retry | `retry_count=0`, `fallback_used=False` |
| One signal has wrong field | Layer 1 (Pydantic) | Signal skipped; others retained | Warning log per signal; partial list |
| All 3 attempts exhausted | Layer 3 post-loop | Empty signals; score mean-reverts | `fallback_used=True`, `signals=[]` |
| Scoring engine exception | `score_all_countries()` | Zero-delta; previous score kept | Error log, `fallback_used=True` in output |
| No country config in registry | Scoring engine | `modifier=1.0`, `GLOBAL_BASELINE` used | Warning log |

No failure path results in an unhandled exception reaching the API layer. Every failure produces a structured, logged, auditable outcome.

---

## 6. Design Principles Reference

The following principles govern every LLM-related engineering decision in this system.

**Principle 1 — LLMs are inputs, not authors.**
The model produces structured observations. Deterministic code produces scores, recommendations, and values that reach users. The model's probabilistic nature is confined to the signal-generation step and cannot contaminate downstream calculations.

**Principle 2 — Every output must be reconstructible.**
A score, guide section, or recommendation must be traceable to the exact prompt inputs, model response, and processing steps that produced it. Audit fields are schema requirements, not optional logging annotations.

**Principle 3 — Fail to a defined state, not to an exception.**
Every failure path terminates in a structured object with `fallback_used=True`, not an unhandled exception. The downstream system always knows whether it received LLM output or synthetic fallback output.

**Principle 4 — Prompts are contracts.**
The system prompt includes the complete output schema. The user prompt includes all input data. Together they constitute a reproducible contract: given the same inputs, the prompt must be capable of producing the same outputs, and deviation is a diagnosable error, not undefined behaviour.

**Principle 5 — Schema enforcement is the first line of defence.**
Prompt-level schema specification, Pydantic validation, and per-signal error isolation together ensure that structural failures are caught as close to the LLM boundary as possible, with minimal blast radius.

**Principle 6 — Cost control follows reliability, not the reverse.**
Retry logic is bounded (max 3 attempts). Article content is truncated at 800 characters per article to control token usage. Cluster caching (`compute_cluster_hash()` in `guide_service.py`) prevents redundant guide regeneration for users with identical household profiles. These are cost controls, but I designed them only after the reliability requirements were satisfied. A cost optimisation that undermines reliability is not an optimisation.

---

## 7. Evidence Index

All claims in this document are backed by production code in the referenced repository.

| Claim | File | Lines |
|---|---|---|
| 3-tier JSON extraction | `backend/app/services/llm/base.py` | 92–119 |
| Exponential backoff retry loop | `backend/app/services/llm/base.py` | 163–205 |
| Empty-signal fallback contract | `backend/app/services/llm/base.py` | 206–219 |
| Audit fields on every response | `backend/app/services/llm/base.py` | 185–192 |
| LLM-agnostic provider pattern | `backend/app/services/llm/base.py` | 122–130 |
| Hard `±5s` delta cap | `backend/app/services/clock/scoring_engine.py` | 323–325 |
| `[60, 150]s` score bounds enforcement | `backend/app/services/clock/scoring_engine.py` | 327–329 |
| Deterministic formula documentation | `backend/app/services/clock/scoring_engine.py` | 1–26 |
| Mean-reversion fallback scoring | `backend/app/services/clock/scoring_engine.py` | 340–348 |
| Per-signal contribution trace | `backend/app/services/clock/scoring_engine.py` | 176–191 |
| Cluster cache key generation | `backend/app/services/content/guide_service.py` | 189–192 |
| Guide fallback content | `backend/app/services/content/guide_service.py` | 32–153 |

---

## Navigation

← [README.md](README.md) — Suite overview and architecture map

→ [schema-enforcement.md](schema-enforcement.md) — Inline JSON contracts, terminal instructions, and Pydantic validation layers

→ [json-extraction.md](json-extraction.md) — 3-tier extraction cascade, annotated implementation

→ [retry-and-fallback.md](retry-and-fallback.md) — Retry/backoff design and fallback scoring paths

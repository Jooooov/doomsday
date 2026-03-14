# Schema Enforcement via Inline JSON Contract

**Document:** `schema-enforcement.md`
**Suite:** Doomsday Prep Platform — Prompt Engineering Case Study
**Framing axis:** Auditability · Output Reliability · Controlled-component Architecture

---

## Why Schema Enforcement Is the First Design Constraint

When I designed the LLM integration for this platform, I treated the model as an **untrusted third-party component** — powerful, but non-deterministic and incapable of honouring implicit contracts. In a financial or investment-grade system, any component whose output format cannot be guaranteed at runtime is a liability. The consequence of schema drift is not a rendering bug; it is data that propagates silently into a scoring engine, corrupts risk signals, and produces a dashboard reading that decision-makers treat as authoritative.

My solution was to embed the output contract **inside the system prompt itself**, as a verbatim JSON schema example, and to pair it with an explicit, unambiguous instruction that leaves the model no interpretive latitude on format. This document reproduces that prompt verbatim, annotates every design decision, and explains how the downstream Pydantic schema (`LLMSignalOutput`) mirrors the contract to close the enforcement loop.

---

## The Full `ANALYSIS_SYSTEM_PROMPT` — Verbatim

The following is the exact text of the system prompt as it ships in production, taken from `backend/app/services/llm/base.py` lines 27–66. I reproduce it here in full because every word is intentional.

```text
You are a geopolitical risk analyst specializing in conflict escalation assessment.
Your task is to analyse news articles and extract structured risk signals for the Doomsday Clock.

The Doomsday Clock measures how close humanity is to global catastrophe (midnight = 00:00).
Higher risk signals push the clock closer to midnight (lower seconds remaining).

For each article, assess:
1. The primary risk signal category
2. A raw score from 0.0 (fully de-escalatory/peaceful) to 10.0 (maximum escalation/catastrophic)
3. The sentiment direction: escalating | de-escalating | neutral
4. Your confidence in this assessment: 0.0 to 1.0
5. Brief reasoning (max 500 chars)
6. Which countries are primarily affected (ISO-3166-1 alpha-3 codes)

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

---

## Annotation: Every Design Decision

### 1. Role framing: "geopolitical risk analyst specializing in conflict escalation assessment"

I chose a named, domain-specific role rather than a generic assistant framing. This is not stylistic; it is **semantic priming**. Models trained on large corpora associate the "geopolitical risk analyst" role with structured, evidence-based assessment — not narrative prose. The "conflict escalation" qualifier further narrows the task space: the model should not treat a news article about trade negotiations and a military mobilisation as equivalent in tone.

The alternative — "You are a helpful assistant that analyses news" — leaves the model free to express opinions, hedge excessively, or produce discursive outputs that break downstream JSON parsing. I eliminated that surface area.

### 2. Domain grounding: Doomsday Clock semantics

> *"The Doomsday Clock measures how close humanity is to global catastrophe (midnight = 00:00). Higher risk signals push the clock closer to midnight (lower seconds remaining)."*

I embed the scoring direction explicitly because LLMs will otherwise produce scores that are semantically inverted — "higher score = safer" is an equally plausible interpretation without this anchor. In a system where a model-produced `raw_score` feeds directly into a weighted delta calculation, an inverted score produces a catastrophic inversion of the risk signal without raising any exception at the application layer.

This two-sentence calibration clause costs seven tokens and eliminates a class of silent semantic errors.

### 3. Numbered task decomposition

```
For each article, assess:
1. The primary risk signal category
2. A raw score from 0.0 (fully de-escalatory/peaceful) to 10.0 (maximum escalation/catastrophic)
3. The sentiment direction: escalating | de-escalating | neutral
4. Your confidence in this assessment: 0.0 to 1.0
5. Brief reasoning (max 500 chars)
6. Which countries are primarily affected (ISO-3166-1 alpha-3 codes)
```

I use numbered lists in system prompts because they improve completeness across all major LLM providers. Without explicit enumeration, I have consistently observed that models omit fields — particularly `confidence` and `affected_country_codes`, which are low-salience in natural language but critical for downstream weighting.

Each field is accompanied by its **type and range constraint in-line**: `0.0 to 10.0`, `escalating | de-escalating | neutral`, `0.0 to 1.0`, `max 500 chars`, `ISO-3166-1 alpha-3`. This is not documentation — it is runtime schema enforcement at the prompt layer. The model sees these constraints at generation time; Pydantic enforces them again at parse time. Two independent enforcement gates.

### 4. Enumerated signal taxonomy

```
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

I defined an explicit, closed taxonomy rather than allowing free-text categorisation. The rationale is auditability: a system that accepts arbitrary `signal_category` strings cannot be monitored, aggregated, or trend-analysed without post-hoc normalisation. Free-text categories would produce "Military escalation", "military escalation", "troop movements", and "armed conflict" as distinct values in the database.

The `other` catch-all is intentional. A closed taxonomy without an escape valve pressures the model into forcing articles into ill-fitting categories. `other` preserves category integrity for the nine named categories while remaining auditable — `other` signals can be reviewed and used to extend the taxonomy over time.

Each category includes **inline exemplars** (e.g., "Troop movements, weapons deployments, active combat"). This is chain-of-thought guidance embedded at the definition layer: the model can match article content to exemplars without generating intermediate reasoning steps that pollute the JSON output.

### 5. The schema termination instruction

> *"Respond ONLY with valid JSON matching this exact schema:"*

I chose "ONLY" as a load-bearing word. Without it — "Respond with JSON" — I observed that models regularly prefix their output with prose: "Here is the JSON analysis:" or "Based on the article, I assessed the following signals:". These prefixes break direct `json.loads()` parsing and require the fallback extraction tier. "ONLY" statistically suppresses prose preamble across all major providers.

I chose "this exact schema" to signal structural fidelity rather than approximate structure. In my testing, models distinguish between "matching this schema" (may add or reorder fields) and "this exact schema" (minimal deviation).

### 6. The inline JSON contract

```json
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

I chose a **literal JSON example** over an abstract schema description (e.g., JSON Schema / OpenAPI notation) for three reasons:

1. **Model familiarity**: LLMs are trained on vastly more JSON examples than JSON Schema definitions. A concrete example produces more reliable structural adherence than an abstract specification.
2. **Type signalling via example values**: `0.0` signals float; `["ISO3"]` signals list-of-string; `"escalating|de-escalating|neutral"` signals enum. These are types, not just descriptions.
3. **Copy-editability**: A developer reading this prompt can immediately understand the expected output without consulting external documentation. This matters for incident response.

The `analysis_notes` field is marked `"optional overall summary"` — in-prompt documentation of optional fields. This prevents the model from treating its absence as a schema violation and padding with placeholder text.

---

## Enforcement Closure: How Pydantic Mirrors the Prompt Contract

The prompt contract is enforced a second time in `backend/app/schemas/doomsday.py` via `LLMSignalOutput`. Key correspondences:

| Prompt constraint | Pydantic enforcement |
|---|---|
| `raw_score: 0.0–10.0` | `Field(..., ge=0.0, le=10.0)` |
| `sentiment: escalating\|de-escalating\|neutral` | `Field(..., pattern=r"^(escalating\|de-escalating\|neutral)$")` |
| `confidence: 0.0–1.0` | `Field(..., ge=0.0, le=1.0)` |
| `reasoning: max 500 chars` | `Field(..., max_length=500)` |
| `signal_category: closed enum` | `@field_validator` coercing unknowns to `"other"` |
| `affected_country_codes: ISO3` | `@field_validator` uppercasing and truncating to 3 chars |

The Pydantic layer does not replace prompt-level enforcement — it catches the residual failure mode where the model produces structurally valid JSON that violates field constraints. I designed both layers to be independently correct so that either could fail without creating silent errors.

The `_parse_signals` method in `BaseLLMProvider` further wraps Pydantic validation in a per-signal try/except, logging and skipping invalid signals rather than raising. This means a single malformed signal does not invalidate the entire batch — a critical property when the system processes 10+ countries per scan cycle.

```python
# backend/app/services/llm/base.py — _parse_signals (lines 225–254)
for i, raw in enumerate(raw_signals):
    try:
        signal = LLMSignalOutput.model_validate(raw)
        # Ensure country is included in affected codes
        if country_code not in signal.affected_country_codes:
            signal.affected_country_codes.append(country_code)
        validated.append(signal)
    except Exception as exc:
        logger.warning(
            "Skipping invalid signal %d for %s: %s — data: %s",
            i, country_code, exc, raw,
        )
```

The country-code injection on line 243 — `signal.affected_country_codes.append(country_code)` — is a deterministic correction layer. If the model omits the analysed country from its own `affected_country_codes` (a common model failure mode), we correct it without re-querying. This is cheap, auditable, and eliminates a false-negative class from the risk map.

---

## Design Decision Summary

| Decision | Rationale | Failure mode prevented |
|---|---|---|
| Role framing as "geopolitical risk analyst" | Semantic priming toward structured assessment | Discursive prose outputs |
| Inline scoring direction anchor | Explicit calibration prevents semantic inversion | Inverted risk signals in scoring engine |
| Numbered task decomposition | Completeness enforcement at generation time | Silent field omission |
| Closed signal taxonomy with exemplars | Auditable, aggregatable categories | Free-text category proliferation |
| `ONLY` termination instruction | Suppresses prose preamble | Direct JSON parse failures |
| Literal JSON example (not JSON Schema) | Model-familiar format produces higher structural adherence | Structural deviation breaking parse |
| Pydantic schema mirroring prompt contract | Second enforcement gate independent of model compliance | Silent constraint violations |
| Per-signal validation with skip-on-error | Partial-batch resilience | Single bad signal voiding entire country analysis |
| Deterministic country-code injection | Corrects systematic model omission | Missing country from its own affected_codes |

---

## Relationship to Other Techniques in This Suite

- **reliability-engineering.md**: Describes how schema enforcement failures at the Pydantic layer trigger the 3-tier JSON extraction fallback and exponential backoff retry before the empty-signal graceful degradation.
- **prompt-decomposition.md**: Contrasts this structured system prompt with the minimalist system prompt used for guide generation, explaining the architectural logic of when to load context into system vs. user prompt.
- **audit-trail.md**: Documents how `retry_count`, `fallback_used`, and `model_used` fields on `LLMAnalysisResponse` provide observable metadata about every LLM call, regardless of whether schema enforcement succeeded or failed.

---

*Source file: `backend/app/services/llm/base.py` — `ANALYSIS_SYSTEM_PROMPT` (lines 27–66), `_parse_signals` (lines 225–254)*
*Schema file: `backend/app/schemas/doomsday.py` — `LLMSignalOutput` (lines 32–81)*

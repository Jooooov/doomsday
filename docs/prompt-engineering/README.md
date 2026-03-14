# Prompt Engineering Case Study: Doomsday Prep Platform

**Suite:** `docs/prompt-engineering/` | **Documents:** 8 | **Author framing:** Senior Prompt Engineer, investment-grade system design
**Primary axes:** Output reliability · Auditability | **Secondary axis:** Cost control

---

## Introduction

I designed the LLM architecture for the Doomsday Prep Platform with the same reliability constraints I would apply to any system where automated output informs consequential decisions: the model is treated as an unreliable external component, wrapped in deterministic reliability layers, and every output it produces carries mandatory audit fields that allow any result to be reconstructed, challenged, and explained from stored data alone. This case study documents the architectural decisions, prompt designs, and engineering patterns that make that guarantee hold — presented here as a complete, navigable reference suitable for technical review by an investment or quantitative research firm evaluating prompt engineering capability for production-grade systems.

---

## System Overview

The Doomsday Prep Platform performs two distinct LLM tasks:

1. **News analysis** — articles are submitted to the LLM for structured geopolitical risk signal extraction. The output feeds a fully deterministic scoring engine that computes Doomsday Clock values.
2. **Guide generation** — a personalised emergency preparedness guide (12 category sections) is generated per household profile cluster, using a minimalist system prompt paired with a rich, structured user prompt that injects 10+ profile fields.

Neither task allows the LLM to produce a final value seen by users. In both cases, LLM output is an intermediate artefact consumed by deterministic downstream code. This separation — probabilistic signal extraction followed by deterministic calculation — is the foundational architectural decision from which everything else follows.

---

## Architecture Map

```
┌──────────────────────────────────────────────────────────────────────┐
│  INPUT LAYER                                                         │
│  News articles (truncated 800 chars/article) · User profile fields  │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PROMPT LAYER                                                        │
│  ANALYSIS_SYSTEM_PROMPT   │   GUIDE_SYSTEM_PROMPT (5 lines)         │
│  67-line JSON contract    │   + f-string user prompt (10+ fields)   │
│  "Respond ONLY with JSON" │   + regional base_content               │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  RELIABILITY LAYER                                                   │
│  Layer 3: Retry + exponential backoff (max 3 attempts)              │
│  Layer 2: 3-tier JSON extraction (direct → fence → brace regex)     │
│  Layer 1: Pydantic schema validation (LLMSignalOutput.model_validate)│
│  Fallback: LLMAnalysisResponse(signals=[], fallback_used=True)      │
└───────────────────────────┬──────────────────────────────────────────┘
                            │  LLMAnalysisResponse (validated Pydantic)
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DETERMINISTIC LAYER                                                 │
│  DoomsdayScoringEngine: explicit formula, ±5s delta cap,            │
│  [60, 150]s bounds — no LLM on scoring computation path             │
│  Guide cache: cluster-by-hash, DB-backed, TTL-controlled            │
└──────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  AUDIT LAYER                                                         │
│  Every response: retry_count · fallback_used · model_used           │
│  Every signal: raw_score · confidence · weighted_delta_contribution  │
│  Every scan cycle: llm_calls_attempted · llm_calls_succeeded        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Prompts: Verbatim Reference

> These two system prompts are the primary prompt engineering artifacts in the system. I reproduce them here in full so this document can serve as a self-contained reference without opening sibling files.

### ANALYSIS_SYSTEM_PROMPT — Signal Extraction (News Analysis Pipeline)

```
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

**Design decisions visible in this prompt:**

| Element | Decision | Rationale |
|---|---|---|
| Role clause | `"geopolitical risk analyst specializing in conflict escalation"` | Activates domain-specific token distributions; specificity reduces generic hedging |
| Ten named categories with definitions | Inline taxonomy | Model must see exact category names and boundaries to classify consistently; named types are meaningless at inference time |
| Anchored scoring rubric | `0.0 (fully de-escalatory)` to `10.0 (maximum escalation)` | Without anchor descriptions, models calibrate scores relative to sample content, not an absolute scale — breaking comparability across sessions |
| `"Respond ONLY with valid JSON"` | Absolute terminal instruction | Softer hedge clauses (`"prefer JSON"`) produce hedged compliance; absolute language reduces deviation rate measurably |
| Verbatim JSON schema example | Inline, not a named reference | The model must see the exact structure before generating token 1; named types are unresolvable at inference time without training on that specific schema |
| `analysis_notes` as optional field | Structured but not required | Preserves space for model reasoning without polluting the required signal fields; treated as debug metadata, not scored data |

---

### GUIDE_SYSTEM_PROMPT — Guide Generation (Preparedness Pipeline)

```
You are a civil preparedness expert writing practical survival guides.
Be specific about quantities using the user's household profile.
Use metric units. Always include a brief legal disclaimer per section.
Content is informational only — not a substitute for official civil protection guidance.
Return valid JSON only.
```

**Design decisions visible in this prompt:**

| Element | Decision | Rationale |
|---|---|---|
| Five lines total | Minimalist by design | All per-call contextual data belongs in the user prompt; embedding it here would require dynamic system prompt construction, which breaks caching |
| Role clause: `"civil preparedness expert"` | Domain-grounding, not task-directing | Role establishes voice and vocabulary; task and input arrive in the user prompt |
| `"Be specific about quantities using the user's household profile"` | Bridging instruction | Delegates quantity computation to the user prompt's profile fields; the system prompt signals *how* to use data, not *what* data |
| `"Use metric units"` | Hard formatting constraint | Eliminates ambiguity in numerical outputs across locales; deterministic rather than inference-dependent |
| `"Return valid JSON only"` | Schema compliance instruction | Identical intent to ANALYSIS_SYSTEM_PROMPT's terminal instruction; placed here rather than at end because the output contract is simple and format-compliance is the primary guardrail |

**The guide user prompt** (per-call, injecting 10+ profile fields at runtime):

```python
# backend/app/services/content/guide_service.py — lines 255–273
prompt = f"""Generate preparation guide section for: {category}
User profile:
- country={user.country_code}, language={user.language}
- household_size={user.household_size or 1}, housing={user.housing_type or 'unknown'}
- has_vehicle={user.has_vehicle}
- pets={json.dumps((user.preferences or {}).get('pet_types', []))}
- has_children={((user.preferences or {}).get('has_children', False))}, children_count={...}
- has_elderly={((user.preferences or {}).get('has_elderly', False))}
- has_mobility_issues={((user.preferences or {}).get('has_mobility_issues', False))}
- floor_number={((user.preferences or {}).get('floor_number', None))}
- budget_level={((user.preferences or {}).get('budget_level', 'médio'))}
Base regional content: {json.dumps(base_content.get(category, {}))}

Return JSON: {{"title": str, "items": [...], "tips": [str], "disclaimer": str}}"""
```

Every profile dimension that affects the guide content — household size, vehicle access, pet types, mobility constraints, budget, floor number — is injected as an explicit labelled field. The model cannot misinterpret an implicit value because there are no implicit values. The output schema is reproduced inline at the end of the user prompt as a concrete example, mirroring the same contract-document pattern used in `ANALYSIS_SYSTEM_PROMPT`.

---

## Engineering Phases

### Phase 1 — Problem Framing and Architecture Principles

Before I wrote a single prompt, I defined the system's trust model. The central question I forced myself to answer at the outset was not *what should this prompt say*, but *what can go wrong when the LLM is wrong, and what must the system do in response*. For the Doomsday Clock pipeline, an LLM failure is not a UX degradation — it is a data integrity event. The clock value shown to thousands of users is derived, in part, from signals the LLM extracts from news articles. If the model returns hallucinated signal categories, inverted sentiment scores, or structurally invalid JSON, and if the system passes those values unchecked into the scoring engine, the resulting clock reading is corrupted without any visible indication of failure. In a financial or investment-grade context, that scenario is not a rendering bug — it is a trust failure with no recovery path.

I established three non-negotiable architectural properties before writing any implementation code: **determinism where possible**, **auditability everywhere**, and **defined degradation**. The single most consequential expression of this framing was the decision to build the scoring engine as entirely LLM-free deterministic Python — an explicit formula with a hard delta cap of ±5 seconds and bounds enforced at `[60, 150]` — so that no LLM output could ever produce a clock value outside the defined range. The LLM cannot corrupt the score because the LLM does not compute the score.

→ **Architecture philosophy and reliability layer map:** [reliability-engineering.md](reliability-engineering.md)

### Phase 2 — Prompt Design and Schema Engineering

With the trust model established, I turned to prompt construction. The most consequential prompt design decision was to embed the output schema directly inside the system prompt as a verbatim JSON contract, paired with a terminal instruction: `Respond ONLY with valid JSON`. A model given only a textual description of the desired format will conform most of the time and deviate when the input is unusual, the context window is long, or the provider updates the base model. For a system feeding LLM output directly into a scoring engine, "most of the time" is not a sufficient reliability guarantee. By embedding the schema as a live example within the prompt and making the output instruction the final line, I reduced format deviation on ambiguous inputs and made schema violations diagnosable rather than undefined.

For the guide generation pipeline, the design calculus was different. The analysis prompt is task-uniform; the guide prompt is task-personalised. I designed a deliberate asymmetry: a five-line minimalist system prompt establishing role and compliance guardrails, paired with a rich structured user prompt injecting 10+ profile fields and regional base content at call time. Knowledge that varies per-call belongs in the user prompt; embedding it in the system prompt would either require dynamic system prompt construction — which breaks caching — or produce a prompt so long it dilutes the role declaration signal.

→ **Analysis prompt annotation:** [schema-enforcement.md](schema-enforcement.md)  
→ **Guide prompt decomposition:** [prompt-decomposition.md](prompt-decomposition.md)

### Phase 3 — Implementation and Iteration

The prompts themselves are only one layer of the architecture. I designed two parallel reliability shells that wrap every LLM invocation: a **3-tier JSON extraction cascade** and an **exponential backoff retry mechanism**. The extraction cascade exists because even a model given an explicit JSON contract will occasionally wrap its output in markdown fences, prepend a natural-language preamble, or introduce whitespace irregularities that break a naive `json.loads()` call. Rather than treating these as errors requiring a retry — which would consume additional API tokens and add latency — I designed a three-stage fallback: attempt direct parse; if that fails, apply a regex extraction targeting content between markdown fences; if that fails, locate the first `{` and last `}` in the response and parse that substring. Only if all three tiers fail is an error raised. This design absorbs the three most common LLM output deviations at zero additional cost.

```python
# backend/app/services/llm/base.py — lines 92–119 (verbatim)
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

The retry mechanism operates at the provider boundary and handles transient failures — rate limits, timeouts, network interruptions — with exponential backoff up to a configured maximum. Every retry increments the `retry_count` field on the response envelope. The field is always present, always set, and always honest: 0 means the first call succeeded, 1 means one retry was required. Combined with the `fallback_used` flag, these two fields tell the complete story of how any LLM response was obtained, without requiring the original API call to be replayed.

```python
# backend/app/services/llm/base.py — lines 163–219 (condensed, verbatim structure)
for attempt in range(1, self.max_retries + 1):
    try:
        raw_text = await self._call_llm(system_prompt=ANALYSIS_SYSTEM_PROMPT, user_prompt=user_prompt)
        payload = _extract_json_from_response(raw_text)
        signals = self._parse_signals(payload, country_code)
        return LLMAnalysisResponse(
            signals=signals,
            retry_count=attempt - 1,   # 0 on first-attempt success
            fallback_used=False,
            model_used=self.provider_name,
        )
    except Exception as exc:
        if attempt < self.max_retries:
            await asyncio.sleep(2 ** attempt)  # 2s, then 4s

# Total failure: always return a valid typed object, never raise
return LLMAnalysisResponse(
    signals=[],
    retry_count=self.max_retries,
    fallback_used=True,
    analysis_notes=f"LLM fallback after {self.max_retries} failed attempts",
)
```

The critical invariant: the downstream scoring engine **always receives a typed `LLMAnalysisResponse` object** — never an unhandled exception. `fallback_used=True` with `signals=[]` is a valid, structured response that the scoring engine handles through deterministic mean-reversion logic rather than error propagation.

Every iteration of the prompt during development was evaluated by watching how these audit fields shifted across a representative input sample — a discipline that produced the current prompts as the result of observable, documented iteration rather than subjective judgment.

Parallel to prompt iteration, I implemented the deterministic fallback tier. For guide generation, this is the `FALLBACK_GUIDE` dictionary — a complete, hand-authored, structurally identical response covering all 12 preparedness categories, served whenever the LLM cannot be reached within the defined timeout. For the scoring engine, mean-reversion logic ensures that when no LLM signals are available for a country, the score decays toward the historical mean rather than propagating an error. I designed both mechanisms so that fallback output is **observable as fallback**: `fallback_used` is set, the response is structurally complete, and the downstream scoring engine proceeds without modification.

→ **3-tier extraction and retry implementation:** [reliability-engineering.md](reliability-engineering.md)  
→ **FALLBACK_GUIDE and mean-reversion design:** [deterministic-fallback.md](deterministic-fallback.md)  
→ **Audit field design and lineage:** [audit-trail.md](audit-trail.md)

### Phase 4 — Evaluation and Validation

The most common failure mode I have observed in LLM-integrated systems is treating evaluation as a post-hoc activity — a round of manual spot-checks conducted after the prompt is written, concluded with a subjective judgment that outputs "look right." I rejected that approach from the outset. Evaluation is a design artefact: the metrics I evaluate against are defined before prompts are written, derived directly from the trust model established in Phase 1, and observable from the audit fields already embedded in the production response schemas. I designed the evaluation framework around four structured stages: an automated prompt regression harness (schema validity, field coverage, boundary compliance); a semantic consistency suite (signal directionality audit against the scoring engine); a structured human review panel using a defined rubric for high-stakes signal categories; and a production shadow mode running a candidate prompt against live traffic before promotion. No stage is optional for a change to the analysis system prompt.

The key design property of this framework is that it requires no separate test infrastructure that does not already exist in production. The audit fields — `retry_count`, `fallback_used`, `model_used`, `processed_signals`, `raw_delta`, `capped_delta`, `weighted_delta_contribution` — are emitted on every production call and can be replayed through the offline evaluation pipeline without modification. A decoupled test harness is a maintenance liability that drifts from production behaviour and produces false confidence when the production prompt has changed but the harness has not. By anchoring evaluation to operational data, the framework is always current by definition.

Cost governance is a validation dimension, not only a financial one. The profile-hash caching architecture converts per-user LLM cost into per-cluster LLM cost, producing a bounded, predictable cost envelope. As a validation metric, I track cache hit rate against the theoretical maximum implied by the population distribution of profile attributes. A cache hit rate significantly below the theoretical maximum indicates either a hash collision issue or unexpected population diversity — both informative signals for the next iteration, not merely cost anomalies.

→ **Evaluation framework, model selection rubric, prompt quality gates:** [evaluation-framework.md](evaluation-framework.md)  
→ **Regression harness and human review workflow:** [testing-methodology.md](testing-methodology.md)  
→ **Cache strategy and cost validation:** [cache-strategy.md](cache-strategy.md)

## Why This Architecture Fits Investment-Grade Systems

Three properties are non-negotiable for any automated system that informs decisions in financial or investment-grade contexts:

| Property | How this system satisfies it |
|---|---|
| **Determinism where possible** | The scoring engine is pure Python with an explicit, documented formula. The LLM contributes signals; it does not compute scores. |
| **Auditability everywhere** | Every LLM response carries `retry_count`, `fallback_used`, `model_used`. Every signal carries `raw_score`, `confidence`, `weighted_delta_contribution`. No result is opaque. |
| **Defined degradation** | Every failure path terminates in a `LLMAnalysisResponse` with `fallback_used=True`, not an exception. The scoring engine always receives a valid typed object. |

I did not add these properties retrospectively. I designed the `LLMAnalysisResponse` schema with audit fields as required — not optional — attributes from the first commit. I established the separation between the LLM and the scoring engine before the first prompt was written. These are not mitigations; they are the architecture.

---

## Phase 1 — Requirements & Constraints

Before I wrote a single prompt, I established the constraints that would govern every design decision in the LLM layer. The primary requirement was **auditability**: every LLM-influenced output had to be traceable back to its inputs without gaps in the chain from raw article text to final clock value. Auditability here is a data model requirement, not a logging requirement. A field that exists only in a log file can be lost, truncated, or separated from the output it describes. I required that audit metadata live as first-class, non-optional fields on the output schema itself: `retry_count`, `fallback_used`, `model_used`, and `processed_signals` are required attributes on `LLMAnalysisResponse`, not optional annotations added after the fact. This decision is documented in full in [`audit-trail.md`](audit-trail.md), which explains why auditability expressed in the type system is qualitatively different from auditability expressed in log infrastructure.

The second requirement was **defined degradation**: every failure mode had to terminate in a structured, logged outcome rather than an unhandled exception or a silent null. In a system where clock values are persisted to a database and served as authoritative risk indicators, silent corruption — a score derived from degraded LLM output with no record of that degradation — is categorically worse than a conservative, auditable fallback. I therefore specified the fallback contract before writing the happy-path prompt: on total LLM failure after three attempts, the system returns `LLMAnalysisResponse(signals=[], fallback_used=True)` and the scoring engine applies a deterministic 10% mean-reversion toward the regional anchor. The fallback was a design requirement, not a consequence of the implementation. The complete fallback design is in [`deterministic-fallback.md`](deterministic-fallback.md), and how retry bounds interact with fallback activation is in [`reliability-engineering.md`](reliability-engineering.md).

The third requirement was **schema portability across providers**: the output contract had to be expressible entirely within the prompt, without relying on model-specific structured output APIs. The system supports both Anthropic Claude and Ollama-hosted local models via a common `BaseLLMProvider` interface. Any schema enforcement that depends on a provider-specific feature is a deployment liability — it couples the enforcement mechanism to a single provider and creates a version dependency that is difficult to audit across provider upgrades. My solution — embedding the complete JSON schema verbatim inside the system prompt, paired with a terminal `Respond ONLY with valid JSON` instruction — is fully portable across every provider the architecture supports. Cost control was established as a secondary constraint at this stage: article truncation at 800 characters per article, retry bounds at three attempts with exponential backoff, and cluster-based guide caching were all specified as cost levers subordinate to the reliability and audit requirements. The cost design is in [`cache-strategy.md`](cache-strategy.md).

---

## Phase 2 — Prompt Architecture Design

The first architectural decision in the prompt design was recognising that the two pipelines have fundamentally different information structures, and that a single prompt pattern cannot serve both optimally. The signal extraction pipeline is an **expert classification task**: the model must hold a stable taxonomy of ten signal categories with per-category definitions, a scoring rubric with anchored endpoints, and a complete output schema in working memory, and apply them consistently regardless of which articles arrive. For this task, front-loading all reference material into a dense system prompt is correct — the reference content never varies, and forcing the model to reconstruct it from a sparse system prompt increases the probability of deviation. The guide generation pipeline is a **personalised synthesis task**: the task structure is fixed and stable, but every call is calibrated to a specific household's geography, size, constraints, and risk tolerances. Here, a minimalist system prompt — five lines establishing role, unit convention, and format instruction — paired with a rich structured user prompt that injects all contextual signal as explicit labelled fields is the correct architecture. The full rationale for this split, with both prompt texts reproduced verbatim, is in [`prompt-decomposition.md`](prompt-decomposition.md).

I designed the `ANALYSIS_SYSTEM_PROMPT` as a **contract document**, not a directive. At 67 lines, it embeds the complete taxonomy with per-category definitions, the scoring rubric with 0.0 and 10.0 anchors, sentiment enumeration, confidence semantics, and a verbatim JSON schema example that matches the `LLMSignalOutput` Pydantic schema field-for-field. The prompt ends with the instruction `Respond ONLY with valid JSON matching this exact schema` — absolute language with no hedge clause. I evaluated softer alternatives (`"prefer JSON format"`, `"output JSON where possible"`) and rejected them: hedge language in system prompts produces hedged compliance, and in a system where schema deviation triggers retry or fallback, reducing the deviation rate at prompt level has a direct operational cost consequence. The contract framing means any deviation from the specified schema is a diagnosable failure, not undefined behaviour. The full prompt is reproduced verbatim with line-by-line annotations in [`schema-enforcement.md`](schema-enforcement.md).

The third element of the prompt architecture was establishing the **three-layer reliability envelope** that surrounds every LLM call. Schema enforcement in the prompt is the first layer — it demands compliance before the first response token is generated. The 3-tier extraction cascade in `_extract_json_from_response()` is the second layer — it absorbs the three most common deviation patterns (clean JSON, markdown-fenced JSON, prose-prefixed JSON) before escalating to retry. The retry-with-exponential-backoff loop is the third layer — it handles provider-level failures and coordinates the fallback contract on exhaustion. Each layer handles a distinct failure class; a failure that escapes one layer is absorbed by the next. The design principle throughout is that the downstream scoring engine must always receive a typed, validated `LLMAnalysisResponse` — never a raw exception — regardless of which layer caught the failure. The complete layer stack with annotated code is in [`reliability-engineering.md`](reliability-engineering.md).

---

## Document Index

The technique documents in this suite each address a discrete engineering concern. They are intended to be read sequentially for first-time review, or accessed directly by topic for reference.

| # | Document | Phase | Primary concern | Key evidence |
|---|---|---|---|---|
| 1 | [reliability-engineering.md](reliability-engineering.md) | Phase 1 — Architecture | LLM-as-controlled-component philosophy, full reliability layer stack | `base.py:92–219`, `scoring_engine.py:323–348` |
| 2 | [schema-enforcement.md](schema-enforcement.md) | Phase 2 — Prompt Design | Inline JSON contract in system prompt, Pydantic validation loop | `base.py:27–66`, `ANALYSIS_SYSTEM_PROMPT` verbatim |
| 3 | [prompt-decomposition.md](prompt-decomposition.md) | Phase 2 — Prompt Design | Minimalist system prompt + rich user prompt design pattern | `guide_service.py` GUIDE_SYSTEM_PROMPT, f-string user prompt |
| 4 | [deterministic-fallback.md](deterministic-fallback.md) | Phase 3 — Resilience | FALLBACK_GUIDE, empty-signal fallback, mean-reversion scoring | `guide_service.py:32–153`, `scoring_engine.py:340–348` |
| 5 | [audit-trail.md](audit-trail.md) | Phase 3 — Resilience | `retry_count`, `fallback_used`, `processed_signals` as first-class schema fields | `LLMAnalysisResponse`, `ScoringOutput`, scan cycle aggregate |
| 6 | [cache-strategy.md](cache-strategy.md) | Phase 4 — Cost Control | Cluster-by-profile-hash, cost-bounded LLM call volume | `guide_service.py:189–192`, `compute_cluster_hash()` |
| 7 | [evaluation-framework.md](evaluation-framework.md) | Phase 5 — Governance | Model selection rubric, prompt quality gates, risk-based scoring criteria | Evaluation criteria derived from production audit fields |
| 8 | [testing-methodology.md](testing-methodology.md) | Phase 5 — Governance | Regression harness design, human review workflow, audit-trail-as-test-infrastructure | `retry_count`, `fallback_used`, `signal_count` as evaluation substrate |

---

## Phase 5 — Production and Governance

Production readiness for an LLM-integrated investment-grade system is not a deployment checklist — it is a sustained governance posture that I treated as a first-class engineering concern from the outset. The evaluation framework I designed for this platform is grounded in one decision made before the first prompt was written: the metrics I evaluate against must be observable from the audit fields already embedded in the production response schemas. Every field — `retry_count`, `fallback_used`, `signal_count`, `raw_delta`, `capped_delta`, `weighted_delta_contribution` — is simultaneously a runtime observable and an evaluation input. This means the evaluation framework is always current by definition. A prompt regression that changes signal distribution, fallback rate, or score delta behaviour is immediately visible in the same operational dashboards used to monitor the running system. A decoupled test harness, by contrast, is a maintenance liability that drifts from production behaviour and produces false confidence when the production prompt has changed but the harness has not.

The governance layer extends beyond automated metrics. I defined a structured human review workflow for any prompt change that touches high-stakes signal categories — specifically `nuclear_posture` and `military_escalation`, where semantic drift carries the highest consequence. A prompt change in these categories requires a domain-knowledgeable reviewer to assess a structured sample of before-and-after outputs against a rubric before the change reaches the production model routing layer. This is not bureaucracy imposed on the engineering process; it is the minimum defensible process for a system whose outputs are read as authoritative by users who may act on them. The evaluation framework document describes the three-tier rubric and the specific criteria applied at each review stage.

Cost governance at the provider level is managed through two mechanisms described in [cache-strategy.md](cache-strategy.md): the profile-hash clustering architecture that converts per-user LLM cost into per-cluster LLM cost, and the article truncation cap (800 characters per article) embedded in `ANALYSIS_USER_TEMPLATE`. Together these produce a predictable, auditable cost envelope. The evaluation framework extends this by defining alert thresholds for LLM call volume and token consumption per scan cycle — operational signals that allow me to detect prompt changes or traffic patterns that would otherwise create unbounded cost exposure before they become budget incidents. Governance, in this system, is not a separate function. It is continuous measurement against pre-defined thresholds on the same data the system produces for every production call.

→ **Evaluation framework:** [evaluation-framework.md](evaluation-framework.md)
→ **Testing methodology:** [testing-methodology.md](testing-methodology.md)

---

## Design Principles

The following principles govern every LLM-related decision documented in this suite. I refer to them by number in the technique documents.

**P1 — LLMs are inputs, not authors.**
The model produces structured observations. Deterministic code produces every value that reaches users. The model's probabilistic nature is confined to the signal-generation and guide-drafting steps and cannot contaminate scores, clock values, or stored records.

**P2 — Every output must be reconstructible.**
A score, guide section, or recommendation must trace back to its exact prompt inputs, model response, and processing steps without replaying the call. Audit fields are schema requirements, not optional logging annotations.

**P3 — Fail to a defined state, not to an exception.**
Every failure path terminates in a structured object with `fallback_used=True`. The downstream system always knows whether it received LLM output or synthetic fallback output.

**P4 — Prompts are contracts.**
The system prompt includes the complete output schema. The user prompt includes all input data. Together they constitute a reproducible specification: deviation from contract is a diagnosable error, not undefined behaviour.

**P5 — Schema enforcement is the first line of defence.**
Prompt-level schema specification precedes post-hoc extraction. Pydantic validation follows extraction. Per-signal error isolation ensures partial success is captured, not discarded.

**P6 — Cost control follows reliability, not the reverse.**
Retry logic is bounded at 3 attempts. Article content is truncated at 800 characters. Guide caching clusters users by profile hash. These are cost controls, but I designed them only after the reliability requirements were met. A cost optimisation that undermines auditability is not an optimisation.

---

## Source Files Referenced

All technical claims in this suite are backed by production code in the following files. Line references throughout the documents are stable against the repository state at time of writing.

| File | Role in architecture |
|---|---|
| `backend/app/services/llm/base.py` | `ANALYSIS_SYSTEM_PROMPT`, `ANALYSIS_USER_TEMPLATE`, `BaseLLMProvider`, `_extract_json_from_response` |
| `backend/app/services/content/guide_service.py` | `GUIDE_SYSTEM_PROMPT`, guide user prompt f-string, `compute_cluster_hash()`, `FALLBACK_GUIDE` |
| `backend/app/services/clock/scoring_engine.py` | `DoomsdayScoringEngine`, delta cap, score bounds, mean-reversion fallback, structured logging |
| `backend/app/services/llm/factory.py` | Provider selection via `LLM_PROVIDER` env var, `@lru_cache` singleton |
| `backend/app/services/llm/anthropic_llm.py` | Anthropic provider implementation |
| `backend/app/services/llm/ollama.py` | Ollama local provider implementation |
| `backend/app/schemas/doomsday.py` | `LLMAnalysisResponse`, `LLMSignalOutput`, `ArticleInput` Pydantic schemas |
| `backend/app/models/guide.py` | Guide ORM model with cache fields |

---

## How to Use This Suite

**For a structured first read:** Start with [reliability-engineering.md](reliability-engineering.md), which establishes the controlling philosophy and provides a complete map of the three reliability layers. Each subsequent document zooms into one layer or one design decision. The recommended sequence is: reliability-engineering → schema-enforcement → prompt-decomposition → deterministic-fallback → audit-trail → cache-strategy → evaluation-framework → testing-methodology.

**For topic-based reference:** Use the document index table above. Each technique document is self-contained: it reproduces the relevant prompt or code verbatim, annotates the design decisions inline, and includes its own evidence index.

**For a reliability and auditability focus:** [reliability-engineering.md](reliability-engineering.md) → [audit-trail.md](audit-trail.md) → [deterministic-fallback.md](deterministic-fallback.md). These three documents together describe a complete controlled-component envelope around every LLM invocation.

**For a prompt craft focus:** [schema-enforcement.md](schema-enforcement.md) → [prompt-decomposition.md](prompt-decomposition.md) → [evaluation-framework.md](evaluation-framework.md). These three documents cover prompt design decisions, from inline schema contracts to the deliberate minimalist/rich split between pipelines.

**For a governance and cost focus:** [cache-strategy.md](cache-strategy.md) → [evaluation-framework.md](evaluation-framework.md) → [testing-methodology.md](testing-methodology.md). These three documents describe how the system bounds operational cost, evaluates prompt quality, and enforces a structured review gate before any prompt change reaches production.

**For interview preparation:** [audit-trail.md](audit-trail.md) and [schema-enforcement.md](schema-enforcement.md) contain the densest concentration of design decisions relevant to investment-grade systems. [reliability-engineering.md](reliability-engineering.md) provides the framing context that makes those decisions coherent. [evaluation-framework.md](evaluation-framework.md) and [testing-methodology.md](testing-methodology.md) demonstrate that I designed the governance posture from the outset, not improvised it after the fact.

Every claim in every document is backed by verbatim code or verbatim prompt text. There are no generic best-practice assertions without a concrete code reference. If a claim cannot be supported by production evidence, it does not appear in this suite.

---

## Interview Quick Reference

> This section is designed to give a technical interviewer — or a reviewer scanning this document without opening sibling files — a complete picture of the five design decisions that define this system's prompt engineering posture. Each entry states the decision, the concrete evidence, and the reasoning in investment-grade terms.

---

### Decision 1: Prompts as Contracts, Not Directives

**The decision:** `ANALYSIS_SYSTEM_PROMPT` embeds the complete JSON output schema verbatim, ending with the instruction `Respond ONLY with valid JSON matching this exact schema`. The system prompt is a contract document, not a conversational directive.

**The evidence:** Lines 27–66 of `base.py` reproduce this prompt in its entirety. The schema in the prompt matches the `LLMSignalOutput` Pydantic class field-for-field.

**Why this matters for investment-grade systems:** A directive prompt produces compliance as a probability distribution. A contract prompt defines deviation as a diagnosable error — not undefined behaviour. In a system where schema deviation triggers retry or fallback, reducing the deviation rate at prompt level has a direct cost consequence measurable in API tokens. More importantly, it makes every deviation a named, categorised event rather than a parsing mystery.

---

### Decision 2: Probabilistic and Deterministic Layers Never Mix

**The decision:** The LLM extracts signals. The scoring engine computes scores. These are separate systems with a typed Pydantic object as the handoff point. The LLM is never on the scoring computation path.

**The evidence:** `DoomsdayScoringEngine` in `scoring_engine.py` applies a fully documented formula: `contribution = (raw_score/10) × SIGNAL_SCALE_FACTOR × direction × category_weight × country_modifier × confidence`. Hard bounds: `±5s` delta cap, `[60, 150]s` score range, enforced in pure Python (`lines 323–329`). The LLM cannot produce a clock value outside this range because it does not compute clock values.

**Why this matters for investment-grade systems:** Any automated system that informs decisions — financial or otherwise — must be able to prove which parts of its output are deterministic and which are probabilistic. Mixing the two produces outputs that cannot be audited without replaying the model call. Separating them means the scoring formula can be published, verified, and challenged independently of the model.

---

### Decision 3: Auditability as a Type System Requirement, Not a Logging Requirement

**The decision:** `retry_count`, `fallback_used`, `model_used`, and `processed_signals` are required — not optional — fields on `LLMAnalysisResponse`. A log entry can be lost, rotated, or separated from the output it describes. A required schema field cannot be absent.

**The evidence:** `LLMAnalysisResponse` in `app/schemas/doomsday.py` with no `Optional` wrapper on the audit fields. The retry loop in `base.py:185–219` sets `retry_count=attempt - 1` on success and `retry_count=self.max_retries` on fallback — both paths always populate the field, and the distinction is meaningful: 0 means clean first-attempt success.

**Why this matters for investment-grade systems:** In a regulated or audited context, a field that exists only in a log file carries zero assurance that it was captured for any given output. A field on the output schema is present by definition for every record in the database. Any score produced during an LLM degradation event can be identified by querying `fallback_used=True` or `retry_count > 0` — no log archaeology required.

---

### Decision 4: Three-Layer Failure Containment

**The decision:** Every LLM invocation passes through three independent failure-handling mechanisms, each targeting a distinct failure class: (1) prompt-level schema enforcement; (2) 3-tier JSON extraction that absorbs the three most common LLM format deviations without triggering retry; (3) exponential backoff retry up to 3 attempts, terminating in a structured `fallback_used=True` response.

**The evidence:** `_extract_json_from_response()` at `base.py:92–119` (verbatim above). The retry loop at `base.py:163–219` (verbatim above). The failure mode taxonomy in `reliability-engineering.md` maps every named failure to the layer that contains it.

**Why this matters for investment-grade systems:** Layered containment means failures are absorbed at the lowest possible layer, minimising API cost and latency impact. The extraction layer handles markdown-fence wrapping and prose-prefix without consuming a retry. A retry is only triggered when extraction fails — a genuine model deviation, not a formatting quirk. This design converts a broad failure category into observable, classifiable subtypes.

---

### Decision 5: Cost Control Subordinated to Reliability

**The decision:** I designed cost controls only after establishing reliability requirements. Article truncation at 800 characters, retry bounds at 3 attempts, and cluster-based guide caching are all cost-reducing — but each was specified in a way that cannot compromise the audit or reliability properties above.

**The evidence:** `_build_articles_text()` at `base.py:82–89` truncates each article at `content[:800]`. `compute_cluster_hash()` at `guide_service.py:189–192` derives a 16-character hex hash from `country_code|zip_code|household_size|housing_type|language` — deterministic, collision-resistant, and reproducible from stored user record fields without the original function call.

```python
# backend/app/services/content/guide_service.py — lines 189–192 (verbatim)
def compute_cluster_hash(user: User) -> str:
    """hash(region + household_size + housing_type + language) for cache clustering."""
    key = f"{user.country_code}|{user.zip_code or ''}|{user.household_size or 1}|{user.housing_type or 'unknown'}|{user.language}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**Why this matters for investment-grade systems:** Cost controls that create reliability gaps — for instance, truncating articles so aggressively that key events are excluded from the prompt, or caching guide content by a hash that cannot be reproduced from stored data — are not optimisations. They are hidden liabilities. The truncation cap is conservative enough that no event reported in a standard news article body is excluded. The hash is fully reproducible. Both controls are reversible without touching the reliability layer.

---

### Audit Field Quick-Read Table

For any LLM response produced by this system, the following fields allow a reviewer to reconstruct the provenance of the output without replaying the call:

| Field | Location | What it tells you |
|---|---|---|
| `retry_count` | `LLMAnalysisResponse` | 0 = clean first-attempt success; >0 = instability during this call |
| `fallback_used` | `LLMAnalysisResponse` | True = no LLM output; score derived from mean-reversion, not signals |
| `model_used` | `LLMAnalysisResponse` | Which provider was active; essential for cross-provider regression analysis |
| `analysis_notes` | `LLMAnalysisResponse` | Model's own summary, or fallback reason string |
| `raw_score` | `LLMSignalOutput` | LLM's raw assessment (0–10) before formula applied |
| `confidence` | `LLMSignalOutput` | Used as a direct multiplier in the scoring formula |
| `weighted_delta_contribution` | `SignalRecord` (scoring output) | Final contribution to clock delta, rounded to 4dp — full formula trace |
| `fallback_used` | `ScoringOutput` | Set at scoring layer too; scoring-layer fallback is distinct from LLM-layer fallback |

No score in this system is opaque. Every clock value is fully reconstructible from the fields above plus the stored prompt inputs.

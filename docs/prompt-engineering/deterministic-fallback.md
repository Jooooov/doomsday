# Deterministic Fallback Design: FALLBACK_GUIDE and Scoring Mean-Reversion

**Technique 5 of 7 — Doomsday Prep Platform LLM Architecture**

---

## The Core Constraint

Every system that delegates decisions to an LLM must answer one question before it goes to production: *what happens when the LLM is unavailable, slow, or returns unusable output?*

For most consumer applications the answer is a generic error message and a retry spinner. For an investment-grade system — one where output correctness and availability must be auditable — that answer is not acceptable. I designed the Doomsday Prep Platform with a hard requirement: **the system must produce meaningful, bounded, auditable output on every cycle, regardless of LLM availability**. The two mechanisms that enforce this requirement are the `FALLBACK_GUIDE` dictionary and the scoring engine's mean-reversion logic.

---

## Layer 1 — Guide Generation Fallback (FALLBACK_GUIDE)

### Design Intent

The guide generation pipeline calls an LLM to produce a personalised civil preparedness guide, streaming 12 category sections to the client via SSE. I designed the fallback tier not as an afterthought but as the load-bearing floor of the entire feature: if the LLM is unavailable at any point during generation, the system must serve a complete, structurally identical response.

### Verbatim Implementation

The `FALLBACK_GUIDE` dictionary in `backend/app/services/content/guide_service.py` (lines 32–153) is a static, hand-authored map of all 12 preparedness categories. Reproduced in full:

```python
FALLBACK_GUIDE: dict[str, dict] = {
    "water": {
        "title": "Água",
        "items": [
            {"text": "Água engarrafada (2 litros por pessoa/dia)", "quantity": 14, "unit": "litros", "priority": 1, "formula": None},
            {"text": "Pastilhas de purificação de água", "quantity": 50, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Recipiente de armazenamento de água potável", "quantity": 1, "unit": "unidades", "priority": 2, "formula": None},
        ],
        "tips": ["Armazene pelo menos 7 dias de água potável.", "Renove o stock a cada 6 meses."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "food": {
        "title": "Alimentação",
        "items": [
            {"text": "Conservas (atum, feijão, tomate)", "quantity": 21, "unit": "latas", "priority": 1, "formula": None},
            {"text": "Cereais e barras energéticas", "quantity": 14, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Abre-latas manual", "quantity": 1, "unit": "unidades", "priority": 1, "formula": None},
        ],
        "tips": ["Escolha alimentos não perecíveis com longa validade.", "Tenha em conta dietas especiais do agregado."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "shelter": { ... },        # 10 further categories, all structurally identical
    "health": { ... },
    "communication": { ... },
    "evacuation": { ... },
    "energy": { ... },
    "security": { ... },
    "documentation": { ... },
    "mental_health": { ... },
    "armed_conflict": { ... },
    "family_coordination": { ... },
}
```

*(Full dictionary: lines 32–153 of `guide_service.py`. Ellipses above are for readability only — all 12 categories are fully populated in source.)*

### Activation Path

The fallback activates at two distinct points in `generate_guide_streaming()`:

**Path A — LLM Unavailable at Startup (lines 211–214)**

```python
try:
    llm = get_llm()
except Exception as e:
    logger.warning(f"LLM unavailable, using fallback guide: {e}")
    llm = None
```

If `get_llm()` raises — provider not configured, container not reachable, API key missing — `llm` is set to `None`. The category loop then checks:

```python
if llm is None:
    section = base_content.get(category) or FALLBACK_GUIDE.get(category, {
        "title": category.replace("_", " ").title(),
        "items": [],
        "tips": [],
        "disclaimer": "Conteúdo informativo.",
    })
    content[category] = section
    yield json.dumps({"type": "category_done", "category": category, "data": section, "fallback": True})
    continue
```

The `fallback: True` flag in the SSE payload is the audit signal — the client and any downstream logging system can detect and record when fallback content was served.

**Path B — Per-Category LLM Error (lines 277–286)**

```python
except Exception as e:
    logger.error(f"Guide generation failed for {category}: {e}")
    section = base_content.get(category) or FALLBACK_GUIDE.get(category, {
        "title": category.replace("_", " ").title(),
        "items": [],
        "tips": [],
        "disclaimer": "Conteúdo informativo.",
    })
    content[category] = section
    yield json.dumps({"type": "category_error", "category": category, "data": section})
```

Even mid-stream, if a single category call fails, the stream continues with fallback content for that category and LLM-generated content for all others. The client receives a structurally complete 12-category guide regardless.

### Fallback Resolution Priority

I designed a three-level resolution order:

1. **Regional base content** — `base_content.get(category)`: pre-generated, region-specific content loaded from `{REGIONS_DIR}/{country_code}/{zip_code}.json` at the start of the request. This is the richest fallback — it has regional specificity without requiring a live LLM call.
2. **FALLBACK_GUIDE** — static hardcoded defaults. No regional specificity, but structurally complete and always available.
3. **Inline minimal stub** — if the category key is somehow missing from FALLBACK_GUIDE, the expression `{"title": category.replace("_", " ").title(), "items": [], ...}` produces a valid empty structure rather than crashing.

This layered resolution means the fallback degrades gracefully through specificity levels rather than binary success/failure.

### Why Hardcoded Content Is the Right Choice Here

I chose to hardcode `FALLBACK_GUIDE` as a static dictionary rather than fetching it from a database or generating it at startup for three reasons:

1. **Zero runtime dependencies**: A hardcoded dict cannot fail to load. A database query can timeout; a file read can fail on a misconfigured path. The fallback must be unconditionally available.
2. **Auditability**: The exact content served in a fallback scenario is visible in source control and deterministic across deployments. Any audit of "what did the user receive on 14 March 2026 at 03:00 UTC when the LLM was down?" can be answered by examining a specific git commit.
3. **Reviewability**: Domain experts (civil protection, legal compliance) can review and approve the fallback content directly in source. There is no intermediary generation step that could produce unreviewed output.

---

## Layer 2 — Doomsday Clock Scoring Fallback (Mean-Reversion)

### The Problem with Frozen Scores

The scoring engine converts LLM-produced news signals into Doomsday Clock score deltas. When the LLM fails or returns empty signals, the naive fallback is to freeze the previous score — apply zero delta and move on. I rejected this approach because frozen scores have a specific failure mode in a system that runs on a cycle: a country that last had news-driven scoring three weeks ago retains a score that may no longer reflect its actual geopolitical position. Any downstream display or alerting built on that score is operating on stale data with no indication of staleness.

### Mean-Reversion as the Fallback Strategy

I designed the fallback to be active rather than passive. When the LLM returns no signals, the scoring engine applies a calibrated mean-reversion toward the country's regional anchor score. The implementation is in `_score_fallback()` in `backend/app/services/clock/scoring_engine.py` (lines 331–372):

```python
def _score_fallback(
    self,
    inp: ScoringInput,
    regional_anchor: float,
) -> ScoringOutput:
    """
    Fallback scoring when the LLM returned no signals.

    Instead of freezing the score, we apply gentle mean-reversion toward
    the regional anchor. This prevents stale scores from drifting too far
    from the calibrated baseline when news is unavailable.

    Mean-reversion rate: 10% of the gap per cycle, capped at ±MAX_DELTA.
    """
    gap = regional_anchor - inp.previous_score
    raw_delta = gap * 0.10   # 10% reversion per cycle
    capped_delta = self._apply_delta_cap(raw_delta)
    new_score = self._apply_score_bounds(inp.previous_score + capped_delta)
    ...
    return ScoringOutput(
        ...
        fallback_used=True,
        processed_signals=[],
    )
```

### The Regional Anchor

The reversion target is `regional_anchor`, which is `CountryConfig.effective_anchor_seconds` — the global baseline (85.0s) multiplied by the country's `regional_multiplier`. Reproduced from `region_registry.py` (lines 98–101):

```python
@property
def effective_anchor_seconds(self) -> float:
    """Global baseline adjusted by regional multiplier."""
    return GLOBAL_BASELINE_SECONDS * self.regional_multiplier
```

Multiplier calibration examples from the registry:

| Country | Multiplier | Anchor (seconds) | Geopolitical rationale |
|---------|-----------|-----------------|----------------------|
| Ukraine (UA) | 0.71 | 60.3s | Active conflict zone — floor at minimum |
| North Korea (KP) | 0.75 | 63.8s | Nuclear + missile posture |
| Russia (RU) | 0.76 | 64.6s | Nuclear posture, active aggressor |
| Taiwan (TW) | 0.80 | 68.0s | Active strait tension |
| China (CN) | 0.82 | 69.7s | Nuclear + geopolitical |
| Portugal (PT) | 1.10 | 93.5s | NATO periphery, no direct exposure |
| Brazil (BR) | 1.25 | 106.3s | Geographically distant |

When the LLM fails for Ukraine, the score reverts at 10% per cycle toward 60.3s — not toward the global baseline of 85.0s. This preserves the geopolitical calibration even in the absence of live signal data.

### Reversion Rate and Cap

I chose 10% per cycle for the reversion rate as a deliberate calibration decision. A country 20 seconds above its anchor will move 2 seconds closer per cycle. At the maximum gap — a country at 150s with a 60s anchor — the raw reversion is 9.0s, which the ±5s delta cap will clamp to 5.0s. The cap guarantee means **the fallback path obeys the same hard constraints as the signal path**. There is no scenario in which the fallback produces a score outside [60.0, 150.0] or moves the clock more than ±5 seconds in a single cycle.

This is the constraint that matters for auditing: the bounds are enforced by code, not by assumption about LLM output quality.

### The Emergency Exception Fallback

Below the mean-reversion fallback sits a second, harder fallback for cases where the scoring engine itself throws an exception (lines 374–388):

```python
def _score_error_fallback(self, inp: ScoringInput) -> ScoringOutput:
    """Emergency fallback on exception — zero delta, keep previous score."""
    return ScoringOutput(
        country_code=inp.country_code,
        country_name=inp.country_name,
        previous_score=inp.previous_score,
        raw_delta=0.0,
        capped_delta=0.0,
        new_score=round(self._apply_score_bounds(inp.previous_score), 3),
        signal_count=0,
        dominant_signal_category=None,
        top_contributing_article=None,
        fallback_used=True,
        processed_signals=[],
    )
```

This is the final safety layer. It fires only if the scoring engine's own logic raises — for example, if `get_country_config()` returns an unexpected type or if the signal list contains data that cannot be processed. In this case I accept the tradeoff: the score freezes at the previous value with `fallback_used=True` and zero delta. The score does not move, but it also does not crash, and the audit trail records exactly what happened.

The caller in `score_all_countries()` wraps each country's scoring call in a try/except, ensuring one country's exception cannot prevent other countries from being scored in the same cycle.

### Fallback Trigger Logic

The signal/fallback branching logic in `score_country()` (lines 151–155):

```python
if inp.llm_response.fallback_used or not inp.llm_response.signals:
    return self._score_fallback(
        inp=inp,
        regional_anchor=regional_anchor,
    )
```

Two conditions route to fallback:
- `fallback_used=True`: set by `BaseLLMProvider` when all retry attempts are exhausted (see `base.py` lines 213–219). The LLM was reachable but produced no usable output after 3 attempts.
- `not inp.llm_response.signals`: the LLM responded and JSON was parsed, but the signals list is empty. This covers the case where the model returns a valid JSON envelope with no signal entries — a silent failure mode that direct status code checking would miss.

---

## Fallback Architecture Summary

```
Guide Generation                    Scoring Engine
─────────────────                   ──────────────────────────────────────
LLM call fails at startup           LLM returns empty signals or fallback_used=True
        │                                       │
        ▼                                       ▼
base_content.get(category)          _score_fallback()
        │                               gap = anchor - previous_score
        │ miss                           raw_delta = gap × 0.10
        ▼                               capped_delta = clamp(raw_delta, ±5s)
FALLBACK_GUIDE.get(category)        new_score = clamp(previous + capped, 60–150s)
        │                                       │
        │ miss                          scoring_engine exception
        ▼                                       │
Inline minimal stub                             ▼
{title, items:[], tips:[], ...}     _score_error_fallback()
                                    zero delta, freeze score, fallback_used=True
```

Every path through this diagram produces:
- A structurally valid response (never a 500, never missing fields)
- A `fallback_used=True` flag visible to logging, monitoring, and audit consumers
- Output that obeys the same schema and bounds constraints as the nominal path

---

## Financial Framing

In regulated financial systems, a component that silently fails or produces out-of-bounds output is a compliance liability, not just an engineering problem. The fallback design here satisfies three properties that matter in audit contexts:

**Completeness**: Every request produces a response. There is no query that returns nothing. A compliance review can always point to a record.

**Boundedness**: The scoring engine's hard constraints — ±5s delta cap, [60, 150] score bounds — apply to fallback paths as strictly as to nominal paths. The constraints are not "best-effort" on the happy path; they are structural invariants enforced in `_apply_delta_cap()` and `_apply_score_bounds()`, called identically from both `score_country()` and `_score_fallback()`.

**Observability**: `fallback_used=True` appears in `ScoringOutput`, in `LLMAnalysisResponse`, and in the SSE payload's `fallback: True` field. An operations team can alert on elevated fallback rates without requiring log parsing; the field is first-class in the data model.

These properties reflect a design principle I applied consistently: the LLM is a signal-enrichment layer inside a deterministic envelope, not the envelope itself. The envelope is always present, always bounded, always auditable.

# Audit Trail Design: Observable LLM Behaviour at Every Layer

**Document:** `audit-trail.md`
**Suite:** Doomsday Prep Platform — Prompt Engineering Case Study
**Author framing:** Senior Prompt Engineer, investment-grade system design
**Primary axes:** Auditability · Output Reliability
**Secondary axis:** Cost control

---

## Design Philosophy

I built the audit trail into the response schema from day one, not as an afterthought. My reasoning was simple: in a system where LLM output influences a risk score that decision-makers read as authoritative, the difference between *auditable* and *not auditable* is the difference between a system you can trust and a system you merely hope is working.

An auditable LLM system is one where, for any historical scan cycle, an operator can answer these questions from stored data alone, without replaying calls:

1. Did the LLM succeed or fall back to degraded operation for this country?
2. How many retry attempts did it take to obtain a usable response?
3. Which model served the call?
4. Exactly which signals were processed by the scoring engine, at what weights?
5. What delta was applied to the score, and was it capped?

I designed three interlocking audit surfaces to answer these questions: the **LLM response envelope** (`retry_count`, `fallback_used`, `model_used`), the **scoring engine output record** (`processed_signals`, `capped_delta`, `raw_delta`), and the **scan cycle aggregate** (`llm_calls_attempted`, `llm_calls_succeeded`, `llm_fallback_used`). Each layer is independently queryable. Together they form a complete lineage from raw news article to final clock score.

---

## Layer 1 — LLM Response Envelope

The first audit surface lives on `LLMAnalysisResponse`, the return type of every call through `BaseLLMProvider.analyse_articles_for_country()`. I designed this schema to carry not just the LLM's output, but the metadata of how that output was obtained.

```python
# backend/app/schemas/doomsday.py — lines 84–92 (verbatim)

class LLMAnalysisResponse(BaseModel):
    """Full LLM response for a batch of articles targeting a country."""

    country_code: str
    signals: list[LLMSignalOutput]
    analysis_notes: str | None = None
    model_used: str | None = None      # ← which provider served this call
    retry_count: int = 0               # ← 0 = first attempt succeeded
    fallback_used: bool = False        # ← True = empty-signal graceful degradation
```

### `retry_count`

This field records how many retry attempts were consumed before a usable response was obtained. The value is computed inside `analyse_articles_for_country()` as `attempt - 1` on the success path, and `self.max_retries` on the total-failure path:

```python
# backend/app/services/llm/base.py — lines 185–218 (annotated)

for attempt in range(1, self.max_retries + 1):          # max_retries = 3
    try:
        raw_text = await self._call_llm(...)
        payload = _extract_json_from_response(raw_text)
        signals = self._parse_signals(payload, country_code)

        return LLMAnalysisResponse(
            ...
            retry_count=attempt - 1,    # ← 0 on first-attempt success
                                        #   1 if first failed, second succeeded
                                        #   2 if two failed, third succeeded
            fallback_used=False,
        )

    except Exception:
        if attempt < self.max_retries:
            await asyncio.sleep(2 ** attempt)  # 2s then 4s backoff

# Total failure path:
return LLMAnalysisResponse(
    ...
    retry_count=self.max_retries,   # ← 3: all attempts exhausted
    fallback_used=True,
)
```

> **Annotation:** `retry_count=0` is the normal state. It means the LLM responded with clean, parseable JSON on the first call — no retries consumed, no backoff delay incurred. A `retry_count` of 1 or 2 is operationally interesting: it means the first response was malformed or unavailable, but the system recovered. `retry_count=3` combined with `fallback_used=True` is the critical signal — it means the LLM layer degraded to empty-signal mode and the scoring engine operated on mean-reversion only.

**Why this matters for cost control:** Retry count is also a cost indicator. Each retry is an additional LLM API call at full token cost. If `retry_count > 0` becomes frequent for a particular provider or model, it indicates a regression in output quality that is costing money as well as latency. This field enables provider-level cost attribution without needing to instrument the HTTP layer separately.

### `fallback_used`

This boolean is `True` in exactly two cases: when all retry attempts are exhausted (total LLM failure), and when the call is short-circuited at entry because no articles were provided:

```python
# backend/app/services/llm/base.py — lines 146–152 (verbatim)

if not articles:
    return LLMAnalysisResponse(
        country_code=country_code,
        signals=[],
        fallback_used=True,                        # ← no articles: forced fallback
        analysis_notes="No articles provided",
    )
```

The `fallback_used` flag is consumed directly by the scoring engine to choose its execution path:

```python
# backend/app/services/clock/scoring_engine.py — line 151 (verbatim)

if inp.llm_response.fallback_used or not inp.llm_response.signals:
    return self._score_fallback(inp=inp, regional_anchor=regional_anchor)
```

> **Annotation:** This coupling is intentional and explicit. The scoring engine does not inspect `retry_count`, `model_used`, or `analysis_notes` — it only needs to know whether it received signals. `fallback_used` is the clean, typed interface between the LLM reliability layer and the deterministic scoring layer. An auditor can query `fallback_used=True` in the database and immediately know that for those scan cycles, the clock moved by mean-reversion rather than by LLM-derived signals. This is the difference between an auditable system and a system that happens to have logs.

### `model_used`

I included `model_used` on the response envelope even though the system currently supports a single configured provider. The rationale is forward-looking: as the system scales to multi-provider routing (e.g., routing nuclear-posture analysis to a specialist model while using a cheaper model for propaganda signals), `model_used` becomes the key for provider-level performance and cost attribution. Instrumenting it from day one costs nothing and preserves the audit trail for future comparison.

---

## Layer 2 — Scoring Engine Output Record

The second audit surface lives on `ScoringOutput`, the dataclass produced by `DoomsdayScoringEngine.score_country()`. This layer captures what the scoring engine did with the LLM's signals — not just the final score, but the complete intermediate calculation.

```python
# backend/app/services/clock/scoring_engine.py — lines 64–84 (verbatim)

@dataclass
class ScoringOutput:
    """Full scoring result for one country, ready to persist."""

    country_code: str
    country_name: str

    previous_score: float
    raw_delta: float          # Un-capped sum of signal contributions
    capped_delta: float       # Actual change applied (bounded by ±MAX_DELTA)
    new_score: float          # Final score after delta + bounds clamping

    signal_count: int
    dominant_signal_category: Optional[str]
    top_contributing_article: Optional[str]
    fallback_used: bool

    processed_signals: List[SignalRecord] = field(default_factory=list)
    calculated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

### `processed_signals`

This is the most granular audit field in the system. It is a list of `SignalRecord` objects — one per LLM signal that the scoring engine actually processed. Each record captures not just the LLM's output but the engine's intermediate calculation:

```python
# backend/app/schemas/doomsday.py — lines 99–121 (verbatim)

class SignalRecord(BaseModel):
    """Enriched signal after scoring engine processing."""

    country_code: str
    signal_category: str
    raw_score: float
    sentiment: str
    confidence: float
    reasoning: str | None = None

    # Computed by the engine
    category_weight: float = 1.0
    country_modifier: float = 1.0
    weighted_delta_contribution: float = 0.0

    # Article provenance
    article_url: str | None = None
    article_title: str | None = None
    article_published_at: datetime | None = None
    article_source: str | None = None

    llm_raw_response: dict[str, Any] | None = None
```

The `weighted_delta_contribution` field is particularly important for auditability. It is the computed contribution of each individual signal to the final `raw_delta`, computed from the core formula:

```python
# backend/app/services/clock/scoring_engine.py — lines 162–186 (annotated)

for llm_signal in inp.llm_response.signals:
    direction = get_sentiment_direction(llm_signal.sentiment)  # -1, +1, or -0.2
    cat_weight = get_category_weight(llm_signal.signal_category)

    contribution = (
        (llm_signal.raw_score / 10.0)   # ← normalise 0–10 to 0.0–1.0
        * SIGNAL_SCALE_FACTOR            # ← platform-level scale constant
        * direction                      # ← -1 (escalating) or +1 (de-escalating)
        * cat_weight                     # ← category importance weight
        * country_modifier               # ← inverse of regional_multiplier
        * llm_signal.confidence          # ← LLM self-reported confidence gates impact
    )

    signal_record = SignalRecord(
        ...
        category_weight=cat_weight,
        country_modifier=country_modifier,
        weighted_delta_contribution=round(contribution, 4),  # ← 4 decimal places
    )
    processed_signals.append(signal_record)
```

> **Annotation:** `processed_signals` is the complete audit lineage from LLM output to score delta. Given a `ScoringOutput` record in the database, an operator can sum `weighted_delta_contribution` across all `processed_signals` and arrive at `raw_delta` — exactly. This property does not hold for systems that compute scores opaquely and log only the final result. I designed `processed_signals` to be persisted alongside the `CountryDeltaResult` so that score changes are always explainable at the signal level, not just at the aggregate level.

### `raw_delta` and `capped_delta`

The scoring engine module docstring identifies `capped_delta` explicitly as part of the audit trail:

```python
# backend/app/services/clock/scoring_engine.py — line 25 (verbatim)
# Note: capped_delta is the ACTUAL change stored in DB (audit trail).
```

The distinction between `raw_delta` and `capped_delta` is material for auditing. If `raw_delta` is significantly larger than `capped_delta` (e.g., `raw_delta = 8.3`, `capped_delta = 5.0`), it means the hard ±5-second cap was applied and the score change was constrained. A reviewer can see exactly how much the LLM signals wanted to move the clock versus how much the deterministic safety bounds allowed:

```python
# backend/app/services/clock/scoring_engine.py — lines 194–200 (verbatim)

raw_delta = sum(s.weighted_delta_contribution for s in processed_signals)

# ── Cap ───────────────────────────────────────────────────────────────────
capped_delta = self._apply_delta_cap(raw_delta)

# ── Compute new score ─────────────────────────────────────────────────────
new_score = self._apply_score_bounds(inp.previous_score + capped_delta)
```

```python
# backend/app/services/clock/scoring_engine.py — lines 323–329 (verbatim)

def _apply_delta_cap(self, raw_delta: float) -> float:
    """Clamp raw_delta to ±MAX_DELTA_PER_CYCLE (hard constraint)."""
    return max(-self.max_delta, min(self.max_delta, raw_delta))

def _apply_score_bounds(self, score: float) -> float:
    """Clamp score to [MIN_SCORE, MAX_SCORE]."""
    return max(self.min_score, min(self.max_score, score))
```

> **Annotation:** Storing both `raw_delta` and `capped_delta` enables a class of audit query that would be impossible with only the final score: "how often did the cap fire?" If `raw_delta` routinely exceeds `capped_delta`, it suggests either the scoring weights are too aggressive or the LLM is over-scoring signals — both are calibration signals that a PE needs to detect. Persisting only `capped_delta` would hide this pattern.

### `fallback_used` on `ScoringOutput`

`fallback_used` appears at both Layer 1 (on `LLMAnalysisResponse`) and Layer 2 (on `ScoringOutput`). I propagated it to the scoring output deliberately, because `ScoringOutput` is the record that gets persisted to the database — not the `LLMAnalysisResponse`, which is ephemeral. A database row with `fallback_used=True` means: for this country in this cycle, the clock position was determined by mean-reversion toward the regional anchor, not by LLM-derived signals. That fact must travel with the record.

The fallback scoring path makes this explicit:

```python
# backend/app/services/clock/scoring_engine.py — lines 331–372 (annotated)

def _score_fallback(self, inp: ScoringInput, regional_anchor: float) -> ScoringOutput:
    """
    Fallback scoring when the LLM returned no signals.
    Mean-reversion rate: 10% of the gap per cycle, capped at ±MAX_DELTA.
    """
    gap = regional_anchor - inp.previous_score
    raw_delta = gap * 0.10   # ← 10% reversion per cycle toward regional anchor
    capped_delta = self._apply_delta_cap(raw_delta)
    new_score = self._apply_score_bounds(inp.previous_score + capped_delta)

    return ScoringOutput(
        ...
        raw_delta=round(raw_delta, 4),
        capped_delta=round(capped_delta, 4),
        new_score=round(new_score, 3),
        signal_count=0,                   # ← zero signals: explicit in the record
        dominant_signal_category=None,    # ← no dominant category
        fallback_used=True,               # ← audit flag: mean-reversion applied
        processed_signals=[],             # ← empty list: no signals to attribute
    )
```

> **Annotation:** The fallback path is a designed scoring behaviour, not an error state. The clock does not freeze when the LLM fails — it applies gentle mean-reversion toward the calibrated regional anchor at 10% per cycle. Storing `fallback_used=True` alongside `signal_count=0` and an empty `processed_signals` list gives an auditor complete visibility into exactly what happened: no signals were available, and the score shifted by a known, deterministic formula. The delta is still attributable; it is just attributed to the anchor rather than to any specific news event.

---

## Layer 3 — Scan Cycle Aggregate

The third audit surface operates at the scan cycle level, not the country level. `ScanCycleResult` aggregates LLM reliability metrics across all countries in a single 6-hour cycle:

```python
# backend/app/schemas/doomsday.py — lines 148–161 (verbatim)

class ScanCycleResult(BaseModel):
    """Aggregate result of a full 6-hour scan cycle across all countries."""

    scan_run_id: uuid.UUID
    started_at: datetime
    completed_at: datetime
    status: str
    country_results: list[CountryDeltaResult]
    total_articles_fetched: int
    total_signals_generated: int
    llm_calls_attempted: int            # ← total calls sent to LLM provider
    llm_calls_succeeded: int            # ← calls that returned usable signals
    llm_fallback_used: bool             # ← True if any country used fallback
```

The `llm_calls_attempted` / `llm_calls_succeeded` pair is the cycle-level reliability ratio. If this cycle processed 12 countries, `llm_calls_attempted=12` and `llm_calls_succeeded=9` means 3 countries operated on fallback for this cycle. Combined with `llm_fallback_used=True`, this is the first signal an on-call operator sees when reviewing a cycle summary.

The `ClockSnapshotResponse` — the API schema for individual timeline data points — also carries `fallback_used` at the country level:

```python
# backend/app/schemas/doomsday.py — lines 182–195 (verbatim)

class ClockSnapshotResponse(BaseModel):
    """A single point-in-time snapshot for the timeline chart."""

    country_code: str
    score_seconds: float
    delta_applied: float
    raw_delta: float
    signal_count: int
    fallback_used: bool                  # ← visible in API response
    dominant_signal_category: str | None
    snapshot_ts: datetime
```

> **Annotation:** Exposing `fallback_used` in the public API response is a deliberate design choice with real implications. Any consumer of the API — a dashboard, an alerting system, a downstream risk aggregator — can distinguish between score changes driven by LLM analysis and score changes driven by mean-reversion. Without this field, a consumer seeing a small positive delta in Ukraine's score during a cycle where the LLM provider was down would have no way to know the movement was mechanical, not analytical. The API surface is part of the audit trail.

---

## How the Three Layers Compose

I designed the audit fields to compose across layers without duplication:

| Question | Layer | Field |
|---|---|---|
| Did the LLM succeed for this country? | LLM envelope | `fallback_used` on `LLMAnalysisResponse` |
| How many retries did it take? | LLM envelope | `retry_count` on `LLMAnalysisResponse` |
| Which model served the call? | LLM envelope | `model_used` on `LLMAnalysisResponse` |
| What signals were processed? | Scoring engine | `processed_signals` on `ScoringOutput` |
| What did each signal contribute? | Scoring engine | `weighted_delta_contribution` on `SignalRecord` |
| Was the delta capped? | Scoring engine | `raw_delta` vs `capped_delta` on `ScoringOutput` |
| Did fallback apply to the final stored score? | Scoring engine | `fallback_used` on `ScoringOutput` / `CountryDeltaResult` |
| What was the cycle-level reliability ratio? | Scan aggregate | `llm_calls_attempted` / `llm_calls_succeeded` on `ScanCycleResult` |
| Is the API response based on LLM analysis? | API response | `fallback_used` on `ClockSnapshotResponse` |

I designed these to be independently queryable. An operator investigating a suspicious score movement does not need to correlate log files across services — every question above is answerable from a single database query against the persisted schema.

---

## Structured Logging as a Parallel Channel

Beyond the schema fields, I designed the structured log entries in the scoring engine to emit the same audit information in a format suitable for log aggregation:

```python
# backend/app/services/clock/scoring_engine.py — lines 219–229 (verbatim)

logger.info(
    "Scored %s: previous=%.2fs raw_delta=%+.4fs capped=%+.4fs new=%.2fs "
    "signals=%d dominant=%s fallback=False",
    inp.country_code,
    inp.previous_score,
    raw_delta,
    capped_delta,
    new_score,
    len(processed_signals),
    dominant_category,
)
```

This log line emits the same values as the `ScoringOutput` fields in a format that a log query (e.g., in Grafana Loki or AWS CloudWatch Insights) can parse with a regex or structured format. The `fallback=False` hard-coded suffix becomes `fallback=True` in the fallback path log. This means the audit trail exists in two independent stores: the database (queryable, persistent, schema-validated) and the log stream (real-time, transient, regex-parseable). If the database write fails, the log provides a recovery path.

---

## Why This Architecture Is Appropriate for Investment-Grade Systems

I would make the following arguments specifically in a financial system review:

**Auditability is not the same as logging.** A system with structured logs but no schema-level audit fields is auditable in theory but not in practice. When a score anomaly occurs at 03:00, the on-call engineer needs to query a database, not grep through log files. I embedded audit fields into the persisted schemas so that post-hoc analysis is a SQL query, not an incident.

**Fallback state must travel with the data.** In financial systems, a number without provenance is a liability. A Doomsday Clock score change of +2.3 seconds is meaningless without knowing whether it came from three `nuclear_posture` signals at high confidence or from a 10% mean-reversion on a cycle where the LLM provider was unreachable. `fallback_used` is that provenance, and I designed it to travel all the way from the LLM response envelope to the public API response without being dropped at any layer boundary.

**The audit trail enables calibration, not just compliance.** `retry_count` is not just an operational flag — it is a quality signal for prompt engineering. If `retry_count > 0` increases after a model version upgrade, it means the new model's JSON compliance regressed. If `raw_delta` routinely exceeds `capped_delta`, the scoring weights need recalibration. The audit fields I designed are the data source for the evaluation framework I use to assess system health over time.

---

## Navigation

- ← [README.md](README.md) — Suite overview and architecture map
- ← [reliability-engineering.md](reliability-engineering.md) — 3-tier JSON extraction and retry loop that produce `retry_count` and `fallback_used`
- ← [schema-enforcement.md](schema-enforcement.md) — Pydantic enforcement that gates what enters `processed_signals`
- → [deterministic-fallback.md](deterministic-fallback.md) — How the scoring engine uses `fallback_used` to activate mean-reversion
- → [evaluation-framework.md](evaluation-framework.md) — How audit fields serve as the primary data source for system health evaluation

---

*Source files: `backend/app/services/llm/base.py` · `backend/app/services/clock/scoring_engine.py` · `backend/app/schemas/doomsday.py`*

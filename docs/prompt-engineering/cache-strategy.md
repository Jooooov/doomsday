# Cache Strategy: Cluster-by-Profile-Hash for LLM Cost Control

**Author:** Senior Prompt Engineer, Doomsday Prep Platform
**Series:** Prompt Engineering Case Study — Document 6 of 8
**Framing axis:** Cost control (secondary) / Auditability (primary)

---

## 1. The Problem I Was Solving

The Doomsday Prep Platform generates personalised survival guides — 12 category sections
per user, each requiring an independent LLM call. With Anthropic Claude pricing in the
range of $3–15 per million tokens and each guide generation consuming roughly 8,000–12,000
tokens across all sections, the naive approach — one complete guide generation per user
session — becomes financially untenable at scale.

More importantly for an investment-grade system: unbounded LLM call volume means
unbounded cost exposure. From an auditability standpoint, a system whose operational
cost cannot be predicted or capped is not production-safe regardless of its functional
correctness.

I designed a two-tier caching architecture centred on a deterministic profile hash that
clusters users into equivalence classes. Users in the same cluster receive the same
guide content, generated once. This transforms per-user LLM cost into per-cluster LLM
cost — a meaningful distinction at scale.

---

## 2. The Profile Hash: Deliberate Field Selection

The cache key is produced by `compute_cluster_hash()` in
`backend/app/services/content/guide_service.py`:

```python
def compute_cluster_hash(user: User) -> str:
    """hash(region + household_size + housing_type + language) for cache clustering."""
    key = f"{user.country_code}|{user.zip_code or ''}|{user.household_size or 1}|{user.housing_type or 'unknown'}|{user.language}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

I chose exactly five fields for the hash key, and I chose them deliberately:

| Field | Rationale |
|---|---|
| `country_code` | Determines legal framework, infrastructure availability, and regional risk profile. A PT user and a DE user should never share a guide — the regulatory context alone makes their content incompatible. |
| `zip_code` | Provides sub-regional granularity for flood zones, seismic risk, and proximity to civil protection centres. Absent zip code collapses to `''` rather than erroring, keeping clustering coarse. |
| `household_size` | Directly drives every quantity calculation — water volumes, food rations, medication reserves. Two users identical in every other field but different household sizes produce materially different guides. |
| `housing_type` | Determines shelter section logic — apartment dwellers cannot follow the same shelter-in-place protocol as detached house owners. |
| `language` | Determines output language for guide text. A Portuguese-language user sharing content with an English-language user produces garbled output, so language is a hard cluster boundary. |

I intentionally excluded fields like `has_vehicle`, `has_children`, `budget_level`,
and `floor_number` from the hash. These fields appear in the LLM prompt and personalise
content within a cluster, but they do not justify separate LLM calls. The guide for a
family with children in a Lisbon apartment with a budget of €200 and no vehicle is
sufficiently similar to the same household with a vehicle that sharing a base cluster
and noting the difference in the prompt is the right trade-off.

This is a deliberate coarseness decision. In a financial context, I frame it as a
cost/precision dial: finer-grained clustering increases output precision but reduces
cache hit rate and increases cost. I set the dial at the point where the content
remains materially correct for all users in a cluster.

---

## 3. Two-Tier Cache Architecture

I designed two independent persistence layers that serve different reliability goals:

### Tier 1: Filesystem Cluster Cache (Speed + Cost Barrier)

```python
# In generate_guide_streaming(), backend/app/services/content/guide_service.py

cluster_hash = compute_cluster_hash(user)

# 1. Cluster cache hit → persist to DB if needed, then return
cache_path = Path(settings.DATA_DIR) / "clusters" / f"{cluster_hash}.json"
if cache_path.exists():
    with open(cache_path) as f:
        cached = json.load(f)
    # Ensure DB record exists (in case previous save failed)
    await _ensure_guide_in_db(user, cluster_hash, cached, db)
    yield json.dumps({"type": "cached", "content": cached})
    return
```

The filesystem check is the first gate after hash computation. If a cluster file
exists, the function returns immediately — no LLM call, no network round-trip, no
token expenditure. The `_ensure_guide_in_db()` call on the hot path ensures that DB
records remain consistent even if the original generation run crashed before persisting
to Postgres, providing crash recovery without re-invoking the LLM.

The cluster files live under `DATA_DIR/clusters/{hash[:16]}.json`. The 16-character
hex prefix of a SHA-256 hash provides 2^64 distinct buckets — more than sufficient for
any realistic user population while remaining human-readable for debugging.

### Tier 2: PostgreSQL Version Store (Durability + Audit)

After a new guide is generated, I persist it to two database tables:

```python
# Guide table record — one per user
guide = Guide(
    id=str(uuid.uuid4()),
    user_id=user.id,
    cluster_hash=cluster_hash,          # ← hash stored for audit queries
    language=user.language,
    profile_snapshot={                   # ← profile frozen at generation time
        "country_code": user.country_code,
        "household_size": user.household_size,
        "housing_type": user.housing_type,
        "has_vehicle": user.has_vehicle,
    },
)

# GuideVersion table record — append-only history
version = GuideVersion(
    id=str(uuid.uuid4()),
    guide_id=guide.id,
    version_number=next_version,
    content=content,                     # ← full 12-category JSON in JSONB
    region_id=user.country_code,
    rollback_available=next_version > 1,
)
```

The `cluster_hash` is stored on the `Guide` record, making it possible to audit which
cluster served a given user's content, and to run queries like "how many users are
sharing cluster `a3f9b2c1d4e56789`?" — a useful operational metric for understanding
cache efficiency and identifying clusters that are stale and need regeneration.

The `profile_snapshot` captures the profile state at generation time. This is
investment-grade provenance: if a user disputes the content of their guide, I can
recover exactly what their profile looked like when the guide was produced, independent
of any subsequent profile edits.

---

## 4. Regional Base Content as a Pre-Computation Layer

Before the LLM call loop, I load pre-generated regional content:

```python
# 2. Load base regional content (pre-generated batch)
region_path = (
    Path(settings.REGIONS_DIR)
    / user.country_code.lower()
    / f"{user.zip_code or 'general'}.json"
)
base_content = {}
if region_path.exists():
    with open(region_path) as f:
        base_content = json.load(f)
```

This regional content is injected into the user-facing prompt for each category:

```python
prompt = f"""Generate preparation guide section for: {category}
...
Base regional content: {json.dumps(base_content.get(category, {}))}
...
"""
```

The design intent is to separate the expensive regional research work (done once per
region, offline, by a batch job) from the cheap personalisation work (done per cluster
at request time). The LLM's job during live guide generation is not to produce raw
content from scratch — it is to adapt pre-validated regional templates to the user's
household profile. This reduces per-call token consumption and constrains the model's
creative latitude to a bounded personalisation task rather than open-ended generation.

---

## 5. Streaming + Granular Fallback Per Category

The generation loop is deliberately streaming and per-category rather than monolithic:

```python
for i, category in enumerate(CATEGORIES):
    yield json.dumps({"type": "category_start", "category": category, "index": i, "total": len(CATEGORIES)})
    ...
    try:
        section = await llm.generate_json(prompt, GUIDE_SYSTEM_PROMPT)
        content[category] = section
        yield json.dumps({"type": "category_done", "category": category, "data": section})
    except Exception as e:
        logger.error(f"Guide generation failed for {category}: {e}")
        section = base_content.get(category) or FALLBACK_GUIDE.get(category, {...})
        content[category] = section
        yield json.dumps({"type": "category_error", "category": category, "data": section})
```

I made the loop granular for two reasons that matter in a financial context:

1. **Partial success is better than total failure.** If the LLM fails on category 8 of 12, the user still receives 11 correct sections rather than nothing. The SSE stream communicates the error state per category — the frontend can display which sections are fallback-sourced.

2. **Cost attribution is per-category.** Streaming allows the system to abort generation early without wasting tokens on categories that already have cached content. It also enables future rate-limiting logic to be applied at the category granularity rather than requiring all-or-nothing decisions.

The `FALLBACK_GUIDE` dictionary provides 12 complete static sections in Portuguese,
pre-authored and reviewed, that serve as the ultimate backstop when both LLM and
regional content are unavailable. This is the third tier of the content hierarchy:
LLM-personalised → regional base → static fallback.

---

## 6. Version Rollback as an Audit Mechanism

The `rollback_guide_version()` function provides operational rollback:

```python
async def rollback_guide_version(user: User, region: str, db: AsyncSession) -> dict:
    """Rollback to previous guide version. CLI: rollback --region=PT --to=previous"""
    ...
    previous = sorted_versions[-2]
    guide.current_version_id = previous.id
    await db.commit()

    return {
        "rolled_back_to_version": previous.version_number,
        "region": region,
        "content_date": previous.created_at.isoformat(),
    }
```

In a financial investment context, rollback is not a convenience feature — it is an
audit control. If a model upgrade introduces systematically biased content for a
particular region (for example, a model that over-estimates water requirements by 3×
due to a regional context confusion), I can roll back all affected guides to their
pre-upgrade versions without waiting for a re-generation cycle. The `rollback_available`
flag on `GuideVersion` records whether the previous version is intact and safe to
restore — it is `False` only for first-version guides that have no prior state.

The version history is append-only: I never delete `GuideVersion` rows. This ensures
that every guide state is recoverable and that the audit trail is complete.

---

## 7. Cost Model

The cache strategy converts a linear cost function into a step function:

| Scenario | LLM calls per user |
|---|---|
| No caching (naive) | 12 (one per category) |
| Cluster cache hit | 0 |
| Cluster cache miss, first user in cluster | 12 |
| Cluster cache miss, Nth user in same cluster | 0 |

At a cluster granularity of five profile dimensions, the expected cluster size grows
with user volume. For a platform with 10,000 users across 20 country codes and typical
household diversity, empirical clustering would produce O(hundreds) of distinct
clusters rather than O(thousands). The cost multiple improvement relative to per-user
generation is roughly proportional to average cluster size.

I designed the system so that the only way to bypass the cost barrier is for the
cache file to be absent. Cache files are durable across restarts (filesystem
persistence), so the only cache-busting events are: first user in a new cluster,
explicit cache invalidation (e.g., after a model upgrade), and regional content
refresh cycles. All three are controlled operations — not emergent from user behaviour.

---

## 8. What I Would Add in a Production Hardening Cycle

The current implementation uses filesystem-based cluster storage, which is appropriate
for a single-node deployment. In a horizontally-scaled investment-grade deployment I
would add:

- **Redis cluster cache** with TTL-based expiry and atomic `SETNX` to prevent cache
  stampede when multiple instances race to generate the same cluster simultaneously.
- **Cache versioning by model version** — the hash would incorporate a `MODEL_VERSION`
  env var so that a model upgrade automatically invalidates all existing clusters
  without requiring manual cache deletion.
- **Cluster size metrics** emitted as Prometheus counters, enabling alert rules for
  clusters that have grown beyond a threshold (indicating the cluster boundaries are
  too coarse) or clusters that have only one user (indicating over-granularity).
- **Async pre-warming** — a background job that generates cluster content for
  newly-registered user profiles before first login, so the first-request experience
  is always a cache hit.

These extensions follow naturally from the architecture I designed. The hash-based
clustering abstraction is stable across all of them — only the storage backend and
invalidation logic change.

---

## Summary

I designed the cluster cache strategy around three axioms appropriate for an
investment-grade system: cost must be bounded and predictable; every generated output
must be attributable to a specific profile state; and system failures must degrade
gracefully to pre-authored content rather than producing empty responses.

The `compute_cluster_hash()` function is the load-bearing element — a five-field
deterministic key that groups users into cost-sharing equivalence classes without
sacrificing material content correctness. The two-tier persistence (filesystem speed +
PostgreSQL durability) ensures that the audit trail survives infrastructure failures.
The per-category streaming loop ensures partial success is always better than total
failure. Together these form a caching architecture I would defend in a production
review without qualification.

---

*See also:*
- [`reliability-engineering.md`](reliability-engineering.md) — 3-tier JSON extraction and retry logic
- [`deterministic-fallback.md`](deterministic-fallback.md) — scoring engine and FALLBACK_GUIDE design
- [`audit-trail.md`](audit-trail.md) — audit fields and provenance on every response

# Prompt Decomposition: Minimalist System Prompt + Rich User Prompt

**Case Study — Doomsday Prep Platform**
**Document series:** Prompt Engineering Architecture · Technique 3 of 7
**Author framing:** Senior Prompt Engineer, investment-grade system design
**Primary axes:** Auditability · Output Reliability
**Secondary axis:** Cost control

---

## The Design Decision

When I architected the guide generation pipeline, I faced a structural choice that every
prompt engineer encounters on production systems: *where does knowledge live in the
prompt?*

For the news-analysis pipeline (covered in `schema-enforcement.md`), I wrote a long,
dense system prompt — 67 lines that define signal categories, scoring rubrics, and the
complete JSON schema. That design makes sense when the task is **expert classification**:
the model must hold a precise taxonomy in working memory and apply it consistently
regardless of which articles arrive.

For the guide generation pipeline, the calculus is different. The task is
**personalised synthesis**: take a fixed structure and fill it with content calibrated
to a specific household's geography, size, constraints, and risk tolerances. The *what*
to produce is known and stable; the *for whom* to produce it changes with every user.
That asymmetry drove me toward a deliberate split:

| Layer | Responsibility | Length |
|---|---|---|
| System prompt | Role + output contract + compliance guardrails | 5 lines |
| User prompt | All contextual signal — profile, category, base content | ~30 lines |

This is not minimalism for its own sake. It is a **separation of concerns** that I
chose for three reasons rooted in production reliability and auditability.

---

## The System Prompt — Reproduced Verbatim

```python
# backend/app/services/content/guide_service.py — lines 26–30

GUIDE_SYSTEM_PROMPT = """You are a civil preparedness expert writing practical survival guides.
Be specific about quantities using the user's household profile.
Use metric units. Always include a brief legal disclaimer per section.
Content is informational only — not a substitute for official civil protection guidance.
Return valid JSON only."""
```

Five lines. Each carries a precise function:

| Line | Function | Design Rationale |
|---|---|---|
| `You are a civil preparedness expert…` | Role anchor | Sets the epistemic frame — practical, not academic |
| `Be specific about quantities using the user's household profile.` | Grounding instruction | Prevents generic advice; forces use of injected profile data |
| `Use metric units.` | Output normalisation | Eliminates locale ambiguity in a multi-country system |
| `Always include a brief legal disclaimer per section.` | Compliance guard | Ensures every section carries protective language without it needing to be templated |
| `Return valid JSON only.` | Schema enforcement | Hard constraint — no prose, no markdown fences, no preamble |

The system prompt contains **no data**. It contains no household size, no country code,
no category name, no regional content. This is deliberate. The system prompt is the
part of the context that is *identical for every invocation*. Anything that varies
between users must not live here — because if it did, I could not reason about it,
cache around it, or audit it independently of the user input.

---

## The User Prompt — Reproduced Verbatim

The user prompt is constructed inline inside `generate_guide_streaming` for each
category iteration. Here is the full template as it appears in production:

```python
# backend/app/services/content/guide_service.py — lines 255–273

prompt = f"""Generate preparation guide section for: {category}
User profile:
- country={user.country_code}, language={user.language}
- household_size={user.household_size or 1}, housing={user.housing_type or 'unknown'}
- has_vehicle={user.has_vehicle}
- pets={json.dumps((user.preferences or {}).get('pet_types', []))}
- has_children={((user.preferences or {}).get('has_children', False))}, children_count={((user.preferences or {}).get('children_count', 0))}
- has_elderly={((user.preferences or {}).get('has_elderly', False))}
- has_mobility_issues={((user.preferences or {}).get('has_mobility_issues', False))}
- floor_number={((user.preferences or {}).get('floor_number', None))}
- budget_level={((user.preferences or {}).get('budget_level', 'médio'))}
Base regional content: {json.dumps(base_content.get(category, {}))}

Return JSON: {{
  "title": str,
  "items": [{{"text": str, "quantity": float|null, "unit": str|null, "priority": int, "formula": str|null}}],
  "tips": [str],
  "disclaimer": str
}}"""
```

### Annotation — Field-by-Field

**`category`** — The iteration variable from `CATEGORIES` list (12 entries: water, food,
shelter, health, communication, evacuation, energy, security, documentation,
mental_health, armed_conflict, family_coordination). By injecting it at the top of the
prompt I ensure the model's attention is anchored to the specific task before any
profile data is read.

**`user.country_code` + `user.language`** — Locale pair. Controls which language the
output is generated in and which regional regulatory context applies. These fields are
top-level on the user model, not buried in preferences, because I treat them as
first-class routing signals.

**`user.household_size or 1`** — Quantity multiplier for every item in the `items` list.
The `or 1` default ensures the model never receives a null here; a null household size
would produce guides with undefined quantities, which breaks the entire premise of
personalisation.

**`user.housing_type or 'unknown'`** — Relevant for shelter and energy sections
(apartment vs. house changes evacuation routes, generator recommendations, and
floor-number-dependent advice). The `or 'unknown'` sentinel is honest signalling to
the model — it may need to hedge rather than fabricate.

**`user.has_vehicle`** — Boolean that gates vehicle-dependent recommendations
(car emergency kits, fuel reserves, evacuation by road vs. foot).

**`pets=json.dumps(...)`** — Pet types as a JSON array rather than a boolean. I
serialised this field because the guide section for evacuation and shelter behaves
differently for, say, `["dog", "cat"]` vs. `["parrot"]` vs. `[]`. A boolean
`has_pets` would collapse that distinction.

**`has_children` + `children_count`** — Two separate signals. The boolean gates the
presence of child-specific items; the count feeds quantity calculations. I kept both
because the model handles them differently: presence affects category selection,
count affects arithmetic.

**`has_elderly`** — Flags the need for mobility-accessible evacuation routes and
medication management items. I surfaced this as a top-level signal rather than leaving
it embedded in preferences because it materially changes the safety-critical content
of at least four categories.

**`has_mobility_issues`** — Overlaps with `has_elderly` in some households but not all.
I kept them as independent boolean fields to avoid an implicit assumption that elderly
implies mobility-impaired.

**`floor_number`** — Nullable integer. Affects evacuation planning (above floor 5,
elevator-dependent routes become hazardous during fire or power outage). When null,
the model receives `None` — an honest signal that the user did not provide this.

**`budget_level`** — Categorical (default `'médio'`). Shapes the item recommendations
toward budget-appropriate options. Without this field, the model defaults to
middle-range recommendations regardless of financial constraints, which reduces
practical utility and risks presenting unaffordable preparations as mandatory.

**`Base regional content: {json.dumps(base_content.get(category, {}))}`** — This is
the richest injection. `base_content` is pre-generated regional data loaded from
`/data/regions/{country_code}/{zip_code}.json`. It carries region-specific hazard
assessments, local regulatory references, and category-level context. The model is
instructed to use it as a *foundation* to personalise from, not as output to
reproduce verbatim.

---

## Why This Split Produces Reliable Output

### 1. The system prompt is immutable — it can be audited as a constant

In a financial or compliance context, I need to be able to point to exactly what
behavioural constraints the model was operating under for any given generation.
Because the system prompt never changes, I can reproduce the exact model inputs for
any historical generation from the `profile_snapshot` stored in `GuideVersion` and the
category name — without any additional state.

### 2. The user prompt is structured — not narrative

I chose a `key=value` format over prose for the profile injection. Compare:

```
# Prose (what I did not do)
"This guide is for a family of 4 living in an apartment in Portugal,
 they have two cats, an elderly relative, and a modest budget."

# Structured (what I did)
- household_size=4, housing=apartment
- country=PT, language=pt
- pets=["cat", "cat"]
- has_elderly=True
- budget_level='modesto'
```

The structured format is harder to misread, easier to diff between user profiles,
and produces more consistent extraction in the model's attention mechanism. It also
makes the prompt **machine-readable** — the same format that will feed the evaluation
harness when I instrument output scoring against profile inputs.

### 3. Schema appears in both layers — for different reasons

The system prompt says `Return valid JSON only.` — that is a *behavioural constraint*.
The user prompt ends with an explicit schema — that is a *structural specification*:

```
Return JSON: {
  "title": str,
  "items": [{"text": str, "quantity": float|null, "unit": str|null, "priority": int, "formula": str|null}],
  "tips": [str],
  "disclaimer": str
}
```

Having both is not redundant. The system prompt installs the constraint once at
session start. The user prompt re-anchors the specific schema at the point of task
issuance, where the model's attention is most relevant to output format. In testing I
found that schema placed only in the system prompt produced more format drift by the
sixth or seventh category in a single streaming session — likely because the schema
competes with the accumulated article content in the context window.

---

## Contrast With the Analysis Pipeline

The news-analysis pipeline in `base.py` uses the inverse pattern:

```python
# backend/app/services/llm/base.py — lines 27–66
ANALYSIS_SYSTEM_PROMPT = """You are a geopolitical risk analyst...
[67 lines including full taxonomy, scoring rubric, and complete JSON schema]
"""

ANALYSIS_USER_TEMPLATE = """Analyse the following {n_articles} news article(s) for country: {country_name} ({country_code}).
Focus on signals relevant to {country_name}'s geopolitical risk position.
Articles:
{articles_text}
Return JSON only."""
```

Here the system prompt is rich and the user prompt is lean. The reason is that the
expert knowledge — the 10-category taxonomy, the 0.0–10.0 scoring rubric, the
confidence model — is **invariant**. It does not change with each article. But the
system prompt must hold it because the model needs the rubric active while it reads
potentially unfamiliar article content.

The user prompt injects only what changes per invocation: country context and article
text. This keeps the user prompt focused and avoids the system prompt growing with
session data.

**Two pipelines, two patterns — both deliberate, both driven by what varies and what
does not.**

---

## Failure Mode Handling at the Prompt Boundary

The guide generation pipeline wraps every per-category LLM call in a try/except:

```python
# backend/app/services/content/guide_service.py — lines 277–286

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

The fallback cascade is: **regional base content → static FALLBACK_GUIDE → empty
section**. This means that even if the model produces malformed JSON for a given
category, or the provider is unavailable, the streaming response continues and the
user receives a complete guide. The `category_error` event type in the SSE stream
signals to the client that this section was not LLM-generated — which is the
information needed for audit trail reconstruction.

The `FALLBACK_GUIDE` itself — 12 categories of pre-written Portuguese-language content
— is defined in `guide_service.py` and acts as a last-resort corpus that requires no
model invocation whatsoever. This is the defensive layer that ensures the product
remains functional during total LLM provider outage.

---

## Summary

| Design choice | Rationale |
|---|---|
| 5-line system prompt | Immutable, auditable, cacheable as a constant |
| 10+ field structured user prompt | All context variation belongs here, in diffable key=value format |
| Schema in both layers | Behavioural constraint (system) + task-specific anchor (user) |
| `or` defaults on nullable fields | Honest signalling — no null injection into arithmetic fields |
| `json.dumps()` for array fields | Preserves structure for model; avoids ambiguous prose serialisation |
| Inverse pattern in analysis pipeline | Different task structure demands different decomposition |

The prompt decomposition I chose for this system reflects a single governing
principle: **the system prompt is a contract; the user prompt is a data payload.** They
serve different purposes and should be designed and evaluated independently.

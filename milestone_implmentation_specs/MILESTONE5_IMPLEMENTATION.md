# Milestone 5 Implementation Spec — Extrude Edit Primitive + Safety + Preview

Last updated: 2026-01-24

Reference: See `PROJECT.md` for the overall roadmap and milestone definitions.

## Goal
Add a single **feature edit** primitive (`extrude`) with explicit targeting, preview-only mode, and **strict verification** (numeric + visual diff) on every edit.

Milestone 5 introduces **feature operations** while preserving determinism and traceability.

## Why feature ops (vs parameter-only)
Parameter edits are the safest, but they assume the design is already parameterized. Feature ops allow edits when a model **does not expose user parameters** and enable **localized geometry changes** (e.g., add a boss or cut) using explicit targeting rules.

## Non-regression constraints
- No UI automation for geometry work.
- All Fusion API calls must run on the main thread via the existing CustomEvent + queue model.
- RPC responses must be deterministic and structured (`ok`, `error`, `data`).
- Prefer API-derived measurements and deterministic renders over OS-level screenshots.

## Scope decisions (locked)
- **Edit primitive:** One command `extrude_feature`.
- **Targeting:** Face-based (planar only) using deterministic selectors.
- **Verification:** Numeric + visual diff required for every edit.
- **Preview:** All edits support `preview=true` to return a structured plan without applying.
 - **Selectors:** `largest_planar` and `normal_closest:+X|-X|+Y|-Y|+Z|-Z` only.

## Deliverables
- New RPC command: `extrude_feature`.
- Selection helper(s) for deterministic planar face targeting.
- Guardrails for safe edits:
  - Operation allowlist
  - Bounds checks on distance
  - Timeouts
  - Topology growth checks (face/edge counts)
- Preview output schema to inspect planned operation before execution.

## Command: `extrude_feature`

### Purpose
Create a single extrude feature from a **selected planar face** with explicit distance and operation type.

### Request
Command: `extrude_feature`

Params:
- `body_name` (string, optional): same resolution rules as other commands.
- `face_selector` (string, default `largest_planar`):
  - `largest_planar` (recommended default)
  - `normal_closest:+X|-X|+Y|-Y|+Z|-Z` (planar only)
- `operation` (string, default `new_body`):
  - `new_body`, `join`, `cut`, `intersect`
- `distance_mm` (number, required): positive number; may be applied in `direction`.
- `direction` (string, default `normal`):
  - `normal` (face normal)
  - `opposite` (negated normal)
- `preview` (bool, default `false`): if true, return a structured plan without applying.
- `verification_tolerance_mm` (number, optional, default `0.1`): numeric tolerance for length-based checks.
- `verification_tolerance_pct` (number, optional, default `1.0`): numeric tolerance for volume-based checks.
- `compute` (bool, default `true`): recompute after apply.
- `units` (string, default `"mm"`): output units (mm only in this milestone).

### Deterministic Algorithm (apply and preview)
1) Resolve active `design` and `rootComp`.
2) Resolve `body_name`:
   - If provided: exact match among visible solid bodies in root component.
   - Else if exactly one visible body exists: use it.
   - Else error with sorted candidates.
3) Collect candidate faces:
   - Only **planar** faces.
4) Score and select face based on `face_selector`.
   - Tie-breaks: score desc → face area desc → centroid tuple → stable face id.
5) Validate `distance_mm`:
   - Must be `> 0` and within guardrail limits.
6) Build a deterministic **preview plan** object.
7) If `preview=true`, return the plan without applying any edits.
8) Apply the extrude feature using the plan parameters.
9) If `compute=true`, force a recompute.
10) Return result + traceability and post-edit measurement summary.

### Guardrails (required)
Locked checks (defaults recommended for initial implementation; adjust as needed):
- `distance_mm` must be `> 0` and `<= MAX_EXTRUDE_MM` (default `50.0`).
- `operation` must be in allowlist.
- Apply time limit: `MAX_APPLY_MS` (default `1500` ms).
- Topology growth check (post-apply):
  - `face_count_delta <= MAX_FACE_DELTA` (default `+150`)
  - `edge_count_delta <= MAX_EDGE_DELTA` (default `+300`)
  - `body_count_delta <= MAX_BODY_DELTA` (default `+1`)

If a guardrail fails after applying:
- Rollback the operation (or attempt to delete the feature).
- Return `ok=false` with a clear error and the preview plan.

### Response (success)
Top-level:
- `ok: true`
- `error: null`
- `data: { ... }`

`data` fields:
- `preview`:
  - `is_preview` (bool)
  - `plan`: {
      `body_name`,
      `face`: { `id`, `selector`, `centroid_mm`, `normal`, `area_mm2` },
      `operation`,
      `distance_mm`,
      `direction`
    }
- `apply` (null if preview):
  - `feature`: { `id`, `name` }
  - `compute`: { `ran` }
  - `timing_ms`
- `measure_before`:
  - `bbox_mm` (optional)
  - `volume_mm3` (optional)
  - `counts`: `{ faces, edges, vertices }`
- `measure_after` (null if preview):
  - `bbox_mm` (optional)
  - `volume_mm3` (optional)
  - `counts`: `{ faces, edges, vertices }`
- `verify` (null if preview):
  - `tolerances`: { `mm`, `pct` }
  - `required_pass` (bool)
  - `warnings`: [string]
  - `metrics_attempted`: [string]
- `trace`:
  - `candidates_considered`: `{ faces }`

### Response (failure)
Return `ok=false` with:
- `error`: specific message
- `preview.plan` (if available)
- `candidates`: list of body names when ambiguous

### Determinism requirements
- Face selection: explicit scoring and tie-breaks; no reliance on collection order.
- All lists sorted.
- Unit conversion centralized and consistent.

## Verification workflow (required for every edit)
Numeric + visual are mandatory for **all** successful applies.

### Pre-state capture
1) `status`
2) `measure_bbox` (target body)
3) `get_camera` + `capture_view` (fixed size)

### Preview
4) `extrude_feature --param preview=true ...`
   - Validate plan contents (face id, distance, operation).

### Apply
5) `extrude_feature --param preview=false ...`

### Post-state capture
6) `measure_bbox` (same body, or new body if `new_body`)
7) `set_camera` + `capture_view` (same size)

### Verify
- Numeric: compare bbox deltas, volume deltas, and face-span deltas within tolerance.
- Visual: run `scripts/image_diff.py` on before/after captures.

### Rollback (mandatory on failure)
If numeric or visual verification fails:
- Delete the created feature/body (implementation detail).
- Re-run measurement + capture to confirm rollback.

## Numeric verification policy (required)
All three numeric checks must be attempted when feasible. Results are categorized as
**required** or **advisory** to reduce false negatives.

### Always attempt
- `bbox`: required for all operations (primary).
- `volume`: required for `join`, `cut`, `intersect`; advisory for `new_body`.
- `face_span`: advisory by default; required if the command specifies a `face_span_selector` (future-proofing).

### Pass/fail rules
- **Fail** if any required metric is missing or outside tolerance.
- **Warn** if advisory metrics are missing or outside tolerance.
- Record all measurements in the response (`measure_before`, `measure_after`, `verify`).

### Preview safety contract (required)
- `preview=true` must be **dry-run only**:
  - No feature/history changes.
  - No transient geometry creation.
  - No recompute side-effects.
- Preview must return the exact IDs and inputs it would use if applied.

### Ambiguity rules
- `new_body` operations must record both source and new body measurements.
- If multiple bodies are created (should not happen), treat as a guardrail failure.

## CLI examples (placeholder)
- Preview:
  - `python3 scripts/fusion_rpc_client.py extrude_feature --param body_name=Body1 --param preview=true --param face_selector=largest_planar --param distance_mm=10 --param operation=new_body`
- Apply:
  - `python3 scripts/fusion_rpc_client.py extrude_feature --param body_name=Body1 --param preview=false --param face_selector=largest_planar --param distance_mm=10 --param operation=new_body`

## Acceptance criteria (Definition of Done)
- `preview=true` returns a deterministic plan without modifying the design.
- `preview=false` applies a single extrude feature deterministically.
- Guardrails are enforced with explicit errors and rollback.
- Numeric verification passes for a known model.
- Visual diff artifacts are produced under `logs/`.

## Project tracking
After implementation + verification:
- Update `PROJECT.md`:
  - Mark Milestone 5 ✅ complete.
  - Add a dated progress-log entry noting extrude primitive + preview/guardrails.

# Milestone 6 Implementation Spec — Core Modeling Commands (80% Coverage)

Last updated: 2026-01-24

Reference: See `PROJECT.md` for the overall roadmap and milestone definitions.

## Goal
Provide a practical, high‑leverage command set so an agent can create/edit most common mechanical parts without custom code. This milestone focuses on **core sketch + feature ops** and deterministic targeting helpers. The agent can still add bespoke commands at runtime, but the default toolbox should cover ~80% of requests.

## Non‑regression constraints
- No UI automation for geometry work.
- All Fusion API calls must run on the main thread via the existing CustomEvent + queue model.
- RPC responses must be deterministic and structured (`ok`, `error`, `data`).
- Prefer API‑derived measurements and deterministic renders over OS‑level screenshots.

## Scope decisions (locked)
- **Sketch foundation** first (create + basic primitives).
- **Feature ops** using deterministic, explicit targeting (selectors, IDs, or named inputs).
- **Preview** support for *all* edit commands (dry‑run only).
- **Shared selection helper** used across commands (faces/edges/vertices).

## Deliverables
### New/expanded commands
1) Sketch:
- `create_sketch`
- `sketch_add_rectangle`
- `sketch_add_circle`
- `sketch_add_line`

2) Feature ops:
- `hole_feature`
- `fillet_feature`
- `chamfer_feature`
- `pattern_feature` (rectangular + circular)
- `mirror_feature`
- `shell_feature`
- `revolve_feature`

3) Feature inventory + deletion:
- `list_features`
- `get_feature_info`
- `delete_feature`

4) Shared selection helpers (new module):
- face selectors: `largest_planar`, `normal_closest:+X|-X|+Y|-Y|+Z|-Z`, `max_bbox_x|y|z`, `min_bbox_x|y|z`, `largest_area`
- edge selectors: `longest_edge`, `normal_closest:*` (planar face edges), `closest_to_point`
- vertex selectors: `closest_to_point`
- adjacency selectors (optional): `adjacent_to_face_id`

## Shared helpers (required)
Add `fusion_rpc_addin/FusionRPCAddIn/commands/_selection_helpers.py` with:
- `_entity_id(entity)` (reuse ordering: entityToken → tempId → entityId)
- `_list_visible_bodies(root_comp)`
- `_resolve_body(root_comp, body_name)`
- `_is_planar(face)`
- `_point_mm(convert_mm, units_mgr, point)`
- `_bbox_mm(entity)` for faces/bodies
- `_select_face(body, selector, units_mgr, convert_mm)` with deterministic tie‑breaks
- `_select_edge(face|body, selector, units_mgr, convert_mm)`
- `_select_vertex(face|body, selector, units_mgr, convert_mm)`

Tie‑break rules (all selectors):
- score desc → area/length desc → centroid tuple → entity id

## Command specs (summary level)
Each command returns:
- `ok` (bool)
- `error` (string|null)
- `data` (object|null)

### `create_sketch`
Purpose: create sketch on a plane or planar face.
Params:
- `plane` (string, optional): `XY|YZ|XZ` (default `XY`)
- `face_id` (string, optional): overrides `plane` if provided
- `origin_mm` (optional): `{x,y,z}` if offset is needed
- `name` (optional)
- `preview` (bool, default `false`)

Response:
- `data.sketch`: `{ id, name, plane, face_id? }`
- `data.preview`: `{ is_preview, plan }`

### `sketch_add_rectangle`
Params:
- `sketch_id`
- `p1_mm`, `p2_mm`
- `centered` (bool, default `false`)
- `preview`

Response: created curve IDs + bounding box.

### `sketch_add_circle`
Params:
- `sketch_id`
- `center_mm`, `radius_mm`
- `preview`

### `sketch_add_line`
Params:
- `sketch_id`
- `p1_mm`, `p2_mm`
- `preview`

### `hole_feature`
Params:
- `body_name` (optional)
- `face_selector` OR `face_id`
- `center_mm` (optional if `point_selector` provided)
- `diameter_mm`
- `depth_mm` (or `through_all=true`)
- `preview`

### `fillet_feature`
Params:
- `edge_selector` OR `edge_id`
- `radius_mm`
- `preview`

### `chamfer_feature`
Params:
- `edge_selector` OR `edge_id`
- `distance_mm` (or `distance_mm_2` for two‑distance)
- `preview`

### `pattern_feature`
Params:
- `feature_id` or `body_name` (base)
- `pattern_type`: `rectangular|circular`
- Rectangular: `axis1`, `axis2`, `count1`, `count2`, `spacing1_mm`, `spacing2_mm`
- Circular: `axis`, `count`, `angle_deg`
- `preview`

### `mirror_feature`
Params:
- `feature_id` or `body_name`
- `mirror_plane`: `XY|YZ|XZ` or `face_id`
- `preview`

### `shell_feature`
Params:
- `body_name`
- `thickness_mm`
- `remove_faces` (optional selectors)
- `preview`

### `revolve_feature`
Params:
- `profile_sketch_id` + `profile_curve_ids`
- `axis_selector` OR `axis_line_mm` (two points)
- `angle_deg` (default `360`)
- `operation` (`new_body|join|cut|intersect`)
- `preview`

### `list_features`
Params:
- `filter_type` (optional)

Response:
- list of `{ id, name, type, body_name? }`

### `get_feature_info`
Params:
- `feature_id`

Response:
- `{ id, name, type, inputs?, bodies?, timeline_index? }`

### `delete_feature`
Params:
- `feature_id`
- `preview`

## Determinism requirements
- Do not rely on collection enumeration order; always sort where ambiguity exists.
- Return sorted lists for candidates and outputs.
- Standardize unit conversion in shared helpers; default outputs in `mm`.
- No timestamps in outputs except in optional debug fields.

## Guardrails (required for all edit commands)
- `preview=true` is **dry‑run only** (no geometry changes, no recompute side‑effects).
- Distance/size inputs must be positive and within safe limits (defaults: 50 mm unless overridden per command).
- Apply timeout similar to Milestone 5 (`MAX_APPLY_MS`).
- Post‑apply topology deltas must not exceed configured thresholds.
- Rollback on guardrail failure (delete feature and recompute).

## Verification workflow (required)
For each edit command:
1) `status`
2) `measure_bbox` (target body)
3) `get_camera` + `capture_view`
4) `preview=true` to validate plan
5) `preview=false` apply
6) `measure_bbox` + `capture_view`
7) Visual diff via `scripts/image_diff.py`
8) Rollback on failure

## Acceptance criteria (Definition of Done)
- Each command supports `preview=true` and returns a deterministic plan.
- Each command succeeds on a simple reference model and produces stable results across repeated calls.
- Guardrails are enforced with explicit errors and rollback.
- Progress log updated with a dated entry per command group.

## Project tracking
After implementation + verification:
- Update `PROJECT.md`:
  - Mark Milestone 6 ✅ complete.
  - Add dated progress‑log entries for each command group.

import importlib
import os
import sys
import time

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _selection_helpers as selection_helpers

importlib.reload(selection_helpers)

COMMAND = "extrude_profile"
REQUIRES_DESIGN = True

MAX_DISTANCE_MM = 100.0
MAX_APPLY_MS = 5000.0
MAX_FACE_DELTA = 300
MAX_EDGE_DELTA = 600
MAX_BODY_DELTA = 1


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _find_sketch(root_comp, sketch_id):
    try:
        sketches = root_comp.sketches
    except Exception:
        return None
    try:
        count = int(sketches.count)
    except Exception:
        count = 0
    for idx in range(count):
        try:
            sketch = sketches.item(idx)
        except Exception:
            continue
        if selection_helpers._entity_id(sketch) == sketch_id:
            return sketch
    return None


def _total_counts(bodies):
    totals = {"faces": 0, "edges": 0, "vertices": 0}
    for body in bodies:
        totals["faces"] += selection_helpers._collection_count(body.faces)
        totals["edges"] += selection_helpers._collection_count(body.edges)
        totals["vertices"] += selection_helpers._collection_count(body.vertices)
    return totals


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    sketch_id = request.get("sketch_id")
    profile_index = request.get("profile_index", 0)
    operation_name = request.get("operation", "new_body")
    distance_mm = request.get("distance_mm")
    direction = request.get("direction", "normal")
    body_name = request.get("body_name")
    through_all = bool(request.get("through_all", False))
    preview = bool(request.get("preview", False))
    compute = bool(request.get("compute", True))

    if not sketch_id:
        return {"ok": False, "error": "sketch_id is required"}

    try:
        profile_index = int(profile_index)
    except Exception:
        return {"ok": False, "error": "profile_index must be an integer"}

    if not through_all:
        try:
            distance_mm = float(distance_mm)
        except Exception:
            return {"ok": False, "error": "distance_mm must be a number"}

        if distance_mm <= 0:
            return {"ok": False, "error": "distance_mm must be > 0"}
        if distance_mm > MAX_DISTANCE_MM:
            return {"ok": False, "error": f"distance_mm exceeds MAX_DISTANCE_MM ({MAX_DISTANCE_MM})"}

    if direction not in ("normal", "opposite"):
        return {"ok": False, "error": f"Unsupported direction: {direction}"}

    operations = {
        "new_body": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
        "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    if operation_name not in operations:
        return {"ok": False, "error": f"Unsupported operation: {operation_name}"}

    sketch = _find_sketch(root_comp, sketch_id)
    if not sketch:
        return {"ok": False, "error": f"sketch_id not found: {sketch_id}"}

    try:
        profile = sketch.profiles.item(profile_index)
    except Exception:
        profile = None
    if not profile:
        return {"ok": False, "error": f"Profile not found at index {profile_index}"}

    body = None
    if body_name:
        body, bodies = selection_helpers._resolve_body(root_comp, body_name)
        if not body:
            candidates = sorted([b.name for b in bodies])
            return {
                "ok": False,
                "error": f"Body not found: {body_name}. Candidates: {candidates}",
                "candidates": candidates,
            }

    plan = {
        "sketch_id": sketch_id,
        "profile_index": profile_index,
        "operation": operation_name,
        "distance_mm": distance_mm if not through_all else None,
        "direction": direction,
        "body_name": body_name,
        "through_all": through_all,
    }

    if preview:
        return {"ok": True, "error": None, "data": {"preview": {"is_preview": True, "plan": plan}}}

    before_visible = selection_helpers._list_visible_bodies(root_comp)
    before_counts = _total_counts(before_visible)
    before_body_count = len(before_visible)

    feature = None
    compute_ran = False
    start_time = time.time()
    try:
        extrudes = root_comp.features.extrudeFeatures
        ext_input = extrudes.createInput(profile, operations[operation_name])
        if through_all:
            try:
                ext_input.setThroughAllExtent(
                    adsk.fusion.ExtentDirections.NegativeExtentDirection
                    if direction == "opposite"
                    else adsk.fusion.ExtentDirections.PositiveExtentDirection
                )
            except Exception:
                try:
                    ext_input.setThroughAllExtent(adsk.fusion.ExtentDirections.PositiveExtentDirection)
                except Exception:
                    pass
        else:
            distance_internal = _mm_to_internal(units_mgr, distance_mm)
            try:
                ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(distance_internal))
            except Exception:
                ext_input.setDistanceExtent(True, adsk.core.ValueInput.createByReal(distance_internal))
        ext_input.isSolid = True
        if body and operation_name in ("cut", "join", "intersect"):
            body_collection = adsk.core.ObjectCollection.create()
            body_collection.add(body)
            try:
                ext_input.participantBodies = body_collection
            except Exception:
                try:
                    ext_input.setParticipantBodies(body_collection)
                except Exception:
                    pass
        feature = extrudes.add(ext_input)
        if compute:
            try:
                design.computeAll()
                compute_ran = True
            except Exception:
                pass
        timing_ms = (time.time() - start_time) * 1000.0
    except Exception as exc:
        if feature:
            try:
                feature.deleteMe()
            except Exception:
                pass
        return {"ok": False, "error": f"Extrude profile failed: {exc}", "data": {"preview": {"plan": plan}}}

    after_visible = selection_helpers._list_visible_bodies(root_comp)
    after_counts = _total_counts(after_visible)
    after_body_count = len(after_visible)

    guardrail_error = None
    if timing_ms > MAX_APPLY_MS:
        guardrail_error = f"Apply exceeded MAX_APPLY_MS ({MAX_APPLY_MS} ms)"
    elif after_counts["faces"] - before_counts["faces"] > MAX_FACE_DELTA:
        guardrail_error = f"face_count_delta exceeded MAX_FACE_DELTA ({MAX_FACE_DELTA})"
    elif after_counts["edges"] - before_counts["edges"] > MAX_EDGE_DELTA:
        guardrail_error = f"edge_count_delta exceeded MAX_EDGE_DELTA ({MAX_EDGE_DELTA})"
    elif after_body_count - before_body_count > MAX_BODY_DELTA:
        guardrail_error = f"body_count_delta exceeded MAX_BODY_DELTA ({MAX_BODY_DELTA})"

    if guardrail_error:
        try:
            feature.deleteMe()
            if compute:
                design.computeAll()
        except Exception:
            pass
        return {"ok": False, "error": guardrail_error, "data": {"preview": {"plan": plan}}}

    return {
        "ok": True,
        "error": None,
        "data": {
            "preview": {"is_preview": False, "plan": plan},
            "apply": {
                "feature": {
                    "id": selection_helpers._entity_id(feature),
                    "name": getattr(feature, "name", None),
                },
                "compute": {"ran": compute_ran},
                "timing_ms": timing_ms,
            },
        },
    }

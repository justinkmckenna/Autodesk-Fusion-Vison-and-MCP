import importlib
import os
import sys
import time

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _feature_helpers as feature_helpers
import _selection_helpers as selection_helpers

importlib.reload(feature_helpers)
importlib.reload(selection_helpers)

COMMAND = "pattern_feature"
REQUIRES_DESIGN = True

MAX_DISTANCE_MM = 50.0
MAX_APPLY_MS = 5000.0
MAX_FACE_DELTA = 500
MAX_EDGE_DELTA = 1000
MAX_BODY_DELTA = 20


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _axis_from_name(root_comp, axis_name):
    axis_name = (axis_name or "").upper()
    if axis_name == "X":
        return root_comp.xConstructionAxis
    if axis_name == "Y":
        return root_comp.yConstructionAxis
    if axis_name == "Z":
        return root_comp.zConstructionAxis
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

    pattern_type = request.get("pattern_type")
    feature_id = request.get("feature_id")
    body_name = request.get("body_name")
    preview = bool(request.get("preview", False))

    if pattern_type not in ("rectangular", "circular"):
        return {"ok": False, "error": "pattern_type must be rectangular or circular"}

    entities = adsk.core.ObjectCollection.create()
    base_label = None
    if feature_id:
        feature, type_name = feature_helpers._find_feature_by_id(root_comp, feature_id)
        if not feature:
            return {"ok": False, "error": f"feature_id not found: {feature_id}"}
        entities.add(feature)
        base_label = {"feature_id": feature_id, "feature_type": type_name}
    else:
        body, bodies = selection_helpers._resolve_body(root_comp, body_name)
        if not body:
            candidates = sorted([b.name for b in bodies])
            if body_name:
                return {
                    "ok": False,
                    "error": f"Body not found: {body_name}. Candidates: {candidates}",
                    "candidates": candidates,
                }
            if not candidates:
                return {"ok": False, "error": "No visible solid body found.", "candidates": []}
            return {
                "ok": False,
                "error": "Multiple visible bodies; specify body_name.",
                "candidates": candidates,
            }
        entities.add(body)
        base_label = {"body_name": body.name}

    plan = {"pattern_type": pattern_type, "base": base_label}

    if pattern_type == "rectangular":
        axis1 = request.get("axis1")
        axis2 = request.get("axis2")
        count1 = request.get("count1")
        count2 = request.get("count2")
        spacing1_mm = request.get("spacing1_mm")
        spacing2_mm = request.get("spacing2_mm")
        try:
            count1 = int(count1)
            count2 = int(count2)
            spacing1_mm = float(spacing1_mm)
            spacing2_mm = float(spacing2_mm)
        except Exception:
            return {"ok": False, "error": "count1/count2 must be ints and spacing1/spacing2 must be numbers"}
        if count1 <= 0 or count2 <= 0:
            return {"ok": False, "error": "count1 and count2 must be > 0"}
        if spacing1_mm <= 0 or spacing2_mm <= 0:
            return {"ok": False, "error": "spacing1_mm and spacing2_mm must be > 0"}
        if spacing1_mm > MAX_DISTANCE_MM or spacing2_mm > MAX_DISTANCE_MM:
            return {"ok": False, "error": f"spacing exceeds MAX_DISTANCE_MM ({MAX_DISTANCE_MM})"}
        axis1_obj = _axis_from_name(root_comp, axis1)
        axis2_obj = _axis_from_name(root_comp, axis2)
        if not axis1_obj or not axis2_obj:
            return {"ok": False, "error": "axis1 and axis2 must be X, Y, or Z"}

        plan.update(
            {
                "axis1": axis1,
                "axis2": axis2,
                "count1": count1,
                "count2": count2,
                "spacing1_mm": spacing1_mm,
                "spacing2_mm": spacing2_mm,
            }
        )

        if preview:
            return {"ok": True, "error": None, "data": {"preview": {"is_preview": True, "plan": plan}}}

        before_visible = selection_helpers._list_visible_bodies(root_comp)
        before_counts = _total_counts(before_visible)
        before_body_count = len(before_visible)
        feature = None
        compute_ran = False
        start_time = time.time()
        try:
            patterns = root_comp.features.rectangularPatternFeatures
            qty1 = adsk.core.ValueInput.createByReal(count1)
            dist1 = adsk.core.ValueInput.createByReal(_mm_to_internal(units_mgr, spacing1_mm))
            pattern_input = patterns.createInput(
                entities,
                axis1_obj,
                qty1,
                dist1,
                adsk.fusion.PatternDistanceType.SpacingPatternDistanceType,
            )
            qty2 = adsk.core.ValueInput.createByReal(count2)
            dist2 = adsk.core.ValueInput.createByReal(_mm_to_internal(units_mgr, spacing2_mm))
            try:
                pattern_input.setDirectionTwo(axis2_obj, qty2, dist2)
            except Exception:
                try:
                    pattern_input.directionTwo = axis2_obj
                    pattern_input.quantityTwo = qty2
                    pattern_input.distanceTwo = dist2
                    pattern_input.distanceTypeTwo = adsk.fusion.PatternDistanceType.SpacingPatternDistanceType
                except Exception as exc:
                    raise RuntimeError(f"Failed to set directionTwo: {exc}")
            feature = patterns.add(pattern_input)
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
            return {"ok": False, "error": f"Rectangular pattern failed: {exc}", "data": {"preview": {"plan": plan}}}

    else:
        axis = request.get("axis")
        count = request.get("count")
        angle_deg = request.get("angle_deg", 360)
        try:
            count = int(count)
            angle_deg = float(angle_deg)
        except Exception:
            return {"ok": False, "error": "count must be int and angle_deg must be numeric"}
        if count <= 0:
            return {"ok": False, "error": "count must be > 0"}
        axis_obj = _axis_from_name(root_comp, axis)
        if not axis_obj:
            return {"ok": False, "error": "axis must be X, Y, or Z"}
        plan.update({"axis": axis, "count": count, "angle_deg": angle_deg})

        if preview:
            return {"ok": True, "error": None, "data": {"preview": {"is_preview": True, "plan": plan}}}

        before_visible = selection_helpers._list_visible_bodies(root_comp)
        before_counts = _total_counts(before_visible)
        before_body_count = len(before_visible)
        feature = None
        compute_ran = False
        start_time = time.time()
        try:
            patterns = root_comp.features.circularPatternFeatures
            qty = adsk.core.ValueInput.createByReal(count)
            angle = adsk.core.ValueInput.createByReal(angle_deg)
            try:
                pattern_input = patterns.createInput(entities, axis_obj, qty, angle)
            except Exception:
                pattern_input = patterns.createInput(entities, axis_obj)
                try:
                    pattern_input.quantity = qty
                except Exception:
                    try:
                        pattern_input.setQuantity(qty)
                    except Exception:
                        pass
                try:
                    pattern_input.totalAngle = angle
                except Exception:
                    try:
                        pattern_input.setTotalAngle(angle)
                    except Exception:
                        pass
            feature = patterns.add(pattern_input)
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
            return {"ok": False, "error": f"Circular pattern failed: {exc}", "data": {"preview": {"plan": plan}}}

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
                "feature": {"id": selection_helpers._entity_id(feature), "name": getattr(feature, "name", None)},
                "compute": {"ran": compute_ran},
                "timing_ms": timing_ms,
            },
        },
    }

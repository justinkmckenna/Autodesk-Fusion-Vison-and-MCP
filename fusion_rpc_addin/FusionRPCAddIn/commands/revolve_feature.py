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

COMMAND = "revolve_feature"
REQUIRES_DESIGN = True

MAX_APPLY_MS = 1500.0
MAX_FACE_DELTA = 400
MAX_EDGE_DELTA = 800
MAX_BODY_DELTA = 5


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


def _find_profile(sketch, curve_ids):
    if not curve_ids:
        try:
            return sketch.profiles.item(0)
        except Exception:
            return None

    curve_ids = set(curve_ids)
    try:
        profiles = sketch.profiles
    except Exception:
        return None

    try:
        count = int(profiles.count)
    except Exception:
        count = 0

    for idx in range(count):
        try:
            profile = profiles.item(idx)
        except Exception:
            continue
        found = set()
        try:
            loops = profile.profileLoops
            loop_count = int(loops.count)
        except Exception:
            loop_count = 0
        for lidx in range(loop_count):
            try:
                loop = loops.item(lidx)
                curves = loop.profileCurves
                curve_count = int(curves.count)
            except Exception:
                continue
            for cidx in range(curve_count):
                try:
                    curve = curves.item(cidx)
                    entity = getattr(curve, "sketchEntity", curve)
                    entity_id = selection_helpers._entity_id(entity)
                    if entity_id:
                        found.add(entity_id)
                except Exception:
                    continue
        if curve_ids.issubset(found):
            return profile
    return None


def _find_edge_by_id(root_comp, edge_id):
    for body in selection_helpers._list_visible_bodies(root_comp):
        for edge in body.edges:
            if selection_helpers._entity_id(edge) == edge_id:
                return edge
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
    convert_mm = context.get("convert_mm")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    sketch_id = request.get("profile_sketch_id")
    profile_curve_ids = request.get("profile_curve_ids")
    axis_selector = request.get("axis_selector")
    axis_line_mm = request.get("axis_line_mm")
    edge_id = request.get("edge_id")
    body_name = request.get("body_name")
    angle_deg = request.get("angle_deg", 360)
    operation_name = request.get("operation", "new_body")
    preview = bool(request.get("preview", False))

    if not sketch_id:
        return {"ok": False, "error": "profile_sketch_id is required"}

    try:
        angle_deg = float(angle_deg)
    except Exception:
        return {"ok": False, "error": "angle_deg must be numeric"}

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
        return {"ok": False, "error": f"profile_sketch_id not found: {sketch_id}"}

    profile = _find_profile(sketch, profile_curve_ids or [])
    if not profile:
        return {"ok": False, "error": "Failed to resolve profile from profile_curve_ids"}

    axis = None
    axis_plan = {}
    if edge_id:
        axis = _find_edge_by_id(root_comp, edge_id)
        if not axis:
            return {"ok": False, "error": f"edge_id not found: {edge_id}"}
        axis_plan = {"edge_id": edge_id}
    elif axis_selector:
        selector = selection_helpers._parse_edge_selector(axis_selector)
        if not selector:
            return {"ok": False, "error": f"Unsupported axis_selector: {axis_selector}"}
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
        selected, _ = selection_helpers._select_edge(body, selector, units_mgr, convert_mm)
        if not selected:
            return {"ok": False, "error": "No edges matched axis_selector."}
        axis = selected["edge"]
        axis_plan = {"axis_selector": axis_selector}
    elif axis_line_mm:
        if not isinstance(axis_line_mm, dict):
            return {"ok": False, "error": "axis_line_mm must be an object with p1 and p2"}
        p1 = axis_line_mm.get("p1")
        p2 = axis_line_mm.get("p2")
        if not isinstance(p1, dict) or not isinstance(p2, dict):
            return {"ok": False, "error": "axis_line_mm must include p1 and p2 points"}
        try:
            p1x = float(p1.get("x", 0.0))
            p1y = float(p1.get("y", 0.0))
            p1z = float(p1.get("z", 0.0))
            p2x = float(p2.get("x", 0.0))
            p2y = float(p2.get("y", 0.0))
            p2z = float(p2.get("z", 0.0))
        except Exception:
            return {"ok": False, "error": "axis_line_mm points must be numeric"}
        axis_plan = {"axis_line_mm": axis_line_mm}
        try:
            axes = root_comp.constructionAxes
            axis_input = axes.createInput()
            p1i = adsk.core.Point3D.create(
                units_mgr.convert(p1x, "mm", units_mgr.internalUnits),
                units_mgr.convert(p1y, "mm", units_mgr.internalUnits),
                units_mgr.convert(p1z, "mm", units_mgr.internalUnits),
            )
            p2i = adsk.core.Point3D.create(
                units_mgr.convert(p2x, "mm", units_mgr.internalUnits),
                units_mgr.convert(p2y, "mm", units_mgr.internalUnits),
                units_mgr.convert(p2z, "mm", units_mgr.internalUnits),
            )
            axis_input.setByTwoPoints(p1i, p2i)
            axis = axes.add(axis_input)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to create axis from axis_line_mm: {exc}"}
    else:
        return {"ok": False, "error": "axis_selector, edge_id, or axis_line_mm is required"}

    plan = {
        "profile_sketch_id": sketch_id,
        "profile_curve_ids": profile_curve_ids,
        "axis": axis_plan,
        "angle_deg": angle_deg,
        "operation": operation_name,
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
        revolves = root_comp.features.revolveFeatures
        rev_input = revolves.createInput(profile, axis, operations[operation_name])
        angle_input = adsk.core.ValueInput.createByString(f"{angle_deg} deg")
        rev_input.setAngleExtent(False, angle_input)
        feature = revolves.add(rev_input)
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
        return {"ok": False, "error": f"Revolve failed: {exc}", "data": {"preview": {"plan": plan}}}

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

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

COMMAND = "fillet_feature"
REQUIRES_DESIGN = True

MAX_RADIUS_MM = 50.0
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


def _total_counts(bodies):
    totals = {"faces": 0, "edges": 0, "vertices": 0}
    for body in bodies:
        totals["faces"] += selection_helpers._collection_count(body.faces)
        totals["edges"] += selection_helpers._collection_count(body.edges)
        totals["vertices"] += selection_helpers._collection_count(body.vertices)
    return totals


def _find_edge_by_id(root_comp, edge_id):
    for body in selection_helpers._list_visible_bodies(root_comp):
        for edge in body.edges:
            if selection_helpers._entity_id(edge) == edge_id:
                return edge
    return None


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")
    convert_mm = context.get("convert_mm")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    edge_id = request.get("edge_id")
    edge_selector = request.get("edge_selector")
    body_name = request.get("body_name")
    point_mm = request.get("point_mm")
    radius_mm = request.get("radius_mm")
    preview = bool(request.get("preview", False))
    compute = bool(request.get("compute", True))

    if not edge_id and not edge_selector:
        return {"ok": False, "error": "edge_id or edge_selector is required"}

    try:
        radius_mm = float(radius_mm)
    except Exception:
        return {"ok": False, "error": "radius_mm must be numeric"}

    if radius_mm <= 0:
        return {"ok": False, "error": "radius_mm must be > 0"}
    if radius_mm > MAX_RADIUS_MM:
        return {"ok": False, "error": f"radius_mm exceeds MAX_RADIUS_MM ({MAX_RADIUS_MM})"}

    edge = None
    if edge_id:
        edge = _find_edge_by_id(root_comp, edge_id)
        if not edge:
            return {"ok": False, "error": f"edge_id not found: {edge_id}"}
    else:
        selector = selection_helpers._parse_edge_selector(edge_selector)
        if not selector:
            return {"ok": False, "error": f"Unsupported edge_selector: {edge_selector}"}
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
        point = None
        if selector["type"] == "closest_to_point":
            if not isinstance(point_mm, dict):
                return {"ok": False, "error": "point_mm is required for closest_to_point"}
            point = {
                "x": float(point_mm.get("x", 0.0)),
                "y": float(point_mm.get("y", 0.0)),
                "z": float(point_mm.get("z", 0.0)),
            }
        selected, _ = selection_helpers._select_edge(body, selector, units_mgr, convert_mm, point_mm=point)
        if not selected:
            return {"ok": False, "error": "No edges matched selector."}
        edge = selected["edge"]

    plan = {
        "edge_id": selection_helpers._entity_id(edge),
        "edge_selector": edge_selector,
        "radius_mm": radius_mm,
    }

    if preview:
        return {
            "ok": True,
            "error": None,
            "data": {"preview": {"is_preview": True, "plan": plan}, "apply": None},
        }

    before_visible = selection_helpers._list_visible_bodies(root_comp)
    before_counts = _total_counts(before_visible)
    before_body_count = len(before_visible)

    feature = None
    compute_ran = False
    start_time = time.time()
    try:
        fillets = root_comp.features.filletFeatures
        fillet_input = fillets.createInput()
        edge_collection = adsk.core.ObjectCollection.create()
        edge_collection.add(edge)
        radius_input = adsk.core.ValueInput.createByReal(_mm_to_internal(units_mgr, radius_mm))
        fillet_input.addConstantRadiusEdgeSet(edge_collection, radius_input, True)
        feature = fillets.add(fillet_input)
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
        return {"ok": False, "error": f"Fillet failed: {exc}", "data": {"preview": {"plan": plan}}}

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

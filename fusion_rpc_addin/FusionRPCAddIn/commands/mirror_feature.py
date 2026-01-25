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

COMMAND = "mirror_feature"
REQUIRES_DESIGN = True

MAX_APPLY_MS = 1500.0
MAX_FACE_DELTA = 400
MAX_EDGE_DELTA = 800
MAX_BODY_DELTA = 10


def _total_counts(bodies):
    totals = {"faces": 0, "edges": 0, "vertices": 0}
    for body in bodies:
        totals["faces"] += selection_helpers._collection_count(body.faces)
        totals["edges"] += selection_helpers._collection_count(body.edges)
        totals["vertices"] += selection_helpers._collection_count(body.vertices)
    return totals


def _find_face_by_id(root_comp, face_id):
    for body in selection_helpers._list_visible_bodies(root_comp):
        for face in body.faces:
            if selection_helpers._entity_id(face) == face_id:
                return face
    return None


def _plane_from_name(root_comp, plane_name):
    plane_name = (plane_name or "").upper()
    if plane_name == "XY":
        return root_comp.xYConstructionPlane
    if plane_name == "YZ":
        return root_comp.yZConstructionPlane
    if plane_name == "XZ":
        return root_comp.xZConstructionPlane
    return None


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    feature_id = request.get("feature_id")
    body_name = request.get("body_name")
    mirror_plane = request.get("mirror_plane")
    face_id = request.get("face_id")
    preview = bool(request.get("preview", False))

    if not feature_id and not body_name:
        return {"ok": False, "error": "feature_id or body_name is required"}

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

    plane_obj = None
    if face_id:
        plane_obj = _find_face_by_id(root_comp, face_id)
        if not plane_obj:
            return {"ok": False, "error": f"face_id not found: {face_id}"}
    else:
        plane_obj = _plane_from_name(root_comp, mirror_plane)
        if not plane_obj:
            return {"ok": False, "error": "mirror_plane must be XY, YZ, XZ, or face_id must be provided"}

    plan = {"base": base_label, "mirror_plane": mirror_plane, "face_id": face_id}

    if preview:
        return {"ok": True, "error": None, "data": {"preview": {"is_preview": True, "plan": plan}}}

    before_visible = selection_helpers._list_visible_bodies(root_comp)
    before_counts = _total_counts(before_visible)
    before_body_count = len(before_visible)

    feature = None
    compute_ran = False
    start_time = time.time()
    try:
        mirrors = root_comp.features.mirrorFeatures
        mirror_input = mirrors.createInput(entities, plane_obj)
        feature = mirrors.add(mirror_input)
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
        return {"ok": False, "error": f"Mirror failed: {exc}", "data": {"preview": {"plan": plan}}}

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

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

COMMAND = "shell_feature"
REQUIRES_DESIGN = True

MAX_DISTANCE_MM = 50.0
MAX_APPLY_MS = 5000.0
MAX_FACE_DELTA = 500
MAX_EDGE_DELTA = 1000
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


def _find_faces_by_ids(root_comp, face_ids):
    found = []
    wanted = set(face_ids or [])
    if not wanted:
        return found
    for body in selection_helpers._list_visible_bodies(root_comp):
        for face in body.faces:
            face_id = selection_helpers._entity_id(face)
            if face_id in wanted:
                found.append(face)
                wanted.remove(face_id)
            if not wanted:
                return found
    return found


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    body_name = request.get("body_name")
    thickness_mm = request.get("thickness_mm")
    remove_faces = request.get("remove_faces")
    preview = bool(request.get("preview", False))
    inside = bool(request.get("inside", True))

    try:
        thickness_mm = float(thickness_mm)
    except Exception:
        return {"ok": False, "error": "thickness_mm must be numeric"}

    if thickness_mm <= 0:
        return {"ok": False, "error": "thickness_mm must be > 0"}
    if thickness_mm > MAX_DISTANCE_MM:
        return {"ok": False, "error": f"thickness_mm exceeds MAX_DISTANCE_MM ({MAX_DISTANCE_MM})"}

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
        return {"ok": False, "error": "Multiple visible bodies; specify body_name.", "candidates": candidates}

    faces_to_remove = []
    auto_selected = []
    if remove_faces:
        if not isinstance(remove_faces, list):
            return {"ok": False, "error": "remove_faces must be a list of face ids"}
        faces_to_remove = _find_faces_by_ids(root_comp, remove_faces)
        if len(faces_to_remove) != len(remove_faces):
            return {"ok": False, "error": "One or more remove_faces ids not found"}
    else:
        selector = selection_helpers._parse_face_selector("largest_planar")
        selected, _ = selection_helpers._select_face(body, selector, units_mgr, context.get("convert_mm"))
        if selected:
            faces_to_remove = [selected["face"]]
            face_id = selection_helpers._entity_id(selected["face"])
            if face_id:
                auto_selected = [face_id]

    plan = {
        "body_name": body.name,
        "thickness_mm": thickness_mm,
        "remove_faces": remove_faces or auto_selected,
        "inside": inside,
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
        shells = root_comp.features.shellFeatures
        try:
            thickness_input = adsk.core.ValueInput.createByString(f"{thickness_mm} mm")
        except Exception:
            thickness_input = adsk.core.ValueInput.createByReal(_mm_to_internal(units_mgr, thickness_mm))
        face_collection = adsk.core.ObjectCollection.create()
        for face in faces_to_remove:
            face_collection.add(face)
        try:
            shell_input = shells.createInput(face_collection, inside)
        except Exception:
            shell_input = shells.createInput(face_collection)
        if inside:
            try:
                shell_input.insideThickness = thickness_input
            except Exception:
                try:
                    shell_input.setInsideThickness(thickness_input)
                except Exception:
                    pass
        else:
            try:
                shell_input.outsideThickness = thickness_input
            except Exception:
                try:
                    shell_input.setOutsideThickness(thickness_input)
                except Exception:
                    pass
        try:
            shell_input.thickness = thickness_input
        except Exception:
            try:
                shell_input.setThickness(thickness_input)
            except Exception:
                pass
        try:
            shell_input.isInside = inside
        except Exception:
            try:
                shell_input.setIsInside(inside)
            except Exception:
                try:
                    shell_input.isOutside = not inside
                except Exception:
                    pass
        feature = shells.add(shell_input)
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
        return {"ok": False, "error": f"Shell failed: {exc}", "data": {"preview": {"plan": plan}}}

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

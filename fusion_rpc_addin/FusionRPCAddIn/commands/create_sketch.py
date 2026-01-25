import importlib
import os
import sys

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _selection_helpers as selection_helpers

importlib.reload(selection_helpers)

COMMAND = "create_sketch"
REQUIRES_DESIGN = True


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _plane_from_name(root_comp, plane_name):
    plane_name = (plane_name or "XY").upper()
    if plane_name == "XY":
        return root_comp.xYConstructionPlane, "XY"
    if plane_name == "YZ":
        return root_comp.yZConstructionPlane, "YZ"
    if plane_name == "XZ":
        return root_comp.xZConstructionPlane, "XZ"
    return None, None


def _find_face_by_id(root_comp, face_id):
    for body in selection_helpers._list_visible_bodies(root_comp):
        try:
            faces = body.faces
        except Exception:
            continue
        for face in faces:
            if selection_helpers._entity_id(face) == face_id:
                return face
    return None


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    plane = request.get("plane", "XY")
    face_id = request.get("face_id")
    origin_mm = request.get("origin_mm")
    name = request.get("name")
    preview = bool(request.get("preview", False))

    if face_id and origin_mm:
        return {"ok": False, "error": "origin_mm is not supported when face_id is provided."}

    face = None
    plane_obj = None
    plane_label = None
    offset_mm = 0.0

    if face_id:
        face = _find_face_by_id(root_comp, face_id)
        if not face:
            return {"ok": False, "error": f"face_id not found: {face_id}"}
    else:
        plane_obj, plane_label = _plane_from_name(root_comp, plane)
        if not plane_obj:
            return {"ok": False, "error": f"Unsupported plane: {plane}"}

        if origin_mm:
            try:
                x_mm = float(origin_mm.get("x", 0.0))
                y_mm = float(origin_mm.get("y", 0.0))
                z_mm = float(origin_mm.get("z", 0.0))
            except Exception:
                return {"ok": False, "error": "origin_mm must include numeric x,y,z"}
            if plane_label == "XY":
                offset_mm = z_mm
            elif plane_label == "YZ":
                offset_mm = x_mm
            elif plane_label == "XZ":
                offset_mm = y_mm

    plan = {
        "plane": plane_label,
        "face_id": face_id,
        "origin_mm": origin_mm,
        "offset_mm": offset_mm if origin_mm else None,
    }

    if preview:
        return {
            "ok": True,
            "error": None,
            "data": {"sketch": None, "preview": {"is_preview": True, "plan": plan}},
        }

    sketch_plane = face or plane_obj
    if not sketch_plane:
        return {"ok": False, "error": "Failed to resolve sketch plane."}

    if origin_mm and plane_obj and abs(offset_mm) > 0.0:
        try:
            planes = root_comp.constructionPlanes
            plane_input = planes.createInput()
            offset_internal = _mm_to_internal(units_mgr, offset_mm)
            plane_input.setByOffset(plane_obj, adsk.core.ValueInput.createByReal(offset_internal))
            sketch_plane = planes.add(plane_input)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to create offset plane: {exc}"}

    try:
        sketch = root_comp.sketches.add(sketch_plane)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to create sketch: {exc}"}

    if name:
        try:
            sketch.name = name
        except Exception:
            pass

    return {
        "ok": True,
        "error": None,
        "data": {
            "sketch": {
                "id": selection_helpers._entity_id(sketch),
                "name": getattr(sketch, "name", None),
                "plane": plane_label,
                "face_id": face_id,
            },
            "preview": {"is_preview": False, "plan": plan},
        },
    }

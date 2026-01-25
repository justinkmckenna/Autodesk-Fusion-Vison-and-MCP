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

COMMAND = "sketch_add_rectangle"
REQUIRES_DESIGN = True


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


def _collect_curve_ids(lines):
    ids = []
    if not lines:
        return ids
    try:
        count = int(lines.count)
    except Exception:
        count = None
    if count is not None:
        for idx in range(count):
            try:
                line = lines.item(idx)
            except Exception:
                continue
            line_id = selection_helpers._entity_id(line)
            if line_id:
                ids.append(line_id)
        return ids
    try:
        for line in lines:
            line_id = selection_helpers._entity_id(line)
            if line_id:
                ids.append(line_id)
    except Exception:
        pass
    return ids


def handle(request, context):
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")

    if not root_comp:
        return {"ok": False, "error": "No active design."}

    sketch_id = request.get("sketch_id")
    p1_mm = request.get("p1_mm")
    p2_mm = request.get("p2_mm")
    centered = bool(request.get("centered", False))
    preview = bool(request.get("preview", False))

    if not sketch_id:
        return {"ok": False, "error": "sketch_id is required"}
    if not isinstance(p1_mm, dict) or not isinstance(p2_mm, dict):
        return {"ok": False, "error": "p1_mm and p2_mm must be objects with x,y,z"}

    try:
        p1x = float(p1_mm.get("x", 0.0))
        p1y = float(p1_mm.get("y", 0.0))
        p1z = float(p1_mm.get("z", 0.0))
        p2x = float(p2_mm.get("x", 0.0))
        p2y = float(p2_mm.get("y", 0.0))
        p2z = float(p2_mm.get("z", 0.0))
    except Exception:
        return {"ok": False, "error": "p1_mm and p2_mm must be numeric"}

    sketch = _find_sketch(root_comp, sketch_id)
    if not sketch:
        return {"ok": False, "error": f"sketch_id not found: {sketch_id}"}

    plan = {
        "sketch_id": sketch_id,
        "p1_mm": {"x": p1x, "y": p1y, "z": p1z},
        "p2_mm": {"x": p2x, "y": p2y, "z": p2z},
        "centered": centered,
    }

    if preview:
        return {
            "ok": True,
            "error": None,
            "data": {"curves": [], "bbox_mm": None, "preview": {"is_preview": True, "plan": plan}},
        }

    p1 = adsk.core.Point3D.create(
        _mm_to_internal(units_mgr, p1x),
        _mm_to_internal(units_mgr, p1y),
        _mm_to_internal(units_mgr, p1z),
    )
    p2 = adsk.core.Point3D.create(
        _mm_to_internal(units_mgr, p2x),
        _mm_to_internal(units_mgr, p2y),
        _mm_to_internal(units_mgr, p2z),
    )

    try:
        if centered:
            lines = sketch.sketchCurves.sketchLines.addCenterPointRectangle(p1, p2)
            dx = abs(p2x - p1x)
            dy = abs(p2y - p1y)
            min_pt = {"x": p1x - dx, "y": p1y - dy, "z": p1z}
            max_pt = {"x": p1x + dx, "y": p1y + dy, "z": p1z}
        else:
            lines = sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)
            min_pt = {"x": min(p1x, p2x), "y": min(p1y, p2y), "z": min(p1z, p2z)}
            max_pt = {"x": max(p1x, p2x), "y": max(p1y, p2y), "z": max(p1z, p2z)}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to create rectangle: {exc}"}

    bbox_mm = {
        "min": min_pt,
        "max": max_pt,
        "size": {
            "x": max_pt["x"] - min_pt["x"],
            "y": max_pt["y"] - min_pt["y"],
            "z": max_pt["z"] - min_pt["z"],
        },
    }

    return {
        "ok": True,
        "error": None,
        "data": {
            "curves": _collect_curve_ids(lines),
            "bbox_mm": bbox_mm,
            "preview": {"is_preview": False, "plan": plan},
        },
    }

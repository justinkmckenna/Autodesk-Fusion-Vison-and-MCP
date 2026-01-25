import importlib
import os
import sys

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _feature_helpers as feature_helpers
import _selection_helpers as selection_helpers

importlib.reload(feature_helpers)
importlib.reload(selection_helpers)

COMMAND = "delete_feature"
REQUIRES_DESIGN = True


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    feature_id = request.get("feature_id")
    preview = bool(request.get("preview", False))

    if not feature_id:
        return {"ok": False, "error": "feature_id is required"}

    feature, type_name = feature_helpers._find_feature_by_id(root_comp, feature_id)
    if not feature:
        return {"ok": False, "error": f"feature_id not found: {feature_id}"}

    plan = {
        "feature_id": feature_id,
        "feature_type": feature_helpers._feature_type_name(feature, type_name),
        "name": getattr(feature, "name", None),
    }

    if preview:
        return {"ok": True, "error": None, "data": {"preview": {"is_preview": True, "plan": plan}}}

    try:
        feature.deleteMe()
        try:
            design.computeAll()
        except Exception:
            pass
    except Exception as exc:
        return {"ok": False, "error": f"Delete failed: {exc}", "data": {"preview": {"plan": plan}}}

    return {"ok": True, "error": None, "data": {"preview": {"is_preview": False, "plan": plan}}}

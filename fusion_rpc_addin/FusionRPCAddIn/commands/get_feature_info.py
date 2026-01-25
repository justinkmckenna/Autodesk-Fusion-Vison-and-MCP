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

COMMAND = "get_feature_info"
REQUIRES_DESIGN = True


def handle(request, context):
    root_comp = context.get("root_comp")
    if not root_comp:
        return {"ok": False, "error": "No active design."}

    feature_id = request.get("feature_id")
    if not feature_id:
        return {"ok": False, "error": "feature_id is required"}

    feature, type_name = feature_helpers._find_feature_by_id(root_comp, feature_id)
    if not feature:
        return {"ok": False, "error": f"feature_id not found: {feature_id}"}

    timeline_index = None
    try:
        timeline_obj = feature.timelineObject
        if timeline_obj:
            timeline_index = timeline_obj.index
    except Exception:
        timeline_index = None

    return {
        "ok": True,
        "error": None,
        "data": {
            "id": selection_helpers._entity_id(feature),
            "name": getattr(feature, "name", None),
            "type": feature_helpers._feature_type_name(feature, type_name),
            "body_name": feature_helpers._feature_body_name(feature),
            "timeline_index": timeline_index,
        },
    }

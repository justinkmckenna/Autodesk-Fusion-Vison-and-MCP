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

COMMAND = "list_features"
REQUIRES_DESIGN = True


def handle(request, context):
    root_comp = context.get("root_comp")
    if not root_comp:
        return {"ok": False, "error": "No active design."}

    filter_type = request.get("filter_type")
    if filter_type:
        filter_type = str(filter_type).lower()

    features_out = []
    for feature, type_name in feature_helpers._iter_features(root_comp):
        obj_type = feature_helpers._feature_type_name(feature, type_name)
        if filter_type:
            if filter_type not in obj_type.lower() and filter_type not in type_name.lower():
                continue
        features_out.append(
            {
                "id": selection_helpers._entity_id(feature),
                "name": getattr(feature, "name", None),
                "type": obj_type,
                "body_name": feature_helpers._feature_body_name(feature),
            }
        )

    features_out.sort(key=lambda item: (item.get("type") or "", item.get("name") or "", item.get("id") or ""))

    return {"ok": True, "error": None, "data": {"features": features_out}}

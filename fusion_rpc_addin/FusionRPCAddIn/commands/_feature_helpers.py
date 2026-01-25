import adsk.fusion

import _selection_helpers as selection_helpers


def _feature_collections(root_comp):
    features = root_comp.features
    return [
        ("extrude", features.extrudeFeatures),
        ("fillet", features.filletFeatures),
        ("chamfer", features.chamferFeatures),
        ("hole", features.holeFeatures),
        ("mirror", features.mirrorFeatures),
        ("rectangular_pattern", features.rectangularPatternFeatures),
        ("circular_pattern", features.circularPatternFeatures),
        ("shell", features.shellFeatures),
        ("revolve", features.revolveFeatures),
    ]


def _iter_features(root_comp):
    for type_name, collection in _feature_collections(root_comp):
        try:
            count = int(collection.count)
        except Exception:
            count = 0
        for idx in range(count):
            try:
                feature = collection.item(idx)
            except Exception:
                continue
            if feature:
                yield feature, type_name


def _feature_type_name(feature, fallback):
    try:
        obj_type = feature.objectType
    except Exception:
        obj_type = None
    if obj_type:
        return obj_type
    return fallback


def _feature_body_name(feature):
    try:
        bodies = feature.bodies
    except Exception:
        bodies = None
    if not bodies:
        return None
    try:
        if bodies.count > 0:
            return bodies.item(0).name
    except Exception:
        return None
    return None


def _find_feature_by_id(root_comp, feature_id):
    if not feature_id:
        return None, None
    for feature, type_name in _iter_features(root_comp):
        if selection_helpers._entity_id(feature) == feature_id:
            return feature, type_name
    return None, None

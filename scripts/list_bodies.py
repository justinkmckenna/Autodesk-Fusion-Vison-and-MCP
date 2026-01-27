import adsk.core, adsk.fusion

app = adsk.core.Application.get()

design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent if design else None

if not root:
    result = {"ok": False, "error": "No active design"}
else:
    bodies = [b.name for b in root.bRepBodies if b.isVisible and b.isSolid]
    result = {"ok": True, "bodies": bodies}

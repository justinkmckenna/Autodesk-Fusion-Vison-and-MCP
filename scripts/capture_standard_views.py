import adsk.core, adsk.fusion, os

app = adsk.core.Application.get()
viewport = app.activeViewport

# Update output directory and resolution if needed.
out_dir = "logs/captures"
width_px = 1200
height_px = 900

if not viewport:
    result = {"ok": False, "error": "No active viewport"}
else:
    os.makedirs(out_dir, exist_ok=True)

    def save_view(name, orientation):
        cam = viewport.camera
        cam.viewOrientation = orientation
        cam.isFitView = True
        viewport.camera = cam
        path = os.path.join(out_dir, f"{name}.png")
        ok = viewport.saveAsImageFile(path, width_px, height_px)
        return {"path": path, "ok": bool(ok)}

    captures = {
        "top": save_view("top", adsk.core.ViewOrientations.TopViewOrientation),
        "front": save_view("front", adsk.core.ViewOrientations.FrontViewOrientation),
        "right": save_view("right", adsk.core.ViewOrientations.RightViewOrientation),
        "iso": save_view("iso", adsk.core.ViewOrientations.IsoTopRightViewOrientation),
    }

    result = {"ok": True, "captures": captures}

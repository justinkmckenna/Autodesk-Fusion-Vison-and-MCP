# Repository Guidelines

## Project Structure & Module Organization
- `FusionRPCAddIn.py`: Fusion add-in source (runs inside Fusion).
- `fusion_rpc_client.py`: CLI utility for RPC commands.
- `logs/`: runtime captures and observations (generated at runtime).

## Build, Test, and Development Commands
- `python3 -m pip install -r requirements.txt` — install dependencies.
- `python3 fusion_rpc_client.py --code-stdin` — run multiline Python via stdin.

## Context7 Guidance
- Use `/autodeskfusion360/autodeskfusion360.github.io` as the primary index to confirm Fusion 360 API surface.
- Use `/ipendle/autodesk-fusion-api-documentation` for more detailed snippets when needed.

## Verification Strategy
- After any edit command (extrude, cut, fillet, pattern, sketch-driven change), run verification to confirm progress toward the end goal.
- Run visual captures after every major feature using `capture_standard_views` and compare against the reference using Pillow (e.g., `draft.png`).
- Run numerical checks after every major feature: `list_bodies`, `measure_bbox`, and targeted measurements for the changed dimension.
- Use other verification means as needed and report to the user if you found other means of measurement for verification useful.

### Verification Snippets (run_python)
- `scripts/list_bodies.py` — list visible solid bodies.
- `scripts/measure_bbox.py` — measure bounding box (mm) for a named body (edit `body_name`).
- `scripts/capture_standard_views.py` — capture top/front/right/iso to `logs/captures`.

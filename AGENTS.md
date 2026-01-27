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
- Run visual captures after every major feature using `capture_standard_views` and compare against the reference (e.g., `draft.png`).
- Run numerical checks after every major feature: `list_bodies`, `measure_bbox`, and targeted measurements for the changed dimension.
  - Use Fusion APIs directly in `run_python` snippets: enumerate `root_comp.bRepBodies` and use `boundingBox` for overall dimensions.
  - For visual captures, use Fusion view APIs via `app.activeViewport` (camera manipulation + `saveAsImageFile`) to set top/front/right/iso and export viewport images, then compare captures with Pillow.

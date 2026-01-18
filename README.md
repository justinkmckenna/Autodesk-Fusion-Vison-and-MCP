# Fusion Vision MCP (macOS)

This project provides a minimal MCP server and agent scaffold for controlling Autodesk Fusion via screen-based automation.

## Pivot: From Vision/UI Automation to Fusion API RPC
UI/vision clicking is brittle for vertex-level selection. General navigation worked, but precise measurement and edit workflows based on vision clicks were unreliable. We pivoted to a native RPC add-in that runs inside Fusion, exposes geometry via the Fusion API, and can load new command modules at runtime (no manual add-in reloads required after initial setup).

Architecture:
Agent/CLI <-> localhost TCP <-> Fusion RPC Add-In <-> Fusion API (main thread)

### Setup and Install (Fusion RPC Add-In)
Fusion add-ins must live in Fusion’s AddIns folder. Copy or symlink the add-in folder from this repo:

- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
- Windows: `%APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns`

From this repo, copy:
`fusion_rpc_addin/FusionRPCAddIn` -> Fusion AddIns folder

### Run the Add-In
1) Fusion -> Utilities -> Add-Ins -> Scripts and Add-Ins
2) Add-Ins tab -> select `FusionRPCAddIn` -> Run
3) Optionally enable “Run on Startup”

### Test from Terminal
```bash
python3 scripts/fusion_rpc_client.py ping
python3 scripts/fusion_rpc_client.py list_bodies
python3 scripts/fusion_rpc_client.py measure_bbox
python3 scripts/fusion_rpc_client.py measure_bbox --body "Body1"
```

### Runtime Commands (No Add-In Toggle Needed)
The add-in discovers command modules from `FusionRPCAddIn/commands/` (one file per command). After initial add-in load, you can add new command files and hot-reload:

```bash
python3 scripts/fusion_rpc_client.py help
python3 scripts/fusion_rpc_client.py reload_commands
```

To pass custom parameters to new commands:
```bash
python3 scripts/fusion_rpc_client.py my_command --param foo=123 --param bar=true
```

### Security + Troubleshooting
- The add-in binds only to `127.0.0.1` (not exposed on the network).
- If the port is in use, set `FUSION_RPC_PORT` before starting Fusion.
- Add-in logs are written to a temp file; the path is shown on startup.

## Files
- `mcp_server.py`: MCP server exposing screen + input tools.
- `agent_runner.py`: Minimal agent runner (simple mode + planner loop stub).
- `calibration.json`: Example region presets.
- `logs/`: Captures, snapshots, and observations (created at runtime).

## macOS Permissions
The MCP process must be granted:
- **Screen Recording** permission to capture screenshots.
- **Accessibility** permission to send mouse/keyboard events.

Grant permissions in **System Settings → Privacy & Security → Screen Recording / Accessibility** for the Python executable you run.

## Quick Start
1) Install requirements:
```bash
python3 -m pip install -r requirements.txt
```

2) Run the minimal demo (ESC ESC → capture timeline/canvas → print stub observation):
```bash
python3 agent_runner.py
```

3) Run the planner loop stub:
```bash
python3 agent_runner.py --loop --max-steps 8
```

4) Force measure panel capture during the loop (for testing):
```bash
python3 agent_runner.py --loop --max-steps 8 --force-measure
```

5) Add delay before each vision request (reduce 429s):
```bash
python3 agent_runner.py --loop --max-steps 8 --vision-delay-ms 4000
```

## Running MCP in a Separate Terminal
If macOS Accessibility permissions are blocking VS Code-hosted processes, run the MCP server from a trusted terminal and connect to it from the agent runner:

1) Start the MCP server in a terminal that has Accessibility + Screen Recording permissions:
```bash
python3 mcp_server.py --tcp-host 127.0.0.1 --tcp-port 8765
```

2) From VS Code (or Codex), connect the agent runner:
```bash
python3 agent_runner.py --connect 127.0.0.1:8765
```

## Notes
- `calibration.json` values are example coordinates. Update them for your display layout.
- `get_screen_info` is available for Retina scale detection to avoid click offsets.
- Vision model integration uses the built-in vision client. Set `FUSION_VISION_API_KEY` and optional `FUSION_VISION_MODEL`/`FUSION_VISION_ENDPOINT` (OpenAI-compatible).
- You can also set these values in a `.env` file in the project root (or set `FUSION_ENV_PATH` to point elsewhere).
- For measurement steps, turn **off** the background grid in Fusion and set selection filters to **Body Vertices** so clicks snap to corners.

"""Minimal MCP stdio server used by the skills/MCP smoke.

Speaks line-delimited JSON-RPC 2.0 on stdin/stdout with just enough of the MCP
protocol to prove a client discovered and connected to it:

- initialize            -> protocolVersion + resources capability
- resources/list        -> one resource, uri "probe://hello"
- resources/read        -> contents text "PONG"
- ping                  -> {}

Anything else gets a JSON-RPC error, so a silent fallback can't pass.
"""

import json
import sys

PROTOCOL_VERSION = "2025-06-18"
RESOURCE_URI = "probe://hello"


def reply(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def handle(request: dict) -> None:
    method = request.get("method")
    request_id = request.get("id")
    if request_id is None:  # notification (initialized, cancelled, ...)
        return
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"resources": {}},
            "serverInfo": {"name": "probe", "version": "0.0.1"},
        }
    elif method == "resources/list":
        result = {
            "resources": [
                {
                    "uri": RESOURCE_URI,
                    "name": "hello",
                    "mimeType": "text/plain",
                }
            ]
        }
    elif method == "resources/read":
        if (request.get("params") or {}).get("uri") != RESOURCE_URI:
            reply(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "unknown resource"},
                }
            )
            return
        result = {"contents": [{"uri": RESOURCE_URI, "mimeType": "text/plain", "text": "PONG"}]}
    elif method == "ping":
        result = {}
    else:
        reply(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            }
        )
        return
    reply({"jsonrpc": "2.0", "id": request_id, "result": result})


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(request, dict):
            handle(request)


if __name__ == "__main__":
    main()

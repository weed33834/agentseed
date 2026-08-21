# Used by indexers (e.g. Glama) that build and probe MCP servers in containers.
# AgentSeed is pure-Python stdlib, so the image is trivial.
FROM python:3.12-slim

WORKDIR /app
COPY server/ ./server/
COPY skills/ ./skills/
COPY plugin.json mcp.json ./

# MCP stdio transport: the indexer sends JSON-RPC over stdin/stdout.
CMD ["python", "server/guard_server.py"]

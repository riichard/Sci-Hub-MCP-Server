# Sci-Hub MCP Server

An MCP server that lets AI assistants search and download academic papers via Sci-Hub.

## Installation

Requires Python 3.10+. Using [uv](https://docs.astral.sh/uv/) is recommended — it creates an isolated environment with no dependency conflicts:

```bash
git clone https://github.com/riichard/Sci-Hub-MCP-Server.git
cd Sci-Hub-MCP-Server
uv venv && uv pip install -e .
source .venv/bin/activate
```

Or with standard pip:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running the server

Default mode is Streamable HTTP on `http://localhost:8000/mcp`:

```bash
python sci_hub_server.py
```

Other transports:

```bash
# Stdio (for local MCP clients)
python sci_hub_server.py --transport stdio

# SSE
python sci_hub_server.py --transport sse --host 0.0.0.0 --port 8000
```

All flags can also be set via environment variables: `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_STREAMABLE_HTTP_PATH`, `MCP_SSE_PATH`, `MCP_MESSAGE_PATH`.

## Claude Desktop setup

For local stdio usage, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scihub": {
      "command": "/path/to/Sci-Hub-MCP-Server/.venv/bin/python",
      "args": ["/path/to/Sci-Hub-MCP-Server/sci_hub_server.py", "--transport", "stdio"]
    }
  }
}
```

For network usage (Streamable HTTP), deploy the server and add the URL via **Settings → Connectors → Add custom connector** in Claude Desktop.

## Mirror configuration

Sci-Hub mirrors go down frequently. Configure fallbacks with environment variables:

| Variable | Default | Description |
|---|---|---|
| `SCIHUB_BASE_URL` | `https://sci-hub.ren` | Primary mirror |
| `SCIHUB_BASE_URLS` | — | Comma-separated additional mirrors |
| `SCIHUB_PROXY` | — | Proxy URL (e.g. `socks5://127.0.0.1:9050`) |
| `SCIHUB_COOKIE` | — | Cookie header (e.g. `cf_clearance=...` for Cloudflare) |
| `SCIHUB_TIMEOUT_SECONDS` | `20` | Request timeout |
| `SCIHUB_HTTP_CLIENT` | auto | `curl_cffi` or `requests` |
| `SCIHUB_DOWNLOAD_DIR` | `~/Downloads` | Fallback download directory |

Example:

```bash
SCIHUB_BASE_URL=https://sci-hub.se SCIHUB_TIMEOUT_SECONDS=30 python sci_hub_server.py
```

## Tools

| Tool | Description |
|---|---|
| `search_scihub_by_doi` | Find a paper by DOI |
| `search_scihub_by_title` | Find a paper by title (resolves DOI via CrossRef) |
| `search_scihub_by_keyword` | Search papers by keyword (returns metadata + PDF URLs where available) |
| `download_scihub_pdf` | Download a PDF to a local path |
| `get_paper_metadata` | Get metadata for a paper by DOI |

## Docker

```bash
docker build -t sci-hub-mcp .
docker run -p 8000:8000 sci-hub-mcp
```

## Contributing

PRs welcome. This is a community-maintained fork of [JackKuo666/Sci-Hub-MCP-Server](https://github.com/JackKuo666/Sci-Hub-MCP-Server).

## License

MIT

## Disclaimer

For research purposes only. Respect copyright laws and use responsibly.

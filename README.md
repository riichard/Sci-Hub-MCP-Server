# Sci-Hub MCP Server

[![smithery badge](https://smithery.ai/badge/@JackKuo666/sci-hub-mcp-server)](https://smithery.ai/server/@JackKuo666/sci-hub-mcp-server)

🔍 Enable AI assistants to search, access, and analyze academic papers through Sci-Hub using a simple MCP interface.

The Sci-Hub MCP Server provides a bridge between AI assistants and Sci-Hub's repository of academic literature through the Model Context Protocol (MCP). It allows AI models to search for scientific articles by DOI, title, or keywords, access their metadata, and download PDFs in a programmatic way.

## ✨ Core Features

- 🔎 Paper Search by DOI: Find papers using their Digital Object Identifier ✅
- 🔍 Paper Search by Title: Locate papers using their full or partial title ✅
- 🔑 Paper Search by Keyword: Discover papers related to specific research areas ✅
- 📊 Metadata Access: Retrieve detailed metadata for specific papers ✅
- 📄 PDF Download: Download full-text PDF content when available ✅

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- FastMCP library

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/JackKuo666/Sci-Hub-MCP-Server.git
   cd Sci-Hub-MCP-Server
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## 📊 Usage

Start the MCP server (network mode, Streamable HTTP, default):

```bash
python sci_hub_server.py
```

Default endpoint (local access):

- `http://localhost:8000/mcp` (server bind address defaults to `0.0.0.0`)

Optional runtime flags:

```bash
# Streamable HTTP (recommended for Claude Desktop)
python sci_hub_server.py --transport streamable-http --host 0.0.0.0 --port 8000 --streamable-http-path /mcp

# SSE transport
python sci_hub_server.py --transport sse --host 0.0.0.0 --port 8000 --sse-path /sse --message-path /messages/

# Stdio transport (legacy/local MCP clients)
python sci_hub_server.py --transport stdio
```

Environment variable equivalents:

- `MCP_TRANSPORT`
- `MCP_HOST`
- `MCP_PORT`
- `MCP_STREAMABLE_HTTP_PATH`
- `MCP_SSE_PATH`
- `MCP_MESSAGE_PATH`
- `MCP_MOUNT_PATH`

## Configure Sci-Hub Mirror

The server now prioritizes `https://sci-hub.ren` by default.

- `SCIHUB_BASE_URL`: Primary Sci-Hub mirror URL/host (default: `https://sci-hub.ren`)
- `SCIHUB_BASE_URLS`: Optional comma-separated additional mirrors
- `SCIHUB_INCLUDE_DEFAULT_MIRRORS`: Whether to append package default mirrors (`false` by default)
- `SCIHUB_PROXY`: Optional proxy URL (for example `socks5://127.0.0.1:9050`)
- `SCIHUB_COOKIE`: Optional cookie header (useful for `cf_clearance` if Cloudflare challenges are active)
- `SCIHUB_TIMEOUT_SECONDS`: Request timeout in seconds (default: `20`)
- `SCIHUB_HTTP_CLIENT`: `curl_cffi` or `requests` (default auto-selects `curl_cffi` when installed)
- `SCIHUB_IMPERSONATE`: Browser fingerprint for `curl_cffi` (default: `chrome124`)
- `SCIHUB_USER_AGENT`: Override user agent string for Sci-Hub/CrossRef requests
- `SCIHUB_REFERER`: Override referer header used for mirror requests
- `SCIHUB_DOWNLOAD_DIR`: Fallback directory for downloads when requested output paths are not writable from the MCP runtime

Example:

```bash
SCIHUB_BASE_URL=https://sci-hub.ren \
SCIHUB_BASE_URLS=sci-hub.se,sci-hub.st \
SCIHUB_TIMEOUT_SECONDS=30 \
python sci_hub_server.py
```

If all mirrors return Cloudflare challenge pages, configure `SCIHUB_PROXY` or `SCIHUB_COOKIE` and retry.

### Keyword Search Behavior

`search_scihub_by_keyword` now returns up to `num_results` items even when some PDFs cannot be resolved.  
Each item has:
- `status: "success"` when a Sci-Hub PDF URL was resolved
- `status: "metadata_only"` when CrossRef metadata was found but Sci-Hub PDF resolution failed

### Download Behavior

`download_scihub_pdf` accepts direct PDF URLs and Sci-Hub page URLs.  
If the provided `output_path` is not writable in the MCP runtime (for example VM paths like `/home/claude/...`), it automatically falls back to `SCIHUB_DOWNLOAD_DIR` (or `~/Downloads`).

## Usage with Claude Desktop (Network MCP Connectors)

Claude Desktop custom connectors use network MCP servers. Use the server URL flow instead of local `claude_desktop_config.json` command entries.

1. Deploy this server where Claude can reach it over HTTPS.
2. Run the server in Streamable HTTP mode (default):
   ```bash
   python sci_hub_server.py --transport streamable-http --host 0.0.0.0 --port 8000
   ```
3. Expose it via TLS (for example behind a reverse proxy) so the MCP endpoint is available at a public URL like:
   - `https://your-domain.example/mcp`
4. In Claude Desktop, open `Settings -> Connectors -> Add custom connector` and paste the MCP URL.

If you prefer SSE, this server also supports it at `/sse` with message posting at `/messages/`.

### Legacy command-based setup (non-Claude clients only)

If another client still needs a local stdio MCP process, run:

```bash
python sci_hub_server.py --transport stdio
```

## 🛠 MCP Tools

The Sci-Hub MCP Server provides the following tools:

1. `search_scihub_by_doi`: Search for a paper on Sci-Hub using its DOI (Digital Object Identifier).
2. `search_scihub_by_title`: Search for a paper on Sci-Hub using its title.
3. `search_scihub_by_keyword`: Search for papers on Sci-Hub using a keyword.
4. `download_scihub_pdf`: Download a paper PDF from Sci-Hub.
5. `get_paper_metadata`: Get metadata information for a paper using its DOI.

### Searching Papers by DOI

You can ask the AI assistant to search for papers using DOI:
```
Can you search Sci-Hub for the paper with DOI 10.1038/nature09492?
```

### Searching Papers by Title

You can search for papers using their title:
```
Can you find the paper titled "Choosing Assessment Instruments for Posttraumatic Stress Disorder Screening and Outcome Research" on Sci-Hub?
```

### Searching Papers by Keyword

You can search for papers related to specific keywords:
```
Can you search Sci-Hub for recent papers about artificial intelligence in medicine?
```

### Downloading Papers

Once you have found a paper, you can download it:
```
Can you download the PDF for this paper to my_paper.pdf?
```

### Getting Paper Metadata

You can request metadata for a paper using its DOI:
```
Can you show me the metadata for the paper with DOI 10.1038/nature09492?
```

## 📁 Project Structure

- `sci_hub_server.py`: The main MCP server implementation using FastMCP
- `sci_hub_search.py`: Contains the logic for searching Sci-Hub and retrieving paper information

## 🔧 Dependencies

- Python 3.10+
- FastMCP
- requests
- bs4
- scihub

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License.

## ⚠️ Disclaimer

This tool is for research purposes only. Please respect copyright laws and use this tool responsibly. The authors do not endorse or encourage any copyright infringement.

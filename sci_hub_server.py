import argparse
import asyncio
import logging
import os
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP
from sci_hub_search import download_paper, search_paper_by_doi, search_paper_by_title, search_papers_by_keyword

def _read_log_level() -> int:
    raw = os.getenv("MCP_LOG_LEVEL", "ERROR").upper()
    return getattr(logging, raw, logging.ERROR)


# Setup logging (stderr only; keep default quiet for stdio transport)
logging.basicConfig(level=_read_log_level(), format='%(asctime)s - %(levelname)s - %(message)s')

SUPPORTED_TRANSPORTS = ("stdio", "sse", "streamable-http")


def _read_int_env(name: str, fallback: int) -> int:
    value = os.getenv(name)
    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError:
        logging.warning("Invalid %s value %r. Falling back to %d.", name, value, fallback)
        return fallback


def _normalize_path(path: str, trailing_slash: bool = False) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if trailing_slash and not normalized.endswith("/"):
        return f"{normalized}/"
    if not trailing_slash and normalized != "/" and normalized.endswith("/"):
        return normalized.rstrip("/")
    return normalized


def _read_transport_env() -> str:
    transport = os.getenv("MCP_TRANSPORT", "streamable-http").strip().lower()
    if transport not in SUPPORTED_TRANSPORTS:
        logging.warning(
            "Invalid MCP_TRANSPORT value %r. Falling back to %s.",
            transport,
            "streamable-http",
        )
        return "streamable-http"
    return transport


DEFAULT_TRANSPORT = _read_transport_env()
DEFAULT_HOST = os.getenv("MCP_HOST", "0.0.0.0")
DEFAULT_PORT = _read_int_env("MCP_PORT", 8000)
DEFAULT_SSE_PATH = _normalize_path(os.getenv("MCP_SSE_PATH", "/sse"))
DEFAULT_MESSAGE_PATH = _normalize_path(os.getenv("MCP_MESSAGE_PATH", "/messages/"), trailing_slash=True)
DEFAULT_STREAMABLE_HTTP_PATH = _normalize_path(os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp"))
DEFAULT_MOUNT_PATH = os.getenv("MCP_MOUNT_PATH") or None

# Initialize FastMCP server
mcp = FastMCP(
    "scihub",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    sse_path=DEFAULT_SSE_PATH,
    message_path=DEFAULT_MESSAGE_PATH,
    streamable_http_path=DEFAULT_STREAMABLE_HTTP_PATH,
)

@mcp.tool()
async def search_scihub_by_doi(doi: str) -> Dict[str, Any]:
    logging.info(f"Searching for paper with DOI: {doi}")
    """
    Search for a paper on Sci-Hub using its DOI (Digital Object Identifier).

    Args:
        doi (str): The Digital Object Identifier of the paper, a unique alphanumeric string 
             that identifies academic, professional, and scientific content 
             (e.g., "10.1038/nature09492").

    Returns:
        Dict[str, Any]: Dictionary containing paper information including:
            - title: The title of the paper
            - author: The author(s) of the paper
            - year: Publication year
            - pdf_url: URL to download the PDF if available
            - status: Success or error status
            - error: Error message if search failed
    """
    try:
        result = await asyncio.to_thread(search_paper_by_doi, doi)
        return result
    except Exception as e:
        return {"error": f"An error occurred while searching by DOI: {str(e)}"}

@mcp.tool()
async def search_scihub_by_title(title: str) -> Dict[str, Any]:
    logging.info(f"Searching for paper with title: {title}")
    """
    Search for a paper on Sci-Hub using its title.

    Args:
        title (str): The full or partial title of the academic paper to search for.
               More specific and complete titles will yield more accurate results.

    Returns:
        Dict[str, Any]: Dictionary containing paper information including:
            - title: The title of the paper
            - author: The author(s) of the paper
            - year: Publication year
            - pdf_url: URL to download the PDF if available
            - status: Success or error status
            - error: Error message if search failed
    """
    try:
        result = await asyncio.to_thread(search_paper_by_title, title)
        return result
    except Exception as e:
        return {"error": f"An error occurred while searching by title: {str(e)}"}

@mcp.tool()
async def search_scihub_by_keyword(keyword: str, num_results: int = 10) -> List[Dict[str, Any]]:
    logging.info(f"Searching for papers with keyword: {keyword}, number of results: {num_results}")
    """
    Search for papers on Sci-Hub using a keyword.

    Args:
        keyword (str): The keyword or search term to use for finding relevant papers.
                 Can be a subject, concept, or any term related to the research area.
        num_results (int, optional): Maximum number of search results to return. 
                      Defaults to 10. Higher values may increase search time.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing information about a paper:
            - title: The title of the paper
            - author: The author(s) of the paper
            - year: Publication year
            - doi: Digital Object Identifier if available
            - pdf_url: URL to download the PDF if available
            - status: Success or error status
            - error: Error message if search failed
    """
    try:
        results = await asyncio.to_thread(search_papers_by_keyword, keyword, num_results)
        return results
    except Exception as e:
        return [{"error": f"An error occurred while searching by keyword: {str(e)}"}]

@mcp.tool()
async def download_scihub_pdf(pdf_url: str, output_path: str) -> str:
    logging.info(f"Attempting to download PDF from {pdf_url} to {output_path}")
    """
    Download a paper PDF from Sci-Hub.

    Args:
        pdf_url (str): The URL of the PDF to download. This should be a direct link to the PDF file,
                 typically obtained from a previous search result's 'pdf_url' field.
        output_path (str): The file path where the downloaded PDF should be saved.
                     Should include the filename with .pdf extension.

    Returns:
        str: A message indicating the download result:
             - Success message with the output path if download was successful
             - Failure message if download failed
             - Error message with exception details if an error occurred
    """
    try:
        result = await asyncio.to_thread(download_paper, pdf_url, output_path)
        if isinstance(result, dict):
            if result.get("success"):
                resolved_path = result.get("path", output_path)
                source_url = result.get("source_url", pdf_url)
                return f"PDF successfully downloaded to {resolved_path} (source: {source_url})"
            error = result.get("error", "unknown error")
            resolved_path = result.get("path", output_path)
            return f"Failed to download PDF to {resolved_path}. {error}"

        # Backward compatibility with older boolean return shape.
        if result:
            return f"PDF successfully downloaded to {output_path}"
        return f"Failed to download PDF to {output_path}"
    except Exception as e:
        return f"An error occurred while downloading PDF: {str(e)}"

@mcp.tool()
async def get_paper_metadata(doi: str) -> Dict[str, Any]:
    logging.info(f"Getting metadata for paper with DOI: {doi}")
    """
    Get metadata information for a paper using its DOI.

    Args:
        doi (str): The Digital Object Identifier of the paper, a unique alphanumeric string
             that identifies the academic paper (e.g., "10.1038/nature09492").

    Returns:
        Dict[str, Any]: Dictionary containing paper metadata including:
            - doi: The DOI of the paper
            - title: The title of the paper
            - author: The author(s) of the paper
            - year: Publication year
            - pdf_url: URL to download the PDF if available
            - status: Success or error status
            - error: Error message if retrieval failed
    """
    try:
        # First search for the paper by DOI
        paper_info = await asyncio.to_thread(search_paper_by_doi, doi)
        
        if paper_info.get('status') == 'success':
            # Extract and return metadata
            return {
                'doi': doi,
                'title': paper_info.get('title', ''),
                'author': paper_info.get('author', ''),
                'year': paper_info.get('year', ''),
                'pdf_url': paper_info.get('pdf_url', ''),
                'status': 'success'
            }
        else:
            return {"error": f"Could not find metadata for paper with DOI {doi}"}
    except Exception as e:
        return {"error": f"An error occurred while getting metadata: {str(e)}"}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sci-Hub MCP server")
    parser.add_argument(
        "--transport",
        choices=SUPPORTED_TRANSPORTS,
        default=DEFAULT_TRANSPORT,
        help="MCP transport to run",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host for network transports")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port for network transports")
    parser.add_argument(
        "--streamable-http-path",
        default=DEFAULT_STREAMABLE_HTTP_PATH,
        help="HTTP path used for streamable-http transport",
    )
    parser.add_argument("--sse-path", default=DEFAULT_SSE_PATH, help="HTTP path used for SSE transport")
    parser.add_argument(
        "--message-path",
        default=DEFAULT_MESSAGE_PATH,
        help="Message path used by SSE transport",
    )
    parser.add_argument(
        "--mount-path",
        default=DEFAULT_MOUNT_PATH,
        help="Optional app mount path for SSE transport",
    )
    return parser.parse_args()


def configure_server(args: argparse.Namespace) -> None:
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = _normalize_path(args.streamable_http_path)
    mcp.settings.sse_path = _normalize_path(args.sse_path)
    mcp.settings.message_path = _normalize_path(args.message_path, trailing_slash=True)


def main() -> None:
    args = parse_args()
    configure_server(args)

    logging.info(
        "Starting Sci-Hub MCP server transport=%s host=%s port=%d streamable_http_path=%s",
        args.transport,
        args.host,
        args.port,
        mcp.settings.streamable_http_path,
    )
    try:
        if args.transport == "sse":
            mcp.run(transport="sse", mount_path=args.mount_path)
        else:
            mcp.run(transport=args.transport)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Sci-Hub MCP server stopped.")


if __name__ == "__main__":
    main()

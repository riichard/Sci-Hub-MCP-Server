import logging
import os
import re
from urllib.parse import unquote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from scihub import SciHub

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover - optional dependency
    curl_requests = None

# Disable HTTPS certificate verification warnings because some mirrors use broken TLS chains.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_SCIHUB_BASE_URL = "https://sci-hub.ren"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

LOGGER = logging.getLogger(__name__)
logging.getLogger("scihub").setLevel(logging.ERROR)


def _get_http_client_name():
    requested = os.getenv("SCIHUB_HTTP_CLIENT", "").strip().lower()
    if requested in {"curl_cffi", "requests"}:
        if requested == "curl_cffi" and curl_requests is None:
            LOGGER.warning("SCIHUB_HTTP_CLIENT=curl_cffi requested but curl_cffi is not installed. Falling back to requests.")
            return "requests"
        return requested

    if requested:
        LOGGER.warning("Unknown SCIHUB_HTTP_CLIENT=%r. Falling back to auto selection.", requested)
    return "curl_cffi" if curl_requests is not None else "requests"


def _normalize_mirror(value):
    """Convert mirror URL/host input to host format."""
    raw = (value or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path or "").strip().strip("/")
    if not host:
        return ""

    return host.split("/")[0]


def _parse_bool_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _get_timeout():
    raw = os.getenv("SCIHUB_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        return timeout
    except ValueError:
        LOGGER.warning("Invalid SCIHUB_TIMEOUT_SECONDS=%r. Falling back to %.1f", raw, DEFAULT_TIMEOUT_SECONDS)
        return DEFAULT_TIMEOUT_SECONDS


def _build_session():
    client_name = _get_http_client_name()
    if client_name == "curl_cffi":
        session = curl_requests.Session(impersonate=os.getenv("SCIHUB_IMPERSONATE", "chrome124"))
    else:
        session = requests.Session()

    session.headers.update(
        {
            "User-Agent": os.getenv("SCIHUB_USER_AGENT", DEFAULT_USER_AGENT),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": os.getenv("SCIHUB_REFERER", "https://sci-hub.ren/"),
        }
    )

    cookie_header = os.getenv("SCIHUB_COOKIE", "").strip()
    if cookie_header:
        session.headers["Cookie"] = cookie_header

    proxy = os.getenv("SCIHUB_PROXY", "").strip()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    return session


def _sanitize_filename(name):
    cleaned = re.sub(r"[^\w.\-]+", "_", name or "paper.pdf").strip("._")
    if not cleaned:
        cleaned = "paper.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def _default_download_dir():
    configured = os.getenv("SCIHUB_DOWNLOAD_DIR", "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _looks_like_vm_path(path):
    normalized = path.replace("\\", "/")
    return normalized.startswith("/home/claude/") or normalized.startswith("/sessions/")


def _prepare_output_path(output_path, pdf_url):
    requested = (output_path or "").strip()
    parsed = urlparse(pdf_url or "")
    fallback_name = _sanitize_filename(os.path.basename(parsed.path) or "paper.pdf")

    if not requested:
        target = os.path.join(_default_download_dir(), fallback_name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        return target

    if _looks_like_vm_path(requested):
        target = os.path.join(_default_download_dir(), _sanitize_filename(os.path.basename(requested)))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        return target

    target = os.path.abspath(os.path.expanduser(requested))
    parent = os.path.dirname(target) or "."
    try:
        os.makedirs(parent, exist_ok=True)
        test_path = os.path.join(parent, f".__scihub_write_test_{os.getpid()}")
        with open(test_path, "wb"):
            pass
        os.remove(test_path)
        return target
    except OSError:
        fallback = os.path.join(_default_download_dir(), _sanitize_filename(os.path.basename(target) or fallback_name))
        os.makedirs(os.path.dirname(fallback), exist_ok=True)
        return fallback


def _get_configured_mirrors():
    """Build prioritized mirror list."""
    primary = _normalize_mirror(os.getenv("SCIHUB_BASE_URL", DEFAULT_SCIHUB_BASE_URL))
    if not primary:
        primary = _normalize_mirror(DEFAULT_SCIHUB_BASE_URL)

    mirrors = [primary]

    extra_raw = os.getenv("SCIHUB_BASE_URLS", "")
    for candidate in [item.strip() for item in extra_raw.split(",") if item.strip()]:
        normalized = _normalize_mirror(candidate)
        if normalized and normalized not in mirrors:
            mirrors.append(normalized)

    include_defaults = _parse_bool_env("SCIHUB_INCLUDE_DEFAULT_MIRRORS", False)
    if include_defaults:
        for candidate in SciHub().available_base_url_list:
            if candidate not in mirrors:
                mirrors.append(candidate)

    return mirrors


def _is_cloudflare_challenge(response):
    text = response.text[:20000] if response.text else ""
    if response.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if response.status_code in {403, 429, 503} and (
        "Just a moment..." in text
        or "cf-browser-verification" in text
        or "Attention Required!" in text
        or "challenge-platform" in text
    ):
        return True
    return False


def _normalize_pdf_candidate(candidate, page_url):
    if not candidate:
        return ""
    src = candidate.strip()
    if src.startswith("//"):
        src = f"https:{src}"
    elif src.startswith("/"):
        src = urljoin(page_url, src)
    elif src.startswith("./") or src.startswith("../"):
        src = urljoin(page_url, src)

    if src.startswith("http://") or src.startswith("https://"):
        return src
    return ""


def _extract_doi_from_url(value):
    parsed = urlparse(value or "")
    if not parsed.path:
        return ""

    path = unquote(parsed.path).strip("/")
    if path.lower().startswith("pdf/"):
        path = path[4:]
    if path.lower().endswith(".pdf"):
        path = path[:-4]

    # Common DOI pattern with numeric prefix.
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", path)
    if match:
        return match.group(1)

    # If path itself looks like DOI after stripping.
    if path.startswith("10.") and "/" in path:
        return path
    return ""


def _extract_pdf_url_from_html(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []

    tag_attr_pairs = [
        ("iframe", "src"),
        ("embed", "src"),
        ("object", "data"),
        ("meta", "content"),
        ("a", "href"),
    ]

    for tag, attr in tag_attr_pairs:
        for element in soup.find_all(tag):
            if tag == "meta" and element.get("name", "").lower() != "citation_pdf_url":
                continue
            value = element.get(attr)
            if value:
                candidates.append(value)

    # Fallback regex for direct PDF links in inline scripts/content.
    for match in re.findall(r"https?://[^\\\"'\\s<>]+\\.pdf(?:\\?[^\\\"'\\s<>]*)?", html or "", re.IGNORECASE):
        candidates.append(match)

    for candidate in candidates:
        normalized = _normalize_pdf_candidate(candidate, page_url)
        if normalized:
            return normalized

    return ""


def _is_probably_pdf_response(response):
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/pdf" in content_type:
        return True
    if response.status_code >= 400:
        return False

    try:
        first_chunk = next(response.iter_content(chunk_size=16), b"")
    except Exception:
        return False
    return first_chunk.startswith(b"%PDF")


def _validate_pdf_candidate(session, pdf_url, timeout):
    try:
        response = session.get(pdf_url, timeout=timeout, verify=False, stream=True, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        return "", f"candidate_request_error:{type(exc).__name__}"

    if _is_cloudflare_challenge(response):
        return "", "candidate_cloudflare_challenge"
    if _is_probably_pdf_response(response):
        return pdf_url, "ok"
    return "", f"candidate_not_pdf_status_{response.status_code}"


def _download_candidate_to_file(session, pdf_url, output_path, timeout):
    response = session.get(pdf_url, timeout=timeout, verify=False, stream=True, allow_redirects=True)
    if _is_cloudflare_challenge(response):
        return False, "cloudflare_challenge"
    if response.status_code >= 400:
        return False, f"http_{response.status_code}"

    first_chunk = b""
    with open(output_path, "wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            if not first_chunk:
                first_chunk = chunk
            handle.write(chunk)

    if first_chunk and not first_chunk.startswith(b"%PDF"):
        return False, "not_pdf_content"
    return True, "ok"


def _try_identifier_with_mirror(session, mirror_host, identifier, timeout):
    endpoints = [
        ("get", f"https://{mirror_host}/{identifier}", None),
        ("post", f"https://{mirror_host}/", {"request": identifier}),
    ]

    last_reason = "no_response"
    for method, url, payload in endpoints:
        try:
            if method == "get":
                response = session.get(url, timeout=timeout, verify=False, allow_redirects=True)
            else:
                response = session.post(url, data=payload, timeout=timeout, verify=False, allow_redirects=True)
        except requests.exceptions.RequestException as exc:
            last_reason = f"request_error:{type(exc).__name__}"
            continue

        if _is_cloudflare_challenge(response):
            last_reason = "cloudflare_challenge"
            continue

        content_type = (response.headers.get("content-type") or "").lower()
        if "application/pdf" in content_type:
            validated_url, reason = _validate_pdf_candidate(session, response.url, timeout)
            if validated_url:
                return validated_url, "ok"
            last_reason = reason
            continue

        pdf_url = _extract_pdf_url_from_html(response.text, response.url)
        if pdf_url:
            validated_url, reason = _validate_pdf_candidate(session, pdf_url, timeout)
            if validated_url:
                return validated_url, "ok"
            last_reason = reason
            continue

        last_reason = f"no_pdf_marker_status_{response.status_code}"

    return "", last_reason


def _resolve_pdf_url(identifier):
    mirrors = _get_configured_mirrors()
    timeout = _get_timeout()
    session = _build_session()
    errors = []

    for mirror in mirrors:
        pdf_url, reason = _try_identifier_with_mirror(session, mirror, identifier, timeout)
        if pdf_url:
            return pdf_url, mirror, errors
        errors.append(f"{mirror}:{reason}")

    return "", "", errors


def _get_crossref_metadata(doi):
    try:
        response = requests.get(
            f"https://api.crossref.org/works/{doi}",
            timeout=15,
            headers={"User-Agent": os.getenv("SCIHUB_USER_AGENT", DEFAULT_USER_AGENT)},
        )
        if response.status_code != 200:
            return {}

        payload = response.json().get("message", {})
        title = ""
        if payload.get("title"):
            title = payload["title"][0]

        year = ""
        for field in ("published-print", "published-online", "issued"):
            date_parts = payload.get(field, {}).get("date-parts", [])
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])
                break

        authors = []
        for item in payload.get("author", []):
            given = (item.get("given") or "").strip()
            family = (item.get("family") or "").strip()
            full = " ".join(part for part in [given, family] if part).strip()
            if full:
                authors.append(full)

        return {
            "title": title,
            "author": ", ".join(authors),
            "year": year,
        }
    except Exception as exc:
        LOGGER.debug("CrossRef metadata lookup failed for DOI %s: %s", doi, exc)
        return {}


def create_scihub_instance():
    """Create a SciHub instance with configured mirrors."""
    sh = SciHub()
    sh.timeout = int(max(_get_timeout(), 1))
    sh.available_base_url_list = _get_configured_mirrors()
    sh.current_base_url_index = 0
    return sh


def search_paper_by_doi(doi):
    """Search Sci-Hub by DOI and return PDF URL + metadata if found."""
    pdf_url, mirror, errors = _resolve_pdf_url(doi)
    if not pdf_url:
        error_msg = "; ".join(errors[:8]) if errors else "no_mirror_response"
        return {
            "doi": doi,
            "status": "not_found",
            "error": (
                "Failed to resolve PDF URL from configured mirrors. "
                f"Details: {error_msg}. "
                "If mirrors return Cloudflare challenge pages, set SCIHUB_PROXY or SCIHUB_COOKIE."
            ),
        }

    metadata = _get_crossref_metadata(doi)
    return {
        "doi": doi,
        "pdf_url": pdf_url,
        "status": "success",
        "mirror": mirror,
        "title": metadata.get("title", ""),
        "author": metadata.get("author", ""),
        "year": metadata.get("year", ""),
    }


def search_paper_by_title(title):
    """Search by title via CrossRef DOI lookup then Sci-Hub DOI resolution."""
    try:
        response = requests.get(
            f"https://api.crossref.org/works?query.title={title}&rows=1",
            timeout=15,
            headers={"User-Agent": os.getenv("SCIHUB_USER_AGENT", DEFAULT_USER_AGENT)},
        )
        if response.status_code == 200:
            data = response.json()
            items = data.get("message", {}).get("items", [])
            if items:
                doi = items[0].get("DOI")
                if doi:
                    return search_paper_by_doi(doi)
    except Exception as exc:
        LOGGER.debug("CrossRef title lookup failed for %r: %s", title, exc)

    return {
        "title": title,
        "status": "not_found",
    }


def search_papers_by_keyword(keyword, num_results=10):
    """Search keyword via CrossRef and resolve each DOI through Sci-Hub."""
    papers = []
    try:
        fetch_rows = min(max(int(num_results) * 4, int(num_results), 20), 100)
        response = requests.get(
            f"https://api.crossref.org/works?query={keyword}&rows={fetch_rows}",
            timeout=20,
            headers={"User-Agent": os.getenv("SCIHUB_USER_AGENT", DEFAULT_USER_AGENT)},
        )
        if response.status_code == 200:
            data = response.json()
            for item in data.get("message", {}).get("items", []):
                doi = item.get("DOI")
                if not doi:
                    continue
                title = ""
                if item.get("title"):
                    title = item["title"][0]

                year = ""
                for field in ("published-print", "published-online", "issued"):
                    date_parts = item.get(field, {}).get("date-parts", [])
                    if date_parts and date_parts[0]:
                        year = str(date_parts[0][0])
                        break

                authors = []
                for author in item.get("author", []):
                    given = (author.get("given") or "").strip()
                    family = (author.get("family") or "").strip()
                    full = " ".join(part for part in [given, family] if part).strip()
                    if full:
                        authors.append(full)

                base = {
                    "doi": doi,
                    "title": title,
                    "author": ", ".join(authors),
                    "year": year,
                    "status": "metadata_only",
                }

                resolved = search_paper_by_doi(doi)
                if resolved.get("status") == "success":
                    base.update(
                        {
                            "status": "success",
                            "pdf_url": resolved.get("pdf_url", ""),
                            "mirror": resolved.get("mirror", ""),
                        }
                    )
                else:
                    if resolved.get("error"):
                        base["error"] = resolved["error"]

                papers.append(base)
                if len(papers) >= num_results:
                    break
    except Exception as exc:
        LOGGER.debug("Keyword search failed for %r: %s", keyword, exc)

    return papers


def download_paper(pdf_url, output_path):
    """Download PDF from resolved Sci-Hub PDF URL."""
    session = _build_session()
    timeout = _get_timeout()
    resolved_output_path = _prepare_output_path(output_path, pdf_url)
    candidates = []

    if pdf_url:
        candidates.append(pdf_url)
        candidates.append(pdf_url.split("#", 1)[0])

    doi = _extract_doi_from_url(pdf_url)
    if doi:
        refreshed = search_paper_by_doi(doi)
        refreshed_url = refreshed.get("pdf_url", "")
        if refreshed_url:
            candidates.append(refreshed_url)
            candidates.append(refreshed_url.split("#", 1)[0])

    # If a non-PDF Sci-Hub page URL is provided, resolve from identifier/path.
    parsed = urlparse(pdf_url or "")
    if parsed.netloc and "sci-hub" in parsed.netloc.lower() and ".pdf" not in parsed.path.lower():
        identifier = parsed.path.strip("/")
        if identifier:
            resolved, _mirror, _errors = _resolve_pdf_url(unquote(identifier))
            if resolved:
                candidates.append(resolved)
                candidates.append(resolved.split("#", 1)[0])

    # Deduplicate while preserving order.
    deduped_candidates = []
    for candidate in candidates:
        normalized = (candidate or "").strip()
        if not normalized:
            continue
        if normalized not in deduped_candidates:
            deduped_candidates.append(normalized)

    errors = []
    try:
        for candidate in deduped_candidates:
            try:
                ok, reason = _download_candidate_to_file(session, candidate, resolved_output_path, timeout)
                if ok:
                    return {"success": True, "path": resolved_output_path, "source_url": candidate}
                errors.append(f"{candidate}:{reason}")
            except Exception as exc:
                errors.append(f"{candidate}:{type(exc).__name__}")
    except Exception as exc:
        errors.append(f"global:{type(exc).__name__}:{exc}")

    # Last-resort path: return a rich error with diagnosis.
    reason = "; ".join(errors[:6]) if errors else "no_candidate_urls"
    return {
        "success": False,
        "path": resolved_output_path,
        "error": (
            "Unable to download PDF from available URLs. "
            f"Details: {reason}. "
            "If host access is restricted in your runtime, download the returned pdf_url from a machine that can reach it."
        ),
    }

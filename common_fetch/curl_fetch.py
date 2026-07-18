"""cheap_pi WebHelper — curl leg.

This drives the project's pinned system ``curl`` binary directly via
``subprocess``. It is the cheap first leg the orchestrator tries before
escalating to the browser leg. For the two legs to be interchangeable at the
Python layer, this function returns the same ``FetchResult`` shape as
``BrowserFetch``: ``StatusCode``, ``StatusCodeText``, ``FinalURL``,
``ResponseHeaders``, ``ContentType``, ``Content``, and ``storageState``.

HTTP 4xx/5xx responses are valid fetch results, not tool errors. Transport
failures such as DNS/TLS/connect/timeout errors are returned as the outer
``err`` in the Go-style ``(result, err)`` tuple. Content classification is
web_helper's ``ContentClassify`` job, not this leg's.

The system curl path comes from ``CHEAP_PI_SYSTEM_CURL`` when set, otherwise it
falls back to ``/usr/bin/curl``.
"""

import json
import os
import subprocess
import tempfile
from typing import Optional

from config import CHROME_UA, ACCEPT_LANGUAGE, REFERER
from web_helper_tools.types import FetchResult, RequestBody, RequestHeaders, ResponseHeaders

# Same Chrome fingerprint the browser leg uses — sourced from the single config.py.
# The User-Agent is a default header here; caller headers override/extend these
# case-insensitively.
_DEFAULT_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept-Language": ACCEPT_LANGUAGE,
    "Referer": REFERER,
}


def _system_curl() -> str:
    return os.environ.get("CHEAP_PI_SYSTEM_CURL", "/usr/bin/curl")


def _normalize_headers(headers) -> list:
    """Accept a header mapping or a sequence of (name, value) pairs.

    Return a list of (str name, str value), dropping entries with a None name.
    """
    if not headers:
        return []
    items = headers.items() if hasattr(headers, "items") else headers
    out = []
    for k, v in items:
        if k is None:
            continue
        out.append((str(k), str(v)))
    return out


def _merge_headers(caller_headers) -> list:
    """Merge default Chrome headers with caller headers, case-insensitively.

    A caller-supplied "user-agent" replaces our default instead of duplicating
    it. Dict insertion order matches JS Map semantics: overriding an existing
    key keeps its original position.
    """
    merged = {}  # lowercased name -> (name, value)
    for k, v in _DEFAULT_HEADERS.items():
        merged[k.lower()] = (k, str(v))
    for k, v in caller_headers:
        merged[k.lower()] = (k, str(v))
    return list(merged.values())


def _content_type_of(pairs: ResponseHeaders) -> str:
    """Content-Type from a [[name, value], ...] pairs list (first match wins)."""
    for name, value in pairs:
        if str(name).lower() == "content-type":
            return value or ""
    return ""


def _final_status_code_text(dump_text: str) -> str:
    """
    _final_status_code_text

    Reason phrase from the final HTTP status line, if curl received one.
    For example: "HTTP/1.1 200 OK" -> "OK".
    HTTP/2 and HTTP/3 responses may not include a reason phrase, so return "".
    """
    status_line = ""
    for line in [ln.rstrip("\r") for ln in (dump_text or "").split("\n")]:
        if line.upper().startswith("HTTP/"):
            status_line = line.strip()

    parts = status_line.split(" ", 2)
    if len(parts) < 3:
        return ""
    return parts[2].strip()


def _final_header_pairs(dump_text: str) -> ResponseHeaders:
    """Parse the ``-D`` header dump.

    On redirects, it holds multiple header blocks; take the LAST block (the final
    response's headers), preserving order + duplicates. Returns [name, value] lists.
    """
    # Split on \r?\n without a regex dependency.
    lines = [ln.rstrip("\r") for ln in (dump_text or "").split("\n")]
    start = 0
    for i, line in enumerate(lines):
        if line.upper().startswith("HTTP/"):
            start = i + 1  # line after the last status line
    pairs = []
    for line in lines[start:]:
        if not line or not line.strip():
            break  # blank line ends the header block
        idx = line.find(":")
        if idx == -1:
            continue
        name = line[:idx].strip()
        value = line[idx + 1:].strip()
        if not name:
            continue
        pairs.append([name, value])
    return pairs


def CurlFetch(
    url: str,
    method: Optional[str] = None,
    request_body: Optional[RequestBody] = None,
    request_headers: Optional[RequestHeaders] = None,
    timeout_ms: int = 40000,
) -> tuple[FetchResult, Optional[Exception]]:
    """Fetch ``url`` by driving the system curl binary. NEVER raises.

    Returns ``(result, err)``. ``err`` is only for curl/tool failures; HTTP
    responses, including 4xx/5xx, are encoded in ``result`` with ``err=None``.
    Content classification is NOT done here.
    """
    result: FetchResult = {
        "StatusCode": None,
        "StatusCodeText": "",
        "FinalURL": url if isinstance(url, str) else "",
        "ResponseHeaders": [],
        "ContentType": "",
        "Content": "",
        "storageState": None,
    }

    if not url or not isinstance(url, str):
        return result, Exception('missing required "url"')

    method = str(method or "GET").upper()
    timeout = timeout_ms if (isinstance(timeout_ms, (int, float)) and timeout_ms > 0) else 40000
    caller_headers = _normalize_headers(request_headers)
    headers = _merge_headers(caller_headers)
    # Mirror the browser leg: body is only sent for non-GET methods.
    has_body = method != "GET" and request_body is not None

    headers_file = None
    body_file = None
    try:
        hf = tempfile.NamedTemporaryFile(prefix="cheap_pi_curl_", suffix=".hdr", delete=False)
        headers_file = hf.name
        hf.close()
        bf = tempfile.NamedTemporaryFile(prefix="cheap_pi_curl_", suffix=".body", delete=False)
        body_file = bf.name
        bf.close()

        args = [
            _system_curl(),
            "-sS",           # silent progress, but surface errors on stderr
            "-L",            # follow redirects
            "--compressed",  # accept + transparently decode gzip/br/deflate
            "--max-time", str(timeout / 1000),
            "-D", headers_file,  # dump response headers (all hops)
            "-o", body_file,     # write raw body here (never rendered)
            # NOTE: no -f/--fail — 4xx/5xx must come back as normal results.
            "-w", "%{http_code}\n%{url_effective}\n%{content_type}",
        ]
        if method != "GET":
            args += ["-X", method]
        if has_body:
            args += ["--data-binary", "@-"]  # read body from stdin, arbitrary/large safe
        for name, value in headers:
            args += ["-H", f"{name}: {value}"]
        args += ["--", url]  # -- so a url starting with '-' isn't parsed as an option

        stdin_bytes = None
        if has_body:
            b = request_body
            if isinstance(b, (bytes, bytearray)):
                stdin_bytes = bytes(b)
            elif isinstance(b, str):
                stdin_bytes = b.encode("utf-8")
            else:
                stdin_bytes = json.dumps(b, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        # curl's own --max-time bounds the request; the subprocess timeout is a
        # generous safety net well above it so it never fires in normal operation.
        proc = subprocess.run(
            args,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=(timeout / 1000) + 10,
        )

        # Transport failure: curl exit != 0 (DNS / TLS / connect / timeout).
        # 4xx/5xx are NOT here — without -f/--fail they exit 0.
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            message = stderr or f"curl exited {proc.returncode}"
            return result, Exception(message)

        writeout = (proc.stdout or b"").decode("utf-8", errors="replace").split("\n")
        http_code_str = writeout[0].strip() if len(writeout) > 0 else ""
        try:
            http_code = int(http_code_str)
        except ValueError:
            http_code = 0
        status_code = http_code if http_code > 0 else None
        url_effective = (writeout[1].strip() if len(writeout) > 1 else "") or url
        content_type_writeout = writeout[2].strip() if len(writeout) > 2 else ""

        dump_text = ""
        try:
            with open(headers_file, "r", encoding="utf-8", errors="replace") as f:
                dump_text = f.read()
        except OSError:
            pass
        response_headers: ResponseHeaders = _final_header_pairs(dump_text)

        content = ""
        try:
            # errors="replace" mirrors Buffer.toString('utf8') (invalid -> U+FFFD).
            with open(body_file, "rb") as f:
                content = f.read().decode("utf-8", errors="replace")
        except OSError:
            pass

        ct = _content_type_of(response_headers) or content_type_writeout

        result["StatusCode"] = status_code
        result["StatusCodeText"] = _final_status_code_text(dump_text)
        result["FinalURL"] = url_effective
        result["ResponseHeaders"] = response_headers
        result["ContentType"] = ct
        result["Content"] = content
        return result, None

    except FileNotFoundError as err:
        # curl binary missing at CHEAP_PI_SYSTEM_CURL.
        return result, SystemError(f"system curl not found: {err}")
    except subprocess.TimeoutExpired:
        return result, TimeoutError(f"curl timed out after {timeout / 1000 + 10:.0f}s")
    except Exception as err:  # never raise
        return result, err
    finally:
        for p in (headers_file, body_file):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass

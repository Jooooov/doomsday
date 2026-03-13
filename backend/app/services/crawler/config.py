"""
Crawler configuration — shared rate-limit, header, and retry settings.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ─── Default headers to mimic a regular browser visit ──────────────────────
_DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "DNT": "1",
}


@dataclass
class RetryPolicy:
    """
    Exponential-backoff retry policy for transient HTTP errors.

    Attributes
    ----------
    max_attempts:
        Total number of attempts (including the first one).
    backoff_base_seconds:
        Base sleep time in seconds; actual sleep = base * 2^attempt + jitter.
    jitter_max_seconds:
        Max random jitter added to each backoff interval.
    retryable_status_codes:
        HTTP codes that trigger a retry (e.g. 429, 503, 502, 500).
    """

    max_attempts: int = 3
    backoff_base_seconds: float = 2.0
    jitter_max_seconds: float = 1.0
    retryable_status_codes: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )

    def sleep_seconds(self, attempt: int) -> float:
        """Return sleep duration for the given attempt number (0-indexed)."""
        backoff = self.backoff_base_seconds * (2 ** attempt)
        jitter = random.uniform(0, self.jitter_max_seconds)  # noqa: S311
        return backoff + jitter


@dataclass
class CrawlerConfig:
    """
    Runtime configuration shared across all crawler pipeline stages.

    Attributes
    ----------
    request_timeout_seconds:
        Per-request HTTP timeout.
    rate_limit_delay_seconds:
        Minimum seconds to wait between consecutive requests to the same host.
    max_content_length_bytes:
        Maximum response body size to process (larger responses are skipped).
    save_html:
        When True, store the raw inner-HTML alongside content_text.
    headers:
        HTTP headers injected into every request.
    retry:
        Retry policy for transient failures.
    follow_redirects:
        Whether to follow HTTP 3xx redirects.
    verify_ssl:
        Whether to verify TLS certificates.
    proxy_url:
        Optional HTTP/HTTPS proxy URL.
    """

    request_timeout_seconds: float = 30.0
    rate_limit_delay_seconds: float = 1.5
    max_content_length_bytes: int = 5 * 1024 * 1024  # 5 MB
    save_html: bool = False
    headers: Dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_HEADERS))
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    follow_redirects: bool = True
    verify_ssl: bool = True
    proxy_url: Optional[str] = None

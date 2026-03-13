"""
Abstract base class for news data sources.

All concrete clients (NewsAPI, GDELT, …) must implement this interface so the
aggregator can treat every source uniformly.
"""
from __future__ import annotations

import abc
from typing import Any, List, Optional

from app.schemas.news import NormalizedArticle


class BaseNewsSource(abc.ABC):
    """
    Interface contract for a news data source.

    Sub-classes must implement:
      - ``fetch``       — retrieve raw articles and return normalised objects
      - ``normalize``   — convert a single raw provider dict to NormalizedArticle
      - ``health_check`` — return True when the upstream API is reachable
      - ``source_name`` — read-only string identifier for this provider
    """

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abc.abstractmethod
    def source_name(self) -> str:
        """Human-readable / machine-stable identifier, e.g. 'newsapi'."""

    @abc.abstractmethod
    async def fetch(
        self,
        query: str,
        country: Optional[str] = None,
        max_results: int = 100,
    ) -> List[NormalizedArticle]:
        """
        Fetch articles matching *query* and return a list of normalised articles.

        Parameters
        ----------
        query:
            Free-text search query forwarded to the provider.
        country:
            Optional ISO-3166-1 alpha-2 country code used for filtering or
            tagging articles (provider-dependent).
        max_results:
            Maximum number of articles to return.  The provider may return
            fewer if there are not enough matching results.
        """

    @abc.abstractmethod
    def normalize(self, raw: Any) -> NormalizedArticle:
        """
        Convert a single raw provider response dict into a NormalizedArticle.

        Parameters
        ----------
        raw:
            Provider-specific dict (e.g. a single element from the NewsAPI
            ``articles`` array or a GDELT artlist item).
        """

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """
        Probe the upstream API.

        Returns True if the API responds successfully, False otherwise.
        Never raises — callers expect a boolean.
        """

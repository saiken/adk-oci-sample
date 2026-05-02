from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import requests


def web_search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, Any]]:
  """Simple web search via DuckDuckGo HTML endpoint.

  Returns a list of {title, url, snippet}.
  """
  if not query or not query.strip():
    return []
  max_results = max(1, min(int(max_results), 10))

  url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
  res = requests.get(
      url,
      timeout=20,
      headers={
          "User-Agent": (
              "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/123.0.0.0 Safari/537.36"
          )
      },
  )
  res.raise_for_status()
  body = res.text

  link_re = re.compile(
      r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
      re.IGNORECASE | re.DOTALL,
  )

  results: list[dict[str, Any]] = []
  for match in list(link_re.finditer(body))[:max_results]:
    raw_href = html.unescape(match.group(1))
    title = _strip_tags(html.unescape(match.group(2))).strip()
    final_url = _unwrap_ddg_redirect(raw_href)

    snippet = ""
    tail = body[match.end() : match.end() + 5000]
    m2 = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', tail, re.I | re.S)
    if m2:
      snippet = _strip_tags(html.unescape(m2.group(1))).strip()

    results.append({"title": title, "url": final_url, "snippet": snippet})

  return results


def _strip_tags(s: str) -> str:
  return re.sub(r"<[^>]+>", "", s)


def _unwrap_ddg_redirect(url: str) -> str:
  try:
    parsed = urlparse(url)
  except ValueError:
    return url
  if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
    qs = parse_qs(parsed.query)
    uddg = qs.get("uddg", [None])[0]
    if uddg:
      return uddg
  return url


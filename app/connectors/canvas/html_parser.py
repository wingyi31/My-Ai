import re
from urllib.parse import (
    urljoin,
    urlparse,
    urlunsplit,
)

from bs4 import BeautifulSoup

#The parser removes query parameters before saving URLs so temporary Canvas verifier information is not printed or persisted
FILE_PATTERN = re.compile(r"/files/(\d+)")
ASSIGNMENT_PATTERN = re.compile(
    r"/assignments/(\d+)"
)
PAGE_PATTERN = re.compile(
    r"/pages/([^/?#]+)"
)


def _remove_query_and_fragment(url: str) -> str:
    parsed = urlparse(url)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "",
        )
    )


def _classify_link(
    url: str,
    base_url: str,
) -> tuple[str, str | None]:
    path = urlparse(url).path

    file_match = FILE_PATTERN.search(path)

    if file_match:
        return "canvas_file", file_match.group(1)

    assignment_match = ASSIGNMENT_PATTERN.search(
        path
    )

    if assignment_match:
        return (
            "canvas_assignment",
            assignment_match.group(1),
        )

    page_match = PAGE_PATTERN.search(path)

    if page_match:
        return "canvas_page", page_match.group(1)

    link_host = urlparse(url).netloc
    canvas_host = urlparse(base_url).netloc

    if link_host and link_host != canvas_host:
        return "external", None

    return "canvas_other", None


def parse_canvas_html(
    html: str,
    base_url: str,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    for unwanted in soup(["script", "style"]):
        unwanted.decompose()

    visible_text = " ".join(
        soup.stripped_strings
    )

    links: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.find_all("a"):
        raw_url = (
            anchor.get("data-api-endpoint")
            or anchor.get("href")
        )

        if not raw_url:
            continue

        absolute_url = urljoin(
            f"{base_url.rstrip('/')}/",
            raw_url,
        )

        safe_url = _remove_query_and_fragment(
            absolute_url
        )

        link_type, canvas_id = _classify_link(
            safe_url,
            base_url,
        )

        key = (
            link_type,
            canvas_id or safe_url,
        )

        if key in seen:
            continue

        seen.add(key)

        links.append(
            {
                "type": link_type,
                "canvas_id": canvas_id,
                "text": " ".join(
                    anchor.stripped_strings
                ),
                "url": safe_url,
            }
        )

    return {
        "text": visible_text,
        "links": links,
    }
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

import httpx

from hatena_translate_repost.models import BlogEntry

ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://www.w3.org/2007/app"
HATENA_NS = "http://www.hatena.ne.jp/info/xmlns#hatenablog"
NAMESPACES = {
    "atom": ATOM_NS,
    "app": APP_NS,
    "hatenablog": HATENA_NS,
}

ET.register_namespace("", ATOM_NS)
ET.register_namespace("app", APP_NS)
ET.register_namespace("hatenablog", HATENA_NS)


class HatenaBlogClient:
    def __init__(self, hatena_id: str, blog_id: str, api_key: str, timeout_seconds: float) -> None:
        self.hatena_id = hatena_id
        self.blog_id = blog_id
        self._http = httpx.Client(
            auth=(hatena_id, api_key),
            follow_redirects=True,
            headers={"Accept": "application/atom+xml, application/xml"},
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HatenaBlogClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @property
    def collection_url(self) -> str:
        return f"https://blog.hatena.ne.jp/{self.hatena_id}/{self.blog_id}/atom/entry"

    def member_url(self, entry_id: str) -> str:
        return f"{self.collection_url}/{entry_id}"

    def get_entry(self, entry_id: str) -> BlogEntry:
        response = self._http.get(self.member_url(entry_id))
        response.raise_for_status()
        return _parse_entry_xml(response.text)

    def list_entries(self, page_url: str | None = None) -> tuple[list[BlogEntry], str | None]:
        response = self._http.get(page_url or self.collection_url)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        entries = [_parse_entry_element(element) for element in root.findall("atom:entry", NAMESPACES)]
        next_link = root.find("atom:link[@rel='next']", NAMESPACES)
        next_url = next_link.attrib.get("href") if next_link is not None else None
        return entries, next_url

    def find_entry_by_url(self, article_url: str, max_pages: int) -> BlogEntry | None:
        normalized_target = article_url.rstrip("/")
        page_url: str | None = None

        for _ in range(max_pages):
            entries, page_url = self.list_entries(page_url)
            for entry in entries:
                if entry.alternate_url and entry.alternate_url.rstrip("/") == normalized_target:
                    return entry
            if page_url is None:
                break

        return None

    def fetch_entry_id_from_public_url(self, url: str) -> str | None:
        """公開記事URLのHTMLからはてなブログの数値エントリーIDを取得する。"""
        try:
            # 公開URLは認証不要。認証ヘッダーが干渉しないよう別クライアントで取得する。
            with httpx.Client(follow_redirects=True, timeout=self._http.timeout) as client:
                response = client.get(url)
            response.raise_for_status()
            match = re.search(r'id="entry-(\d+)"', response.text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def create_entry(self, entry: BlogEntry, draft: bool = False) -> BlogEntry:
        payload = _build_entry_xml(entry, self.hatena_id, draft)
        response = self._http.post(
            self.collection_url,
            content=payload,
            headers={"Content-Type": "application/atom+xml;type=entry;charset=utf-8"},
        )
        response.raise_for_status()
        return _parse_entry_xml(response.text)


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text


def _parse_entry_xml(xml_text: str) -> BlogEntry:
    return _parse_entry_element(ET.fromstring(xml_text))


def _parse_entry_element(element: ET.Element) -> BlogEntry:
    title = _text(element.find("atom:title", NAMESPACES))
    content_element = element.find("atom:content", NAMESPACES)
    content = _text(content_element)
    content_type = "text/plain"
    if content_element is not None:
        content_type = content_element.attrib.get("type", "text/plain")

    categories = [category.attrib["term"] for category in element.findall("atom:category", NAMESPACES) if "term" in category.attrib]
    edit_link = element.find("atom:link[@rel='edit']", NAMESPACES)
    alternate_link = element.find("atom:link[@rel='alternate']", NAMESPACES)
    draft_element = element.find("app:control/app:draft", NAMESPACES)
    published_element = element.find("atom:published", NAMESPACES)
    entry_id = _extract_entry_id(element, edit_link)

    return BlogEntry(
        entry_id=entry_id,
        title=title,
        content=content,
        content_type=content_type,
        categories=categories,
        edit_url=edit_link.attrib.get("href") if edit_link is not None else None,
        alternate_url=alternate_link.attrib.get("href") if alternate_link is not None else None,
        draft=_text(draft_element).strip().lower() == "yes",
        published=_text(published_element) or None,
    )


def _extract_entry_id(element: ET.Element, edit_link: ET.Element | None) -> str:
    if edit_link is not None:
        href = edit_link.attrib.get("href", "")
        if href:
            return href.rstrip("/").split("/")[-1]

    raw_id = _text(element.find("atom:id", NAMESPACES)).strip()
    if raw_id:
        return raw_id.rsplit("-", maxsplit=1)[-1]
    raise ValueError("Could not determine entry ID from Hatena response")


def _build_entry_xml(entry: BlogEntry, hatena_id: str, draft: bool) -> bytes:
    root = ET.Element(ET.QName(ATOM_NS, "entry"))
    ET.SubElement(root, ET.QName(ATOM_NS, "title")).text = entry.title

    author = ET.SubElement(root, ET.QName(ATOM_NS, "author"))
    ET.SubElement(author, ET.QName(ATOM_NS, "name")).text = hatena_id

    content = ET.SubElement(root, ET.QName(ATOM_NS, "content"), {"type": entry.content_type})
    content.text = entry.content

    for category_name in entry.categories:
        ET.SubElement(root, ET.QName(ATOM_NS, "category"), {"term": category_name})

    if entry.published:
        ET.SubElement(root, ET.QName(ATOM_NS, "published")).text = entry.published
        ET.SubElement(root, ET.QName(ATOM_NS, "updated")).text = entry.published

    control = ET.SubElement(root, ET.QName(APP_NS, "control"))
    ET.SubElement(control, ET.QName(APP_NS, "draft")).text = "yes" if draft else "no"

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
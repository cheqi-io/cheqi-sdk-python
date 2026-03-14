"""XML canonicalization helpers for receipt integrity verification."""

from __future__ import annotations

from lxml import etree


def canonicalize_xml(xml_str: str) -> str:
    """Canonicalize XML with formatting-only whitespace removed.

    This removes whitespace-only text nodes between elements, preserves
    meaningful text content, then applies exclusive XML C14N without comments.
    """
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml_str.encode("utf-8"), parser=parser)
    _remove_whitespace_only_text_nodes(root)
    canonical = etree.tostring(
        root,
        method="c14n",
        exclusive=True,
        with_comments=False,
    )
    return canonical.decode("utf-8")


def _remove_whitespace_only_text_nodes(element: etree._Element) -> None:
    if len(element) > 0 and element.text is not None and element.text.strip() == "":
        element.text = None

    for child in element:
        _remove_whitespace_only_text_nodes(child)
        if child.tail is not None and child.tail.strip() == "":
            child.tail = None

"""Safe source transforms shared by the deck server and standalone exporter."""

import re


TEMPLATE_START_RE = re.compile(r"<template\b", re.IGNORECASE)
SECTION_START_RE = re.compile(r"<section\b", re.IGNORECASE)
TEMPLATE_END_RE = re.compile(r"</template\s*>", re.IGNORECASE)


def _tag_end(document, start):
    """Return the end offset of an opening tag, ignoring > inside quoted attributes."""
    quote = None
    for offset in range(start, len(document)):
        char = document[offset]
        if quote:
            if char == quote:
                quote = None
        elif char in ('"', "'"):
            quote = char
        elif char == ">":
            return offset + 1
    raise ValueError("slide opening tag is not closed")


def _attributes(opening):
    """Yield (lower-name, value, span-start, span-end) for real start-tag attrs."""
    cursor = 1
    while cursor < len(opening) and not opening[cursor].isspace() and opening[cursor] not in ">/":
        cursor += 1
    while cursor < len(opening):
        span_start = cursor
        while cursor < len(opening) and opening[cursor].isspace():
            cursor += 1
        if cursor >= len(opening) or opening[cursor] in ">/":
            return
        name_start = cursor
        while cursor < len(opening) and not opening[cursor].isspace() and opening[cursor] not in "=/>":
            cursor += 1
        name = opening[name_start:cursor].lower()
        if not name:
            cursor += 1
            continue
        while cursor < len(opening) and opening[cursor].isspace():
            cursor += 1
        value = None
        if cursor < len(opening) and opening[cursor] == "=":
            cursor += 1
            while cursor < len(opening) and opening[cursor].isspace():
                cursor += 1
            if cursor < len(opening) and opening[cursor] in ('"', "'"):
                quote = opening[cursor]
                cursor += 1
                value_start = cursor
                while cursor < len(opening) and opening[cursor] != quote:
                    cursor += 1
                value = opening[value_start:cursor]
                if cursor < len(opening):
                    cursor += 1
            else:
                value_start = cursor
                while cursor < len(opening) and not opening[cursor].isspace() and opening[cursor] != ">":
                    cursor += 1
                value = opening[value_start:cursor]
        yield name, value, span_start, cursor


def _slides_template_bounds(document):
    for match in TEMPLATE_START_RE.finditer(document):
        opening_end = _tag_end(document, match.start())
        opening = document[match.start():opening_end]
        if any(name == "id" and value == "slides" for name, value, _start, _end in _attributes(opening)):
            closing = TEMPLATE_END_RE.search(document, opening_end)
            if not closing:
                raise ValueError("slides template is not closed")
            return opening_end, closing.start()
    return None


def slide_openings(document):
    bounds = _slides_template_bounds(document)
    if not bounds:
        return []
    content_start, content_end = bounds
    result = []
    for match in SECTION_START_RE.finditer(document, content_start, content_end):
        end = _tag_end(document, match.start())
        opening = document[match.start():end]
        classes = next((value or "" for name, value, _start, _end in _attributes(opening) if name == "class"), "")
        if "slide" in classes.split():
            result.append((match.start(), end, opening))
    return result


def _is_archived(opening):
    return any(name == "data-archived" and value == "1" for name, value, _start, _end in _attributes(opening))


def _with_archive_state(opening, archived):
    spans = [(start, end) for name, _value, start, end in _attributes(opening) if name == "data-archived"]
    clean = opening
    for start, end in reversed(spans):
        clean = clean[:start] + clean[end:]
    return clean[:-1] + ' data-archived="1">' if archived else clean


def archived_slide_pages(document):
    return [
        page
        for page, (_start, _end, opening) in enumerate(slide_openings(document), 1)
        if _is_archived(opening)
    ]


def set_archived_slides(document, archived_pages, dom_total):
    """Set the complete 1-based archived-page list and return updated source."""
    openings = slide_openings(document)
    if dom_total != len(openings):
        raise ValueError("源文件页数已变化，请刷新后再修改")
    archived = {int(page) for page in archived_pages}
    if any(page < 1 or page > len(openings) for page in archived):
        raise ValueError("归档页码不在源文件范围内")
    if len(archived) >= len(openings):
        raise ValueError("至少保留一张当前页面")

    updated = document
    for page, (start, end, opening) in reversed(list(enumerate(openings, 1))):
        updated = updated[:start] + _with_archive_state(opening, page in archived) + updated[end:]
    return updated


def strip_archived_slides(document):
    """Remove archived slide sections while leaving the surrounding template intact."""
    bounds = _slides_template_bounds(document)
    openings = slide_openings(document)
    if not bounds or not openings:
        return document, 0
    template_end = bounds[1]

    updated = document
    removed = 0
    for index in range(len(openings) - 1, -1, -1):
        start, _end, opening = openings[index]
        if not _is_archived(opening):
            continue
        stop = openings[index + 1][0] if index + 1 < len(openings) else template_end
        updated = updated[:start] + updated[stop:]
        removed += 1
    return updated, removed

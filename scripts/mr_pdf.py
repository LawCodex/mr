"""Two-column aware text extraction for Journal officiel PDFs (poppler pdftotext -bbox-layout).

pdftotext's own reading order sometimes interleaves the two columns of the JO; here every page
is re-assembled from word boxes: the gutter is located per page, lines crossing it with no gap
are treated as full-width, and each horizontal band between full-width lines is emitted as
left column then right column.
"""
import re
import subprocess

from lxml import etree

NS = "{http://www.w3.org/1999/xhtml}"


def _words_lines(page):
    lines = []
    for blk_i, blk in enumerate(page.iter(NS + "block")):
        for ln in blk.iter(NS + "line"):
            words = [(float(w.get("xMin")), float(w.get("xMax")), float(w.get("yMin")), float(w.get("yMax")), w.text or "")
                     for w in ln.iter(NS + "word")]
            if words:
                lines.append((blk_i, words))
    return lines


def _gutter(words, width):
    lo, hi = int(width * 0.38), int(width * 0.62)
    best, bx = None, width / 2
    for x in range(lo, hi + 1):
        c = sum(1 for w in words if w[0] - 1 <= x <= w[1] + 1)
        score = (c, abs(x - width / 2))
        if best is None or score < best:
            best, bx = score, x
    return bx, best[0]


def page_lines(page, top=68, bottom_margin=0):
    width = float(page.get("width"))
    height = float(page.get("height"))
    lines = _words_lines(page)
    allw = [w for _, ws in lines for w in ws if w[2] >= top and w[3] <= height - bottom_margin]
    if not allw:
        return []
    g, cover = _gutter(allw, width)
    two_col = cover <= max(2, len(allw) // 200)
    items = []  # (kind, y, x, blk, text) kind: F full, L left, R right
    for blk, ws in lines:
        ws = [w for w in ws if w[2] >= top and w[3] <= height - bottom_margin]
        if not ws:
            continue
        ws.sort(key=lambda w: w[0])
        y = min(w[2] for w in ws)
        if not two_col:
            items.append(("F", y, ws[0][0], blk, " ".join(w[4] for w in ws)))
            continue
        left = [w for w in ws if (w[0] + w[1]) / 2 < g]
        right = [w for w in ws if (w[0] + w[1]) / 2 >= g]
        crosses = any(w[0] < g < w[1] for w in ws)
        if left and right and crosses:
            items.append(("F", y, ws[0][0], blk, " ".join(w[4] for w in ws)))
            continue
        if left:
            items.append(("L", y, left[0][0], blk, " ".join(w[4] for w in left)))
        if right:
            items.append(("R", y, right[0][0], blk, " ".join(w[4] for w in right)))
    items.sort(key=lambda it: it[1])
    out = []
    band = []

    def flush_band():
        for side in ("L", "R"):
            col = [it for it in band if it[0] == side]
            col.sort(key=lambda it: (round(it[1], 0), it[2]))
            prev_blk = None
            prev_y = None
            for it in col:
                if prev_blk is not None and (it[3] != prev_blk or (prev_y is not None and it[1] - prev_y > 16)):
                    out.append("")
                out.append(it[4])
                prev_blk, prev_y = it[3], it[1]
            if col:
                out.append("")
        band.clear()

    for it in items:
        if it[0] == "F":
            flush_band()
            out.append(it[4])
            out.append("")
        else:
            band.append(it)
    flush_band()
    return out


def pdf_pages(path, top=68):
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", "-bbox-layout", path, "-"], capture_output=True)
    data = r.stdout
    if not data:
        return []
    try:
        root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
    except etree.XMLSyntaxError:
        return []
    pages = []
    for page in root.iter(NS + "page"):
        pages.append("\n".join(page_lines(page, top=top)))
    return pages

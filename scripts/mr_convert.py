#!/usr/bin/env python3
"""Convert Mauritanian sources (see mr_fetch.py) to LawCodex Markdown.

Usage: python mr_convert.py RAW_DIR OUT_REPO_DIR
"""
import collections
import datetime
import json
import os
import re
import sys
import unicodedata
import urllib.parse

from lxml import html as LH

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mr_pdf  # noqa: E402
import mr_text  # noqa: E402

RAW, OUT = sys.argv[1], sys.argv[2]
TODAY = datetime.date.today().isoformat()
LOG = open(os.path.join(RAW, "convert.log"), "w", encoding="utf-8")

AR_HEAD = [(r"^(الكتاب|الجزء)\s", 2), (r"^الباب\s", 3), (r"^الفصل\s", 4), (r"^الفرع\s", 5)]
FR_HEAD = [(r"^(LIVRE|Livre)\s", 2), (r"^(TITRE|Titre)\s", 3), (r"^(CHAPITRE|Chapitre)\s", 4), (r"^(Section|SECTION)\s", 5),
           (r"^(Sous-section|SOUS-SECTION)\s", 6)]
AR_ART = re.compile(r"^((?:ال)?مادة\s*(?:الأولى|\(?\s*\d+\s*\)?)(?:\s*(?:مكرر|جديدة|\(جديدة\)))?)\s*[:\-–\.]*\s*(.*)$")
FR_ART = re.compile(r"(?i)^((?:Article|Art)\.?\s*(?:premier|1er|unique|\d+(?:\s*(?:bis|ter|quater|nouveau|\(nouveau\)))?))\s*[\.:\-–—]*\s*(.*)$")


def yq(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def clean(s):
    s = unicodedata.normalize("NFKC", s).replace("\xa0", " ").replace("ـ", "")
    return re.sub(r"[ \t]+", " ", s).strip()


def to_md(lines, lang, reflow, blank_breaks=True):
    out, para = [], []
    heads = AR_HEAD if lang == "ar" else FR_HEAD
    art = AR_ART if lang == "ar" else FR_ART

    def flush():
        if para:
            out.extend([" ".join(para).strip(), ""])
            para.clear()

    pending_art = None
    for raw in lines:
        s = raw.strip()
        if not s or re.fullmatch(r"[\-–\s]*\d{1,4}[\-–\s]*", s):
            if not reflow or (not s and blank_breaks):
                flush()
            continue
        if pending_art is not None:
            # "المادة" / "102" / "(جديدة):" split over lines in the CC page
            s = pending_art + " " + s
            pending_art = None
        if lang == "ar" and re.fullmatch(r"(?:ال)?مادة", s):
            pending_art = s
            continue
        if len(s) < 120:
            lvl = next((l for rx, l in heads if re.match(rx, s)), None)
            if lvl:
                flush()
                out.extend(["#" * lvl + " " + s, ""])
                continue
        m = art.match(s)
        if m and len(m.group(1)) < 40:
            flush()
            out.extend(["###### " + re.sub(r"\s+", " ", m.group(1)).strip(), ""])
            rest = m.group(2).strip().lstrip(":").strip()
            if rest:
                para.append(rest)
            continue
        if reflow:
            if para and (re.search(r"[\.:;؛]$", para[-1]) or re.match(r"^[\-–•\*]|^\d+[\.\)°]\s|^[a-z]\)\s", s)):
                flush()
            para.append(s)
        else:
            para.append(s)
            flush()
    flush()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def html_lines(frag):
    el = LH.fromstring("<div>" + frag + "</div>")
    for br in el.iter("br"):
        br.tail = "\n" + (br.tail or "")
    for p in el.iter("p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
        p.tail = "\n" + (p.tail or "")
    return [clean(x) for x in el.text_content().split("\n")]


def main():
    counts = collections.Counter()
    for p in json.load(open(os.path.join(RAW, "cc_posts.json"), encoding="utf-8")):
        title = clean(LH.fromstring("<div>" + p["title"]["rendered"] + "</div>").text_content())
        lines = [l for l in html_lines(p["content"]["rendered"]) if l and l != "تنزيل" and not re.fullmatch(r"ـ+", l)]
        if sum(len(l) for l in lines) < 1000:
            print("SHORT", p["link"], title, file=LOG)
            continue
        if p["id"] == 465:
            fn = os.path.join(OUT, "ar", "constitution", "constitution-1991.md")
            fm = ["title: " + yq(title), 'identifier: "Constitution du 20 juillet 1991 (ordonnance n° 91-022), révisée"',
                  "type: constitution", "jurisdiction: mr", "language: ar", "date: 1991-07-20", "last_amended: 2017-08-15",
                  "consolidated: true", "status: in_force"]
            typ = "constitution"
        else:
            m = re.search(r"رقم\s*([\d\-]+)", title)
            ident = m.group(1) if m else str(p["id"])
            fn = os.path.join(OUT, "ar", "organic-laws", "organic-law-%s.md" % re.sub(r"[^0-9]+", "-", ident).strip("-"))
            fm = ["title: " + yq(title), "identifier: " + yq(ident), "type: organic_law", "jurisdiction: mr",
                  "language: ar", "status: unknown"]
            typ = "organic_law"
        fm += ["source: " + yq(p["link"]), "publisher: \"Conseil constitutionnel de Mauritanie\"", "retrieved: " + TODAY]
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w", encoding="utf-8") as f:
            f.write("---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + to_md(lines, "ar", False))
        counts[("ar", typ)] += 1
    man = os.path.join(RAW, "manifest.jsonl")
    if os.path.exists(man):
        for line in open(man, encoding="utf-8"):
            d = json.loads(line)
            path = os.path.join(RAW, "dl", d["file"])
            raw_pages = mr_pdf.pdf_pages(path, top=30)
            text = "\n".join(raw_pages)
            ar_share = len(mr_text.AR.findall(text)) / max(1, len(re.findall(r"\w", text)))
            lang = "ar" if ar_share > 0.3 else "fr"
            if lang == "ar":
                lines = mr_text.pdf_lines(path, arabic=True)
                ok, why = mr_text.acceptable([l for l in lines if l.strip()])
                if not ok:
                    print("SKIP quality", why, d["key"], file=LOG)
                    counts["skipped"] += 1
                    continue
            else:
                lines = []
                for pg in raw_pages:
                    lines.extend(pg.split("\n"))
                    lines.append("")
                words = re.findall(r"[A-Za-zÀ-ÿ]+", text)
                share = sum(1 for w in words if w.lower() in ("de", "la", "le", "et", "les", "des", "du", "à", "en", "par", "au")) / max(1, len(words))
                if len(words) < 200 or share < 0.12:
                    print("SKIP quality fr (scanned or garbled)", round(share, 3), len(words), d["key"], file=LOG)
                    counts["skipped"] += 1
                    continue
            name = d["key"][:-4]
            m = re.search(r"(code|loi)-(\d{4})(?:-(\d+))?-?(.*)", name)
            slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"^mauritanie-", "", name.lower())).strip("-")
            nonempty = [l.strip() for l in lines if l.strip()]
            ti = next((i for i, l in enumerate(nonempty[:60]) if re.search(r"(?i)^(loi|ordonnance|مدونة|قانون)\s*n", l)
                       and re.search(r"(?i)portant|relative|code|instituant|abrogeant", " ".join(nonempty[i:i + 3]))), None)
            if ti is None:
                ti = next((i for i, l in enumerate(nonempty[:60]) if re.search(r"(?i)^(code|loi|ordonnance)", l)), 0)
            parts = [nonempty[ti]]
            for l in nonempty[ti + 1:ti + 4]:
                if parts[-1].rstrip().endswith((".", ";")) or re.match(r"(?i)^(l.assembl|le pr[ée]sident|vu |titre|chapitre|article|journal)", l):
                    break
                parts.append(l)
            title = re.sub(r"\s+", " ", " ".join(parts)).strip()
            if lang == "fr" and "code" in name.lower() and not re.search(r"(?i)code", title) and (
                    re.search(r"(?i)ratification|journal officiel", title) or not re.match(r"(?i)^(loi|ordonnance)", title)):
                # the PDF is a whole Journal officiel issue: keep only the text enacting the code
                flat = [l.strip() for l in lines]
                st = next((i for i in range(len(flat)) if re.match(r"(?i)^(loi|ordonnance)\s*n", flat[i])
                           and re.search(r"(?i)portant\s+code|code\s+(de|des|du)", " ".join(flat[i:i + 4]))), None)
                if st is None:
                    print("SKIP code heading not found in JO issue", d["key"], file=LOG)
                    counts["skipped"] += 1
                    continue
                en = next((j for j in range(st + 30, len(flat)) if re.match(r"(?i)^(loi|d[ée]cret|ordonnance|arr[êe]t[ée]|d[ée]cision)\s*n\s*°", flat[j])), len(flat))
                lines = flat[st:en]
                nonempty = [l for l in lines if l]
                parts = [nonempty[0]]
                for l in nonempty[1:4]:
                    if parts[-1].endswith((".", ";")) or re.match(r"(?i)^(l.assembl|le pr[ée]sident|vu |titre|chapitre|article|journal)", l):
                        break
                    parts.append(l)
                title = re.sub(r"\s+", " ", " ".join(parts)).strip()
            typ = "code" if "code" in name.lower() else "law"
            sub = "codes" if typ == "code" else ("lois" if lang == "fr" else "laws")
            fn = os.path.join(OUT, lang, sub, slug + ".md")
            fm = ["title: " + yq(clean(title)), "identifier: " + yq(urllib.parse.unquote(d["original"].rsplit("/", 1)[-1])),
                  "type: " + typ, "jurisdiction: mr", "language: " + lang]
            if m:
                fm.append("year: %s" % m.group(2))
            fm += ["status: unknown", "source: " + yq(urllib.parse.unquote(d["original"])),
                   "archived_source: " + yq(d["wayback"]),
                   "archived: %s-%s-%s" % (d["timestamp"][:4], d["timestamp"][4:6], d["timestamp"][6:8]),
                   "retrieved: " + TODAY]
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            with open(fn, "w", encoding="utf-8") as f:
                f.write("---\n" + "\n".join(fm) + "\n---\n\n# " + clean(title) + "\n\n" + to_md(lines, lang, True))
            counts[(lang, typ)] += 1
    jo_laws(counts)
    for k, v in sorted(counts.items(), key=str):
        print(k, v)


HEAD_RX = re.compile(r"(?i)^(loi|ordonnance)(\s+(organique|constitutionnelle|constitutionnelle\s+r[ée]f[ée]rendaire))?\s*n\s*[°o]\s*(\d{2,4})\s*[-–\.]\s*(\d{2,4})")


def jo_laws(counts):
    """Laws and ordinances cut out of archived French Journal officiel issues."""
    man = os.path.join(RAW, "jo_manifest.jsonl")
    if not os.path.exists(man):
        return
    seen = set()
    for line in open(man, encoding="utf-8"):
        d = json.loads(line)
        path = os.path.join(RAW, "jo", d["file"])
        pages = mr_pdf.pdf_pages(path, top=40)
        L = [l.strip() for pg in pages for l in pg.split("\n")]
        text = "\n".join(L)
        if len(re.findall(r"[A-Za-zÀ-ÿ]+", text)) < 500:
            print("JO scanned/empty", d["key"], file=LOG)
            continue
        heads = [i for i, l in enumerate(L) if re.match(r"^I\s*[-–]?\s*LOIS", l)]
        ends = [i for i, l in enumerate(L) if re.match(r"^II\s*[-–]?\s*D[ÉE]CRETS", l)]
        if len(heads) < 2:
            continue
        st = heads[1]
        en = next((e for e in ends if e > st), len(L))
        sec = L[st + 1:en]
        idx = [i for i, l in enumerate(sec) if HEAD_RX.match(l) and "…" not in l and not re.search(r"\.{4,}", l)]
        issue_m = re.search(r"(\d{4})", d["key"])
        for k, i in enumerate(idx):
            j = idx[k + 1] if k + 1 < len(idx) else len(sec)
            chunk = sec[i:j]
            m = HEAD_RX.match(chunk[0])
            kind = m.group(1).lower() + ("-" + m.group(3).lower().split()[0] if m.group(3) else "")
            a, b = m.group(4), m.group(5)
            year, num = (a, b) if len(a) == 4 else (b, a) if len(b) == 4 else (a, b)
            if len(year) != 4:
                continue
            key = (kind, year, num.lstrip("0") or "0")
            if key in seen or sum(len(x) for x in chunk) < 200:
                continue
            seen.add(key)
            parts = [chunk[0]]
            last = 0
            for n_, l in enumerate(chunk[1:5], start=1):
                if not l:
                    if len(parts) > 1:
                        break
                    continue
                if re.match(r"(?i)^(l.assembl|le pr[ée]sident|le parlement|le s[ée]nat|vu |titre|chapitre|article)", l):
                    break
                parts.append(l)
                last = n_
            title = re.sub(r"\s+", " ", " ".join(parts)).strip()
            typ = {"loi": "law", "ordonnance": "ordinance", "loi-organique": "organic_law",
                   "loi-constitutionnelle": "constitutional_law"}.get(kind, "law")
            sub = {"law": "lois", "ordinance": "ordonnances", "organic_law": "lois-organiques",
                   "constitutional_law": "lois-constitutionnelles"}[typ]
            fn = os.path.join(OUT, "fr", sub, year, "%s-%s-%s.md" % (kind, year, num))
            fm = ["title: " + yq(title), "identifier: " + yq("%s n° %s-%s" % (kind.replace("-", " ").capitalize(), year, num)),
                  "type: " + typ, "jurisdiction: mr", "language: fr", "year: %s" % year, "status: unknown",
                  "official_journal: " + yq("Journal officiel de la République Islamique de Mauritanie n° %s" % (issue_m.group(1) if issue_m else d["key"])),
                  "source: " + yq(urllib.parse.unquote(d["original"])), "archived_source: " + yq(d["wayback"]),
                  "archived: %s-%s-%s" % (d["timestamp"][:4], d["timestamp"][4:6], d["timestamp"][6:8]),
                  "retrieved: " + TODAY, "note: \"Text as published in the Journal officiel (not consolidated).\""]
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            with open(fn, "w", encoding="utf-8") as f:
                f.write("---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + to_md(chunk[last + 1:], "fr", True, blank_breaks=False))
            counts[("fr", "jo_" + typ)] += 1


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Regenerate README.md for the Mauritania repository. Usage: python mr_readme.py REPO_DIR"""
import collections
import datetime
import os
import sys

REPO = sys.argv[1]
counts = collections.Counter()
years = collections.defaultdict(set)
for lang in ("ar", "fr"):
    base = os.path.join(REPO, lang)
    for root, _, files in os.walk(base):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(root, base).split(os.sep)
                counts[(lang, rel[0])] += 1
                if len(rel) > 1:
                    years[(lang, rel[0])].add(rel[1])
rows = "\n".join("| `%s/%s/` | %d | %s |" % (l, c, n, ("%s–%s" % (min(years[(l, c)]), max(years[(l, c)]))) if years[(l, c)] else "")
                 for (l, c), n in sorted(counts.items()))
total = sum(counts.values())
today = datetime.date.today().isoformat()

README = f"""# Mauritania (MR) — legislation as Markdown

Part of [LawCodex](https://github.com/LawCodex): the legislation of every country as plain Markdown in git.

The Constitution of the Islamic Republic of Mauritania (Arabic, consolidated), consolidated codes and laws
in **French**, and laws/ordinances published in the French edition of the *Journal officiel de la République
Islamique de Mauritanie* (2017–2026).

**Total: {total} texts** (retrieved {today}).

| Directory | Files | Years |
|---|---|---|
{rows}

## Structure

```
ar/constitution/constitution-1991.md          Constitution of 20 July 1991, as revised in 2006, 2012 and 2017
ar/organic-laws/organic-law-92-04.md          ordonnance n° 92-04 (organic law on the Constitutional Council)
fr/codes/code-<year>-<name>.md                codes (as published by the SGG)
fr/lois/<year>/loi-<year>-<number>.md         laws cut out of Journal officiel issues
fr/lois-organiques/…, fr/ordonnances/…, fr/lois-constitutionnelles/…
```

Headings: LIVRE `##`, TITRE `###`, CHAPITRE `####`, Section `#####`; articles `######`.
Laws are texts as originally published in the Journal officiel (not consolidated); `status` is `unknown`
except for the Constitution.

## Sources

* **Conseil constitutionnel** (conseil-constitutionnel.mr), category «الدستور» and «القوانين والنظم», read
  through the site's public WordPress REST API: the Arabic Constitution consolidated with the constitutional
  laws of 2006, 2012 and 2017, and the organic law on the Constitutional Council.
* **Ministère Secrétariat Général du Gouvernement** (msgg.gov.mr): «codes consolidés» PDFs and the French
  Journal officiel issues. **msgg.gov.mr's robots.txt disallows all crawling (`Disallow: /`)**, so the live site
  was not accessed: only **Internet Archive captures** of its documents were used (each file records the
  original URL and the capture). For the Journal officiel, section «I – LOIS & ORDONNANCES» of each archived
  issue is cut into one file per law/ordinance (`scripts/mr_convert.py:jo_laws`).

## Not covered / known gaps

* Only Journal officiel issues captured by the Internet Archive (from about 2017) are covered, and only the
  French edition; laws before 2017 are mostly missing.
* Codes whose archived PDF is a scan (environment 2000, personal status 2001, livestock 2004, water 2005,
  forestry 2007) were skipped (no OCR).
* No French text of the Constitution was found in a usable form (the SGG's `upload/Constitution.pdf` was not
  archived); the Arabic consolidated text of the Constitutional Council is published.
* Arabic Journal officiel issues and Arabic versions of the codes were not processed.
* Decrees, arrêtés and decisions (section II of the Journal officiel) are out of scope.

## Licence

Laws and official texts are public documents of the Mauritanian State, published in the Journal officiel. The Markdown conversion is published under CC0.

## Regenerate

```
python scripts/mr_fetch.py ../_raw/mr cc msgg jo
python scripts/mr_convert.py ../_raw/mr .
python scripts/mr_readme.py .
```
Requires Python 3 with `requests`, `lxml`, `pypdf`, and poppler-utils (`pdftotext`).
"""
open(os.path.join(REPO, "README.md"), "w", encoding="utf-8").write(README)
print(total)

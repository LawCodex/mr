#!/usr/bin/env python3
"""Fetch Mauritanian legislation.

1. Conseil constitutionnel (conseil-constitutionnel.mr): consolidated Constitution (Arabic) and the
   organic texts in category "القوانين والنظم", via the site's public WordPress REST API.
2. Ministère Secrétariat Général du Gouvernement (msgg.gov.mr): consolidated codes ("codes consolidés")
   and law PDFs. msgg.gov.mr's robots.txt disallows all crawling ("Disallow: /"), so the live site is NOT
   accessed; only Internet Archive (Wayback Machine) captures of its documents are used.

Usage: python mr_fetch.py RAW_DIR [cc] [msgg]
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse

import requests

UA = "LawCodex/1.0 (+https://github.com/LawCodex)"
RAW = sys.argv[1]
DL = os.path.join(RAW, "dl")
os.makedirs(DL, exist_ok=True)
S = requests.Session()
S.headers["User-Agent"] = UA
CC = "https://conseil-constitutionnel.mr/?rest_route=/wp/v2/"


def get(url, delay=1.5, **kw):
    for i in range(10):
        try:
            r = S.get(url, timeout=180, **kw)
            time.sleep(delay)
            if r.status_code == 200:
                return r
            if r.status_code in (400, 403, 404):
                return None
        except requests.RequestException as e:
            print("retry", str(e)[-80:], flush=True)
        time.sleep(min(10 * (i + 1), 120))
    return None


def cc():
    out = os.path.join(RAW, "cc_posts.json")
    posts = []
    for cat in (5, 13):
        r = get(CC + "posts", params={"categories": cat, "per_page": 50,
                                      "_fields": "id,date,modified,link,title,content"})
        if r is not None:
            posts += r.json()
    json.dump(posts, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("cc posts", len(posts), flush=True)


def msgg():
    man_path = os.path.join(RAW, "manifest.jsonl")
    done = set()
    if os.path.exists(man_path):
        done = {json.loads(x)["key"] for x in open(man_path, encoding="utf-8")}
    caps = {}
    for pat in ("msgg.gov.mr/codes/", "www.msgg.gov.mr/codes/", "msgg.gov.mr/upload/", "msgg.gov.mr/sites/default/files/"):
        r = get("https://web.archive.org/cdx/search/cdx", params={
            "url": pat, "matchType": "prefix", "fl": "original,timestamp", "filter": "statuscode:200"})
        for line in (r.text.splitlines() if r is not None else []):
            orig, ts = line.split(" ")
            base = urllib.parse.unquote(orig.split("?")[0]).rstrip("/")
            name = base.rsplit("/", 1)[-1]
            if not name.lower().endswith(".pdf"):
                continue
            if not re.search(r"(?i)code|constitution|^loi|ordonnance", name):
                continue
            caps.setdefault(name.lower(), []).append((ts, orig))
    man = open(man_path, "a", encoding="utf-8")
    for name, cl in sorted(caps.items()):
        if name in done:
            continue
        for ts, orig in sorted(set(cl), reverse=True)[:5]:
            r = get("https://web.archive.org/web/%sid_/%s" % (ts, orig), delay=2)
            if r is None or r.content[:5] != b"%PDF-":
                continue
            if "truncated" in r.headers.get("warning", ""):
                continue
            fn = hashlib.sha1(name.encode()).hexdigest()[:16] + ".pdf"
            open(os.path.join(DL, fn), "wb").write(r.content)
            man.write(json.dumps({"key": name, "file": fn, "original": orig.split("?")[0],
                                  "wayback": "https://web.archive.org/web/%s/%s" % (ts, orig),
                                  "timestamp": ts}, ensure_ascii=False) + "\n")
            man.flush()
            print("got", name, flush=True)
            break


def jo():
    """French Journal officiel issues archived from msgg.gov.mr."""
    out_dir = os.path.join(RAW, "jo")
    os.makedirs(out_dir, exist_ok=True)
    man_path = os.path.join(RAW, "jo_manifest.jsonl")
    done = set()
    if os.path.exists(man_path):
        done = {json.loads(x)["key"] for x in open(man_path, encoding="utf-8")}
    caps = {}
    for pat in ("msgg.gov.mr/sites/default/files/", "msgg.gov.mr/JO/", "msgg.gov.mr/uploads/", "www.msgg.gov.mr/sites/default/files/"):
        r = get("https://web.archive.org/cdx/search/cdx", params={
            "url": pat, "matchType": "prefix", "fl": "original,timestamp", "filter": "statuscode:200"})
        for line in (r.text.splitlines() if r is not None else []):
            orig, ts = line.split(" ")
            name = urllib.parse.unquote(orig.split("?")[0]).rstrip("/").rsplit("/", 1)[-1]
            m = re.match(r"(?i)^j\.?o\.?[\s\-]*(\d{4})\s*(bis\s*)?([AF])[\s\-]*du[\s\-]*([\d\.]+)", name)
            m2 = re.match(r"(?i)^mauritanie-jo-(\d{4})-(\d{4})\.pdf", name)
            if m and m.group(3).upper() == "F":
                key = "jo-%s%s" % (m.group(1), "bis" if m.group(2) else "")
            elif m2:
                key = "jo-%s" % m2.group(2)
            else:
                continue
            caps.setdefault(key, []).append((ts, orig))
    print("jo issues", len(caps), flush=True)
    man = open(man_path, "a", encoding="utf-8")
    for key, cl in sorted(caps.items()):
        if key in done:
            continue
        for ts, orig in sorted(set(cl), reverse=True)[:4]:
            r = get("https://web.archive.org/web/%sid_/%s" % (ts, orig), delay=2)
            if r is None or r.content[:5] != b"%PDF-" or "truncated" in r.headers.get("warning", ""):
                continue
            fn = key + ".pdf"
            open(os.path.join(out_dir, fn), "wb").write(r.content)
            man.write(json.dumps({"key": key, "file": fn, "original": orig.split("?")[0],
                                  "wayback": "https://web.archive.org/web/%s/%s" % (ts, orig), "timestamp": ts},
                                 ensure_ascii=False) + "\n")
            man.flush()
            print("got", key, flush=True)
            break


if __name__ == "__main__":
    for st in sys.argv[2:] or ["cc", "msgg"]:
        globals()[st]()

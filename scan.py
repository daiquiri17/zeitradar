#!/usr/bin/env python3
"""ZEIT-Radar: scannt einmal täglich zeit.de, findet neue Artikel und
schlüsselt sie nach ZEIT ONLINE und DIE ZEIT (Print) auf.

Nur Python-Standardbibliothek, keine Installation nötig.
Erzeugt: data/articles.json (Gedächtnis) und docs/index.html (Webseite).
"""
import datetime as dt
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "articles.json"
OUT_FILE = ROOT / "docs" / "index.html"
TZ = ZoneInfo("Europe/Berlin")

RSS_SOURCES = ["https://newsfeed.zeit.de/index"]   # Feed der Startseite
HTML_SOURCES = ["https://www.zeit.de/index"]        # Startseite selbst
SHOW_DAYS = 30        # so viele Tage zeigt die Webseite
FORGET_DAYS = 365     # danach wird ein Artikel aus dem Gedächtnis gelöscht
USER_AGENT = "Mozilla/5.0 (compatible; ZEIT-Radar/1.0; private Nutzung)"

# DIE ZEIT (Print): /2026/40/slug  oder  /zeit-magazin/2026/40/slug
PRINT_RE = re.compile(
    r"^/(?:(?P<section>[a-z0-9-]+)/)?(?P<year>\d{4})/(?P<issue>\d{1,2})/(?P<slug>[a-z0-9-]+)$")
# ZEIT ONLINE: /politik/deutschland/2026-09/slug
ONLINE_RE = re.compile(
    r"^/(?P<section>[a-z0-9-]+(?:/[a-z0-9-]+)*)/(?P<year>\d{4})-(?P<month>\d{2})/(?P<slug>[a-z0-9-]+)$")

SKIP_SECTIONS = {"video", "thema", "serie", "autoren", "angebote", "zustimmung", "suche",
                 "administratives", "hilfe", "impressum", "abo", "newsletter", "index"}
SECTION_NAMES = {
    "zeit-magazin": "ZEITmagazin", "campus": "ZEIT Campus", "zett": "ze.tt",
    "wissen": "Wissen", "politik": "Politik", "wirtschaft": "Wirtschaft",
    "gesellschaft": "Gesellschaft", "kultur": "Kultur", "digital": "Digital",
    "sport": "Sport", "arbeit": "Arbeit", "gesundheit": "Gesundheit",
    "entdecken": "Entdecken", "mobilitaet": "Mobilität", "hamburg": "Hamburg",
    "news": "Nachrichten", "green": "Green", "podcasts": "Podcasts",
}
TITLE_NOISE = re.compile(r"Z\+\s*\(abopflichtiger Inhalt\)|abopflichtiger Inhalt|\bZ\+", re.I)


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def section_name(slug):
    return SECTION_NAMES.get(slug, slug.replace("-", " ").title()) if slug else ""


def normalize(href):
    """Gibt den bereinigten Pfad eines zeit.de-Links zurück (oder None)."""
    u = urlsplit(urljoin("https://www.zeit.de/", (href or "").strip()))
    if u.netloc not in ("www.zeit.de", "zeit.de"):
        return None
    path = u.path.rstrip("/")
    path = re.sub(r"/(komplettansicht|seite-\d+)$", "", path)
    return path or None


def classify(path):
    m = PRINT_RE.match(path)
    if m:
        sec = m["section"]
        if sec in SKIP_SECTIONS:
            return None
        return {"redaktion": "zeit", "ressort": section_name(sec),
                "ausgabe": f"{int(m['issue'])}/{m['year']}"}
    m = ONLINE_RE.match(path)
    if m:
        first = m["section"].split("/")[0]
        if first in SKIP_SECTIONS:
            return None
        return {"redaktion": "online", "ressort": section_name(first), "ausgabe": ""}
    return None


def fetch(url):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"})
    with urlopen(req, timeout=30) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), r.read().decode(charset, "replace")


class LinkParser(HTMLParser):
    """Sammelt Links der Startseite und merkt sich Z+-Markierungen der Teaser."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self._a, self._articles = [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        blob = " ".join(str(v) for v in a.values() if v).lower()
        zp = "zplus" in blob or "z-plus" in blob
        if tag == "article":
            self._articles.append({"zplus": zp, "idx": []})
        elif zp and self._articles:
            self._articles[-1]["zplus"] = True
        if tag == "a" and a.get("href"):
            self._a = {"href": a["href"], "attr": clean(a.get("title")), "text": [], "zplus": zp}

    def handle_data(self, data):
        if self._a is not None:
            self._a["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            raw = clean(" ".join(self._a["text"]))
            if "abopflichtig" in raw.lower():
                self._a["zplus"] = True
            self._a["text"] = clean(TITLE_NOISE.sub("", raw))
            self.links.append(self._a)
            if self._articles:
                self._articles[-1]["idx"].append(len(self.links) - 1)
            self._a = None
        elif tag == "article" and self._articles:
            art = self._articles.pop()
            if art["zplus"]:
                for i in art["idx"]:
                    self.links[i]["zplus"] = True
            if self._articles:
                self._articles[-1]["idx"].extend(art["idx"])


def candidates_from_rss(body):
    root = ET.fromstring(body)
    for item in root.iter("item"):
        yield item.findtext("link"), clean(item.findtext("title")), False, 3


def candidates_from_html(body):
    p = LinkParser()
    p.feed(body)
    for link in p.links:
        if link["attr"]:
            yield link["href"], link["attr"], link["zplus"], 2
        text = link["text"]
        if re.match(r"^\d+\s+Kommentar", text):
            text = ""
        yield link["href"], text, link["zplus"], 1


def scan():
    found, errors = {}, []

    def add(href, title, zplus, prio):
        path = normalize(href)
        info = classify(path) if path else None
        if not info:
            return
        f = found.setdefault(path, {**info, "url": "https://www.zeit.de" + path,
                                    "title": "", "zplus": False, "_prio": 0})
        f["zplus"] = f["zplus"] or zplus
        title = title[:250]
        if title and (prio > f["_prio"] or (prio == f["_prio"] and len(title) > len(f["title"]))):
            f["title"], f["_prio"] = title, prio

    for url in RSS_SOURCES:
        try:
            _, body = fetch(url)
            for c in candidates_from_rss(body):
                add(*c)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Feed {url}: {e}")
    for url in HTML_SOURCES:
        try:
            final, body = fetch(url)
            if "zustimmung" in final:
                errors.append(f"{url}: Zustimmungsseite statt Startseite erhalten, nur Feed genutzt")
                continue
            for c in candidates_from_html(body):
                add(*c)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Startseite {url}: {e}")
    for f in found.values():
        f.pop("_prio")
        if not f["title"]:
            f["title"] = f["url"].rsplit("/", 1)[-1].replace("-", " ").capitalize()
    return found, errors


def load_state():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text("utf-8"))
    return {"articles": {}, "scans": []}


def main():
    now = dt.datetime.now(TZ)
    today = now.date().isoformat()
    state = load_state()
    found, errors = scan()
    if not found:
        print("Keine Artikel gefunden.", *errors, sep="\n", file=sys.stderr)
        sys.exit(1)

    first_run = not state["articles"]
    new = 0
    for path, f in found.items():
        a = state["articles"].get(path)
        if a is None:
            state["articles"][path] = {**f, "first_seen": today,
                                       "first_seen_ts": now.isoformat(timespec="minutes"),
                                       "last_seen": today}
            new += 1
        else:
            a["last_seen"] = today
            a["zplus"] = a.get("zplus") or f["zplus"]
            if f["title"] and len(f["title"]) > len(a.get("title", "")) and a.get("title", "") in f["title"]:
                a["title"] = f["title"]

    cutoff = (now.date() - dt.timedelta(days=FORGET_DAYS)).isoformat()
    state["articles"] = {p: a for p, a in state["articles"].items() if a["last_seen"] >= cutoff}
    state["scans"] = (state["scans"] + [{
        "date": today, "ts": now.isoformat(timespec="minutes"), "gefunden": len(found),
        "neu": new, "erster_scan": first_run, "fehler": errors}])[-400:]

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    render(state, now)
    print(f"{len(found)} Artikel gefunden, davon {new} neu.", *errors, sep="\n")


def render(state, now):
    show_from = (now.date() - dt.timedelta(days=SHOW_DAYS)).isoformat()
    articles = [a for a in state["articles"].values() if a["first_seen"] >= show_from]
    scans = [s for s in state["scans"] if s["date"] >= show_from]
    data = json.dumps({"articles": articles, "scans": scans}, ensure_ascii=False)
    data = data.replace("</", "<\\/")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text((ROOT / "template.html").read_text("utf-8").replace("__DATA__", data), "utf-8")


if __name__ == "__main__":
    main()

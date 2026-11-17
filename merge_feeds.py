#!/usr/bin/env python3
"""Junta todos os feeds de feeds.opml num único feed RSS 2.0 (feed.xml).

Uso:
    pip install feedparser
    python merge_feeds.py                       # lê feeds.opml, grava feed.xml
    python merge_feeds.py --days 14 --max 300   # janela e limite de itens

Cada item sai com o nome da fonte entre colchetes no título, ex.:
    [Nielsen Norman Group] Journey Mapping 101
"""
import argparse
import calendar
import concurrent.futures as cf
import html
import time
import xml.etree.ElementTree as ET
from email.utils import formatdate

import feedparser

USER_AGENT = "ux-feed-aggregator/1.0 (+https://github.com/)"


def read_opml(path):
    tree = ET.parse(path)
    feeds = []
    for node in tree.iter("outline"):
        url = node.get("xmlUrl")
        if url:
            feeds.append({
                "name": node.get("title") or node.get("text") or url,
                "url": url,
                "site": node.get("htmlUrl") or url,
            })
    # categoria = outline pai sem xmlUrl
    for parent in tree.iter("outline"):
        if parent.get("xmlUrl"):
            continue
        for child in parent.findall("outline"):
            for f in feeds:
                if f["url"] == child.get("xmlUrl"):
                    f["category"] = parent.get("title") or parent.get("text")
    return feeds


def fetch(feed):
    try:
        parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
    except Exception as exc:  # rede, parse etc.
        return feed, [], str(exc)
    if parsed.bozo and not parsed.entries:
        return feed, [], str(parsed.get("bozo_exception", "feed inválido"))
    return feed, parsed.entries, None


def entry_timestamp(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return calendar.timegm(value)
    return None


def build(feeds, days, max_items, title, link):
    cutoff = time.time() - days * 86400
    items, seen, report = [], set(), []

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for feed, entries, error in pool.map(fetch, feeds):
            if error:
                report.append(f"ERRO  {feed['name']}: {error}")
                continue
            kept = 0
            for e in entries:
                url = e.get("link")
                ts = entry_timestamp(e)
                if not url or url in seen or ts is None or ts < cutoff:
                    continue
                seen.add(url)
                kept += 1
                summary = e.get("summary", "")
                items.append({
                    "title": f"[{feed['name']}] {html.unescape(e.get('title', '(sem título)'))}",
                    "link": url,
                    "ts": ts,
                    "summary": summary,
                    "source": feed,
                    "author": e.get("author", ""),
                })
            report.append(f"ok    {feed['name']}: {kept} itens")

    items.sort(key=lambda i: i["ts"], reverse=True)
    items = items[:max_items]

    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = link
    ET.SubElement(ch, "description").text = "Feed agregado de publicações e fóruns de UI/UX (Brasil e internacional)."
    ET.SubElement(ch, "language").text = "pt-br"
    ET.SubElement(ch, "lastBuildDate").text = formatdate(usegmt=True)
    for it in items:
        node = ET.SubElement(ch, "item")
        ET.SubElement(node, "title").text = it["title"]
        ET.SubElement(node, "link").text = it["link"]
        ET.SubElement(node, "guid", isPermaLink="true").text = it["link"]
        ET.SubElement(node, "pubDate").text = formatdate(it["ts"], usegmt=True)
        ET.SubElement(node, "description").text = it["summary"]
        if it["source"].get("category"):
            ET.SubElement(node, "category").text = it["source"]["category"]
        ET.SubElement(node, "source", url=it["source"]["url"]).text = it["source"]["name"]
    return ET.ElementTree(rss), report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opml", default="feeds.opml")
    ap.add_argument("--out", default="feed.xml")
    ap.add_argument("--days", type=int, default=14, help="só itens dos últimos N dias")
    ap.add_argument("--max", type=int, default=300, help="máximo de itens no feed")
    ap.add_argument("--title", default="Agregador UI/UX")
    ap.add_argument("--link", default="https://example.com/feed.xml",
                    help="URL pública onde o feed.xml vai ficar")
    args = ap.parse_args()

    tree, report = build(read_opml(args.opml), args.days, args.max, args.title, args.link)
    ET.indent(tree)
    tree.write(args.out, encoding="utf-8", xml_declaration=True)
    print("\n".join(report))
    print(f"\n{args.out} gravado com {len(tree.getroot().find('channel').findall('item'))} itens.")


if __name__ == "__main__":
    main()

import os
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path


PAGE_URL = os.environ.get("PAGE_URL", "https://www.et001.com/gameguide/freegametest.html").strip()
LASTMOD = os.environ.get("LASTMOD") or date.today().isoformat()
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def first_existing(candidates):
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def resolve_sitemap_path():
    explicit = os.environ.get("SITEMAP_PATH")
    if explicit:
        return Path(explicit)

    return first_existing(
        [
            "sitemap.xml",
            "public/sitemap.xml",
            "seo-publish-pack/sitemap.xml",
        ]
    ) or Path("sitemap.xml")


def resolve_html_path():
    explicit = os.environ.get("HTML_PATH")
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None

    return first_existing(
        [
            "freegametest.html",
            "gameguide/freegametest.html",
            "public/gameguide/freegametest.html",
            "freegametest-seo-optimized.html",
        ]
    )


def qname(ns, tag):
    return f"{{{ns}}}{tag}" if ns else tag


def update_sitemap():
    sitemap_path = resolve_sitemap_path()
    sitemap_path.parent.mkdir(parents=True, exist_ok=True)

    ET.register_namespace("", SITEMAP_NS)

    if sitemap_path.exists():
        tree = ET.parse(sitemap_path)
        root = tree.getroot()
        ns = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    else:
        ns = SITEMAP_NS
        root = ET.Element(qname(ns, "urlset"))
        tree = ET.ElementTree(root)

    target_url = None
    for url_node in root.findall(qname(ns, "url")):
        loc = url_node.find(qname(ns, "loc"))
        if loc is not None and (loc.text or "").strip() == PAGE_URL:
            target_url = url_node
            break

    if target_url is None:
        target_url = ET.SubElement(root, qname(ns, "url"))
        loc = ET.SubElement(target_url, qname(ns, "loc"))
        loc.text = PAGE_URL

    lastmod = target_url.find(qname(ns, "lastmod"))
    if lastmod is None:
        lastmod = ET.SubElement(target_url, qname(ns, "lastmod"))
    lastmod.text = LASTMOD

    changefreq = target_url.find(qname(ns, "changefreq"))
    if changefreq is None:
        changefreq = ET.SubElement(target_url, qname(ns, "changefreq"))
        changefreq.text = "daily"

    priority = target_url.find(qname(ns, "priority"))
    if priority is None:
        priority = ET.SubElement(target_url, qname(ns, "priority"))
        priority.text = "0.8"

    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass

    tree.write(sitemap_path, encoding="utf-8", xml_declaration=True)

    # Normalize the sitemap protocol namespace if an older file used https.
    text = sitemap_path.read_text(encoding="utf-8")
    text = text.replace(
        'xmlns="https://www.sitemaps.org/schemas/sitemap/0.9"',
        'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
    )
    sitemap_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Updated sitemap lastmod: {sitemap_path} -> {LASTMOD}")


def update_html_dates():
    html_path = resolve_html_path()
    if not html_path:
        print("No freegametest HTML file found; skipped HTML date update.")
        return

    text = html_path.read_text(encoding="utf-8")
    y, m, d = LASTMOD.split("-")
    zh_date = f"{int(y)} 年 {int(m)} 月 {int(d)} 日"
    iso_datetime = f"{LASTMOD}T00:00:00+08:00"

    text = re.sub(r'("dateModified"\s*:\s*")[^"]+(")', rf"\g<1>{LASTMOD}\2", text)
    text = re.sub(r'(datetime=")[^"]+(")', rf"\g<1>{iso_datetime}\2", text)
    text = re.sub(r'(dateTime=")[^"]+(")', rf"\g<1>{iso_datetime}\2", text)
    text = re.sub(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", zh_date, text)

    html_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Updated HTML modified date: {html_path} -> {LASTMOD}")


def main():
    update_sitemap()
    update_html_dates()


if __name__ == "__main__":
    main()

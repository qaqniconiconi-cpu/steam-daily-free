"""Build the standalone Steam discount entry from the shared public page."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gameguide/freegametest.html"
TARGET = ROOT / "gameguide/steamdeals.html"


def build():
    page = SOURCE.read_text(encoding="utf-8")
    page = page.replace('data-default-tab="free"', 'data-default-tab="deals"', 1)
    page = page.replace("/gameguide/freegametest.html", "/gameguide/steamdeals.html")
    static, separator, app = page.partition('<script type="text/babel">')
    if not separator:
        raise ValueError("Public page is missing its React application")

    title = "Steam 折扣史低｜热门游戏特惠价格 - 外星仔"
    description = "查看 Steam 热门游戏折扣、当前价格与史低情报，结合好评率、中文支持和发售时间挑选游戏。"
    static = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", static, count=1)
    metadata = {
        "description": description,
        "keywords": "Steam折扣史低,Steam折扣,Steam史低,Steam特惠,Steam游戏打折",
        "og:title": title,
        "og:description": description,
        "og:image:alt": "Steam 折扣史低与热门游戏特惠情报",
        "twitter:title": title,
        "twitter:description": description,
    }
    for name, content in metadata.items():
        pattern = rf'(<meta (?:name|property)="{re.escape(name)}" content=")[^"]*(">)'
        static, count = re.subn(pattern, lambda match: match[1] + content + match[2], static)
        if count != 1:
            raise ValueError(f"Expected exactly one {name} meta tag")

    static = static.replace("外星仔游戏情报站 - 喜加一", "外星仔游戏情报站 - Steam折扣")
    static = static.replace("最新免费游戏实时更新", "Steam 折扣情报实时更新")
    static = static.replace("今日喜加一 <span", "Steam 折扣史低 <span")
    static = static.replace("</span> 免费游戏白嫖", "</span> 热门游戏特惠")
    static = static.replace("Steam喜加一与Epic限免游戏", "Steam 折扣史低")

    def update_schema(match):
        schema = json.loads(match[1])
        for entity in schema["@graph"]:
            if entity["@type"] == "CollectionPage":
                entity["name"] = "Steam 折扣史低与热门游戏特惠"
                entity["description"] = description
                entity["mainEntity"] = {"@id": "https://www.et001.com/gameguide/steamdeals.html#faq"}
                entity["about"] = ["Steam折扣史低", "Steam折扣", "Steam特惠", "Steam春促", "Steam夏促", "Steam秋促", "Steam冬促"]
        return '<script type="application/ld+json">\n' + json.dumps(schema, ensure_ascii=False, indent=8) + "\n    </script>"

    static = re.sub(r'<script type="application/ld\+json">(.*?)</script>', update_schema, static, count=1, flags=re.S)
    TARGET.write_text(static + separator + app, encoding="utf-8")
    print(f"Built {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    build()

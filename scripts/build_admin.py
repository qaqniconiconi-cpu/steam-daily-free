"""Export the admin page and publisher as one uploadable HTML file."""
import argparse
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
page = (root / "admin/freegamestaffonly_ordered_fixed.html").read_text(encoding="utf-8")
core = (root / "admin/publish-core.js").read_text(encoding="utf-8")
marker = '<script src="publish-core.js"></script>'
if page.count(marker) != 1:
    raise ValueError("Expected exactly one publisher script")
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(page.replace(marker, "<script>\n" + core + "\n</script>"), encoding="utf-8")
print(args.output.resolve())

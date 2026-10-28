import ast
import unittest
from pathlib import Path


class WorkflowSortTest(unittest.TestCase):
    def test_upcoming_stays_last_even_with_smaller_manual_order(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/update_games.yml").read_text()
        source = workflow.split("          import requests", 1)[1].split("\n          EOF", 1)[0]
        source = "import requests" + "\n".join(line[10:] for line in source.splitlines())
        tree = ast.parse(source)
        function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "sort_output_items")
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<workflow sort>", "exec"), scope)
        result = scope["sort_output_items"]([
            {"zh_title": "Upcoming", "is_upcoming": True, "sort_order": 1},
            {"zh_title": "Active default"},
            {"zh_title": "Active sorted", "sort_order": 0},
        ])
        self.assertEqual([item["zh_title"] for item in result], ["Active sorted", "Active default", "Upcoming"])


if __name__ == "__main__":
    unittest.main()

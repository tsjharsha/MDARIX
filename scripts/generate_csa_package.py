from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validation.csa_package import build_package, render_markdown

root = Path(__file__).resolve().parents[1]
package = build_package()
(root / "docs" / "CSA_MVP_VALIDATION_PACKAGE.md").write_text(render_markdown(package), encoding="utf-8")
(root / "docs" / "CSA_MVP_VALIDATION_PACKAGE.json").write_text(__import__("json").dumps(package, indent=2), encoding="utf-8")
print("Generated docs/CSA_MVP_VALIDATION_PACKAGE.md and .json")

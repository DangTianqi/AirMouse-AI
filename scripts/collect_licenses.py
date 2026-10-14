"""Bundle installed dependency notices without importing heavy runtime modules."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "artifacts/third-party"
DEST.mkdir(parents=True, exist_ok=True)
for dist in distributions():
    name = dist.metadata["Name"]
    for file in dist.files or []:
        if any(word in str(file).lower() for word in ("license", "copying", "notice")):
            source = Path(dist.locate_file(file))
            if source.is_file():
                target = DEST / name / str(file).replace("..", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
print(f"Third-party notices collected: {DEST}")

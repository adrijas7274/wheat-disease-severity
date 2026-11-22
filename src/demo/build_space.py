"""Assemble a Hugging Face Space folder for the demo (nothing is uploaded).

    python -m src.demo.build_space [--out dist/hf_space]

The folder holds: app.py, the `src` package, configs/config.yaml, the frozen policy (with the checkpoint path
pointing inside the Space), the example photos, the SegFormer-B0 checkpoint (~15 MB), a CPU requirements file and
the Space README with its metadata header. SAM 2.1 tiny is downloaded by the app on first start.
No dataset images other than the three CC BY 4.0 examples are copied.
"""

import argparse
import json
import shutil
from pathlib import Path

SPACE_CHECKPOINT = "checkpoints/segformer_b0.pt"
REQUIREMENTS = """# CPU Space. torch CPU wheels from the PyTorch index.
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.5.1
torchvision==0.20.1
numpy==1.26.4
pillow==10.4.0
pyyaml==6.0.2
pandas==2.2.3
scikit-learn==1.5.2
scikit-image==0.24.0
opencv-python-headless==4.10.0.84
albumentations==1.4.18
segmentation-models-pytorch==0.3.4
transformers==4.46.3
sam2==1.1.0
gradio==5.9.1
pydantic==2.10.6
"""
SPACE_README = """---
title: Wheat Leaf Disease Severity
emoji: 🌾
colorFrom: green
colorTo: yellow
sdk: gradio
sdk_version: 5.9.1
app_file: app.py
pinned: false
license: cc-by-nc-4.0
short_description: Wheat leaf disease severity with retake and consult checks
---

# Wheat leaf disease severity (research demo)

Upload a wheat leaf photo, choose the disease, tap the main leaf. The app outlines the leaf, marks the diseased
pixels, estimates severity (lesion area / leaf area), and either answers, asks for a retake (photo-quality check)
or says "consult an expert" (the estimate is unstable).

**Decision support, not expert advice.** Severity levels and recommendations are placeholders that have not been
validated. Non-commercial use only: the region model was trained on PlantSeg (CC BY-NC 4.0).

Code, results and limitations: TODO_GITHUB_LINK
"""


def build(out: Path) -> None:
    from src.demo.pipeline import POLICY_FILE

    if out.exists():
        raise SystemExit(f"{out} exists; choose a new folder or delete it yourself")
    out.mkdir(parents=True)
    shutil.copy("demo/app.py", out / "app.py")
    shutil.copytree("src", out / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (out / "configs").mkdir()
    shutil.copy("configs/config.yaml", out / "configs/config.yaml")
    (out / "demo").mkdir()
    shutil.copytree("demo/examples", out / "demo/examples")
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    src_ckpt = Path(policy["model"]["checkpoint"])
    policy["model"]["checkpoint"] = SPACE_CHECKPOINT
    (out / POLICY_FILE).write_text(json.dumps(policy, indent=1), encoding="utf-8")
    (out / "checkpoints").mkdir()
    shutil.copy(src_ckpt, out / SPACE_CHECKPOINT)
    (out / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (out / "README.md").write_text(SPACE_README, encoding="utf-8")
    (out / ".gitattributes").write_text("*.pt filter=lfs diff=lfs merge=lfs -text\n*.jpg filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    print(f"Space folder ready: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="dist/hf_space")
    build(Path(parser.parse_args().out))


if __name__ == "__main__":
    main()

"""Make sure the two checkpoints exist before the demo starts (downloads SAM 2.1 tiny on a fresh Space).

SegFormer-B0 ships with the Space (`checkpoints/segformer_b0.pt`, ~15 MB); SAM 2.1 hiera-tiny (156 MB) is
downloaded once from Meta's public URL and checked against the SHA-256 recorded in experiments/LOG.md.
"""

import hashlib
import json
import urllib.request
from pathlib import Path

SAM2_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt"
SAM2_SHA256 = "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"
SAM2_PATH = Path("data/checkpoints/sam2/sam2.1_hiera_tiny.pt")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_checkpoints(policy_path: Path = Path("demo/final_policy.json")) -> None:
    seg = Path(json.loads(policy_path.read_text(encoding="utf-8"))["model"]["checkpoint"])
    if not seg.exists():
        raise FileNotFoundError(f"SegFormer-B0 checkpoint missing: {seg}")
    if not SAM2_PATH.exists():
        SAM2_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SAM2_PATH.with_suffix(".part")
        print(f"Downloading SAM 2.1 tiny from {SAM2_URL} ...", flush=True)
        urllib.request.urlretrieve(SAM2_URL, tmp)
        if sha256(tmp) != SAM2_SHA256:
            tmp.unlink()
            raise RuntimeError("SAM 2 checkpoint checksum mismatch")
        tmp.rename(SAM2_PATH)

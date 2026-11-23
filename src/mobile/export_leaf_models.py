"""Export the phone-sized leaf finders to ONNX (FP32 and INT8) for the Phase 8 comparison.

MobileSAM (Apache 2.0, github.com/ChaoningZhang/MobileSAM at a pinned commit) is exported here:
    encoder  1x3x1024x1024 normalised, padded image -> 1x256x64x64 embedding
    decoder  embedding + points -> 4 low-resolution mask logits (1x4x256x256) and 4 scores; the browser and
             `src.mobile.leaf_finders` upsample and crop them, so the decoder does not depend on the photo size.
EfficientSAM-Ti (Apache 2.0, github.com/yformer/EfficientSAM) ships its own ONNX encoder and decoder; they are
only copied and quantised.

INT8: onnxruntime dynamic quantisation of MatMul/Gemm only (a dynamically quantised Conv becomes ConvInteger,
which the onnxruntime CPU provider and onnxruntime-web do not implement), as for SegFormer in `src.export`.

The third-party repositories are fetched to data/third_party/ at the commits in THIRD_PARTY (gitignored).

Usage:
    python -m src.mobile.export_leaf_models [--out data/mobile_models]
"""

import argparse
import shutil
import sys
from pathlib import Path

THIRD_PARTY = {
    "MobileSAM": {"repo": "ChaoningZhang/MobileSAM", "commit": "f706ad9c4eb7f219c00d9050e46328518ffb65d2",
                  "weights": "weights/mobile_sam.pt",
                  "sha256": "6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f"},
    "EfficientSAM": {"repo": "yformer/EfficientSAM", "commit": "d525f622e6f640acf5a0fc37c7ca1f243da5bde0",
                     "encoder_sha256": "84ed466ffcc5c1f8d08409bc34a23bb364ab2c15e402cb12d4335a42be0e0951",
                     "decoder_sha256": "a62f8fa5ea080447c0689418d69e58f1e83e0b7adf9c142e2bd9bcc8045c0b11"},
}
TP_DIR = Path("data/third_party")
OUT_DIR = Path("data/mobile_models")


def sha256(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check(path: Path, expected: str) -> None:
    got = sha256(path)
    if got != expected:
        raise RuntimeError(f"{path}: SHA-256 {got} does not match the pinned {expected}")


def load_mobile_sam():
    """MobileSAM (vit_t) in eval mode on CPU, from the pinned checkout."""
    info = THIRD_PARTY["MobileSAM"]
    root = TP_DIR / "MobileSAM"
    _check(root / info["weights"], info["sha256"])
    sys.path.insert(0, str(root.resolve()))
    from mobile_sam import sam_model_registry  # noqa: E402

    model = sam_model_registry["vit_t"](checkpoint=str(root / info["weights"]))
    return model.eval()


def export_mobile_sam(out: Path) -> tuple[Path, Path]:
    """Encoder and low-resolution decoder ONNX files (FP32)."""
    import torch

    model = load_mobile_sam()

    class Encoder(torch.nn.Module):
        def __init__(self, sam):
            super().__init__()
            self.enc = sam.image_encoder

        def forward(self, x):
            return self.enc(x)

    class Decoder(torch.nn.Module):
        """Point prompt -> the 4 low-resolution mask logits and their scores (no upsampling)."""

        def __init__(self, sam):
            super().__init__()
            self.sam = sam
            # computed inside the graph (not stored as 64x64 constants), which keeps the file small
            self.grid = sam.prompt_encoder.image_embedding_size

        def forward(self, image_embeddings, point_coords, point_labels):
            pe = self.sam.prompt_encoder
            coords = (point_coords + 0.5) / self.sam.image_encoder.img_size
            emb = pe.pe_layer._pe_encoding(coords)
            lab = point_labels.unsqueeze(-1).expand_as(emb)
            emb = emb * (lab != -1) + pe.not_a_point_embed.weight * (lab == -1)
            for i in range(pe.num_point_embeddings):
                emb = emb + pe.point_embeddings[i].weight * (lab == i)
            dense_pe = pe.pe_layer(self.grid).unsqueeze(0)
            no_mask = pe.no_mask_embed.weight.reshape(1, -1, 1, 1).expand(1, -1, *self.grid)
            masks, scores = self.sam.mask_decoder.predict_masks(image_embeddings=image_embeddings, image_pe=dense_pe,
                                                                 sparse_prompt_embeddings=emb, dense_prompt_embeddings=no_mask)
            return masks, scores

    enc_path, dec_path = out / "mobile_sam_encoder.onnx", out / "mobile_sam_decoder.onnx"
    with torch.no_grad():
        torch.onnx.export(Encoder(model), torch.zeros(1, 3, 1024, 1024), str(enc_path), opset_version=17,
                          input_names=["image"], output_names=["image_embeddings"])
        emb = torch.zeros(1, 256, 64, 64)
        pts, labs = torch.zeros(1, 2, 2), torch.tensor([[1.0, -1.0]])
        torch.onnx.export(Decoder(model), (emb, pts, labs), str(dec_path), opset_version=17,
                          input_names=["image_embeddings", "point_coords", "point_labels"],
                          output_names=["low_res_masks", "scores"],
                          dynamic_axes={"point_coords": {1: "n"}, "point_labels": {1: "n"}})
    return enc_path, dec_path


def copy_efficient_sam(out: Path) -> tuple[Path, Path]:
    """The EfficientSAM-Ti ONNX encoder and decoder from the pinned checkout, checksum-verified."""
    info = THIRD_PARTY["EfficientSAM"]
    src = TP_DIR / "EfficientSAM" / "weights"
    enc, dec = out / "efficient_sam_vitt_encoder.onnx", out / "efficient_sam_vitt_decoder.onnx"
    for name, target, key in ((src / "efficient_sam_vitt_encoder.onnx", enc, "encoder_sha256"),
                              (src / "efficient_sam_vitt_decoder.onnx", dec, "decoder_sha256")):
        _check(name, info[key])
        shutil.copyfile(name, target)
    return enc, dec


def quantise(fp32: Path) -> Path:
    """Dynamic INT8 (MatMul/Gemm) copy next to `fp32`, named *_int8.onnx."""
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.shape_inference import quant_pre_process

    pre = fp32.with_name(fp32.stem + "_pre.onnx")
    dst = fp32.with_name(fp32.stem + "_int8.onnx")
    try:
        quant_pre_process(str(fp32), str(pre), skip_symbolic_shape=True)
        src = pre
    except Exception as exc:  # some exported graphs do not pre-process; quantise the original then
        print(f"pre-processing skipped for {fp32.name}: {exc}")
        src = fp32
    quantize_dynamic(str(src), str(dst), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul", "Gemm"])
    if pre.exists():
        pre.unlink()
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    files = [*export_mobile_sam(args.out), *copy_efficient_sam(args.out)]
    files += [quantise(f) for f in list(files)]
    for f in files:
        print(f"{f.name:45s} {f.stat().st_size / 1e6:7.1f} MB  sha256 {sha256(f)[:16]}...")


if __name__ == "__main__":
    main()

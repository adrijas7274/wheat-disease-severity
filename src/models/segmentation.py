"""Model builders for Phase 2 infected-region segmentation baselines.

Both models are wrapped to expose the same forward(images) -> logits
[B, num_classes, H, W] interface (matching input resolution), so train.py
and evaluate.py stay model-agnostic. SegFormer's native output is at 1/4
resolution and needs upsampling; DeepLabV3+ already outputs at input
resolution.
"""

import segmentation_models_pytorch as smp
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import SegformerForSemanticSegmentation

SEGFORMER_CHECKPOINT = "nvidia/segformer-b0-finetuned-ade-512-512"
MODEL_NAMES = ("deeplabv3plus", "segformer")


class _SegformerWrapper(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        logits = self.model(pixel_values=images).logits
        return F.interpolate(logits, size=images.shape[-2:], mode="bilinear", align_corners=False)


def build_deeplabv3plus_mobilenet(num_classes: int = 2) -> nn.Module:
    return smp.DeepLabV3Plus(
        encoder_name="timm-mobilenetv3_large_100",
        encoder_weights="imagenet",
        in_channels=3,
        classes=num_classes,
    )


def build_segformer_b0(num_classes: int = 2) -> nn.Module:
    model = SegformerForSemanticSegmentation.from_pretrained(
        SEGFORMER_CHECKPOINT, num_labels=num_classes, ignore_mismatched_sizes=True,
    )
    return _SegformerWrapper(model)


def build_model(name: str, num_classes: int = 2) -> nn.Module:
    if name == "deeplabv3plus":
        return build_deeplabv3plus_mobilenet(num_classes)
    if name == "segformer":
        return build_segformer_b0(num_classes)
    raise ValueError(f"model name must be one of {MODEL_NAMES}, got {name!r}")

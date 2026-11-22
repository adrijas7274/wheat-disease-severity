"""Dice + cross-entropy loss for binary infected-region segmentation (the project plan Phase 2)."""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceCELoss(nn.Module):
    """Weighted sum of cross-entropy and soft Dice loss, for 2-class
    (background=0, infected=1) segmentation logits of shape [B, 2, H, W].
    """

    def __init__(self, dice_weight: float = 0.5):
        super().__init__()
        if not 0.0 <= dice_weight <= 1.0:
            raise ValueError(f"dice_weight must be in [0, 1], got {dice_weight}")
        self.dice_weight = dice_weight
        self.ce = nn.CrossEntropyLoss()

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = self.ce(logits, targets)

        probs_infected = F.softmax(logits, dim=1)[:, 1]
        targets_f = (targets == 1).float()
        intersection = (probs_infected * targets_f).sum(dim=(1, 2))
        union = probs_infected.sum(dim=(1, 2)) + targets_f.sum(dim=(1, 2))
        dice = (2 * intersection + 1e-6) / (union + 1e-6)
        dice_loss = 1 - dice.mean()

        return (1 - self.dice_weight) * ce_loss + self.dice_weight * dice_loss

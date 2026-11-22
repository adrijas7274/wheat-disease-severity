import pytest
import torch

from src.severity.losses import DiceCELoss


def test_loss_lower_for_correct_prediction():
    torch.manual_seed(0)
    targets = torch.tensor([[[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]], dtype=torch.long)

    # logits strongly favouring the correct class
    correct_logits = torch.zeros(1, 2, 4, 4)
    correct_logits[0, 1] = (targets[0] == 1).float() * 10 - 5
    correct_logits[0, 0] = -correct_logits[0, 1]

    # logits strongly favouring the WRONG class everywhere
    wrong_logits = -correct_logits

    loss_fn = DiceCELoss()
    correct_loss = loss_fn(correct_logits, targets)
    wrong_loss = loss_fn(wrong_logits, targets)

    assert correct_loss.item() < wrong_loss.item()


def test_loss_is_differentiable():
    logits = torch.randn(2, 2, 8, 8, requires_grad=True)
    targets = torch.randint(0, 2, (2, 8, 8))

    loss = DiceCELoss()(logits, targets)
    loss.backward()

    assert logits.grad is not None
    assert not torch.isnan(logits.grad).any()


def test_dice_weight_zero_matches_pure_ce():
    torch.manual_seed(1)
    logits = torch.randn(2, 2, 4, 4)
    targets = torch.randint(0, 2, (2, 4, 4))

    import torch.nn as nn
    ce_only = nn.CrossEntropyLoss()(logits, targets)
    dice_ce_zero = DiceCELoss(dice_weight=0.0)(logits, targets)

    assert abs(ce_only.item() - dice_ce_zero.item()) < 1e-6


def test_invalid_dice_weight_raises():
    with pytest.raises(ValueError):
        DiceCELoss(dice_weight=1.5)

from pathlib import Path

import torch
import torch.nn as nn

from src.train import load_checkpoint, save_checkpoint


class _TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(4, 2)

    def forward(self, x):
        return self.linear(x)


def test_save_and_load_checkpoint_roundtrip(tmp_path: Path) -> None:
    model = _TinyModel()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    # take one optimizer step so its state dict is non-trivial
    loss = model(torch.randn(3, 4)).sum()
    loss.backward()
    optimizer.step()

    path = tmp_path / "last_checkpoint.pt"
    history = [{"epoch": 1, "val_iou": 0.5}]
    save_checkpoint(path, model, optimizer, epoch=1, best_val_iou=0.5,
                     epochs_without_improvement=0, history=history)

    new_model = _TinyModel()
    new_optimizer = torch.optim.AdamW(new_model.parameters(), lr=1e-3)
    checkpoint = load_checkpoint(path, new_model, new_optimizer, device=torch.device("cpu"))

    assert checkpoint["epoch"] == 1
    assert checkpoint["best_val_iou"] == 0.5
    assert checkpoint["epochs_without_improvement"] == 0
    assert checkpoint["history"] == history
    # model weights actually restored, not just left at random init
    for p1, p2 in zip(model.parameters(), new_model.parameters()):
        assert torch.equal(p1, p2)
    # optimizer state (e.g. Adam moment estimates) actually restored
    assert new_optimizer.state_dict()["state"].keys() == optimizer.state_dict()["state"].keys()

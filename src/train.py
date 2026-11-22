"""Train a Phase 2 infected-region segmentation baseline.

Usage:
    python -m src.train --config configs/config.yaml --model deeplabv3plus
    python -m src.train --config configs/config.yaml --model segformer
    python -m src.train --config configs/config.yaml --model deeplabv3plus --debug

Resumable: a full checkpoint (model, optimizer, epoch, best-so-far, history)
is saved every epoch to <exp_dir>/last_checkpoint.pt. If interrupted:
    python -m src.train --config configs/config.yaml --model segformer --resume experiments/<exp_dir>/last_checkpoint.pt
continues from the next epoch with identical state - this is a real resume
(optimizer momentum etc. included), not a restart from the best weights only.

See the project plan Phase 2 and experiments/LOG.md (2026-10-03/04/05/07) for why
this is "infected-region" segmentation, not lesion segmentation, and why
the main baseline is binary rather than 6-class.
"""

import argparse
import shutil
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from src.data.severity_transforms import CorruptionAugmentedDataset, TransformedSeverityDataset
from src.data.wheat_severity_dataset import WheatSeverityDataset
from src.models.segmentation import MODEL_NAMES, build_model
from src.severity.losses import DiceCELoss
from src.severity.metrics import binary_iou
from src.utils.config import load_config
from src.utils.experiment import MetricLogger, create_experiment_dir
from src.utils.seeding import set_seed


def build_dataloaders(config: dict, image_size: int, debug: bool, batch_size: int, corruption_aug: float = 0.0):
    train_base = WheatSeverityDataset(config, split="train", subset="close_up")
    val_base = WheatSeverityDataset(config, split="val", subset="close_up")
    if debug:
        train_base.rows = train_base.rows[:20]
        val_base.rows = val_base.rows[:10]

    n_train = len(train_base)
    if corruption_aug > 0:  # Phase 5 baseline: phone corruptions on the training photos only, never on val
        train_base = CorruptionAugmentedDataset(train_base, corruption_aug, config["seed"])
    train_ds = TransformedSeverityDataset(train_base, image_size, train=True)
    val_ds = TransformedSeverityDataset(val_base, image_size, train=False)

    # num_workers=0: this dataset is small and Windows multiprocessing
    # DataLoader workers add startup overhead/fragility not worth it here.
    # drop_last=True on train only: a trailing batch of size 1 crashes
    # BatchNorm in training mode (model.train()); eval mode uses running
    # stats so val/test don't need this and we'd rather score every image.
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)
    return train_loader, val_loader, n_train, len(val_base)


def train_one_epoch(model, loader, optimizer, loss_fn, device) -> float:
    model.train()
    total_loss, n = 0.0, 0
    for batch in loader:
        images = batch["image"].to(device)
        masks = batch["mask"].to(device)
        optimizer.zero_grad()
        logits = model(images)
        loss = loss_fn(logits, masks)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
        n += images.size(0)
    return total_loss / n if n else 0.0


@torch.no_grad()
def evaluate_val_iou(model, loader, device) -> float:
    model.eval()
    ious = []
    for batch in loader:
        images = batch["image"].to(device)
        masks = batch["mask"].numpy()
        preds = model(images).argmax(dim=1).cpu().numpy()
        for p, m in zip(preds, masks):
            ious.append(binary_iou(p, m))
    return sum(ious) / len(ious) if ious else 0.0


def save_checkpoint(path: Path, model, optimizer, epoch: int, best_val_iou: float,
                     epochs_without_improvement: int, history: list[dict]) -> None:
    torch.save({
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "best_val_iou": best_val_iou,
        "epochs_without_improvement": epochs_without_improvement,
        "history": history,
    }, path)


def load_checkpoint(path: Path, model, optimizer, device) -> dict:
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    return checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--model", required=True, choices=MODEL_NAMES)
    parser.add_argument("--debug", action="store_true", help="~20 train / ~10 val images, 1 epoch, forced CPU")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--patience", type=int, default=10, help="early-stopping patience on val IoU")
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--resume", default=None, help="path to a last_checkpoint.pt to resume from")
    parser.add_argument("--corruption-aug", type=float, default=0.0,
                        help="Phase 5: probability of replacing a training photo by a phone-corrupted copy (random type and level)")
    args = parser.parse_args()

    config = load_config(args.config)
    set_seed(config["seed"])

    device = torch.device("cpu" if args.debug else ("cuda" if torch.cuda.is_available() else "cpu"))
    image_size = 128 if args.debug else config["image"]["size"]
    batch_size = args.batch_size or (2 if args.debug else 8)
    epochs = args.epochs if args.epochs is not None else (1 if args.debug else 100)

    train_loader, val_loader, n_train, n_val = build_dataloaders(config, image_size, args.debug, batch_size, args.corruption_aug)
    print(f"device={device} image_size={image_size} batch_size={batch_size} "
          f"n_train={n_train} n_val={n_val} epochs={epochs}")

    model = build_model(args.model, num_classes=2).to(device)
    loss_fn = DiceCELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    start_epoch = 0
    best_val_iou = -1.0
    epochs_without_improvement = 0
    history: list[dict] = []

    if args.resume:
        resume_path = Path(args.resume)
        exp_dir = resume_path.parent
        checkpoint = load_checkpoint(resume_path, model, optimizer, device)
        start_epoch = checkpoint["epoch"]  # 0-indexed epochs already completed
        best_val_iou = checkpoint["best_val_iou"]
        epochs_without_improvement = checkpoint["epochs_without_improvement"]
        history = checkpoint["history"]
        print(f"Resumed from {resume_path}: {start_epoch} epochs already done, "
              f"best_val_iou={best_val_iou:.4f}, epochs_without_improvement={epochs_without_improvement}")
    else:
        exp_name = f"{args.model}{'_corruption_aug' if args.corruption_aug > 0 else ''}{'_debug' if args.debug else ''}"
        exp_dir = create_experiment_dir(exp_name, config_path=args.config)
        exclude_file = Path(config["data"].get("split_exclude_file") or "")
        if exclude_file.is_file():  # so the run folder records exactly which images were left out
            shutil.copy(exclude_file, exp_dir / exclude_file.name)

    logger = MetricLogger(exp_dir)
    checkpoint_path = exp_dir / "last_checkpoint.pt"

    for epoch in range(start_epoch, epochs):
        t0 = time.time()
        train_loss = train_one_epoch(model, train_loader, optimizer, loss_fn, device)
        val_iou = evaluate_val_iou(model, val_loader, device)
        epoch_time = time.time() - t0
        peak_mem_mb = torch.cuda.max_memory_allocated(device) / 1e6 if device.type == "cuda" else None

        msg = f"epoch {epoch + 1}/{epochs} train_loss={train_loss:.4f} val_iou={val_iou:.4f} time={epoch_time:.1f}s"
        if peak_mem_mb is not None:
            msg += f" peak_mem={peak_mem_mb:.0f}MB"
        print(msg, flush=True)
        history.append({
            "epoch": epoch + 1, "train_loss": train_loss, "val_iou": val_iou,
            "time_s": epoch_time, "peak_mem_mb": peak_mem_mb,
        })

        if val_iou > best_val_iou:
            best_val_iou = val_iou
            epochs_without_improvement = 0
            torch.save(model.state_dict(), exp_dir / "best_model.pt")
        else:
            epochs_without_improvement += 1

        # Saved every epoch (not just on improvement) so a kill/crash loses
        # at most one epoch of progress, including optimizer state.
        save_checkpoint(checkpoint_path, model, optimizer, epoch + 1, best_val_iou,
                         epochs_without_improvement, history)
        logger.update({
            "model": args.model, "best_val_iou": best_val_iou, "history": history,
            "device": str(device), "image_size": image_size, "batch_size": batch_size,
            "n_train": n_train, "n_val": n_val, "debug": args.debug, "finished": False,
            "corruption_aug": args.corruption_aug,
        })
        logger.save()

        if not args.debug and epochs_without_improvement >= args.patience:
            print(f"Early stopping at epoch {epoch + 1} (no val IoU improvement for {args.patience} epochs)")
            break

    logger.metrics["finished"] = True
    logger.save()
    print(f"Done. Best val IoU: {best_val_iou:.4f}. Experiment dir: {exp_dir}")


if __name__ == "__main__":
    main()

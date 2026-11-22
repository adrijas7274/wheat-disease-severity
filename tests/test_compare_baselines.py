import pytest
import torch
import torch.nn as nn

from src.compare_baselines import count_params, measure_cpu_inference_time, paired_iou_differences


def test_paired_iou_differences_matches_by_image_id():
    a = [
        {"image_id": "x.jpg", "iou": 0.5},
        {"image_id": "y.jpg", "iou": 0.7},
    ]
    b = [
        {"image_id": "y.jpg", "iou": 0.8},  # deliberately different order
        {"image_id": "x.jpg", "iou": 0.6},
    ]

    diffs = paired_iou_differences(a, b)

    assert sorted(diffs) == sorted([0.6 - 0.5, 0.8 - 0.7])


def test_paired_iou_differences_raises_on_mismatched_ids():
    a = [{"image_id": "x.jpg", "iou": 0.5}]
    b = [{"image_id": "z.jpg", "iou": 0.6}]

    with pytest.raises(ValueError, match="same image_ids"):
        paired_iou_differences(a, b)


def test_count_params():
    model = nn.Linear(4, 2)  # 4*2 weights + 2 bias = 10
    assert count_params(model) == 10


def test_measure_cpu_inference_time_returns_positive_float():
    model = nn.Sequential(nn.Conv2d(3, 4, 3, padding=1))
    t = measure_cpu_inference_time(model, image_size=16, n_runs=2, n_warmup=1)
    assert isinstance(t, float)
    assert t > 0

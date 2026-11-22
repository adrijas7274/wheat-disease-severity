import numpy as np
import torch

from src.models.inference import predict_region, resize_mask
from src.severity.auto_click import click_from_region


def test_click_is_deepest_point_of_the_largest_component():
    region = np.zeros((40, 60), bool)
    region[2:6, 2:6] = True          # small component
    region[10:31, 20:41] = True      # 21 x 21 square, centre (x=30, y=20)
    assert click_from_region(region, (40, 60)) == (30, 20)


def test_click_is_mapped_back_to_original_pixels_and_lies_on_the_region():
    region = np.zeros((40, 60), bool)
    region[10:31, 20:41] = True
    x, y = click_from_region(region, (400, 600, 3))
    assert (x, y) == (305, 205)  # centre of output pixel (30, 20), scaled by 10
    assert resize_mask(region, (400, 600))[y, x]


def test_no_prediction_gives_the_image_centre():
    assert click_from_region(np.zeros((40, 60), bool), (400, 600, 3)) == (300, 200)


def test_ties_go_to_the_first_pixel_in_row_major_order():
    region = np.zeros((10, 10), bool)
    region[2:4, 2:8] = True  # 2 rows: every pixel has the same depth
    assert click_from_region(region, (10, 10)) == (2, 2)


def test_component_touching_the_border_is_not_deepest_at_the_border():
    region = np.zeros((20, 20), bool)
    region[0:11, 0:11] = True
    assert click_from_region(region, (20, 20)) == (5, 5)


def test_8_connectivity_joins_diagonal_pixels():
    region = np.zeros((12, 12), bool)
    region[0:3, 0:3] = True
    region[3:6, 3:6] = True      # touches the first square only at a corner: one component of 18
    region[8:12, 8:12] = True    # separate square of 16
    x, y = click_from_region(region, (12, 12))
    assert x < 6 and y < 6


class _Left(torch.nn.Module):
    """Fake model: predicts 'infected' on the left half of whatever it is given."""

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        logits = torch.zeros(images.shape[0], 2, *images.shape[-2:])
        logits[:, 1, :, : images.shape[-1] // 2] = 1.0
        return logits


def test_predict_region_removes_the_padding():
    image = np.full((100, 200, 3), 128, np.uint8)  # wide image: padded top and bottom to a square
    region = predict_region(_Left(), image, image_size=64, device="cpu")
    assert region.shape == (32, 64)
    assert region[:, :32].all() and not region[:, 32:].any()

import numpy as np
from PIL import Image

from src.data import near_duplicates as nd


def _photo(seed: int, size: tuple[int, int] = (240, 180)) -> Image.Image:
    """Smooth random image (blurred noise), so resizing behaves like it does on a photo."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (6, 8, 3), dtype=np.uint8)
    return Image.fromarray(small).resize(size, Image.BICUBIC)


def _features(images: list[Image.Image]) -> tuple[np.ndarray, np.ndarray]:
    return np.array([nd.dhash(i) for i in images]), np.array([nd.thumbnail(i) for i in images])


def test_resized_copy_is_found_and_other_images_are_not():
    a = _photo(1)
    images = [a, _photo(2), a.resize((480, 360), Image.BILINEAR), _photo(3)]
    pairs = nd.find_pairs(*_features(images))
    assert [(i, j) for i, j, *_ in pairs] == [(0, 2)]


def test_thumbnail_test_rejects_a_hash_only_match():
    a = _photo(1)
    brighter = Image.fromarray(np.clip(np.asarray(a).astype(int) + 60, 0, 255).astype(np.uint8))
    hashes, thumbs = _features([a, brighter])
    assert nd.find_pairs(hashes, thumbs, max_thumb_diff=255) != []
    assert nd.find_pairs(hashes, thumbs) == []


def test_groups_join_chained_pairs():
    pairs = [(0, 1, 0, 0.0), (1, 4, 2, 1.0), (2, 3, 1, 0.5)]
    assert nd.groups(6, pairs) == [[0, 1, 4], [2, 3]]

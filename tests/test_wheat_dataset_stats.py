from src.data.wheat_dataset_stats import compute_counts, compute_disputed_counts
from src.data.wheat_severity_dataset import WheatSeverityDataset


def test_compute_counts(tiny_config: dict) -> None:
    counts = compute_counts(tiny_config)

    assert counts[("wheat stripe rust", "train", "close_up")] == 2  # stripe_1.jpg + stripe_6.jpg (disputed)
    assert counts[("wheat stripe rust", "train", "wide")] == 1
    assert counts[("wheat stripe rust", "train", "non_photo")] == 1
    assert counts[("wheat stripe rust", "train", "skip")] == 1
    assert counts[("wheat stripe rust", "train", "untagged")] == 1
    assert counts[("wheat leaf rust", "val", "close_up")] == 1
    assert counts[("wheat leaf rust", "test", "close_up")] == 2  # leaf_2.jpg + leaf_3.jpg (disputed)
    # excluded disease/plant never appear at all
    assert all(disease not in ("wheat head scab", "tomato early blight") for disease, _, _ in counts)


def test_compute_disputed_counts(tiny_config: dict) -> None:
    disputed_counts = compute_disputed_counts(tiny_config)

    assert disputed_counts[("wheat stripe rust", "train")] == 1  # stripe_6.jpg
    assert disputed_counts[("wheat leaf rust", "test")] == 1  # leaf_3.jpg
    assert ("wheat leaf rust", "val") not in disputed_counts  # leaf_1.jpg not disputed


def test_save_sample_overlays_no_close_up_yet(tiny_config: dict, tmp_path) -> None:
    from src.data.wheat_dataset_stats import save_sample_overlays

    # empty out the close_up train subset by pointing at an empty processed dir
    empty_config = dict(tiny_config)
    empty_config["data"] = dict(tiny_config["data"])
    empty_config["data"]["processed_dir"] = str(tmp_path / "empty_processed")

    out_path = tmp_path / "overlays.png"
    result = save_sample_overlays(empty_config, out_path)

    assert result is False
    assert not out_path.exists()


def test_save_sample_overlays_with_data(tiny_config: dict, tmp_path) -> None:
    from src.data.wheat_dataset_stats import save_sample_overlays

    out_path = tmp_path / "overlays.png"
    result = save_sample_overlays(tiny_config, out_path, n=4, cols=2)

    assert result is True
    assert out_path.exists()

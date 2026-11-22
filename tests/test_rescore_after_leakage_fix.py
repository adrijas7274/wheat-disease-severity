from src import rescore_after_leakage_fix as rs


def _per_image(offset: float) -> dict[str, list[dict]]:
    def rows(base: float) -> list[dict]:
        return [{"image_id": f"img{i}", "disease": "wheat leaf rust" if i < 3 else "wheat stripe rust",
                 "iou": base + 0.05 * i, "dice": base + 0.05 * i, "area_err": 0.01 * i} for i in range(6)]

    return {"deeplabv3plus": rows(0.3 + offset), "segformer": rows(0.4 + offset)}


def test_no_leak_set_drops_only_the_leaked_images():
    sets = rs.build_sets(_per_image(0.0), _per_image(0.1), leaked={"img0", "img5"})
    assert sets["original"]["segformer"]["n_test_images"] == 6
    assert sets["original_no_leak"]["segformer"]["n_test_images"] == 4
    assert sets["retrained"]["deeplabv3plus"]["n_test_images"] == 6
    assert sets["original_no_leak"]["segformer"]["per_disease_iou"]["wheat leaf rust"]["n"] == 2
    # segformer rows are 0.1 above deeplab rows on every image
    diff = sets["original"][rs.PAIRED]
    assert abs(diff["mean"] - 0.1) < 1e-9 and diff["excludes_zero"]


def test_markdown_has_three_columns_and_the_paired_row():
    table = rs.markdown_tables(rs.build_sets(_per_image(0.0), _per_image(0.1), leaked={"img0"}))
    header = table.splitlines()[0]
    assert "original (n = 6)" in header and "no leaked test images (n = 5)" in header and "retrained (n = 6)" in header
    assert "| paired IoU difference | SegFormer minus DeepLabV3+ | +0.100" in table
    assert "| leaf rust | SegFormer-B0 |" in table

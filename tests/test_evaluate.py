from src.evaluate import summarize


def test_summarize_overall_and_per_disease():
    per_image = [
        {"image_id": "a.jpg", "disease": "d1", "iou": 0.8, "dice": 0.9, "area_err": 0.1},
        {"image_id": "b.jpg", "disease": "d1", "iou": 0.6, "dice": 0.7, "area_err": 0.2},
        {"image_id": "c.jpg", "disease": "d2", "iou": 0.4, "dice": 0.5, "area_err": 0.3},
    ]

    result = summarize(per_image)

    assert result["n_test_images"] == 3
    assert abs(result["overall_iou"]["mean"] - 0.6) < 1e-9
    assert result["per_disease_iou"]["d1"]["n"] == 2
    assert result["per_disease_iou"]["d2"]["n"] == 1
    assert abs(result["per_disease_iou"]["d1"]["mean"] - 0.7) < 1e-9
    assert abs(result["per_disease_iou"]["d2"]["mean"] - 0.4) < 1e-9

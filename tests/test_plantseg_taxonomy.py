from src.data.plantseg_taxonomy import CLASSES, CROP_ALIASES, class_name_from_file_name, plant_of


def test_classes_has_116_entries() -> None:
    assert len(CLASSES) == 116
    assert CLASSES[0] == ""


def test_plant_of_single_word() -> None:
    assert plant_of("apple black rot") == "apple"
    assert plant_of("tomato early blight") == "tomato"


def test_plant_of_bell_pepper() -> None:
    assert plant_of("bell pepper bacterial spot") == "bell pepper"


def test_plant_of_grapevine_aliases_to_grape() -> None:
    assert plant_of("grapevine leafroll disease") == "grape"
    assert plant_of("grape black rot") == "grape"


def test_class_name_from_file_name_numeric_suffix() -> None:
    assert class_name_from_file_name("apple_black_rot_1.jpg") == "apple black rot"


def test_class_name_from_file_name_google_suffix() -> None:
    assert class_name_from_file_name("apple_black_rot_google_0005.jpg") == "apple black rot"


def test_class_name_from_file_name_longest_match_wins() -> None:
    # "bell_pepper_bacterial_spot_..." must not be mis-parsed as a shorter
    # unrelated prefix - there's no such collision in PlantSeg today, but this
    # guards the sort-by-length logic regardless.
    assert class_name_from_file_name("bell_pepper_bacterial_spot_12.jpg") == "bell pepper bacterial spot"


def test_class_name_from_file_name_unknown_returns_none() -> None:
    assert class_name_from_file_name("not_a_real_class_1.jpg") is None


def test_crop_aliases_cover_all_candidates_from_claude_md() -> None:
    expected = {
        "tomato", "chilli/pepper", "rice", "potato", "maize/corn",
        "wheat", "cotton", "grape", "mango", "banana",
    }
    assert set(CROP_ALIASES) == expected


def test_crop_aliases_unsupported_crops_are_empty() -> None:
    # PlantSeg has no cotton or mango classes at all.
    assert CROP_ALIASES["cotton"] == ()
    assert CROP_ALIASES["mango"] == ()

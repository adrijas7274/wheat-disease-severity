from src.data.build_skip_contact_sheet import skip_rows


def test_skip_rows_filters_to_skip_tag(tiny_config: dict) -> None:
    rows = skip_rows(tiny_config)
    assert {r["name"] for r in rows} == {"stripe_4.jpg"}

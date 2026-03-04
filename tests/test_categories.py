from ygg_torznab.adapters.nostr.categories import (
    TORZNAB_CATEGORIES,
    TORZNAB_TO_YGG,
    YGG_TO_TORZNAB,
    torznab_cats_to_tags,
    torznab_cats_to_ygg_subcats,
)


def test_ygg_to_torznab_contains_expected_mappings() -> None:
    assert YGG_TO_TORZNAB[2183] == 2000  # Film -> Movies
    assert YGG_TO_TORZNAB[2184] == 5000  # Serie TV -> TV
    assert YGG_TO_TORZNAB[2148] == 3000  # Musique -> Audio


def test_torznab_to_ygg_reverse_mapping() -> None:
    # Movies (2000) should include Film (2183)
    assert 2183 in TORZNAB_TO_YGG[2000]
    # TV (5000) should include Serie TV (2184) and Emission TV (2182)
    assert 2184 in TORZNAB_TO_YGG[5000]
    assert 2182 in TORZNAB_TO_YGG[5000]


def test_torznab_to_ygg_sorted() -> None:
    for ygg_ids in TORZNAB_TO_YGG.values():
        assert ygg_ids == sorted(ygg_ids)


def test_torznab_categories_all_have_id_and_name() -> None:
    for cat in TORZNAB_CATEGORIES:
        assert "id" in cat
        assert "name" in cat
        assert isinstance(cat["id"], int)
        assert isinstance(cat["name"], str)


def test_torznab_cats_to_ygg_subcats_single() -> None:
    result = torznab_cats_to_ygg_subcats([2000])
    assert 2183 in result  # Film


def test_torznab_cats_to_ygg_subcats_multiple() -> None:
    result = torznab_cats_to_ygg_subcats([2000, 5000])
    assert 2183 in result  # Film
    assert 2184 in result  # Serie TV


def test_torznab_cats_to_ygg_subcats_deduplicates() -> None:
    result = torznab_cats_to_ygg_subcats([2000, 2000])
    assert len(result) == len(set(result))


def test_torznab_cats_to_ygg_subcats_unknown() -> None:
    result = torznab_cats_to_ygg_subcats([9999])
    assert result == []


def test_torznab_cats_to_ygg_subcats_empty() -> None:
    result = torznab_cats_to_ygg_subcats([])
    assert result == []


def test_torznab_cats_to_ygg_subcats_sorted() -> None:
    result = torznab_cats_to_ygg_subcats([5070])  # TV/Anime -> 2178, 2179
    assert result == sorted(result)
    assert 2178 in result
    assert 2179 in result


# --- Nostr #t tag mapping tests ---


def test_torznab_cats_to_tags_movies() -> None:
    tags = torznab_cats_to_tags([2000])
    assert "film" in tags


def test_torznab_cats_to_tags_tv() -> None:
    tags = torznab_cats_to_tags([5000])
    assert "série-tv" in tags or "série tv" in tags


def test_torznab_cats_to_tags_empty() -> None:
    assert torznab_cats_to_tags([]) == []


def test_torznab_cats_to_tags_unknown() -> None:
    assert torznab_cats_to_tags([9999]) == []


def test_torznab_cats_to_tags_sorted() -> None:
    tags = torznab_cats_to_tags([2000, 5000])
    assert tags == sorted(tags)


def test_torznab_cats_to_tags_deduplicates() -> None:
    tags = torznab_cats_to_tags([2000, 2000])
    assert len(tags) == len(set(tags))

from clipper.metadata import campaigns as C


def test_kai_only_on_kai():
    assert C.eligible("Kai", ["Kai Cenat"]) == ["kai"]


def test_lacy_with_jason_goes_to_lacy_and_core_not_jason():
    keys = C.eligible("Lacy", ["JasonTheWeen"])
    assert set(keys) == {"core", "lacy", "lacy_gta"}


def test_lacy_alone_no_core():
    assert set(C.eligible("lacy", [])) == {"lacy", "lacy_gta"}


def test_non_gta_lacy_skips_marathon():
    assert C.eligible("Lacy", [], gta6=False) == ["lacy"]


def test_core_youtube_source():
    keys = C.eligible("Lacy", ["Adapt"], source="core_yt", gta6=False)
    assert "core_yt" in keys and "core" not in keys and "lacy" in keys


def test_caption_has_all_tags_and_passes_checks():
    keys = C.eligible("Lacy", ["Jason"])
    cap = C.caption("loses it in the CORE GTA 6 marathon 💀", "Lacy", ["Jason"], keys, extra=["#GTA6"])
    for t in ("#CORE", "#Lacy", "#JasonTheWeen", "#GTA6"):
        assert t in cap
    assert cap.startswith("Lacy:")
    assert C.problems("LACY CAN'T STOP CRASHING", cap, keys, "Lacy") == []


def test_problems_flags_missing_name_and_serbian():
    keys = ["kai"]
    assert C.problems("he is so mad", "Kai Cenat ljut #KaiCenat", keys, "Kai")[0].startswith("on-screen")
    assert any("non-English" in p for p in C.problems("KAI CENAT čeka", "#KaiCenat", keys, "Kai"))

from clipper.metadata.post_kit import as_text, build


def test_post_kit_all_platforms():
    k = build(lines=["POV: it's November 19\nand you finally load in", "welcome to Leonida."], days=5,
              topics=["lucia", "x"], sound="Song", sound_ref="https://t/1")
    assert k["hook"] == "POV: it's November 19 and you finally load in… welcome to Leonida."
    assert "#gta6" in k["tiktok"]["caption"] and "#gta6countdown" in k["tiktok"]["caption"] and "#lucia" in k["tiktok"]["caption"]
    assert len(k["tiktok"]["hashtags"]) <= 6
    assert k["youtube"]["title"].endswith("#Shorts") and len(k["youtube"]["title"]) <= 100
    assert "5 days left" in k["youtube"]["description"] and len(k["x"]["text"]) <= 280
    assert k["tiktok"]["cover_text"] == "POV: it's November 19 and you finally load in"
    assert "YOUTUBE SHORTS" in as_text(k)


def test_post_kit_landscape_and_countdown():
    k = build(lines=["5 DAYS", "ARE YOU READYYYYYY"], days=5, orientation="landscape")
    assert k["hook"].startswith("5 days.") and "youtube_shorts" in k["platforms"]   # every video goes to both
    assert "YOUTUBE SHORTS" in as_text(k)
    k0 = build(lines=[], days=0)
    assert "#gta6countdown" not in k0["tiktok"]["caption"] and "out now" in k0["youtube"]["description"]

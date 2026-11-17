import numpy as np

from clipper.editing import lyric_fx as L


def _frame():
    f = np.full((1920, 1080, 3), 100, np.uint8)
    f[656:1264] = (40, 120, 200)
    return f


def test_red_word_and_white_word_draw_on_picture():
    o = L.Overlay([{"type": "word", "t0": 0, "t1": 1, "text": "ATTENTION", "style": "red"}], (656, 608))
    out = o.draw(_frame(), 0.5)
    mid = out[900:1020]
    assert (mid[..., 2] > 180).sum() > 2000          # red letters in the middle of the picture
    o2 = L.Overlay([{"type": "word", "t0": 0, "t1": 1, "text": "TESTIFY"}], (656, 608))
    assert (o2.draw(_frame(), 0.5)[900:1020].min(-1) > 220).sum() > 500   # white letters


def test_mask_shows_picture_only_inside_letters():
    o = L.Overlay([{"type": "mask", "t0": 0, "t1": 1, "text": "HEAVEN"}], (656, 608))
    out = o.draw(_frame(), 0.5)
    assert out[100:300].max() == 0                    # outside the word: black
    assert out[880:1040].max() > 100                  # inside the word: footage


def test_window_and_caption():
    o = L.Overlay([{"type": "window", "t0": 0, "t1": 1, "from": 0.2, "to": 0.2}], (656, 608))
    out = o.draw(_frame(), 0.5)
    assert out[960, 540].max() > 0 and out[700, 50].max() == 0
    cap = L.caption_rgba("GTA 6 in 2 days btw \U0001F62E‍\U0001F4A8", 50)
    assert cap.shape[2] == 4 and cap.shape[1] > 300


def test_no_show_outside_time():
    o = L.Overlay([{"type": "word", "t0": 1, "t1": 2, "text": "SKY", "style": "red"}], (656, 608))
    assert np.array_equal(o.draw(_frame(), 0.5), _frame())

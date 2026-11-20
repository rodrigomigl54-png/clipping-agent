"""Compare what Whisper heard in each narration section with the script; list sections with missing/extra words.
Usage: python qa.py [vo_dir]  -> prints suspicious sections (to regenerate: delete their wav + json, rerun voice.py)."""
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
VO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/claude-0/lf2vo")
ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                   "fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
SCALE = {"hundred": 100, "thousand": 1000, "million": 10 ** 6}


def numify(words):
    out, cur, total, inside = [], 0, 0, False
    for w in words + ["<end>"]:
        parts = w.split("-")
        if all(p in ONES or p in TENS for p in parts) or w in SCALE or (w == "and" and inside):
            inside = True
            if w in SCALE:
                cur = max(cur, 1) * SCALE[w]
                if SCALE[w] >= 1000:
                    total, cur = total + cur, 0
            elif w != "and":
                cur += sum(ONES.get(p, TENS.get(p, 0)) for p in parts)
            continue
        if inside:
            out.append(str(total + cur))
            total, cur, inside = 0, 0, False
        if w != "<end>":
            out.append(w)
    return out


def norm(text):
    text = text.lower().replace("gta vi", "gta 6").replace("gta v", "gta 5").replace("%", " percent")
    text = re.sub(r"(\d),(\d)", r"\1\2", text)
    toks = re.findall(r"[a-z0-9']+(?:-[a-z]+)*", text)
    toks = numify(toks)
    return [t.replace("'", "") for t in toks]


def main():
    script = json.loads((HERE / "script.json").read_text())
    bad = []
    for sec in script["sections"]:
        p = VO / f"{sec['id']}.wav.json"
        if not p.exists():
            continue
        heard = json.loads(p.read_text())["heard"]
        a, b = norm(sec["text"]), norm(heard)
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        diffs = [(op, " ".join(a[i1:i2]), " ".join(b[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
        miss = sum(i2 - i1 for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("delete", "replace"))
        extra = sum(j2 - j1 for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("insert", "replace"))
        flag = miss + extra > 3 or any(op == "insert" for op, *_ in diffs) or any(op == "delete" and len(x.split()) > 1 for op, x, _ in diffs)
        print(f"{'!!' if flag else 'ok'} {sec['id']:6s} ratio {sm.ratio():.3f}  {diffs[:6]}")
        if flag:
            bad.append(sec["id"])
    print("REGENERATE:", " ".join(bad))


if __name__ == "__main__":
    main()

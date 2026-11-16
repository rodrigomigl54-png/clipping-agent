import sys, json; sys.path.insert(0, '/home/user/clipping-agent')
from pathlib import Path
from clipper.editing import template_edit as T
from clipper.editing.hype_editor import Shot
from clipper.cli import App, _post_kit
from clipper.metadata.post_kit import as_text
src = '/home/user/clipping-agent/assets/footage/gta5/trailer.mp4'
BAR = 0.1
def sh(a, b, cx=0.5): return Shot(src=src, start=a, end=b, motion=0.03, peak=a, bright=80, sat=80, hue=20, sharp=600, detail=0.1, cx=cx, bar=BAR)
tpl = json.load(open('/home/user/clipping-agent/config/hype_templates/tanart_lossantos.json'))
tpl['transition'] = 'none'; tpl['orientation'] = 'landscape'
c = [0.0] + tpl['cuts'] + [tpl['duration']]
plan = [(6.0, 9.07, 6.35, 1.0, 0.62), (11.6, 13.15, 11.62, 0.55, 0.5), (9.07, 11.6, 9.08, 0.93, 0.5),
        (29.73, 31.33, 29.74, 0.59, 0.5), (19.87, 22.8, 19.9, 1.0, 0.5), (42.47, 45.8, 42.5, 1.0, 0.5),
        (22.8, 27.27, 23.0, 1.0, 0.45), (62.6, 64.33, 62.62, 0.65, 0.5), (39.4, 42.47, 39.45, 1.0, 0.68),
        (69.47, 70.67, 69.48, 0.45, 0.5), (70.67, 72.25, 70.7, 0.55, 0.5), (72.25, 76.0, 73.0, 1.0, 0.5)]
fills = [T.Fill(c[i], c[i + 1], sh(a, b, cx), s0, sp) for i, (a, b, s0, sp, cx) in enumerate(plan)]
out = Path('/home/user/clipping-agent/outputs/_PRIVATE_TEST/GTA6/2026-11-16/PRIVATE-TEST_gta6_tanart_lossantos_3d.mp4')
res = T.render_template(tpl, fills, out, {"days": 3}, audio_from='/home/user/clipping-agent/assets/hype_refs/tanart_lossantos.mp4',
                        src_size=(1280, 720))
kit = _post_kit(App(), tpl, 3)
kit["tiktok"]["caption"] = "13 years in Los Santos… 3 days left 💔 #gta5 #gta6 #lossantos #gtav #nostalgia"
kit["youtube"]["title"] = "Goodbye Los Santos… GTA 6 in 3 Days 💔 #Shorts"
kit["tiktok"]["cover_text"] = "I'm really gonna miss Los Santos"
out.with_suffix('.post.txt').write_text(as_text(kit, 'tanart_lossantos'))
json.dump({**res, "post": kit, "template": "tanart_lossantos"}, open(out.with_suffix('.json'), 'w'), indent=2, ensure_ascii=False)
print(res['file'], res['duration'], res['upscale'], res['size'])

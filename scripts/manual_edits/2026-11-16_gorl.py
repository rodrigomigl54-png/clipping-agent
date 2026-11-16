import sys, json; sys.path.insert(0, '/home/user/clipping-agent')
from pathlib import Path
from clipper.editing import template_edit as T
from clipper.editing.hype_editor import Shot
from clipper.metadata.post_kit import build, as_text
src = '/home/user/clipping-agent/assets/footage/gta6_launch/launch.mp4'
def sh(a, b, cx): return Shot(src=src, start=a, end=b, motion=0.03, peak=a, bright=80, sat=80, hue=20, sharp=600, detail=0.1, cx=cx, bar=0.056)
tpl = {"id": "clips51_gorl", "orientation": "vertical", "duration": 10.308, "transition": "none", "fade_out_from": None,
       "text": [{"type": "counter", "ease": True, "t0": 0.6, "t1": 10.308, "t_stop": 7.0, "from": 100, "to": "{days}",
                 "suffix": "DAYS", "size": 0.17, "y": 0.5}],
       "text_style": {"glow": 0.3}}
fills = [T.Fill(0.0, 3.0, sh(25.73, 27.2, 0.33), 25.76, 0.46),
         T.Fill(3.0, 5.0, sh(62.53, 63.4, 0.52), 62.54, 0.4),
         T.Fill(5.0, 7.6, sh(39.8, 41.67, 0.62), 39.83, 0.66),
         T.Fill(7.6, 10.308, sh(25.73, 27.2, 0.33), 25.74, 0.5)]
out = Path('/home/user/clipping-agent/outputs/_PRIVATE_TEST/GTA6/2026-11-16/PRIVATE-TEST_gta6_clips51_gorl_3d.mp4')
res = T.render_template(tpl, fills, out, {"days": 3}, audio_from='/home/user/clipping-agent/assets/hype_refs/clips51_gorl.mp4',
                        src_size=(1920, 1080))
kit = build(lines=["G or L for the music?", "3 DAYS"], days=3, seed="clips51_gorl", sound="original sound (end0rsement)",
            sound_ref="https://www.tiktok.com/@gta.6.clips51/video/7707992694819212576")
kit["hook"] = "G or L for the music? 🎵 3 days."
kit["tiktok"]["caption"] = "G or L for the music? 🎵 3 days. #gta6 #gtavi #gta6countdown #lucia #gta6edit"
kit["youtube"]["title"] = "GTA 6 in 3 Days… G or L for the music? 🎵 #Shorts"
out.with_suffix('.post.txt').write_text(as_text(kit, 'clips51_gorl'))
json.dump({**res, "post": kit, "template": "clips51_gorl"}, open(out.with_suffix('.json'), 'w'), indent=2, ensure_ascii=False)
print(res['file'], res['duration'], res['upscale'])

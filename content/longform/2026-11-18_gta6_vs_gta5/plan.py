"""Shot plan for long-form #1 (GTA 6 vs GTA 5). Keys = sentence index in the section (script sentences);
each beat lasts until the next key. Shot refs: 'v:gp|tr|of|ng:<start>' = GTA V footage, '6:t1|t2|fe|pl|la:<start>' =
GTA VI footage (starts from data/shot_cache). Graphics: items / counter / stars / stamp / title (clipper.editing.longform).
"""

I = lambda text, on, **k: {"text": text, "on": on, **k}          # noqa: E731

PLAN = {
 "hook": {
  0: {"shots": ["v:tr:62.6", "v:tr:69.47"]},
  1: {"split": [["v:gp:24.07", "6:la:4.4"]]},
  2: {"split": [["v:gp:22.0", "6:t1:31.07"]]},
  3: {"shots": ["6:t2:152.87", "6:la:39.8", "6:t1:32.6"]},
  4: {"shots": ["6:la:46.33"], "kw": "COPS REMEMBER YOU"},
  5: {"shots": ["6:la:72.13", "6:la:52.33"], "kw": "LIMITED WEAPONS"},
  6: {"shots": ["6:la:41.67"], "kw": "CASH ISN'T SAFE"},
  7: {"g": "title", "bg": "6:t2:6.33", "lines": ["GTA V  vs  GTA VI", "15 BIGGEST DIFFERENCES"]},
  8: {"shots": ["6:t2:117.93", "6:la:60.2"]},
  9: {"shots": ["6:t1:2.67", "6:la:13.53"], "src": "SOURCES: ROCKSTAR + HANDS-ON PREVIEWS"},
 },
 "15": {
  0: {"card": True, "bg": "6:t1:18.4"},
  1: {"shots": ["v:gp:38.13", "v:tr:6.33", "v:gp:11.87"]},
  2: {"shots": ["v:gp:24.07", "v:gp:29.93"]},
  3: {"shots": ["6:t1:18.4", "6:t1:32.6"]},
  4: {"shots": ["6:t2:6.33"]},
  5: {"shots": ["6:la:2.0", "6:la:13.53"]},
  6: {"shots": ["6:t1:21.73", "6:t2:138.13", "6:t1:27.47"]},
  7: {"split": [["v:gp:25.93", "6:t2:152.87"]]},
 },
 "14": {
  0: {"card": True, "bg": "6:t2:6.33"},
  1: {"shots": ["v:gp:131.4", "v:gp:129.87"]},
  2: {"g": "items", "bg": "6:t2:6.33", "title": "LEONIDA · 6 REGIONS", "cols": 3, "items": [
      I("VICE CITY", "Vice", nth=1), I("LEONIDA KEYS", "Keys"), I("GRASSRIVERS", "Grassrivers"),
      I("PORT GELLHORN", "Gellhorn"), I("AMBROSIA", "Ambrosia"), I("MOUNT KALAGA", "Kalaga")]},
  9: {"g": "stamp", "bg": "6:la:4.4", "text": "OFFICIAL SIZE: NOT CONFIRMED", "sub": "every number online is an estimate"},
  11: {"shots": ["6:la:54.53", "6:t2:147.33", "6:t2:148.27"]},
 },
 "13": {
  0: {"card": True, "bg": "6:t1:19.2"},
  1: {"shots": ["v:gp:172.27", "v:gp:169.27", "v:ng:8.47"]},
  4: {"shots": ["6:t1:20.73"]},
  5: {"shots": ["6:t1:19.2", "6:t1:20.73", "6:t1:42.4"]},
  6: {"shots": ["6:la:27.2", "6:t2:138.13"]},
 },
 "12": {
  0: {"card": True, "bg": "6:t2:81.4"},
  1: {"shots": ["v:gp:15.07", "v:ng:38.53"]},
  3: {"shots": ["6:t1:2.67", "6:t2:81.4", "6:la:62.53"], "src": "SOURCE: EDGE PREVIEW"},
  4: {"g": "stamp", "bg": "6:la:4.4", "text": "TROPICAL STORMS + HURRICANES", "sub": "reported by Game Informer",
      "src": "SOURCE: GAME INFORMER"},
  5: {"g": "stamp", "bg": "6:t2:114.07", "text": "HOW OFTEN? NOT REVEALED", "sub": "Rockstar hasn't said"},
  6: {"shots": ["6:t2:119.67", "6:la:69.27"]},
 },
 "11": {
  0: {"card": True, "bg": "6:fe:43.73"},
  1: {"shots": ["v:gp:166.2", "v:gp:206.07", "v:gp:207.6"]},
  2: {"shots": ["v:ng:27.6"]},
  3: {"g": "items", "bg": "6:t2:138.13", "title": "SHOWN IN PREVIEWS", "cols": 4, "src": "SOURCE: PREVIEW COVERAGE", "items": [
      I("FAN BOATS", "fan"), I("BASKETBALL", "basketball", nth=1), I("SCUBA DIVING", "scuba"), I("KAYAKING", "kayaking"),
      I("BASE JUMPING", "BASE"), I("SKYDIVING", "skydiving"), I("DIRT BIKING", "dirt"), I("WEIGHTLIFTING", "weightlifting")]},
  4: {"shots": ["6:pl:4.53"]},
  5: {"shots": ["6:t1:55.0", "6:t2:140.07", "6:la:56.4"]},
 },
 "10": {
  0: {"card": True, "bg": "6:fe:12.4"},
  1: {"shots": ["v:of:7.73", "v:of:11.2", "v:gp:60.93"]},
  2: {"shots": ["6:fe:12.4"]},
  3: {"g": "items", "bg": "6:la:52.33", "title": "TRACKED STATS (PREVIEWS)", "cols": 3, "src": "SOURCE: PREVIEW REPORTS", "items": [
      I("HEALTH", "health"), I("CARDIO", "cardio"), I("STAMINA", "stamina"), I("STRENGTH", "strength"),
      I("CALORIES", "calories"), I("BODY FAT", "body"),
      I("GYM MEMBERSHIP", "membership", wide=True), I("3 EXERCISES / DAY", "exercises", wide=True)]},
  5: {"shots": ["6:t2:103.13"], "kw": "NOT FULLY EXPLAINED YET"},
 },
 "09": {
  0: {"card": True, "bg": "6:t1:46.53"},
  1: {"shots": ["v:gp:268.8"], "kw": "LIFEINVADER = A WEBSITE"},
  2: {"shots": ["6:t1:46.53"]},
  3: {"shots": ["6:t1:49.93", "6:t1:51.13", "6:t1:57.33"]},
  4: {"shots": ["6:fe:8.2"], "src": "SOURCE: ROCKSTAR · EXTENDED LOOK"},
  5: {"shots": ["6:t1:52.2", "6:t1:43.93"]},
 },
 "08": {
  0: {"card": True, "bg": "6:t1:21.73"},
  1: {"g": "counter", "bg": "6:t1:21.73", "src": "SOURCE: PREVIEW COVERAGE (EDGE)", "bars": [
      {"label": "GTA VI", "value": 600000, "on": "six", "color": "pink"},
      {"label": "GTA V", "value": 55000, "on": "fifty-five", "color": "grey"}], "title": "NPC ANIMATIONS"},
  3: {"shots": ["6:pl:3.4", "6:t2:118.87"]},
  4: {"shots": ["6:t1:21.73"]},
  5: {"shots": ["6:t1:54.0"]},
 },
 "07": {
  0: {"card": True, "bg": "6:la:63.4"},
  1: {"shots": ["v:tr:39.4", "v:ng:19.33", "v:ng:50.73"], "kw": "2013 · PS3 / XBOX 360"},
  2: {"g": "items", "bg": "6:t1:24.87", "title": "GTA VI AT LAUNCH", "cols": 2, "src": "SOURCE: ROCKSTAR NEWSWIRE", "items": [
      I("PLAYSTATION 5", "PlayStation"), I("XBOX SERIES X|S", "Xbox"), I("30 FPS TARGET", "thirty"),
      I("PS5 PRO: RAY-TRACED SHADOWS", "ray-traced", wide=True), I("NO PC AT LAUNCH", "PC", wide=True, color="red")]},
  5: {"shots": ["6:t1:31.07", "6:la:44.4"]},
 },
 "06": {
  0: {"card": True, "bg": "6:la:71.4"},
  1: {"shots": ["v:gp:104.47"]},
  2: {"g": "items", "bg": "v:gp:93.47", "title": "GTA V · 3 SPECIAL ABILITIES", "cols": 3, "items": [
      I("MICHAEL: BULLET TIME", "Michael"), I("FRANKLIN: DRIVING SLOW-MO", "Franklin"), I("TREVOR: RAGE", "Trevor")]},
  5: {"shots": ["6:la:64.2", "6:la:52.33"], "kw": "FOCUS", "slow": True, "src": "SOURCE: ROCKSTAR (VIA PREVIEWS)"},
  6: {"g": "items", "bg": "6:la:35.67", "title": "GTA VI · ONE SHARED ABILITY", "cols": 1, "items": [
      I("FOCUS · JASON + LUCIA", "Three", wide=True, color="pink")]},
 },
 "05": {
  0: {"g": "title", "bg": "6:la:38.33", "lines": ["THE TOP 5"]},
  1: {"shots": ["6:t2:117.93"]},
  2: {"card": True, "bg": "6:la:63.4"},
  3: {"shots": ["v:tr:57.2", "v:gp:158.73"]},
  5: {"shots": ["6:la:63.4", "6:t1:24.87"], "kw": "GPS TRACKER", "src": "SOURCE: EDGE PREVIEW"},
  6: {"shots": ["6:fe:31.53", "6:t2:120.73"]},
  7: {"shots": ["6:t1:32.6"]},
 },
 "04": {
  0: {"card": True, "bg": "6:la:41.67"},
  1: {"shots": ["v:gp:268.8", "v:gp:251.13"]},
  3: {"g": "items", "bg": "6:la:41.67", "title": "3 WAYS TO HOLD MONEY", "cols": 3, "src": "SOURCE: ROCKSTAR (VIA PREVIEWS)", "items": [
      I("CASH", "cash", nth=1, off="lose", offnote="LOST WHEN YOU DIE"), I("ATM CARD", "ATM", nth=1),
      I("BUCKME BANK", "BuckMe", note_on="safe", note="SAFE")]},
  6: {"shots": ["6:la:59.27"], "kw": "LOOT → FENCE"},
  7: {"shots": ["6:la:44.4", "6:t1:59.53"]},
 },
 "03": {
  0: {"card": True, "bg": "6:fe:42.6"},
  1: {"shots": ["v:gp:201.33", "v:gp:204.2"]},
  2: {"g": "items", "bg": "v:of:39.4", "title": "GTA V LOADOUT", "cols": 3, "items": [
      I("ROCKET LAUNCHER", "Rocket"), I("MINIGUN", "miniguns"), I("10 RIFLES", "ten"), I("ALL INVISIBLE", "invisible", wide=True, color="red")]},
  3: {"shots": ["6:fe:42.6"]},
  4: {"g": "items", "bg": "6:t2:74.87", "title": "GTA VI LOADOUT", "cols": 2, "src": "SOURCE: ROB NELSON (ROCKSTAR)", "items": [
      I("2 HANDGUNS · CONCEALED", "conceal", wide=True), I("LONG GUN #1 · ON YOUR BACK", "long", wide=True),
      I("LONG GUN #2 · IN YOUR HANDS", "second", wide=True), I("FULL LOADOUT · IN YOUR CAR", "loadout", wide=True)]},
  6: {"shots": ["6:t1:68.67", "6:t1:76.53"]},
 },
 "02": {
  0: {"card": True, "bg": "6:la:39.8"},
  1: {"shots": ["v:gp:58.27"]},
  2: {"shots": ["v:of:25.4"], "kw": "MICHAEL"},
  3: {"shots": ["v:of:33.27"], "kw": "FRANKLIN"},
  4: {"shots": ["v:of:11.2"], "kw": "TREVOR"},
  5: {"shots": ["6:la:39.8", "6:la:25.73"], "kw": "JASON + LUCIA"},
  6: {"shots": ["6:t1:6.53", "6:la:62.53"]},
  7: {"shots": ["6:t1:72.87", "6:t1:30.0"]},
  8: {"shots": ["v:gp:56.13"]},
  9: {"shots": ["6:la:66.4"]},
 },
 "01": {
  0: {"card": True, "bg": "6:la:70.2"},
  1: {"shots": ["v:tr:60.73"]},
  2: {"shots": ["v:of:48.47", "v:of:46.8"]},
  3: {"shots": ["6:la:70.2"]},
  4: {"shots": ["6:t1:48.6"], "kw": "WITNESS OR ALARM", "src": "SOURCE: ROB NELSON (ROCKSTAR)"},
  5: {"g": "items", "bg": "6:t2:114.07", "title": "THE POLICE REMEMBER", "cols": 3, "src": "SOURCE: ROB NELSON / GAMESRADAR", "items": [
      I("YOUR CAR", "car", nth=1, off="Swap"), I("YOUR CLOTHES", "clothes", off="outfit"), I("YOUR LOOK", "appearance", off="low")]},
  8: {"g": "stars", "bg": "6:t2:117.93", "on": "six", "title": "WANTED LEVEL"},
  9: {"shots": ["6:t1:64.6"], "kw": "CRIMINAL PROFILE", "src": "SOURCE: ROCKSTAR (VIA PREVIEWS)"},
  10: {"shots": ["v:tr:60.73"]},
  11: {"shots": ["6:t2:117.93"]},
 },
 "outro": {
  0: {"split": [["v:tr:62.6", "6:la:35.67"]]},
  1: {"g": "title", "bg": "6:la:35.67", "lines": ["13 YEARS"]},
  2: {"shots": ["v:tr:6.33", "v:gp:34.07"]},
  3: {"shots": ["6:t1:60.47", "6:la:57.87"]},
  4: {"shots": ["6:t1:2.67", "6:t2:152.87", "6:la:66.4"]},
  5: {"g": "title", "bg": "6:t2:152.87", "lines": ["WHICH DIFFERENCE", "ARE YOU MOST HYPED FOR?"]},
  6: {"g": "title", "bg": "6:la:35.67", "lines": ["SUBSCRIBE", "GTA 6 EVERY DAY"]},
  7: {"g": "end", "bg": "6:t2:140.07", "lines": ["SEE YOU IN LEONIDA"]},
 },
}

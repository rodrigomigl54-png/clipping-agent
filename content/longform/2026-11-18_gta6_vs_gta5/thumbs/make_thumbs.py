from comp import *
OUT='/home/user/clipping-agent/outputs/longform/thumbs/'
import os; os.makedirs(OUT,exist_ok=True)
outs=[]
# 1 VS split, Trevor vs Jason&Lucia
c=np.zeros((H,W,3),np.uint8)
c[:,:640]=grade(fit(bgcover('vinewood.png'),640,720,0.45),1.1,1.0,-25,2)
c[:,640:]=grade(fit(bgcover('vc_neon.png'),640,720,0.5),1.4,1.1,-15,2)
c=vignette(c,0.45)
place(c,cutout('trevor',620),-30,720); place(c,cutout('jl_car',600,glow=(200,120,255)),1300,720,'br')
cv2.circle(c,(640,400),95,(255,255,255),-1,cv2.LINE_AA); cv2.circle(c,(640,400),85,RED,-1,cv2.LINE_AA); over(c,T('VS',110,WHITE,6),640,398,1)
over(c,T('GTA 5',110,WHITE),190,90,1); over(c,T('GTA 6',110,YEL),1090,90,1); outs.append(('01_vs',c))
# 2 IT'S NOT GTA 5
c=vignette(grade(fit(bgcover('vc_neon.png'),W,H,0.5),1.45,1.1,-25,3),0.6)
place(c,cutout('lucia_balc',690,glow=(255,200,120)),1290,720,'br')
over(c,T("IT'S NOT",150,WHITE,12,-4),370,200,1); over(c,T('GTA 5!',190,YEL,14,-4),380,380,1)
over(c,T('15 HUGE CHANGES',62,WHITE,7),370,560,1); outs.append(('02_not_gta5',c))
# 3 COPS REMEMBER YOU
c=vignette(grade(fit(bgcover('burncop.png'),W,H,0.6),1.3,1.15,-10,1.5),0.6)
place(c,cutout('lucia_rifle',650),-20,720)
over(c,T('THE COPS',120,WHITE,11),900,170,1); over(c,T('REMEMBER YOU',120,RED,11),880,310,1)
for i in range(6):
    cx,cy,r=640+i*105,470,46
    pts=np.array([[cx+(r if j%2==0 else r*0.45)*np.cos(-np.pi/2+j*np.pi/5),cy+(r if j%2==0 else r*0.45)*np.sin(-np.pi/2+j*np.pi/5)] for j in range(10)],np.int32)
    cv2.fillPoly(c,[pts],WHITE,cv2.LINE_AA); cv2.polylines(c,[pts],True,(0,0,0),4,cv2.LINE_AA)
outs.append(('03_cops',c))
# 4 13 YEARS LATER Franklin -> Jason
c=np.zeros((H,W,3),np.uint8)
c[:,:640]=cv2.cvtColor(cv2.cvtColor(fit(bgcover('vinewood.png'),640,720,0.5),cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)//2+40
c[:,640:]=grade(fit(bgcover('lucia_balc.png'),640,720,0.3),1.5,1.1,-10,3)
c=vignette(c,0.4)
place(c,cutout('franklin',600),20,720); place(c,cutout('jason_phone',640,glow=(200,120,255)),1290,720,'br')
over(c,T('2013',90,(200,200,200)),170,80,1); over(c,T('2026',90,YEL),1110,80,1)
over(c,T('13 YEARS',130,WHITE,12),640,250,1); over(c,T('LATER...',130,YEL,12),640,390,1); outs.append(('04_13years',c))
# 5 DON'T PLAY GTA 6 LIKE GTA 5
c=vignette(grade(fit(bgcover('cop6.png'),W,H,0.4),1.3,1.1,-30,4),0.6)
place(c,cutout('jl_car',650,glow=(255,255,255)),1300,720,'br')
over(c,T("DON'T PLAY",120,WHITE,11,-3),370,150,1); over(c,T('GTA 6',170,YEL,13,-3),360,310,1); over(c,T('LIKE GTA 5',120,RED,11,-3),370,470,1)
outs.append(('05_dont_play',c))
# 6 EVERYTHING CHANGED  old/new labels, Trevor grey vs Lucia color
c=np.zeros((H,W,3),np.uint8)
g5=grade(fit(bgcover('trevor.png'),640,720,0.5),0.2,1.0,-30,6); c[:,:640]=g5
c[:,640:]=grade(fit(bgcover('vc_neon.png'),640,720,0.6),1.5,1.1,-20,4)
place(c,cutout('trevor',640,glow=(150,150,150)),0,720); place(c,cutout('lucia_balc',660,glow=(255,200,120)),1260,720,'br')
cv2.rectangle(c,(636,0),(644,720),WHITE,-1)
over(c,T('EVERYTHING',120,WHITE,11),640,110,1); over(c,T('CHANGED',120,YEL,11),640,235,1)
arrow(c,470,560,800,560); outs.append(('06_everything',c))
# 7 GTA 6 IS ON ANOTHER LEVEL - J&L convertible big
c=vignette(grade(fit(bgcover('lucia_balc.png'),W,H,0.35),1.45,1.1,-20,5),0.5)
place(c,cutout('jl_conv',560,glow=(255,255,255)),640,720,'bc')
over(c,T('GTA 6 vs GTA 5',96,WHITE,10),640,90,1); over(c,T('NOT EVEN CLOSE',112,YEL,12),640,210,1); outs.append(('07_not_close',c))
# 8 15 THINGS GTA 5 COULDN'T DO
c=vignette(grade(fit(bgcover('vc_neon.png'),W,H,0.5),1.4,1.1,-30,4),0.6)
place(c,cutout('jason_phone',700,glow=(200,120,255),flip=True),-40,720)
over(c,T('15 THINGS',125,YEL,12),900,180,1); over(c,T('GTA 5',125,WHITE,12),900,320,1); over(c,T("COULDN'T DO",125,RED,12),900,460,1)
outs.append(('08_15_things',c))
for n,c in outs: cv2.imwrite(OUT+f'{n}.jpg',c,[cv2.IMWRITE_JPEG_QUALITY,94])
small=[cv2.resize(c,(640,360)) for _,c in outs]
for i,(n,_) in enumerate(outs): cv2.putText(small[i],n,(8,350),0,0.7,(0,255,0),2)
cv2.imwrite('grid.jpg',np.vstack([np.hstack(small[i:i+2]) for i in range(0,8,2)]))
print('done')

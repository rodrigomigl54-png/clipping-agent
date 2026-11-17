from comp import *
OUT='/home/user/clipping-agent/outputs/longform/thumbs/'
def bright(f,cx=0.5,blur=0,sat=1.35,con=1.08,br=8,w=W,h=H):
    return grade(fit(bgcover(f),w,h,cx),sat,con,br,blur)
def giant(c,text,y,size=260,color=WHITE,stroke=14,shadow=True):
    im=text_rgba(text,'anton',size,color,stroke=stroke)
    if im.shape[1]>W-30: im=cv2.resize(im,None,fx=(W-30)/im.shape[1],fy=(W-30)/im.shape[1])
    if shadow:
        sh=im.copy(); sh[...,:3]=0; sh[...,3]=(cv2.GaussianBlur(sh[...,3].astype(np.float32),(0,0),12)*0.8).astype(np.uint8)
        over(c,sh,W/2+10,y+14,1)
    over(c,im,W/2,y,1)
def badge(c,text,x,y,bg,fg=WHITE,size=58):
    im=text_rgba(text,'anton',size,fg,stroke=0,shadow=False)
    from clipper.editing.longform import box
    box(c,x-im.shape[1]/2-22,y-im.shape[0]/2+6,x+im.shape[1]/2+22,y+im.shape[0]/2-6,bg,1.0,radius=14)
    over(c,im,x,y,1)
outs=[]
# M1 UPGRADED behind Jason, bright Vice City day
c=vignette(bright('vcsky.png',0.5,1.5),0.35)
giant(c,'UPGRADED',150,300)
place(c,cutout('jason_phone',640,stroke=6,glow=(255,255,255)),1290,725,'br')
badge(c,'GTA 5',150,640,(60,60,60)); arrow(c,250,640,360,640,22); badge(c,'GTA 6',460,640,(170,60,255))
outs.append(('M1_upgraded',c))
# M2 Glooby-style: GTA V world | GTA VI world, Lucia center
c=np.zeros((H,W,3),np.uint8)
c[:,:640]=bright('aerial5.png',0.45,1.2,1.2,1.05,0,640,720); c[:,640:]=bright('vcsky.png',0.4,1.2,1.4,1.08,8,640,720)
c=vignette(c,0.3)
for x,t,col in [(150,'GTA 5',(60,60,60)),(1130,'GTA 6',(170,60,255))]: badge(c,t,x,80,col,size=70)
place(c,cutout('lucia_conv',620,stroke=7,glow=(255,200,90)),640,735,'bc')
badge(c,'15 HUGE DIFFERENCES',640,660,(30,30,235),size=54)
outs.append(('M2_worlds',c))
# M3 13 YEARS behind Jason & Lucia, beach day
c=vignette(bright('beach6.png',0.5,6,1.4,1.05,10),0.35)
giant(c,'13 YEARS',165,310)
place(c,cutout('jl_conv',520,stroke=6),640,722,'bc')
badge(c,'GTA 5 → GTA 6',640,330,(30,30,235),size=56) if False else None
outs.append(('M3_13years',c))
# M4 NOT GTA 5 behind Jason & Lucia standing
c=vignette(bright('vcsky.png',0.65,4,1.5),0.35)
giant(c,'NOT GTA 5',140,290,YEL)
place(c,cutout('jl_car',560,stroke=6),640,760,'bc')
outs.append(('M4_not_gta5',c))
# M5 EVERYTHING CHANGED (Lucia close, Trevor small greyscale in corner)
c=vignette(bright('beach6.png',0.6,8,1.4,1.05,10),0.35)
giant(c,'CHANGED',150,300)
t=cutout('trevor',420,stroke=5,glow=(200,200,200)); g=cv2.cvtColor(cv2.cvtColor(t[...,:3],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR); t[...,:3]=g
place(c,t,30,720); badge(c,'2013',190,640,(60,60,60),size=46)
place(c,cutout('lucia_conv',600,stroke=7,glow=(255,200,90)),1290,740,'br')
badge(c,'2026',470,640,(170,60,255),size=46); arrow(c,280,640,390,640,22)
outs.append(('M5_changed',c))
for n,c in outs: cv2.imwrite(OUT+f'{n}.jpg',c,[cv2.IMWRITE_JPEG_QUALITY,94])
small=[cv2.resize(c,(640,360)) for _,c in outs]+[np.zeros((360,640,3),np.uint8)]
cv2.imwrite('modern.jpg',np.vstack([np.hstack(small[i:i+2]) for i in range(0,6,2)]))

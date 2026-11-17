import sys; sys.path.insert(0,'/home/user/clipping-agent')
import cv2, numpy as np
from clipper.editing.longform import text_rgba, over
W,H=1280,720
def bgcover(f, blur=0, sat=1.3, bright=1.0, x0=0.0, x1=1.0):
    im=cv2.imread(f); rows=np.where(im.mean((1,2))>8)[0]; im=im[rows.min():rows.max()+1]
    w=im.shape[1]; im=im[:,int(x0*w):int(x1*w)]
    return im
def fit(im,w,h,cx=0.5):
    s=max(w/im.shape[1],h/im.shape[0]); im=cv2.resize(im,None,fx=s,fy=s,interpolation=cv2.INTER_LANCZOS4)
    x=int(min(max(cx*im.shape[1]-w/2,0),im.shape[1]-w)); y=(im.shape[0]-h)//2; return im[y:y+h,x:x+w]
def grade(im,sat=1.35,con=1.15,br=0,blur=0):
    if blur: im=cv2.GaussianBlur(im,(0,0),blur)
    im=cv2.convertScaleAbs(im,alpha=con,beta=br); hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV).astype(np.float32); hsv[...,1]*=sat
    return cv2.cvtColor(np.clip(hsv,0,255).astype(np.uint8),cv2.COLOR_HSV2BGR)
def cutout(name,h,stroke=8,glow=(255,255,255),flip=False):
    a=cv2.imread(f'cut_{name}.png',cv2.IMREAD_UNCHANGED)
    if flip: a=a[:,::-1].copy()
    ys,xs=np.where(a[...,3]>40); a=a[ys.min():ys.max()+1,xs.min():xs.max()+1]
    s=h/a.shape[0]; a=cv2.resize(a,None,fx=s,fy=s,interpolation=cv2.INTER_LANCZOS4)
    pad=stroke*4; a=cv2.copyMakeBorder(a,pad,pad,pad,pad,cv2.BORDER_CONSTANT,value=(0,0,0,0))
    al=a[...,3]; k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*stroke+1,2*stroke+1)); dil=cv2.dilate(al,k)
    g=cv2.GaussianBlur(dil.astype(np.float32),(0,0),stroke*1.5)
    out=np.zeros_like(a,dtype=np.float32)
    col=np.array(glow,np.float32)
    outA=np.clip(np.maximum(dil, g*0.8),0,255)
    outA[-pad-2:,:]=al[-pad-2:,:]          # bottom is cut by the frame: no outline there
    out[...,:3]=col; out[...,3]=outA
    sub=a.astype(np.float32); sa=sub[...,3:4]/255
    out[...,:3]=sub[...,:3]*sa+out[...,:3]*(1-sa); out[...,3]=np.maximum(out[...,3],sub[...,3])
    # subject pop: contrast/saturation
    rgb=grade(out[...,:3].astype(np.uint8),1.25,1.12,5); out[...,:3]=rgb
    return out.astype(np.uint8)
def place(canvas,img,x,y,anchor='bl'):
    h,w=img.shape[:2]
    if anchor=='bl': x,y=x,y-h
    elif anchor=='br': x,y=x-w,y-h
    elif anchor=='bc': x,y=x-w//2,y-h
    over(canvas,img,x,y,1,anchor='tl')
def T(text,size,color,stroke=10,rot=0):
    im=text_rgba(text,'anton',size,color,stroke=stroke)
    if rot:
        h,w=im.shape[:2]; M=cv2.getRotationMatrix2D((w/2,h/2),rot,1); c,s=abs(M[0,0]),abs(M[0,1])
        nw,nh=int(h*s+w*c),int(h*c+w*s); M[0,2]+=nw/2-w/2; M[1,2]+=nh/2-h/2
        im=cv2.warpAffine(im,M,(nw,nh),flags=cv2.INTER_LINEAR,borderValue=(0,0,0,0))
    return im
def arrow(c,x0,y0,x1,y1,th=34,col=(30,30,235)):
    cv2.arrowedLine(c,(x0,y0),(x1,y1),(255,255,255),th+12,cv2.LINE_AA,tipLength=0.35)
    cv2.arrowedLine(c,(x0,y0),(x1,y1),col,th,cv2.LINE_AA,tipLength=0.35)
def vignette(c,s=0.55):
    yy,xx=np.mgrid[0:H,0:W]; d=np.sqrt(((xx-W/2)/(W/2))**2+((yy-H/2)/(H/2))**2); m=np.clip(1-s*(d-0.4),0.35,1)
    return (c*m[...,None]).astype(np.uint8)
YEL=(0,230,255); RED=(40,30,235); WHITE=(255,255,255); PINK=(170,60,255)

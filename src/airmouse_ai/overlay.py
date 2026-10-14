"""Small OpenCV overlay, rendered only at preview frequency in the vision process."""
import math

FINGERS = ((1,"T",(255,174,78), (0,1,2,3,4)),
           (2,"I",(65,220,255), (0,5,6,7,8)),
           (3,"M",(255,222,75), (5,9,10,11,12)),
           (4,"R",(205,145,255), (9,13,14,15,16)),
           (5,"P",(112,235,146), (13,17,18,19,20)))


def draw_preview(rgb, hand, mirror=True, landmarks=True):
    import cv2
    canvas=cv2.resize(rgb,(480,360),interpolation=cv2.INTER_AREA)
    if mirror:
        canvas=cv2.flip(canvas,1)
    valid = hand is not None and len(hand.points)==21 and all(
        len(p)==3 and all(math.isfinite(v) for v in p) for p in hand.points)
    if valid and landmarks:
        def pixel(i):
            x,y,_=hand.points[i]
            return (round(max(0,min(1,1-x if mirror else x))*479),
                    round(max(0,min(1,y))*359))
        for number,name,color,chain in FINGERS:
            for a,b in zip(chain,chain[1:]):
                cv2.line(canvas,pixel(a),pixel(b),color,2,cv2.LINE_AA)
            for i in chain[1:]:
                cv2.circle(canvas,pixel(i),4,color,-1,cv2.LINE_AA)
                cv2.circle(canvas,pixel(i),4,(15,25,35),1,cv2.LINE_AA)
            x,y=pixel(chain[-1])
            x=max(3,min(437,x+7)); y=max(52,min(351,y-9))
            label=f'{number}:{name}'
            cv2.putText(canvas,label,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.46,(10,20,30),3,cv2.LINE_AA)
            cv2.putText(canvas,label,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.46,color,1,cv2.LINE_AA)
        cv2.line(canvas,pixel(0),pixel(17),(112,235,146),2,cv2.LINE_AA)
    cv2.rectangle(canvas,(0,0),(479,31),(18,31,42),-1)
    text = ('HAND TRACKED | '+('3D' if hand.world_points else 'IMAGE XYZ')) if valid else 'NO HAND - keep fingers visible'
    cv2.putText(canvas,text,(10,21),cv2.FONT_HERSHEY_SIMPLEX,.49,
                (112,235,146) if valid else (235,210,180),1,cv2.LINE_AA)
    return canvas

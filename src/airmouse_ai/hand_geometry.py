"""Orientation-independent finger geometry. No Qt, OpenCV or native input."""
from dataclasses import dataclass
import math
from .config import Tuning


@dataclass(frozen=True)
class Hand:
    points: tuple[tuple[float,float,float], ...]
    aspect: float = 1.0
    world_points: tuple[tuple[float,float,float], ...] | None = None
    handedness: str = ""


@dataclass(frozen=True)
class Geometry:
    fingers: tuple[int,...]  # Extended=1, folded=0, uncertain=-1; never treat uncertainty as folded.
    curls: tuple[float,...]
    thumb: int
    pinch: float
    pinch_shape: bool
    palm: float
    local: tuple[tuple[float,float],...]
    fist: bool = False
    shortcut_ready: bool = False
    open_digits: tuple[bool,...] = (False,False,False,False,False)


def angle(a,b,c) -> float:
    u=tuple(x-y for x,y in zip(a,b)); v=tuple(x-y for x,y in zip(c,b))
    norm=math.sqrt(sum(x*x for x in u)*sum(x*x for x in v))
    if norm<1e-10:
        return 0.0
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(u,v))/norm))))


def valid(points) -> bool:
    return points is not None and len(points)==21 and all(
        len(p)==3 and all(math.isfinite(v) for v in p) for p in points)


def analyze(hand: Hand | None,t: Tuning=Tuning()) -> Geometry | None:
    try:
        if hand is None or not valid(hand.points) or not math.isfinite(hand.aspect) or hand.aspect<=0:
            return None
        image=tuple((x*hand.aspect,y,z*hand.aspect) for x,y,z in hand.points)
        image_palm=max(math.dist(image[5],image[17]),math.dist(image[0],image[9])*.8)
        if image_palm<t.min_palm:
            return None
        p=image
        palm=image_palm
        if valid(hand.world_points):
            scale=math.dist(hand.world_points[5],hand.world_points[17])
            if .005<scale<.25:
                p=hand.world_points
                palm=scale
        states=[]; curls=[]; distal_angles=[]; tucked=[]; opened=[]
        for mcp in (5,9,13,17):
            pip,dip,tip=mcp+1,mcp+2,mcp+3
            joint=angle(p[mcp],p[pip],p[dip])
            distal=angle(p[pip],p[dip],p[tip])
            length=sum(math.dist(p[a],p[b]) for a,b in ((mcp,pip),(pip,dip),(dip,tip)))
            straightness=math.dist(p[mcp],p[tip])/max(length,1e-8)
            opened.append(min(joint,distal)>=t.five_extended_angle and straightness>=t.five_straightness)
            folded=joint<t.folded_angle or straightness<t.folded_straightness
            tucked.append(folded and math.dist(p[mcp],p[tip])/palm<t.fist_tip_reach)
            if mcp==17:
                if joint>=t.pinky_extended_angle and distal>=t.pinky_extended_angle and straightness>=t.pinky_extended_straightness:
                    states.append(1)
                elif min(joint,distal)<=t.pinky_folded_angle or straightness<t.pinky_folded_straightness:
                    states.append(0)
                else:
                    states.append(-1)
            elif joint>=t.extended_angle and distal>=t.extended_angle and straightness>=t.extended_straightness:
                states.append(1)
            elif joint<t.folded_angle or straightness<t.folded_straightness:
                states.append(0)
            else:
                states.append(-1)
            curls.append(max(0,min(1,(180-min(joint,distal))/150)))
            distal_angles.append(distal)
        thumb_angle=angle(p[2],p[3],p[4])
        spread=math.dist(p[4],p[17])/max(1e-8,math.dist(p[3],p[17]))
        thumb=(1 if thumb_angle>=t.extended_angle and spread>t.thumb_reach else
               0 if thumb_angle<t.folded_angle or spread<t.thumb_fold_reach else -1)
        open_digits=(thumb_angle>=t.five_extended_angle and spread>=t.five_thumb_reach,*opened)
        pinch=math.dist(p[4],p[8])/palm
        # A tucked fist is not an opposed thumb/index pinch. Pinky is deliberately
        # excluded here: it freezes movement but may not silently release a held button.
        shape=(states[1:3]==[0,0] and distal_angles[0]>=t.pinch_distal_angle and
               math.dist(p[5],p[8])/palm>=t.pinch_index_reach)
        local=tuple(((hand.points[m+3][0]-hand.points[m][0])/image_palm,
                     (hand.points[m+3][1]-hand.points[m][1])/image_palm) for m in (5,9,13,17))
        return Geometry(tuple(states),tuple(curls),thumb,pinch,shape,image_palm,local,
                        all(tucked) and thumb==0 and not shape,
                        states==[0,0,1,1] and thumb!=1,open_digits)
    except (TypeError,ValueError,OverflowError):
        return None

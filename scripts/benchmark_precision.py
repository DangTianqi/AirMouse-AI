"""Algorithm-only fine pointer comparison with an archived v1.9 filter."""
import importlib.util,json,math,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from airmouse_ai.cursor import CursorFilter
spec=importlib.util.spec_from_file_location('airmouse_ai.cursor_v19',ROOT/'tests/fixtures/cursor_v19.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
def measure(factory):
    def make():
        f=factory(1920,1080);f.update_relative(0,0,False,anchor=(500,500),now=0);return f
    f=make();out=[]
    for i in range(1,25):
        p=f.update_relative(i*.003,0,False,now=i/24)
        if p:out.append(p[0])
    slow_steps=[b-a for a,b in zip(out,out[1:])]
    f=make();fine=[]
    for i in range(1,9):
        p=f.update_relative(i*.0005,0,False,now=i/24)
        if p:fine.append(p[0])
    micro=f.position[0]-500
    f=make()
    for i in range(1,49):f.update_relative(i*.0005,0,False,now=i/24)
    peak=f.position[0];reversal=None
    for i in range(1,49):
        f.update_relative(.024-i*.0005,0,False,now=2+i/24)
        if reversal is None and f.position[0]<peak-.5:reversal=i/24*1000
    f=make()
    for i in range(1,25):f.update_relative(i*.003,0,False,now=i/24)
    at_stop=f.position
    for i in range(1,101):f.update_relative(.072+.007*math.sin(i*1.7),.007*math.cos(i*2.1),False,now=1+i/24)
    stop_drift=math.dist(at_stop,f.position)
    rates={}
    for rate in (15,20,24,30):
        f=make()
        for i in range(1,rate*2+1):f.update_relative(.2*i/rate,0,False,now=i/rate)
        rates[rate]=round(f.position[0]-500,2)
    start=time.perf_counter()
    for i in range(10000):f.update_relative(.4+.007*math.sin(i),0,False,now=3+i/24)
    return {'slow_max_step_px':max(slow_steps),'slow_median_step_px':sorted(slow_steps)[len(slow_steps)//2],
      'micro_004_palm_travel_px':round(micro,3),'micro_integer_outputs':fine,
      'slow_reversal_first_pixel_ms':None if reversal is None else round(reversal,1),
      'stop_plus_tremor_total_drift_px':round(stop_drift,3),'same_stroke_fps_travel_px':rates,
      'filter_us_per_sample':round((time.perf_counter()-start)*1e6/10000,2)}
r={'scope':'Synthetic normalized finger input; unit direction multipliers; 1920x1080; no camera/OS input. Timing excludes acquisition/recognition.',
   'v1.9':measure(legacy.CursorFilter),'v1.10_precise':measure(CursorFilter)}
(ROOT/'artifacts').mkdir(exist_ok=True)
(ROOT/'artifacts/cursor-v1.10.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))

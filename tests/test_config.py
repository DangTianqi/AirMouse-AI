from dataclasses import asdict
import json
import pytest
from airmouse_ai.config import Settings, load, save


def test_save_load_atomic(tmp_path):
    p=tmp_path/'nested/config.json'
    s=Settings(scroll_speed=2.5, camera_index=2, preview=False)
    save(s,p)
    assert load(p)==s
    assert list(p.parent.glob('*.tmp'))==[]
    assert json.loads(p.read_text())==asdict(s)


def test_corrupt_and_invalid(tmp_path):
    p=tmp_path/'config.json'
    assert load(p)==Settings()
    p.write_text('{bad')
    assert load(p)==Settings()
    for raw in ([],None,{'camera_index':True,'preview':'false','scroll_speed':float('nan'),
                         'cursor_speed':99,'target_fps':-1,'version':99}):
        assert Settings.validated(raw)==Settings()


def test_all_multipliers_accept_ten_and_survive_restart(tmp_path):
    values={name:10.0 for name in ('scroll_speed','stabilization','cursor_up_speed',
                                 'cursor_down_speed','cursor_left_speed','cursor_right_speed')}
    s=Settings.validated({'version':4,**values})
    for name in values: assert getattr(s,name)==(9.9 if name=='cursor_down_speed' else 10)
    p=tmp_path/'config.json'; save(s,p)
    assert load(p)==s


@pytest.mark.parametrize('value',[0,-1,10.1,float('inf'),float('nan'),True,'10'])
def test_directional_settings_reject_invalid_values(value):
    for name in ('cursor_up_speed','cursor_down_speed','cursor_left_speed','cursor_right_speed'):
        assert getattr(Settings.validated({'version':4,name:value}),name)==getattr(Settings(),name)


def test_v2_shared_speed_migrates_to_directions_without_losing_preferences():
    s=Settings.validated({'version':2,'cursor_speed':2.0,'scroll_speed':2.5,
                          'landmarks':False,'preview':False,'stabilization':1.7})
    assert s.version==6 and s.cursor_up_speed==3.6
    assert s.cursor_down_speed==2.6 and s.cursor_left_speed==s.cursor_right_speed==2
    assert not s.landmarks and not s.preview and s.stabilization==1.7 and s.scroll_speed==2.5
    assert Settings.validated(asdict(s))==s


def test_current_direction_preferences_are_independent():
    s=Settings.validated({'version':4,'cursor_up_speed':7.1,'cursor_down_speed':.5,
                          'cursor_left_speed':3.4,'cursor_right_speed':10})
    assert (s.cursor_up_speed,s.cursor_down_speed,s.cursor_left_speed,s.cursor_right_speed)==(7.1,.5,3.4,10)


@pytest.mark.parametrize('version',[1,2,3,4,5])
def test_old_default_scroll_upgrades_once_and_custom_values_survive(version,tmp_path):
    s=Settings.validated({'version':version,'scroll_speed':1.0})
    assert s.version==6 and s.scroll_speed==2.0
    custom=Settings.validated({'version':version,'scroll_speed':3.3})
    assert custom.scroll_speed==3.3
    s.scroll_speed=1.0
    path=tmp_path/'config.json'; save(s,path)
    assert load(path).version==6 and load(path).scroll_speed==1.0

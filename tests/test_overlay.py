import numpy as np
from airmouse_ai.overlay import draw_preview
from conftest import hand_pose


def test_overlay_labels_stay_readable_in_both_mirror_modes(monkeypatch):
    import cv2
    original=cv2.putText
    labels=[]
    def put(*args,**kwargs):
        labels.append(args[1])
        return original(*args,**kwargs)
    monkeypatch.setattr(cv2,'putText',put)
    for mirror in (False,True):
        labels.clear()
        image=draw_preview(np.zeros((480,640,3),dtype=np.uint8),hand_pose('open'),mirror)
        assert image.shape==(360,480,3)
        for label in ('1:T','2:I','3:M','4:R','5:P'):
            assert label in labels
        assert any('HAND TRACKED' in label for label in labels)
    labels.clear()
    draw_preview(np.zeros((480,640,3),dtype=np.uint8),None)
    assert any('NO HAND' in label for label in labels)

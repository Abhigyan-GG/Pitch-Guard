import cv2
import numpy as np

from src.pitchguard import CORNERS, project, synthetic_frame
from src.vision import CameraRegistration, KitClassifier, Observation


def test_torso_kit_assignment_and_abstention():
    classifier=KitClassifier('#e62d2d','#1e5fe6')
    frame=np.full((200,300,3),(40,110,40),np.uint8)
    frame[30:100,30:90]=(45,45,230)
    obs=Observation([20,10,100,180],[60,180],.9)
    classifier.assign(frame,obs);assert obs.team=='own'
    empty=Observation([150,10,210,180],[180,180],.9)
    classifier.assign(frame,empty);assert empty.team=='unknown'


def test_camera_transform_and_cut_rejection():
    frame,_=synthetic_frame()
    camera=CameraRegistration(frame,CORNERS,moving=True)
    transform=np.float32([[1,0,9],[0,1,6],[0,0,1]])
    moved=cv2.warpPerspective(frame,transform,(960,600))
    H,status=camera.update(moved)
    assert status['valid'] and status['validation_error_px']<3
    image_point=project([[400,300]],transform)
    expected=project([[400,300]],camera.initial_H)
    np.testing.assert_allclose(project(image_point,H),expected,atol=.4)
    lost,quality=camera.update(np.zeros_like(frame))
    assert lost is None and not quality['valid']


def test_fixed_mode_rejects_camera_movement():
    frame,_=synthetic_frame();camera=CameraRegistration(frame,CORNERS,moving=False)
    moved=cv2.warpAffine(frame,np.float32([[1,0,12],[0,1,5]]),(960,600))
    H,status=camera.update(moved)
    assert H is None and not status['valid']

"""Real ArUco pixels: identity, direction, perspective, geometry and missing frames."""
import math
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vision.robot_vision import detect_robot, exclude_robot_regions

TEST_CONFIG = dict(marker_id=0, marker_size_mm=50, body_length_mm=100,
                   body_width_mm=150, center_offset_right_mm=0, center_offset_forward_mm=0)


def paste_marker(image, center, size=100, turns=0, marker_id=0):
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = np.rot90(cv2.aruco.generateImageMarker(dictionary, marker_id, size), turns).copy()
    x,y = [round(v-size/2) for v in center]
    cv2.rectangle(image,(x-15,y-15),(x+size+14,y+size+14),(255,255,255),-1)
    image[y:y+size,x:x+size] = cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
    return image


def main():
    for angle in (0,45,90,180,270):
        image=paste_marker(np.full((800,800,3),210,np.uint8),(400,400),120,3)
        image=cv2.warpAffine(image,cv2.getRotationMatrix2D((400,400),angle,1),(800,800),borderValue=(210,210,210))
        robot=detect_robot(image,TEST_CONFIG)
        assert robot['heading_valid'] and robot['geometry_valid'],(angle,robot)
        error=(robot['heading_rad']-math.radians(angle)+math.pi)%(2*math.pi)-math.pi
        assert abs(error)<.04,(angle,robot)
        assert np.linalg.norm(np.array(robot['center_px'])-[400,400])<3
    image=np.full((800,800,3),210,np.uint8)
    paste_marker(image,(200,200),marker_id=1)
    assert not detect_robot(image,TEST_CONFIG)['detected']
    paste_marker(image,(400,400))
    assert detect_robot(image,TEST_CONFIG)['marker_id']==0
    paste_marker(image,(600,600))
    assert not detect_robot(image,TEST_CONFIG)['detected'],'Duplicate ID accepted'
    for x,y in ((260,260),(260,540),(500,240),(500,560)):
        cv2.circle(image,(x,y),27,(0,0,230),-1)
    assert not detect_robot(np.full((800,800,3),210,np.uint8),TEST_CONFIG)['detected']
    wheels=np.full((800,800,3),210,np.uint8)
    for x,y in ((260,260),(260,540),(500,240),(500,560)):
        cv2.circle(wheels,(x,y),27,(0,0,230),-1)
        cv2.circle(wheels,(x,y),13,(15,15,15),-1)
    assert not detect_robot(wheels,TEST_CONFIG)['detected'],'Wheel fallback still active'
    image=paste_marker(np.full((800,800,3),210,np.uint8),(400,400))
    car=detect_robot(image,TEST_CONFIG)
    assert exclude_robot_regions([{'bbox_px':[360,380,10,10]}, {'bbox_px':[50,50,10,10]}],car)==[{'bbox_px':[50,50,10,10]}]
    # Wheel boxes can straddle a body edge with their centres OUTSIDE it.
    # Rotations exercise corners too; a clear block in front must remain visible.
    for angle in (0,30,90,145):
        matrix=cv2.getRotationMatrix2D((400,400),angle,1)
        hull=cv2.transform(np.float32([[[300,350],[500,350],[500,450],[300,450]]]),matrix)[0]
        body={'detected':True,'geometry_valid':True,'body_polygon_px':hull.tolist()}
        edge=cv2.transform(np.float32([[[400,340]]]),matrix)[0,0]
        wheel={'bbox_px':[float(edge[0]-15),float(edge[1]-15),30,30]}
        assert cv2.pointPolygonTest(hull,tuple(map(float,edge)),False)<0
        distant={'bbox_px':[100,100,20,20]}
        assert exclude_robot_regions([wheel,distant],body)==[distant],(angle,wheel)
    body={'detected':True,'geometry_valid':True,
          'body_polygon_px':[[300,350],[500,350],[500,450],[300,450]]}
    front_block={'bbox_px':[390,325,20,20]}  # Five pixels clear of car, kept.
    assert exclude_robot_regions([front_block],body)==[front_block]
    no_size=detect_robot(image,{**TEST_CONFIG,'body_width_mm':None})
    assert no_size['heading_valid'] and not no_size['geometry_valid']
    assert len(exclude_robot_regions([{'bbox_px':[360,380,10,10]}],no_size))==1
    offset=detect_robot(image,{**TEST_CONFIG,'center_offset_right_mm':10,'center_offset_forward_mm':20})
    assert np.linalg.norm(np.array(offset['center_px'])-[419.3,359.9])<2,offset
    warped=cv2.warpPerspective(image,cv2.getPerspectiveTransform(np.float32([[0,0],[799,0],[799,799],[0,799]]),np.float32([[90,30],[730,80],[790,730],[20,790]])),(800,800),borderValue=(210,210,210))
    assert detect_robot(warped,TEST_CONFIG)['heading_valid']
    asset=cv2.imdecode(np.fromfile(Path(__file__).with_name('markers')/'aruco-4x4-50-id0.png',np.uint8),1)
    assert detect_robot(asset,TEST_CONFIG)['marker_id']==0
    invalid=detect_robot(image,{**TEST_CONFIG,'marker_size_mm':0})
    assert not invalid['detected']
    # All three motion gates reject a real marker with unmeasured body geometry.
    from control.single_push_control import SinglePushControl
    from control.approach_control import ApproachControl
    from control.vision_wifi_test import PulseGate
    assert PulseGate.pose(no_size) is None
    assert SinglePushControl().update(no_size,(),{},0,0,0)['command']=='stop'
    assert not ApproachControl().update(no_size,(),{},0,0,0)['can_start']
    print('PASS: rotations, perspective, ID filtering, duplicate ID, no wheel fallback, offsets, body exclusion, printed asset, missing geometry blocks all motion modes')


if __name__=='__main__':
    main()

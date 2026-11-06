"""Check wheel geometry under rotation, uncertainty and missing observations."""
import math
import sys

import cv2
import numpy as np

from robot_vision import detect_robot, exclude_robot_regions


def scene(front_width=320):
    image = np.full((800,800,3),210,np.uint8)
    for x,y in ((260,260),(260,540),(500,400-front_width/2),(500,400+front_width/2)):
        cv2.circle(image,(int(x),int(y)),27,(0,0,230),-1)
        cv2.circle(image,(int(x),int(y)),13,(15,15,15),-1)
    return image


def main():
    for angle in (0,45,90,180,270):
        transform=cv2.getRotationMatrix2D((400,400),angle,1)
        image=cv2.warpAffine(scene(),transform,(800,800),borderValue=(210,210,210))
        result=detect_robot(image)
        assert result['detected'] and result['heading_valid'], (angle,result)
        error=(result['heading_rad']-math.radians(angle)+math.pi)%(2*math.pi)-math.pi
        assert abs(error)<.08,(angle,result)
    uncertain=detect_robot(scene(280))
    assert uncertain['detected'] and not uncertain['heading_valid'],uncertain
    assert uncertain['heading_rad'] is None
    incomplete=scene();incomplete[180:310,440:560]=210
    assert not detect_robot(incomplete)['detected']
    assert not detect_robot(np.full((800,800,3),210,np.uint8))['detected']
    blocks=np.full((800,800,3),210,np.uint8)
    for x,y in ((260,260),(260,540),(500,240),(500,560)):
        cv2.rectangle(blocks,(x-25,y-25),(x+25,y+25),(0,0,230),-1)
    assert not detect_robot(blocks)['detected'], 'Solid red blocks mistaken for wheels'
    car=detect_robot(scene())
    assert exclude_robot_regions([{'bbox_px':[360,380,10,10]}, {'bbox_px':[50,50,10,10]}],car)==[{'bbox_px':[50,50,10,10]}]
    if len(sys.argv)>1:
        image=cv2.imdecode(np.fromfile(sys.argv[1],dtype=np.uint8),1)
        actual=detect_robot(image)
        assert actual['detected'] and actual['heading_valid'],actual
        assert actual['front_px'][0]>actual['rear_px'][0]
        assert abs(actual['heading_rad'])<.2,actual
        for turn in (1,2,3):
            rotated=detect_robot(np.rot90(image,turn).copy())
            assert rotated['detected'] and rotated['heading_valid'],rotated
            error=(rotated['heading_rad']-actual['heading_rad']-turn*math.pi/2+math.pi)%(2*math.pi)-math.pi
            assert abs(error)<.15,(turn,rotated)
        print('PASS: supplied car photo and its three rotations, front points right in original')
    print('PASS: five rotations, equal-width uncertain heading, missing wheel, empty frame, solid red blocks, car exclusion')


if __name__=='__main__':
    main()

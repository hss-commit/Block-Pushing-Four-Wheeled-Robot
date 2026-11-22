"""ID-specific roof marker localisation. No colour fallback or pose prediction."""
import json
import math
from pathlib import Path

import cv2
import numpy as np

CONFIG_PATH = Path(__file__).with_name('robot_marker.json')
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
DETECTOR = cv2.aruco.ArucoDetector(DICTIONARY)


def validate_config(config):
    if type(config['marker_id']) is not int or not 0 <= config['marker_id'] < 50:
        raise ValueError('marker_id must be 0..49')
    for key in ('marker_size_mm', 'center_offset_right_mm', 'center_offset_forward_mm'):
        if type(config[key]) not in (int, float) or not math.isfinite(config[key]):
            raise ValueError('invalid ' + key)
    if config['marker_size_mm'] <= 0:
        raise ValueError('marker_size_mm must be positive')
    for key in ('body_length_mm', 'body_width_mm'):
        if config[key] is not None and (type(config[key]) not in (int, float) or
                not math.isfinite(config[key]) or config[key] <= 0):
            raise ValueError('invalid ' + key)
    return config


def load_config():
    return validate_config(json.loads(CONFIG_PATH.read_text(encoding='utf-8')))


def detect_robot(image, config=None, *, retry_low_contrast=False):
    """Marker top edge points forward; footprint is a projection at roof height."""
    missing = {'detected': False, 'heading_valid': False, 'geometry_valid': False,
               'reason': 'NEED ARUCO 4X4_50 ID 0', 'executable': False}
    try:
        config = load_config() if config is None else validate_config(config)
    except (OSError, ValueError, KeyError, TypeError):
        return {**missing, 'reason': 'INVALID MARKER SETTINGS / USE MENU M'}
    corners, ids, _ = DETECTOR.detectMarkers(image)
    marker_id = config['marker_id']
    matches = [] if ids is None else np.flatnonzero(ids.ravel() == marker_id).tolist()
    if retry_low_contrast and not matches:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        enhanced = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
        sharpened = cv2.addWeighted(enhanced, 1.7, blurred, -.7, 0)
        corners, ids, _ = DETECTOR.detectMarkers(sharpened)
        matches = [] if ids is None else np.flatnonzero(ids.ravel() == marker_id).tolist()
    if len(matches) != 1:
        return {**missing, 'reason': ('DUPLICATE ROBOT MARKER ID' if matches else
                    f"NEED ARUCO 4X4_50 ID {config['marker_id']}")}
    quad = np.float32(corners[matches[0]].reshape(4, 2))
    if abs(cv2.contourArea(quad)) < 100 or not cv2.isContourConvex(quad):
        return {**missing, 'reason': 'MARKER TOO SMALL / INVALID'}
    half = config['marker_size_mm'] / 2
    transform = cv2.getPerspectiveTransform(np.float32([[-half,-half],[half,-half],[half,half],[-half,half]]), quad)
    center_local = np.array([config['center_offset_right_mm'], -config['center_offset_forward_mm']])
    geometry_valid = config['body_length_mm'] is not None and config['body_width_mm'] is not None
    length = config['body_length_mm'] if geometry_valid else config['marker_size_mm']
    width = config['body_width_mm'] if geometry_valid else config['marker_size_mm']
    local = np.array([[0,0], [0,-length/2], [0,length/2],
                      [-width/2,-length/2],[width/2,-length/2],
                      [width/2,length/2],[-width/2,length/2]], np.float32) + center_local
    projected = cv2.perspectiveTransform(local.reshape(1,-1,2).astype(np.float32), transform)[0]
    if not np.isfinite(projected).all() or not cv2.isContourConvex(projected[3:]):
        return {**missing, 'reason': 'INVALID PROJECTED BODY'}
    center, front, rear = projected[:3]
    direction = front - rear
    if np.linalg.norm(direction) < 2:
        return {**missing, 'reason': 'MARKER HEADING INVALID'}
    return {'detected': True, 'heading_valid': True, 'geometry_valid': geometry_valid,
            'reason': f"ARUCO ID {config['marker_id']}" + ('' if geometry_valid else ' / SET BODY SIZE: MENU M'),
            'marker_id': config['marker_id'], 'marker_corners_px': quad.tolist(),
            'center_px': center.tolist(), 'front_px': front.tolist(), 'rear_px': rear.tolist(),
            'heading_rad': math.atan2(-float(direction[1]), float(direction[0])),
            'body_polygon_px': projected[3:].tolist(), 'executable': False}


def draw_robot(image, robot, calibrated=False, field_mm=1200):
    colour = (0,255,0) if robot.get('geometry_valid') else (0,170,255)
    label = 'ROBOT: ' + robot['reason']
    if robot['detected']:
        center = tuple(np.rint(robot['center_px']).astype(int))
        cv2.polylines(image, [np.rint(robot['marker_corners_px']).astype(np.int32)], True, (255,220,0), 2)
        if robot['geometry_valid']:
            cv2.polylines(image, [np.rint(robot['body_polygon_px']).astype(np.int32)], True, colour, 2)
        cv2.drawMarker(image, center, colour, cv2.MARKER_CROSS, 22, 2)
        end = tuple(np.rint(np.array(robot['center_px']) + .65*(np.array(robot['front_px'])-robot['rear_px'])).astype(int))
        cv2.arrowedLine(image, center, end, colour, 3, tipLength=.25)
        if calibrated:
            x,y = robot['center_px']
            robot['center_ground_estimate_mm'] = [x*field_mm/(image.shape[1]-1), (image.shape[0]-1-y)*field_mm/(image.shape[0]-1)]
            label += ' | approx %.0f, %.0f mm' % tuple(robot['center_ground_estimate_mm'])
    y = image.shape[0]-20
    cv2.rectangle(image,(0,y-27),(image.shape[1],image.shape[0]),(25,25,25),-1)
    cv2.putText(image,label,(12,y),cv2.FONT_HERSHEY_SIMPLEX,.55,colour,1,cv2.LINE_AA)


def exclude_robot_regions(regions, robot, *, front_contact_px=0):
    """Reject candidates overlapping the car, including wheels across its edges.

    A caller tracking an established push target can also consider candidates
    within a narrow strip at the front edge.
    """
    if not robot.get('detected') or not robot.get('geometry_valid'):
        return regions
    hull = np.float32(robot['body_polygon_px'])
    front_edge = hull[1] - hull[0]
    front_width = float(np.linalg.norm(front_edge))
    if front_contact_px and front_width > front_contact_px:
        tangent = front_edge / front_width
        outward = np.array([-tangent[1], tangent[0]])
        if (hull.mean(axis=0) - hull[0]) @ outward > 0:
            outward = -outward
    else:
        front_contact_px = 0
    kept = []
    for region in regions:
        x,y,w,h = region['bbox_px']
        box = np.float32([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
        overlap,_ = cv2.intersectConvexConvex(hull,box)
        if overlap>0 and region.get('contour_px'):
            # Bounding boxes include empty corners around rotated/irregular
            # colour blobs. Count actual silhouette pixels before rejecting.
            left,top=int(math.floor(x)),int(math.floor(y))
            shape=(max(1,int(math.ceil(h))+1),max(1,int(math.ceil(w))+1))
            colour=np.zeros(shape,np.uint8);body=np.zeros(shape,np.uint8)
            contour=np.rint(np.asarray(region['contour_px'])-[left,top]).astype(np.int32)
            cv2.fillPoly(colour,[contour],1)
            cv2.fillPoly(body,[np.rint(hull-[left,top]).astype(np.int32)],1)
            total=int(np.count_nonzero(colour))
            if total and np.count_nonzero(colour & body)<=.15*total:
                overlap=0
        if overlap <= 0:
            kept.append(region)
        elif front_contact_px:
            offset = np.array([x+w/2, y+h/2]) - hull[0]
            side_margin = front_contact_px / 2
            if (offset @ outward >= -front_contact_px and
                    side_margin <= offset @ tangent <= front_width-side_margin):
                kept.append(region)
    return kept


def retain_contact_target(regions, robot, previous, *, block_side_px,
                          other_points_mm=(), max_shift_mm=30, expected_point_mm=None):
    """Keep just one previously measured block in the front contact strip.

    Other overlapping candidates (including wheels) still use body exclusion.
    This returns measured detections only, never a predicted block position.
    Coordinates are from the calibrated 1200mm field view.
    """
    outside=exclude_robot_regions(regions,robot)
    if previous is None or not robot.get('geometry_valid') or not robot.get('detected'):
        return outside
    hull=np.asarray(robot['body_polygon_px'],float)
    body_length=float(np.linalg.norm((hull[0]+hull[1]-hull[2]-hull[3])/2))
    # Allow the ground block to project inside a roof-height body outline,
    # but never open the rear or the side-wheel strips.
    depth=min(body_length*.4,max(block_side_px*2,body_length*.2))
    candidates=exclude_robot_regions(regions,robot,front_contact_px=depth)
    previous_point=expected_point_mm if expected_point_mm is not None else (previous['x_mm'],previous['y_mm'])
    old_size=max(previous['bbox_px'][2:])
    matches=[]
    for region in candidates:
        size=max(region['bbox_px'][2:])
        if not .45*old_size<=size<=min(2*old_size,2*block_side_px):
            continue
        point=(region['x_mm'],region['y_mm'])
        distance=math.dist(point,previous_point)
        if distance<=max_shift_mm:
            matches.append((distance,region))
    matches.sort(key=lambda item:item[0])
    if not matches or (len(matches)>1 and matches[1][0]-matches[0][0]<=5):
        return outside
    distance,target=matches[0]
    point=(target['x_mm'],target['y_mm'])
    if any(math.dist(point,other)<=distance+5 for other in other_points_mm):
        return outside
    if target not in outside:
        outside.append(target)
    return outside

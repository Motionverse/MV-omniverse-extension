import pathlib
from typing import cast, Union, List
import carb
from pxr import Vt, Gf, UsdSkel, Usd, Sdf, UsdGeom
import omni.timeline
import omni.usd
import omni.kit.window.file
import struct
import numpy as np
def log_info(msg):
    carb.log_info("{}".format(msg))

def log_warn(msg):
    carb.log_warn("{}".format(msg))

def log_error(msg):
    carb.log_error("{}".format(msg))

def get_rig_index(model_joint_names, rig_mappings):
    candidates = [mapping["joint_mappings"].keys() for mapping in rig_mappings]
    index = None

    for i in range(len(candidates)):
        if all([(joint in model_joint_names) for joint in candidates[i]]):
            index = i      
    return index

def get_all_descendents(prim: Usd.Prim, result: List[Usd.Prim] = []):
    if len(result) == 0:
        result.append(prim)
    children = prim.GetChildren()
    result.extend(list(children))
    for child in children:
        get_all_descendents(child, result)

def find_skeleton(path):
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(path)
    descendants = []
    get_all_descendents(prim, descendants)
    skeleton = next(filter(lambda x: x.IsA(UsdSkel.Skeleton), descendants), None)
    assert skeleton is not None, "Could not find skeleton"
    return UsdSkel.Skeleton(skeleton)
def find_blendShapes(path):
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(path)
    descendants = []
    get_all_descendents(prim, descendants)
    blendShapePrims = list(filter(lambda x: x.IsA(UsdSkel.BlendShape), descendants))
    blendShapes = [UsdSkel.BlendShape(blendShape) for blendShape in blendShapePrims]

    return blendShapes

def get_this_files_path():
    return pathlib.Path(__file__).parent.absolute().as_posix()

class FrameDetections():
    def __init__(self):
        self.body_poses = None
        self.faces = None   
        self.body_pose_names = ("Hips","LeftUpLeg","RightUpLeg","LeftLeg","RightLeg","LeftFoot","RightFoot","Spine","Spine1","Neck","Head","LeftShoulder","RightShoulder","LeftArm",
        "RightArm","LeftForeArm","RightForeArm","LeftHand","RightHand","LeftToeBase","RightToeBase","LeftHandThumb1","LeftHandThumb2","LeftHandThumb3",
        "LeftHandIndex1","LeftHandIndex2","LeftHandIndex3","LeftHandMiddle1","LeftHandMiddle2","LeftHandMiddle3","LeftHandRing1","LeftHandRing2","LeftHandRing3","LeftHandPinky1",
        "LeftHandPinky2","LeftHandPinky3","RightHandThumb1","RightHandThumb2","RightHandThumb3","RightHandIndex1","RightHandIndex2","RightHandIndex3","RightHandMiddle1",
        "RightHandMiddle2","RightHandMiddle3","RightHandRing1","RightHandRing2","RightHandRing3","RightHandPinky1","RightHandPinky2","RightHandPinky3") 
    def ParseFromString(self,value):
        message_list=struct.unpack("415f",value)
        self.faces = message_list[:51]
        body_data = np.array(message_list[51:]).reshape(-1, 7) #joints num, 4+3
        self.body_poses  = [{'rotation': body_data[idx][:4], 'position': body_data[idx][4:]} 
                             for idx in range(len(self.body_pose_names))]
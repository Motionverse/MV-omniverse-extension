from email import message
from operator import le
import carb
import omni.ext
import omni.ui as ui
import omni.timeline
import omni.usd
import omni.kit.window.file
from pxr import Vt, Gf, UsdSkel, Usd, Sdf, UsdGeom
import struct
import asyncio
import pathlib
from typing import cast, Union, List
import traceback
import webbrowser
from .constants import *
import json
import glob
import numpy as np

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
    print(UsdSkel.Skeleton(skeleton))
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
# 
# styles for UIController class
# 
style_btn_enabled = {
    "Button": {"border_radius": 5.0,"margin": 5.0,"padding": 10.0,"background_color": 0xFFFF7E09,"border_color": 0xFFFD761D},
    "Button:hovered": {"background_color": 0xFFFF4F00},
    "Button:pressed": {"background_color": 0xFFFAE26F},
    "Button.Label": {"color": 0xFFFFFFFF},
}
style_btn_disabled = {
    "Button": {"border_radius": 3.0,"margin": 5.0,"padding": 10.0,"background_color": 0xFFC0E0C0,"border_color": 0xFFFD7F1D},
    "Button:hovered": {"background_color": 0xFFC0C0C0, "background_gradient_color": 0xFFFFAE5A},
    "Button:pressed": {"background_color": 0xFFC0C0C0, "background_gradient_color": 0xFFFAB26D},
    "Button.Label": {"color": 0xFF808080},
}
style_status_circle_green = {"background_color": 0xFF00FF00, "border_width": 0}
style_status_circle_red = {"background_color": 0xFF0000FF, "border_width": 0}
style_btn_goto_motionverse = {"Button": {"border_width": 0.0, "border_radius": 3.0, "margin": 5.0, "padding": 10.0}}
#
# UIController class
#
class UIController:
    def __init__(self, ext):
        self.ext = ext
        self.extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext.ext_id)
        self._streaming_active = False
        self._window = ui.Window(WINDOW_NAME,width=600, height=260)

        self.build_ui()

    def build_ui(self):
        with self._window.frame:
            with ui.VStack(height=0):
                with ui.HStack():
                    #logo
                    logo_path = f"{self.extension_path}{LOGO_FILEPATH}"
                    ui.Image(logo_path, width=50,height=50,fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,alignment=ui.Alignment.CENTER)
                    ui.Spacer()
                    ui.Button(
                        CS_GOTO_BTN_TEXT,width=ui.Percent(10),  style=style_btn_goto_motionverse,alignment=ui.Alignment.RIGHT_CENTER, clicked_fn=self.launch_motionverse_website)
                
                with ui.HStack():
                    # green/red status
                    with ui.VStack(width=50, alignment=ui.Alignment.TOP):

                        self._status_circle = ui.Circle(
                            radius = 8,size_policy=ui.CircleSizePolicy.FIXED, style=style_status_circle_red
                        )

                        ui.Spacer()
                    with ui.VStack():
                        # CaptureStream device selection drop-down
                        with ui.HStack():

                            ui.Label(
                                CS_HOSTNAME_TEXT, width=ui.Percent(20), alignment=ui.Alignment.RIGHT_CENTER
                            )

                            ui.Spacer(width=CS_H_SPACING)

                            with ui.VStack(width=ui.Percent(50)):
                                ui.Spacer()
                                self.source_ip_field = ui.StringField(
                                    model=ui.SimpleStringModel("192.168.10.113"), height=0, visible=True
                                )
                                ui.Spacer()
                            ui.Label(
                                CS_PORT_TEXT, width=ui.Percent(10), alignment=ui.Alignment.RIGHT_CENTER
                            )
                            with ui.VStack(width=ui.Percent(10)):
                                ui.Spacer()
                                self.source_port_field = ui.StringField(
                                    model=ui.SimpleStringModel("4188"), height=0, visible=True
                                )
                                ui.Spacer()

                        # skeleton selection
                        with ui.HStack():

                            ui.Label(
                                SKEL_SOURCE_EDIT_TEXT, width=ui.Percent(20), alignment=ui.Alignment.RIGHT_CENTER
                            )

                            ui.Spacer(width=CS_H_SPACING)

                            with ui.VStack(width=ui.Percent(50)):
                                ui.Spacer()
                                self._skeleton_to_drive_stringfield = ui.StringField(
                                    model=ui.SimpleStringModel(SKEL_INVALID_TEXT), height=0, enabled=False
                                )
                                ui.Spacer()

                            ui.Spacer(width=CS_H_SPACING)

                            self._skel_select_button = ui.Button(
                                SKEL_SOURCE_BTN_TEXT, width=0, clicked_fn=self.select_skeleton
                            )
                    # rig selection
                        with ui.HStack():

                            ui.Label(RIG_DROPDOWN_TEXT, width=ui.Percent(20), alignment=ui.Alignment.RIGHT_CENTER)

                            ui.Spacer(width=CS_H_SPACING)

                            with ui.VStack(width=ui.Percent(75)):
                                ui.Spacer()
                                self._selected_rig_label = ui.Label("")
                                ui.Spacer()
                        # start/stop stream buttons
                        with ui.HStack():

                            ui.Spacer(width=ui.Percent(20))

                            self._start_button = ui.Button(
                                CS_START_BTN_TEXT,
                                width=0,
                                clicked_fn=self.start_streaming,
                                enabled=not self.streaming_active,
                                style=style_btn_disabled if self.streaming_active else style_btn_enabled,
                            )

                            ui.Spacer(width=CS_H_SPACING)

                            self._stop_button = ui.Button(
                                CS_STOP_BTN_TEXT,
                                width=0,
                                clicked_fn=self.stop_streaming,
                                enabled=self.streaming_active,
                                style=style_btn_enabled if self.streaming_active else style_btn_disabled,
                            )

                        ui.Spacer(height=5)
                  
    def select_skeleton(self):
        paths = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if paths:
            path = paths[0]
            try:
                self.ext.init_skeletons(path)
            except Exception as ex:
                self._skeleton_to_drive_stringfield.model.set_value(SKEL_INVALID_TEXT)
            self._selected_rig_label.text = self.ext.selected_rig_name or RIG_UNSUPPORTED_TEXT

    def launch_motionverse_website(self):
        webbrowser.open_new_tab(CS_URL)

    def update_ui(self):
        if self.streaming_active:
            self._start_button.enabled = False
            self._start_button.set_style(style_btn_disabled)
            self._stop_button.enabled = True
            self._stop_button.set_style(style_btn_enabled)
        else:
            self._start_button.enabled = self.ext.ready_to_stream
            self._start_button.set_style(
                style_btn_enabled if self.ext.ready_to_stream else style_btn_disabled
            )
            self._stop_button.enabled = False
            self._stop_button.set_style(style_btn_disabled)

        if self.streaming_active:
            self._status_circle.set_style(style_status_circle_green)
        else:
            self._status_circle.set_style(style_status_circle_red)

        self._skeleton_to_drive_stringfield.model.set_value(self.ext.target_skeleton_path)
    def start_streaming(self):
        self.ext.connect()
    def stop_streaming(self):
        self.ext.disconnect("User cancelled")

    @property
    def streaming_active(self):
        return self._streaming_active

    @streaming_active.setter
    def streaming_active(self, value):
        self._streaming_active = value

class MotionverseExtension(omni.ext.IExt):
    def __init__(self):
        self._net_io_task = None
        self._update_skeleton_task = None
        self.target_skeleton = None
        self.skel_cache = UsdSkel.Cache()

    def on_startup(self, ext_id):
        self.import_rig_mappings_from_json_files()
        self.ext_id = ext_id
        stream = omni.kit.app.get_app().get_update_event_stream()
        self.update_sub = stream.create_subscription_to_pop(self.update_ui, name="update frame")
        self.ui_controller = UIController(self)

    def connect(self):       					
        self.disconnect("Resetting connection")
        host = self.ui_controller.source_ip_field.model.as_string
        port = self.ui_controller.source_port_field.model.as_int

        loop = asyncio.get_event_loop()
        queue = asyncio.Queue(maxsize=10, loop=loop)

        if self._net_io_task:
            loop.run_until_complete(asyncio.wait({self._net_io_task}, timeout=1.0))
        if self._update_skeleton_task:
            loop.run_until_complete(asyncio.wait({self._update_skeleton_task}, timeout=1.0))

        self._net_io_task = loop.create_task(self._do_net_io(host, port, queue))
        self._update_skeleton_task = loop.create_task(self._update_skeleton_loop(queue))

        self._net_io_task.add_done_callback(self.on_task_complete)
        self._update_skeleton_task.add_done_callback(self.on_task_complete)

    def on_task_complete(self, fut=None):
        if fut is self._net_io_task:
            self._update_skeleton_task.cancel()
        elif fut is self._update_skeleton_task:
            self._net_io_task.cancel()
        self.ui_controller.streaming_active = False

    async def _do_net_io(self, host, port, queue):
        self.ui_controller.streaming_active = True
        writer = None
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(b"ov")
            await self._read_client(reader, queue)
        except asyncio.CancelledError:
            print("Network streaming cancelled")
        except:
            carb.log_error(traceback.format_exc())
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
                print("TCP connection closed")
            print("Net I/O task stopped")

    async def _read_client(self, reader, queue):
        while True:
            message_data = await reader.readexactly(1660)
            await queue.put(message_data)
    async def _update_skeleton_loop(self, queue):
        try:
            while True:
                message = await queue.get()
                fd = FrameDetections()
                fd.ParseFromString(message)
                self.update_skeleton(fd)

        except asyncio.CancelledError:
            print("Skeleton update task cancelled")
        except:
            carb.log_error(traceback.format_exc())
    def disconnect(self, reason=str()):
        streaming_active = False
        if self._net_io_task is not None:
            self._net_io_task.cancel()

    def import_rig_mappings_from_json_files(self):

        self.rig_mappings = []
        rig_filenames = glob.glob(get_this_files_path() + "/xform_*.json")
        if rig_filenames is not None:
            for filename in rig_filenames:
                rig_mapfile = open(filename, "r")
                if rig_mapfile is not None:
                    self.rig_mappings.append(json.load(rig_mapfile))
                else:
                    print("error - could not load file %s" % filename)
    def init_skeletons(self, skel_root_path):
        self.selected_rig_index = None
        self.motion_skel_anim = None
        self.selected_joints = None
        stage = omni.usd.get_context().get_stage()
        selected_skeleton = find_skeleton(skel_root_path)
        blendShapes = find_blendShapes(skel_root_path)

        print("skel_cache =====",self.skel_cache)


        skel_query = self.skel_cache.GetSkelQuery(selected_skeleton)
        print("selected_skeleton ====",selected_skeleton)
        print("blendShapes[0] ====",blendShapes[0])

        # blendShape_query = UsdSkel.BlendShapeQuery(blendShapes[0])
        # print("blendShape_query",blendShape_query)

        joint_tokens = skel_query.GetJointOrder()

        jointPaths = [Sdf.Path(jointToken) for jointToken in joint_tokens]


    

        all_joint_names = [jointPath.name for jointPath in jointPaths]

      

        

        


        
 
        # all_blendshape_names = [blendShapePath.name for blendShapePath in blendShapePaths]
        
        self.selected_rig_index = get_rig_index(all_joint_names, self.rig_mappings)
        assert self.selected_rig_index is not None, "Unsupported rig"

      

        self.target_skeleton = selected_skeleton

        self.target_skel_root = UsdSkel.Root.Find(self.target_skeleton.GetPrim())
        # print("target_skeleton = ",self.target_skeleton.GetPrim())

        # skel_root_rotate_xyz is a set of rotations in XYZ order used to align the rest pose
        # with wrnch's axes (+Y up, +Z forward)
        skel_root_rotate_xyz = self.rig_mappings[self.selected_rig_index]["skel_root_rotate_xyz"]
        rot_x = Gf.Rotation(Gf.Vec3d(1, 0, 0), skel_root_rotate_xyz[0])
        rot_y = Gf.Rotation(Gf.Vec3d(0, 1, 0), skel_root_rotate_xyz[1])
        rot_z = Gf.Rotation(Gf.Vec3d(0, 0, 1), skel_root_rotate_xyz[2])
        self.rest_xform_adjust = Gf.Matrix4d()
        self.rest_xform_adjust.SetRotate(rot_x * rot_y * rot_z)
        self.rest_xform_adjust_inverse = self.rest_xform_adjust.GetInverse()
  

        if not skel_query.HasRestPose():
            xforms = skel_query.ComputeJointLocalTransforms()
            self.target_skeleton.GetRestTransformsAttr().Set(xforms)
            self.skel_cache.Clear()


 
    def update_skeleton(self, fd):
        if self.selected_joints is None:
            self._init_animation(fd.body_pose_names)
        num_joints = len(self.rest_xforms_anim_global)
        root_index = self.motion_to_anim_index["Hips"]
        motion_xforms_global = Vt.Matrix4dArray(num_joints)
        for i, pose in enumerate(fd.body_poses):
            name = fd.body_pose_names[i]
            if name in self.motion_to_anim_index:
                anim_index = self.motion_to_anim_index[name]
                q = pose['rotation']
                t = pose['position']
                rot = Gf.Rotation(Gf.Quatd(q[3], q[0], q[1], q[2]))
                trans = Gf.Vec3d(t[0], t[1], t[2])

                xform = Gf.Matrix4d()
                xform.SetTransform(rot, trans)

                motion_xforms_global[anim_index] = xform
               
        target_pose_xforms_global = Vt.Matrix4dArray(
            [
                base_xform * motion_xform
                for motion_xform, base_xform in zip(motion_xforms_global, self.rest_xforms_anim_global)
            ]
        )

        root_xform = self.rest_xform_adjust_inverse

        target_xforms_local = UsdSkel.ComputeJointLocalTransforms(
            self.anim_topology, target_pose_xforms_global, root_xform
        )

        anim_rotations = Vt.QuatfArray([Gf.Quatf(xform.ExtractRotationQuat()) for xform in target_xforms_local])

        height_offset = 0

        # Apply root motion to the animation attr
        local_translations_attr = self.motion_skel_anim.GetTranslationsAttr()
        local_translations = local_translations_attr.Get(0)
        local_translations[root_index] = Gf.Vec3f(
            root_xform.Transform(
                Gf.Vec3d(0, 1, 0) * height_offset + motion_xforms_global[root_index].ExtractTranslation()
            )
        )
        local_translations_attr.Set(local_translations, 0)

        # Apply joint rotations to animation attr
        self.motion_skel_anim.GetRotationsAttr().Set(anim_rotations, 0)


    def _init_animation(self,selected_joints):
        stage = omni.usd.get_context().get_stage()
        rig_mapping = self.rig_mappings[self.selected_rig_index]["joint_mappings"]
        skel_query = self.skel_cache.GetSkelQuery(self.target_skeleton)

        
        joint_tokens = skel_query.GetJointOrder()
    
        

        joint_names = {Sdf.Path(token).name: token for token in joint_tokens}

        print(joint_names)
        # Lookup index of joint by token
        joint_token_indices = {token: index for index, token in enumerate(joint_tokens)}

        motion_to_token = {
            value: joint_names[key] for key, value in rig_mapping.items() if value in selected_joints
        }

        
        anim_tokens = Vt.TokenArray(motion_to_token.values())
        assert len(anim_tokens) > 0

        anim_token_indices = {token: index for index, token in enumerate(anim_tokens)}


        active_token_indices = [joint_token_indices[token] for token in anim_tokens]
        self.motion_to_anim_index = {
            motion_name: anim_token_indices[token] for motion_name, token in motion_to_token.items()
        }

        self.anim_topology = UsdSkel.Topology([Sdf.Path(token) for token in anim_tokens])
        assert self.anim_topology.Validate()

       
        anim_path = self.target_skeleton.GetPath().AppendChild("SkelRoot")
       
        self.motion_skel_anim = UsdSkel.Animation.Define(stage, anim_path)

        print("anim_tokens=",anim_tokens)

        self.motion_skel_anim.GetJointsAttr().Set(anim_tokens)
        self.motion_skel_anim.GetBlendShapesAttr().Set(anim_tokens)

        # Set our UsdSkelAnimation as the animationSource of the UsdSkelSkeleton
        binding = UsdSkel.BindingAPI.Apply(self.target_skeleton.GetPrim())
        binding.CreateAnimationSourceRel().SetTargets([self.motion_skel_anim.GetPrim().GetPath()])

        # Set initial the scale, translation, and rotation attributes for the UsdSkelAnimation.
        # Note that these attributes need to be in the UsdSkelSkeleton's Local Space.
        root_xform = Gf.Matrix4d()
        root_xform.SetIdentity()
        root_xform = self.rest_xform_adjust
        identity_xform = Gf.Matrix4d()
        identity_xform.SetIdentity()

        rest_xforms_local = self.target_skeleton.GetRestTransformsAttr().Get()
        assert rest_xforms_local, "Skeleton has no restTransforms"
        skel_topology = skel_query.GetTopology()


        anim_start_index = active_token_indices[0]
        xform_accum = Gf.Matrix4d()
        xform_accum.SetIdentity()
        index = skel_topology.GetParent(anim_start_index)
        while index >= 0:
            xform_accum = rest_xforms_local[index] * xform_accum
            rest_xforms_local[index] = identity_xform
            index = skel_topology.GetParent(index)

        rest_xforms_local[anim_start_index] = xform_accum * rest_xforms_local[anim_start_index]

        # Set the rest pose transforms
        self.target_skeleton.GetRestTransformsAttr().Set(rest_xforms_local)

        # Joint transforms in world coordinates such that the t-pose is aligned with wrnch's
        # base t-pose (+Y up, +Z forward)
        rest_xforms_global = UsdSkel.ConcatJointTransforms(skel_topology, rest_xforms_local, root_xform)

        # Get the subset of the rest transforms that correspond to our UsdSkelAnimation attrs.
        # We're going to concatenate these to the wrx transforms to get the desired
        # pose
        self.rest_xforms_anim_global = Vt.Matrix4dArray([rest_xforms_global[i] for i in active_token_indices])

        base_xforms_anim_local = UsdSkel.ComputeJointLocalTransforms(
            self.anim_topology, self.rest_xforms_anim_global, identity_xform
        )

        self.motion_skel_anim.SetTransforms(base_xforms_anim_local, 0)

        self.selected_joints = set(selected_joints)
    def update_ui(self, dt):
        try:
            self.ui_controller.update_ui()
        except:
            self.disconnect("Error updating UI")
            raise
    def on_shutdown(self):
        self.ext = None
        self._window = None
    @property
    def ready_to_stream(self):
        has_skeleton_target = self.target_skeleton is not None and self.target_skeleton.GetPrim()
        return has_skeleton_target


    @property
    def target_skeleton_path(self):

        if not self.target_skeleton or not self.target_skeleton.GetPrim():
            return ""
        else:
            return str(self.target_skeleton.GetPath())
    @property
    def selected_rig_name(self):
        if self.selected_rig_index is not None:
            return self.rig_mappings[self.selected_rig_index]["display_name"]
        else:
            return None

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

        




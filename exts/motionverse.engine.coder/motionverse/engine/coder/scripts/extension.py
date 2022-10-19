import carb
import omni.ext
import omni.timeline
import omni.usd
import omni.kit.window.file
import traceback
import json
import glob
import asyncio
from email import message
from operator import le
from pxr import Vt, Gf, UsdSkel, Usd, Sdf, UsdGeom
from typing import cast, Union, List

from .constants import *
from .ui import *
from .styles import *
from .utils import *

class MotionverseExtension(omni.ext.IExt):
    def __init__(self):
        self._net_io_task = None
        self._update_skeleton_task = None
        self.target_skeleton = None
        self.skel_root_path = None
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
            log_info("Network streaming cancelled")
        except:
            carb.log_error(traceback.format_exc())
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
                log_info("TCP connection closed")
            log_info("Net I/O task stopped")

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
            log_info("Skeleton update task cancelled")
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
                    log_info("error - could not load file %s" % filename)

    def init_skeletons(self, skel_root_path):

        self.selected_rig_index = None
        self.motion_skel_anim = None
        self.selected_joints = None
        self.skel_root_path = skel_root_path
        selected_skeleton = find_skeleton(skel_root_path)
        skel_query = self.skel_cache.GetSkelQuery(selected_skeleton)
        joint_tokens = skel_query.GetJointOrder()
        jointPaths = [Sdf.Path(jointToken) for jointToken in joint_tokens]
        all_joint_names = [jointPath.name for jointPath in jointPaths]

        self.selected_rig_index = get_rig_index(all_joint_names, self.rig_mappings)

        assert self.selected_rig_index is not None, "Unsupported rig"
        self.target_skeleton = selected_skeleton
        self.target_skel_root = UsdSkel.Root.Find(self.target_skeleton.GetPrim())
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

        local_translations_attr = self.motion_skel_anim.GetTranslationsAttr()
        local_translations = local_translations_attr.Get(0)
        local_translations[root_index] = Gf.Vec3f(
            root_xform.Transform(
                Gf.Vec3d(0, 1, 0) * height_offset + motion_xforms_global[root_index].ExtractTranslation()
            )
        )
        local_translations_attr.Set(local_translations, 0)

        self.motion_skel_anim.GetRotationsAttr().Set(anim_rotations, 0)
        # self.motion_skel_anim.GetBlendShapeWeightsAttr().Set(fd.faces,0)

    def _init_animation(self,selected_joints):
        stage = omni.usd.get_context().get_stage()
        rig_mapping = self.rig_mappings[self.selected_rig_index]["joint_mappings"]
        skel_query = self.skel_cache.GetSkelQuery(self.target_skeleton)
        joint_tokens = skel_query.GetJointOrder()
        joint_names = {Sdf.Path(token).name: token for token in joint_tokens}
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
        self.motion_skel_anim.GetJointsAttr().Set(anim_tokens)
        # self.motion_skel_anim.GetBlendShapesAttr().Set(anim_tokens)

        binding = UsdSkel.BindingAPI.Apply(self.target_skeleton.GetPrim())
        binding.CreateAnimationSourceRel().SetTargets([self.motion_skel_anim.GetPrim().GetPath()])

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

        self.target_skeleton.GetRestTransformsAttr().Set(rest_xforms_local)

        rest_xforms_global = UsdSkel.ConcatJointTransforms(skel_topology, rest_xforms_local, root_xform)

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
        log_info("on_shutdown")
        self.ui_controller.shutdown()
        self.ui_controller = None
        self.disconnect("Extension is shutting down")


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
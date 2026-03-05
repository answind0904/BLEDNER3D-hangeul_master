bl_info = {
    "name": "hangeul_master_v1.0_hasw87",
    "author": "hasw87@mbc.co.kr",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Hangeul Edit Tab",
    "description": "한글캐릭터 순차애니메이션 제작을 위한 도구(MBCNewsDesign_하상우)",
    "category": "Object",
}

import bpy
import os
import math
import mathutils

# --- [도우미 함수] 블렌더 4.x 및 5.0 호환 F-Curve 추출 ---
def get_fcurves(anim_data):
    if not anim_data or not anim_data.action:
        return []
    action = anim_data.action
    if hasattr(action, "fcurves"):
        return action.fcurves
    else:
        try:
            import bpy_extras.anim_utils
            slot = getattr(anim_data, "action_slot", None)
            if slot is not None:
                channelbag = bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)
                if channelbag:
                    return channelbag.fcurves
        except:
            pass
    return []

# --- 1. 머티리얼 자동 생성 (True Normal 유지) ---
class OT_Hangeul_Create_Mat_V27(bpy.types.Operator):
    bl_idname = "object.hangeul_create_mat_v27"
    bl_label = "트루 노말 마스킹 재질 자동생성"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat_name = "Hangeul_TrueNormal_Mask"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        node_out = nodes.new('ShaderNodeOutputMaterial')
        node_out.location = (1000, 0)

        mix_front = nodes.new('ShaderNodeMixShader')
        mix_front.location = (800, 0)
        
        mix_side = nodes.new('ShaderNodeMixShader')
        mix_side.location = (600, 0)

        bsdf_front = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_front.label = "앞면 (Front/Back)"
        bsdf_front.location = (400, 300)
        bsdf_front.inputs['Base Color'].default_value = (1, 0.1, 0.1, 1)

        bsdf_side = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_side.label = "두께 (Side)"
        bsdf_side.location = (200, -100)
        bsdf_side.inputs['Base Color'].default_value = (0.1, 1, 0.1, 1)

        bsdf_bevel = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_bevel.label = "베벨 (Bevel)"
        bsdf_bevel.location = (200, -500)
        bsdf_bevel.inputs['Base Color'].default_value = (0.1, 0.1, 1, 1)

        geo_node = nodes.new('ShaderNodeNewGeometry')
        geo_node.location = (-1000, 200)

        vec_transform = nodes.new('ShaderNodeVectorTransform')
        vec_transform.vector_type = 'NORMAL'
        vec_transform.convert_from = 'WORLD'
        vec_transform.convert_to = 'OBJECT'
        vec_transform.location = (-800, 200)

        sep_xyz = nodes.new('ShaderNodeSeparateXYZ')
        sep_xyz.location = (-600, 200)

        math_abs = nodes.new('ShaderNodeMath')
        math_abs.operation = 'ABSOLUTE'
        math_abs.location = (-400, 200)

        math_comp_front = nodes.new('ShaderNodeMath')
        math_comp_front.operation = 'COMPARE'
        math_comp_front.inputs[1].default_value = 1.0 
        math_comp_front.inputs[2].default_value = 0.05 
        math_comp_front.location = (-150, 200)

        math_comp_side = nodes.new('ShaderNodeMath')
        math_comp_side.operation = 'COMPARE'
        math_comp_side.inputs[1].default_value = 0.0 
        math_comp_side.inputs[2].default_value = 0.05 
        math_comp_side.location = (-150, -100)

        links.new(geo_node.outputs['True Normal'], vec_transform.inputs['Vector'])
        links.new(vec_transform.outputs['Vector'], sep_xyz.inputs['Vector'])
        links.new(sep_xyz.outputs['Z'], math_abs.inputs[0])
        links.new(math_abs.outputs[0], math_comp_front.inputs[0])
        links.new(math_abs.outputs[0], math_comp_side.inputs[0])

        links.new(bsdf_bevel.outputs[0], mix_side.inputs[1])
        links.new(bsdf_side.outputs[0], mix_side.inputs[2])
        links.new(math_comp_side.outputs[0], mix_side.inputs[0]) 

        links.new(mix_side.outputs[0], mix_front.inputs[1])
        links.new(bsdf_front.outputs[0], mix_front.inputs[2])
        links.new(math_comp_front.outputs[0], mix_front.inputs[0]) 

        links.new(mix_front.outputs[0], node_out.inputs['Surface'])

        context.scene.hangeul_v27_tool.mat_main = mat
        self.report({'INFO'}, "True Normal 셰이더 생성 완료!")
        return {'FINISHED'}

# --- 2. 속성 정의 ---
class Hangeul_V27_Props(bpy.types.PropertyGroup):
    text_input: bpy.props.StringProperty(name="내용", default="싱크베이크", update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    font_path: bpy.props.StringProperty(name="폰트 선택", subtype='FILE_PATH', update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    
    anim_factor: bpy.props.FloatProperty(name="진행도 (프리뷰)", default=1.0, min=0.0, max=1.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    overlap: bpy.props.FloatProperty(name="오버래핑", default=0.5, min=0.0, max=0.99, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    ease_intensity: bpy.props.FloatProperty(name="감속 강도 (프리뷰)", default=3.0, min=0.1, max=10.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    
    common_z_start: bpy.props.FloatProperty(name="시작 Z", default=2.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    common_rot_x: bpy.props.FloatProperty(name="시작 RX", default=45.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    common_rot_y: bpy.props.FloatProperty(name="시작 RY", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    common_rot_z: bpy.props.FloatProperty(name="시작 RZ", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    
    kerning: bpy.props.FloatProperty(name="자간", default=1.1, min=0.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    extrude: bpy.props.FloatProperty(name="두께", default=0.05, min=0.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    bevel: bpy.props.FloatProperty(name="베벨 깊이", default=0.01, min=0.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    outline_offset: bpy.props.FloatProperty(name="추가 외곽선", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    
    mat_main: bpy.props.PointerProperty(name="마스터 재질", type=bpy.types.Material, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    char_sizes: bpy.props.FloatVectorProperty(name="사이즈", size=20, default=[1.0]*20, update=lambda self, context: bpy.ops.object.hangeul_v27_refresh() if self.is_live else None)
    
    is_live: bpy.props.BoolProperty(name="라이브 편집 모드", default=True)

# --- 3. 실시간 프리뷰 로직 ---
class OT_Hangeul_V27_Refresh(bpy.types.Operator):
    bl_idname = "object.hangeul_v27_refresh"
    bl_label = "Hangeul V27 Refresh"
    bl_options = {'INTERNAL', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.hangeul_v27_tool
        if not props.is_live:
            return {'FINISHED'}
            
        p_name = "Hangeul_Group"
        p_obj = bpy.data.objects.get(p_name)
        
        if p_obj:
            for child in p_obj.children: bpy.data.objects.remove(child, do_unlink=True)
        else:
            p_obj = bpy.data.objects.new(p_name, None)
            context.collection.objects.link(p_obj)

        l_font = None
        if props.font_path and os.path.exists(props.font_path):
            try: l_font = bpy.data.fonts.load(props.font_path)
            except: pass

        count = len(props.text_input)
        if count == 0: return {'FINISHED'}

        current_x_cursor = 0.0
        for i, char in enumerate(props.text_input):
            if i >= 20: break
            
            s = props.char_sizes[i]
            if i > 0:
                prev_s = props.char_sizes[i-1]
                current_x_cursor += ((prev_s * 0.5) + (s * 0.5)) * props.kerning
                
            interval = (1.0 - props.overlap) / count
            start_t = i * interval
            end_t = start_t + props.overlap + interval
            raw_f = max(0.0, min(1.0, (props.anim_factor - start_t) / (end_t - start_t) if end_t > start_t else 1.0))
            eased_f = 1.0 - pow(1.0 - raw_f, props.ease_intensity) 
            inv_f = 1.0 - eased_f

            f_curve = bpy.data.curves.new(type="FONT", name=f"HV27_Char_{i}")
            f_curve.body = char
            if l_font: f_curve.font = l_font
            
            f_curve.align_x = 'CENTER'
            f_curve.align_y = 'BOTTOM'
            f_curve.size = s 
            
            f_curve.extrude = props.extrude
            f_curve.bevel_depth = props.bevel
            f_curve.bevel_resolution = 4
            f_curve.offset = props.outline_offset - props.bevel
            
            if props.mat_main:
                f_curve.materials.append(props.mat_main)
            
            t_obj = bpy.data.objects.new(name=f"HV27_Obj_{i}", object_data=f_curve)
            context.collection.objects.link(t_obj)
            
            rx = math.radians(props.common_rot_x * inv_f)
            ry = math.radians(props.common_rot_y * inv_f)
            rz = math.radians(props.common_rot_z * inv_f)
            rot_euler = mathutils.Euler((rx, ry, rz), 'XYZ')
            
            pivot_local = mathutils.Vector((0.0, s * 0.5, 0.0))
            pivot_rotated = pivot_local.copy()
            pivot_rotated.rotate(rot_euler)
            
            comp_offset = pivot_local - pivot_rotated
            anim_z = props.common_z_start * inv_f
            
            t_obj.location = (
                current_x_cursor + comp_offset.x, 
                comp_offset.y, 
                anim_z + comp_offset.z
            )
            
            t_obj.rotation_euler = rot_euler
            t_obj.parent = p_obj
            
        return {'FINISHED'}

# --- 4. 💡 동기화 & 스마트 키프레임 베이크 ---
class OT_Hangeul_Bake_Anim_V27(bpy.types.Operator):
    bl_idname = "object.hangeul_bake_anim_v27"
    bl_label = "스마트 키프레임 동기화 베이크"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.hangeul_v27_tool
        p_name = "Hangeul_Group"
        p_obj = bpy.data.objects.get(p_name)
        
        if not p_obj or not p_obj.children:
            self.report({'WARNING'}, "베이크할 텍스트가 없습니다.")
            return {'CANCELLED'}

        props.is_live = False
        
        # 💡 핵심: 사용자가 '진행도(anim_factor)'에 찍어둔 키프레임을 추적합니다.
        global_start_frame = context.scene.frame_start
        global_end_frame = context.scene.frame_end
        
        scene_fcurves = get_fcurves(context.scene.animation_data)
        for fc in scene_fcurves:
            if "anim_factor" in fc.data_path:
                if len(fc.keyframe_points) >= 2:
                    # 진행도 키프레임의 가장 첫 프레임과 마지막 프레임을 베이크 구간으로 설정
                    global_start_frame = fc.keyframe_points[0].co.x
                    global_end_frame = fc.keyframe_points[-1].co.x
                break
                
        total_frames = global_end_frame - global_start_frame
        
        count = len(props.text_input)
        current_x_cursor = 0.0
        
        for i, char in enumerate(props.text_input):
            if i >= 20: break
            s = props.char_sizes[i]
            
            if i > 0:
                prev_s = props.char_sizes[i-1]
                current_x_cursor += ((prev_s * 0.5) + (s * 0.5)) * props.kerning

            # 전체 구간 대비 이 글자가 움직일 로컬 타임 계산
            interval = (1.0 - props.overlap) / count
            start_t = i * interval
            end_t = start_t + props.overlap + interval
            
            char_start_frame = global_start_frame + (start_t * total_frames)
            char_end_frame = global_start_frame + (end_t * total_frames)

            # 애니메이션 시작(Offset) 상태
            rx_s = math.radians(props.common_rot_x)
            ry_s = math.radians(props.common_rot_y)
            rz_s = math.radians(props.common_rot_z)
            rot_start = mathutils.Euler((rx_s, ry_s, rz_s), 'XYZ')
            
            pivot_local = mathutils.Vector((0.0, s * 0.5, 0.0))
            pivot_start = pivot_local.copy()
            pivot_start.rotate(rot_start)
            comp_start = pivot_local - pivot_start
            
            loc_start = (
                current_x_cursor + comp_start.x,
                comp_start.y,
                props.common_z_start + comp_start.z
            )

            # 애니메이션 종료(정착) 상태
            rot_end = mathutils.Euler((0.0, 0.0, 0.0), 'XYZ')
            loc_end = (current_x_cursor, 0.0, 0.0)

            t_obj = bpy.data.objects.get(f"HV27_Obj_{i}")
            if not t_obj: continue
            
            t_obj.animation_data_clear()

            # 변화가 있는 축만 2-Point 키프레임 찍기
            for axis_idx in range(3):
                if abs(loc_start[axis_idx] - loc_end[axis_idx]) > 0.0001:
                    t_obj.location[axis_idx] = loc_start[axis_idx]
                    t_obj.keyframe_insert(data_path="location", index=axis_idx, frame=char_start_frame)
                    
                    t_obj.location[axis_idx] = loc_end[axis_idx]
                    t_obj.keyframe_insert(data_path="location", index=axis_idx, frame=char_end_frame)
                else:
                    t_obj.location[axis_idx] = loc_end[axis_idx]

                if abs(rot_start[axis_idx] - rot_end[axis_idx]) > 0.0001:
                    t_obj.rotation_euler[axis_idx] = rot_start[axis_idx]
                    t_obj.keyframe_insert(data_path="rotation_euler", index=axis_idx, frame=char_start_frame)
                    
                    t_obj.rotation_euler[axis_idx] = rot_end[axis_idx]
                    t_obj.keyframe_insert(data_path="rotation_euler", index=axis_idx, frame=char_end_frame)
                else:
                    t_obj.rotation_euler[axis_idx] = rot_end[axis_idx]

            # Easy Ease 적용 (Blender 4.0 ~ 5.0 자동 호환)
            obj_fcurves = get_fcurves(t_obj.animation_data)
            for fcurve in obj_fcurves:
                for kp in fcurve.keyframe_points:
                    kp.interpolation = 'BEZIER'
                    kp.handle_left_type = 'AUTO'
                    kp.handle_right_type = 'AUTO'

        # 메쉬 변환 및 Smooth by Angle
        bpy.ops.object.select_all(action='DESELECT')
        for child in p_obj.children:
            if child.type == 'FONT':
                child.select_set(True)
                
        if context.selected_objects:
            context.view_layer.objects.active = context.selected_objects[0]
            bpy.ops.object.convert(target='MESH')
            
            for obj in context.selected_objects:
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.shade_smooth()
                if hasattr(obj.data, "use_auto_smooth"):
                    obj.data.use_auto_smooth = True
                    obj.data.auto_smooth_angle = math.radians(30)
                else:
                    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))

        self.report({'INFO'}, "동기화 스마트 베이크가 완료되었습니다!")
        return {'FINISHED'}

# --- 5. UI 패널 ---
class VIEW3D_PT_Hangeul_V27_Panel(bpy.types.Panel):
    bl_label = "한글 마스터 (Sync Bake)"
    bl_idname = "VIEW3D_PT_hangeul_v27_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '한글 편집'

    def draw(self, context):
        layout = self.layout
        props = context.scene.hangeul_v27_tool
        
        row = layout.row()
        row.prop(props, "is_live", toggle=True, icon='PLAY' if props.is_live else 'PAUSE')
        
        layout.prop(props, "text_input")
        layout.prop(props, "font_path")
        
        anim = layout.box()
        anim.label(text="진행도 제어 (여기에 키프레임을 잡으세요!)", icon='ANIM')
        anim.prop(props, "anim_factor", slider=True, text="진행도")
        anim.prop(props, "overlap", slider=True)
        anim.prop(props, "ease_intensity", text="감속 강도")
        
        off = anim.box()
        off.prop(props, "common_z_start")
        row = off.row(align=True)
        row.prop(props, "common_rot_x", text="RX")
        row.prop(props, "common_rot_y", text="RY")
        row.prop(props, "common_rot_z", text="RZ")
        
        geo = layout.box()
        geo.label(text="지오메트리", icon='MODIFIER')
        geo.prop(props, "outline_offset")
        geo.prop(props, "kerning")
        geo.prop(props, "extrude")
        geo.prop(props, "bevel")
        
        mat = layout.box()
        mat.label(text="트루 노말 마스킹", icon='SHADING_RENDERED')
        mat.operator("object.hangeul_create_mat_v27", text="재질 자동생성", icon='NODE_MATERIAL')
        mat.prop(props, "mat_main", text="마스터 재질")
        
        bake = layout.box()
        bake.label(text="최종 출력", icon='RENDER_ANIMATION')
        bake.operator("object.hangeul_bake_anim_v27", text="스마트 동기화 베이크", icon='KEYINGSET')
        
        layout.separator()
        layout.label(text="개별 사이즈:")
        grid = layout.grid_flow(row_major=True, columns=4, even_columns=True)
        for i in range(len(props.text_input)):
            if i >= 20: break
            item = grid.box()
            char_text = f"[{props.text_input[i]}]"
            item.label(text=char_text)
            item.prop(props, "char_sizes", index=i, text="")

@bpy.app.handlers.persistent
def hangeul_v27_handler(scene):
    try: 
        if scene.hangeul_v27_tool.is_live:
            bpy.ops.object.hangeul_v27_refresh()
    except: pass

classes = (OT_Hangeul_Create_Mat_V27, Hangeul_V27_Props, OT_Hangeul_V27_Refresh, OT_Hangeul_Bake_Anim_V27, VIEW3D_PT_Hangeul_V27_Panel)

def register():
    for cls in classes:
        if hasattr(bpy.types, cls.__name__): bpy.utils.unregister_class(cls)
        bpy.utils.register_class(cls)
    bpy.types.Scene.hangeul_v27_tool = bpy.props.PointerProperty(type=Hangeul_V27_Props)
    if hangeul_v27_handler not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(hangeul_v27_handler)

def unregister():
    if hangeul_v27_handler in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(hangeul_v27_handler)
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.hangeul_v27_tool

if __name__ == "__main__":

    register()


bl_info = {
    "name": "Hangeul Master V32 (Native Mat Fix)",
    "author": "Gemini",
    "version": (32, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Hangeul Edit Tab",
    "description": "네이티브 4-슬롯(Front/Back/Extrude/Bevel) 완벽 분리 및 통합 베이크",
    "category": "Object",
}

import bpy
import os
import math
import mathutils

_is_rendering = False

@bpy.app.handlers.persistent
def hangeul_render_pre(scene):
    global _is_rendering
    _is_rendering = True

@bpy.app.handlers.persistent
def hangeul_render_post(scene):
    global _is_rendering
    _is_rendering = False

@bpy.app.handlers.persistent
def hangeul_render_cancel(scene):
    global _is_rendering
    _is_rendering = False

def get_fcurves(anim_data):
    if not anim_data or not anim_data.action: return []
    action = anim_data.action
    if hasattr(action, "fcurves"): return action.fcurves
    else:
        try:
            import bpy_extras.anim_utils
            slot = getattr(anim_data, "action_slot", None)
            if slot is not None:
                channelbag = bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)
                if channelbag: return channelbag.fcurves
        except: pass
    return []

# --- 1. 속성 정의 (직관적인 3개 재질 슬롯 추가) ---
class Hangeul_V32_Props(bpy.types.PropertyGroup):
    text_input: bpy.props.StringProperty(name="내용", default="네이티브재질", update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    font_path: bpy.props.StringProperty(name="폰트 선택", subtype='FILE_PATH', update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    
    anim_factor: bpy.props.FloatProperty(name="진행도", default=1.0, min=0.0, max=1.0, precision=3, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    overlap: bpy.props.FloatProperty(name="오버래핑", default=0.5, min=0.0, max=0.99, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    ease_intensity: bpy.props.FloatProperty(name="감속 강도", default=3.0, min=0.1, max=10.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    
    common_x_start: bpy.props.FloatProperty(name="시작 X", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    common_y_start: bpy.props.FloatProperty(name="시작 Y", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    common_z_start: bpy.props.FloatProperty(name="시작 Z", default=2.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    
    common_rot_x: bpy.props.FloatProperty(name="시작 RX", default=45.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    common_rot_y: bpy.props.FloatProperty(name="시작 RY", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    common_rot_z: bpy.props.FloatProperty(name="시작 RZ", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    
    kerning: bpy.props.FloatProperty(name="자간", default=1.1, min=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    extrude: bpy.props.FloatProperty(name="두께", default=0.05, min=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    bevel: bpy.props.FloatProperty(name="베벨", default=0.01, min=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    outline_offset: bpy.props.FloatProperty(name="외곽선", default=0.0, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    
    # 💡 핵심: 부위별 독립적인 마테리얼 슬롯 부활
    mat_front: bpy.props.PointerProperty(name="앞면 (Front)", type=bpy.types.Material, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    mat_side: bpy.props.PointerProperty(name="옆면 (Side)", type=bpy.types.Material, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    mat_bevel: bpy.props.PointerProperty(name="베벨 (Bevel)", type=bpy.types.Material, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    
    char_sizes: bpy.props.FloatVectorProperty(name="사이즈", size=20, default=[1.0]*20, update=lambda self, context: bpy.ops.object.hangeul_v32_refresh() if self.is_live else None)
    is_live: bpy.props.BoolProperty(name="라이브 모드", default=True)

# --- 2. 실행 로직 ---
class OT_Hangeul_V32_Refresh(bpy.types.Operator):
    bl_idname = "object.hangeul_v32_refresh"
    bl_label = "Refresh"
    bl_options = {'INTERNAL', 'UNDO'}
    
    def execute(self, context):
        global _is_rendering
        props = context.scene.hangeul_v32_tool
        if not props.is_live or _is_rendering: return {'FINISHED'}
            
        p_obj = bpy.data.objects.get("Hangeul_Group")
        if p_obj:
            for child in p_obj.children: bpy.data.objects.remove(child, do_unlink=True)
        else:
            p_obj = bpy.data.objects.new("Hangeul_Group", None)
            context.collection.objects.link(p_obj)

        l_font = None
        if props.font_path and os.path.exists(props.font_path):
            try: l_font = bpy.data.fonts.load(props.font_path)
            except: pass

        count = len(props.text_input)
        if count == 0: return {'FINISHED'}
        
        # 더미 마테리얼 (빈 슬롯 에러 방지용)
        dummy_mat = bpy.data.materials.get("Hangeul_Default")
        if not dummy_mat: dummy_mat = bpy.data.materials.new(name="Hangeul_Default")
        
        mat_f = props.mat_front if props.mat_front else dummy_mat
        mat_s = props.mat_side if props.mat_side else dummy_mat
        mat_b = props.mat_bevel if props.mat_bevel else dummy_mat

        curr_x = 0.0
        for i, char in enumerate(props.text_input):
            if i >= 20: break
            s = props.char_sizes[i]
            if i > 0: curr_x += ((props.char_sizes[i-1] * 0.5) + (s * 0.5)) * props.kerning
                
            interval = (1.0 - props.overlap) / count
            start_t = i * interval
            end_t = start_t + props.overlap + interval
            raw_f = max(0.0, min(1.0, (props.anim_factor - start_t) / (end_t - start_t) if end_t > start_t else 1.0))
            inv_f = 1.0 - (1.0 - pow(1.0 - raw_f, props.ease_intensity))

            f_curve = bpy.data.curves.new(type="FONT", name=f"HV32_Char_{i}")
            f_curve.body = char
            if l_font: f_curve.font = l_font
            f_curve.align_x, f_curve.align_y = 'CENTER', 'BOTTOM'
            f_curve.size = s 
            f_curve.extrude, f_curve.bevel_depth = props.extrude, props.bevel
            f_curve.bevel_resolution, f_curve.offset = 4, props.outline_offset - props.bevel
            
            # 💡 핵심: 블렌더 텍스트 4-슬롯 법칙 완벽 준수
            f_curve.materials.clear()
            f_curve.materials.append(mat_f) # [Index 0] 앞면 (Front)
            f_curve.materials.append(mat_f) # [Index 1] 뒷면 (Back - 앞면과 동일하게)
            f_curve.materials.append(mat_s) # [Index 2] 두께 (Extrude/Side)
            f_curve.materials.append(mat_b) # [Index 3] 베벨 (Bevel)
            
            t_obj = bpy.data.objects.new(name=f"HV32_Obj_{i}", object_data=f_curve)
            context.collection.objects.link(t_obj)
            
            rot_euler = mathutils.Euler((math.radians(props.common_rot_x * inv_f), math.radians(props.common_rot_y * inv_f), math.radians(props.common_rot_z * inv_f)), 'XYZ')
            p_local = mathutils.Vector((0.0, s * 0.5, 0.0))
            p_rot = p_local.copy()
            p_rot.rotate(rot_euler)
            comp = p_local - p_rot
            
            t_obj.location = (curr_x + (props.common_x_start * inv_f) + comp.x, (props.common_y_start * inv_f) + comp.y, (props.common_z_start * inv_f) + comp.z)
            t_obj.rotation_euler = rot_euler
            t_obj.parent = p_obj
        return {'FINISHED'}

# --- 3. 동기화 베이크 ---
class OT_Hangeul_Bake_Anim_V32(bpy.types.Operator):
    bl_idname = "object.hangeul_bake_anim_v32"
    bl_label = "스마트 동기화 베이크 (Mesh 변환)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.hangeul_v32_tool
        p_obj = bpy.data.objects.get("Hangeul_Group")
        if not p_obj or not p_obj.children: return {'CANCELLED'}
        props.is_live = False
        
        g_start, g_end = context.scene.frame_start, context.scene.frame_end
        for fc in get_fcurves(context.scene.animation_data):
            if "anim_factor" in fc.data_path and len(fc.keyframe_points) >= 2:
                g_start, g_end = fc.keyframe_points[0].co.x, fc.keyframe_points[-1].co.x
                break
        
        total_f, count = g_end - g_start, len(props.text_input)
        curr_x = 0.0
        for i, char in enumerate(props.text_input):
            if i >= 20: break
            s = props.char_sizes[i]
            if i > 0: curr_x += ((props.char_sizes[i-1] * 0.5) + (s * 0.5)) * props.kerning
            
            t_start = g_start + (i * (1.0 - props.overlap) / count * total_f)
            t_end = t_start + (props.overlap + (1.0 - props.overlap) / count) * total_f
            
            rot_s = mathutils.Euler((math.radians(props.common_rot_x), math.radians(props.common_rot_y), math.radians(props.common_rot_z)), 'XYZ')
            p_rot = mathutils.Vector((0.0, s * 0.5, 0.0))
            p_rot.rotate(rot_s)
            comp_s = mathutils.Vector((0.0, s * 0.5, 0.0)) - p_rot
            
            l_start = (curr_x + props.common_x_start + comp_s.x, props.common_y_start + comp_s.y, props.common_z_start + comp_s.z)
            l_end = (curr_x, 0.0, 0.0)

            t_obj = bpy.data.objects.get(f"HV32_Obj_{i}")
            if t_obj:
                t_obj.animation_data_clear()
                for a in range(3):
                    if abs(l_start[a] - l_end[a]) > 0.001:
                        t_obj.location[a] = l_start[a]; t_obj.keyframe_insert(data_path="location", index=a, frame=t_start)
                        t_obj.location[a] = l_end[a]; t_obj.keyframe_insert(data_path="location", index=a, frame=t_end)
                    else: t_obj.location[a] = l_end[a]
                    if abs(rot_s[a]) > 0.001:
                        t_obj.rotation_euler[a] = rot_s[a]; t_obj.keyframe_insert(data_path="rotation_euler", index=a, frame=t_start)
                        t_obj.rotation_euler[a] = 0.0; t_obj.keyframe_insert(data_path="rotation_euler", index=a, frame=t_end)
                for fc in get_fcurves(t_obj.animation_data):
                    for kp in fc.keyframe_points: kp.interpolation, kp.handle_left_type, kp.handle_right_type = 'BEZIER', 'AUTO', 'AUTO'

        bpy.ops.object.select_all(action='DESELECT')
        for child in p_obj.children: child.select_set(True)
        bpy.context.view_layer.objects.active = context.selected_objects[0]
        # 메쉬 변환 시 네이티브 인덱스가 그대로 면(Face) 속성에 구워집니다.
        bpy.ops.object.convert(target='MESH')
        for obj in context.selected_objects:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
        return {'FINISHED'}

# --- 4. UI 패널 ---
class VIEW3D_PT_Hangeul_V32_Panel(bpy.types.Panel):
    bl_label = "한글 마스터 V32 (완벽 재질)"
    bl_idname = "VIEW3D_PT_hangeul_v32_panel"
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', '한글 편집'

    def draw(self, context):
        layout = self.layout
        props = context.scene.hangeul_v32_tool
        
        layout.prop(props, "is_live", toggle=True, icon='PLAY' if props.is_live else 'PAUSE')
        layout.prop(props, "text_input")
        layout.prop(props, "font_path")
        
        anim = layout.box()
        anim.label(text="애니메이션 제어", icon='ANIM')
        anim.prop(props, "anim_factor", slider=True)
        anim.prop(props, "overlap", slider=True)
        anim.prop(props, "ease_intensity")
        
        loc = anim.box()
        loc.label(text="시작 위치 (Offset)", icon='OBJECT_ORIGIN')
        loc.prop(props, "common_x_start")
        loc.prop(props, "common_y_start")
        loc.prop(props, "common_z_start")
        
        rot = anim.box()
        rot.label(text="시작 회전") 
        row = rot.row(align=True)
        row.prop(props, "common_rot_x", text="X")
        row.prop(props, "common_rot_y", text="Y")
        row.prop(props, "common_rot_z", text="Z")
        
        geo = layout.box()
        geo.label(text="지오메트리", icon='MODIFIER')
        row = geo.row(align=True)
        row.prop(props, "extrude")
        row.prop(props, "bevel")
        geo.prop(props, "kerning")
        geo.prop(props, "outline_offset")
        
        # 💡 자동생성 버튼 삭제, 직관적인 3개 슬롯 UI로 변경
        mat = layout.box()
        mat.label(text="재질 (각 부위별 독립 적용)", icon='MATERIAL')
        mat.prop(props, "mat_front")
        mat.prop(props, "mat_side")
        mat.prop(props, "mat_bevel")
        
        layout.separator()
        layout.operator("object.hangeul_bake_anim_v32", icon='KEYINGSET', text="스마트 동기화 베이크 (메쉬 변환)")
        
        layout.separator()
        layout.label(text="개별 사이즈:")
        grid = layout.grid_flow(row_major=True, columns=4, even_columns=True)
        for i in range(len(props.text_input)):
            if i >= 20: break
            item = grid.box()
            item.label(text=f"[{props.text_input[i]}]")
            item.prop(props, "char_sizes", index=i, text="")

@bpy.app.handlers.persistent
def hangeul_v32_handler(scene):
    try: 
        if not _is_rendering and hasattr(scene, "hangeul_v32_tool") and scene.hangeul_v32_tool.is_live:
            bpy.ops.object.hangeul_v32_refresh()
    except: pass

classes = (Hangeul_V32_Props, OT_Hangeul_V32_Refresh, OT_Hangeul_Bake_Anim_V32, VIEW3D_PT_Hangeul_V32_Panel)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.hangeul_v32_tool = bpy.props.PointerProperty(type=Hangeul_V32_Props)
    bpy.app.handlers.render_pre.append(hangeul_render_pre)
    bpy.app.handlers.render_post.append(hangeul_render_post)
    bpy.app.handlers.render_cancel.append(hangeul_render_cancel)
    bpy.app.handlers.frame_change_post.append(hangeul_v32_handler)

def unregister():
    bpy.app.handlers.render_pre.remove(hangeul_render_pre)
    bpy.app.handlers.render_post.remove(hangeul_render_post)
    bpy.app.handlers.render_cancel.remove(hangeul_render_cancel)
    bpy.app.handlers.frame_change_post.remove(hangeul_v32_handler)
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.hangeul_v32_tool

if __name__ == "__main__":
    register()

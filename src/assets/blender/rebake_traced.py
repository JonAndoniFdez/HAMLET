import bpy, os, sys, argparse, traceback, json, time

# HOW TO USE
#
# "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" -b -P "C:\JonanStuff\BlenderScripts\rebake_traced.py" -- --obj "C:\JonanStuff\Hands\Escaneado3.obj" --outdir "C:\JonanStuff\Hands\Escaneado3_v2.obj" --size 4096 --margin 16 --uvb "UVMap_2" --trace --renders --wire_after --export_uv_layout > "C:\JonanStuff\Hands\rebake_trace.log" 2>&1

# -------------------- Utils: logging & tracing --------------------
def log(m): print(f"[INFO] {m}")
def die(m): print(f"[ERROR] {m}"); sys.exit(1)
def ts(): return time.strftime("%Y%m%d_%H%M%S")

TRACE_DIR = None

def save_checkpoint(step_label):
    if not TRACE_DIR: return
    path = os.path.join(TRACE_DIR, f"{ts()}_{step_label}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    print(f"[TRACE] Checkpoint: {path}")

def dump_state(step_label, obj=None, mat=None, active_img_node=None):
    data = {"step": step_label, "scene": {}, "object": {}, "material": {}, "bake": {}}
    sc = bpy.context.scene
    data["scene"]["engine"] = sc.render.engine
    data["bake"] = dict(
        target=sc.render.bake.target,
        use_selected_to_active=sc.render.bake.use_selected_to_active,
        use_pass_direct=sc.render.bake.use_pass_direct,
        use_pass_indirect=sc.render.bake.use_pass_indirect,
        margin=sc.render.bake.margin,
        cage_extrusion=sc.render.bake.cage_extrusion,
        samples=sc.cycles.samples if sc.render.engine == "CYCLES" else None,
    )
    if obj:
        uvs = []
        for l in obj.data.uv_layers:
            uvs.append({"name": l.name, "active": (obj.data.uv_layers.active==l), "active_render": l.active_render})
        data["object"]["name"] = obj.name
        data["object"]["uv_layers"] = uvs
        data["object"]["materials"] = [m.name if m else None for m in obj.data.materials]
    if mat:
        nodes = []
        for n in mat.node_tree.nodes:
            entry = {"name": n.name, "type": n.type, "label": getattr(n, "label","")}
            if n.type == 'TEX_IMAGE' and n.image:
                entry["image"] = dict(name=n.image.name, size=list(getattr(n.image, "size", [])), filepath=str(n.image.filepath_raw))
            if n.type == 'UVMAP':
                entry["uv_map"] = n.uv_map
            nodes.append(entry)
        data["material"]["name"] = mat.name
        act = mat.node_tree.nodes.active
        data["material"]["active_node"] = dict(name=act.name, type=act.type) if act else None
    if active_img_node and getattr(active_img_node, "image", None):
        im = active_img_node.image
        data["active_image_node"] = dict(
            node=active_img_node.name,
            image=im.name,
            size=list(im.size) if hasattr(im, "size") else None,
            filepath=str(im.filepath_raw),
        )
    if TRACE_DIR:
        out = os.path.join(TRACE_DIR, f"{ts()}_{step_label}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[TRACE] State: {out}")
    else:
        print("[TRACE]", step_label, data)

def quick_view_render(path_png):
    sc = bpy.context.scene
    sc.render.filepath = path_png
    try:
        bpy.ops.render.render(write_still=True)
        print(f"[TRACE] Render: {path_png}")
    except Exception as e:
        print(f"[TRACE] Render failed: {e}")

# -------------------- CLI --------------------
def parse_args():
    argv = sys.argv
    if "--" in argv: argv = argv[argv.index("--")+1:]
    else: argv = []
    p = argparse.ArgumentParser("UV_A->UVMap_2 EMIT bake with traces")
    p.add_argument("--obj", required=True, help="Path to .obj")
    p.add_argument("--outdir", default=None, help="Output folder (default, next to OBJ)")
    p.add_argument("--uvb", default="UVMap_2", help="Name of target UV (will be created if it doesn't exist)")
    p.add_argument("--size", default="4096", help="'source' or integer (e.g., 4096)")
    p.add_argument("--margin", type=int, default=16, help="Bake margin (px)")
    p.add_argument("--trace", action="store_true", help="Save .blend/.json per step in _trace")
    p.add_argument("--renders", action="store_true", help="Save before.png / after.png in _trace")
    p.add_argument("--wire_after", action="store_true", help="Connect baked texture to material to see result")
    p.add_argument("--export_uv_layout", action="store_true", help="Export UV layout of UVMap_2")
    return p.parse_args(argv)

# -------------------- Core steps --------------------
def scene_empty_factory():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log("1) Empty scene ready")

def import_obj(path):
    if not os.path.isfile(path): die(f"OBJ not found: {path}")
    res = bpy.ops.wm.obj_import(filepath=path, forward_axis='NEGATIVE_Z', up_axis='Y')
    if 'FINISHED' not in res: die("OBJ import failed")
    mesh_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH'] \
             or  [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not mesh_objs: die("No mesh after import")
    obj = mesh_objs[0]
    log("2) OBJ imported")
    return obj

def ensure_uvmap_2_smart(obj, uv_name):
    uv_layers = obj.data.uv_layers
    if uv_name not in uv_layers:
        uv_layers.new(name=uv_name)
    log(f"3) {uv_name} created (if it didn't exist)")

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    uv_layers.active = uv_layers[uv_name]

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    try:
        bpy.ops.uv.smart_project(
            angle_limit=85.0,
            island_margin=0.0,
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=False,
            margin_method='SCALED',
            rotation_method='AXIS_ALIGNED',
        )
    except:
        bpy.ops.uv.smart_project(
            angle_limit=85.0,
            island_margin=0.0,
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=False,
        )
    bpy.ops.object.mode_set(mode='OBJECT')
    log(f"4) Smart UV Project applied to {uv_name}")

def get_original_material_and_image_node(obj):
    if not obj.data.materials or obj.data.uv_layers is None or obj.data.materials[0] is None:
        mat = bpy.data.materials.new(name="Material_Original")
        mat.use_nodes = True
        obj.data.materials.append(mat)
    mat = obj.data.materials[0]
    mat.use_nodes = True
    nt = mat.node_tree
    img_nodes = [n for n in nt.nodes if n.type == 'TEX_IMAGE']
    tex_in = img_nodes[0] if img_nodes else None
    return mat, tex_in

def create_newhandtexture_node(mat, uv_name, width, height):
    nt = mat.node_tree
    new_img = bpy.data.images.new("NewHandTexture", width=width, height=height, alpha=True, float_buffer=False)
    new_img.generated_color = (0.0, 0.0, 0.0, 1.0)
    tex_node = nt.nodes.new("ShaderNodeTexImage"); tex_node.image = new_img
    tex_node.label = "NewHandTexture_Node"; tex_node.location = (-300, -220)
    uvnode = nt.nodes.new("ShaderNodeUVMap"); uvnode.uv_map = uv_name; uvnode.location = (-560, -220)
    nt.links.new(uvnode.outputs['UV'], tex_node.inputs['Vector'])
    nt.nodes.active = tex_node
    log(f"5) NewHandTexture created {width}x{height} and connected to {uv_name}")
    return tex_node

def ensure_uvmap_for_original_texture(mat, tex_in, original_uv_name):
    if not tex_in:
        log("6) No original texture; continuing anyway")
        return
    nt = mat.node_tree
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = original_uv_name
    uvn.location = (tex_in.location.x - 260, tex_in.location.y)
    try:
        nt.links.new(uvn.outputs['UV'], tex_in.inputs['Vector'])
    except:
        pass
    ok = any(l.to_node==tex_in and l.to_socket==tex_in.inputs['Vector'] for l in nt.links)
    log(f"6) UVMap connected to original texture? {ok}")

def set_cycles_emit_bake(margin_px):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'NONE'
    except: pass
    sc.cycles.samples = 1
    sc.render.bake.target = 'IMAGE_TEXTURES'
    sc.render.bake.use_selected_to_active = False
    sc.render.bake.use_pass_direct = False
    sc.render.bake.use_pass_indirect = False
    sc.render.bake.margin = margin_px
    sc.render.bake.cage_extrusion = 0.0
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    sc.display_settings.display_device = 'sRGB'
    force_bake_type_emit()
    log("7) Cycles+Bake configured (EMIT passed in operator)")

def force_bake_type_emit():
    sc = bpy.context.scene
    where = None
    ok = False
    try:
        sc.render.bake.type = 'EMIT'
        where = "scene.render.bake.type"
        ok = True
    except Exception:
        pass
    if not ok:
        try:
            sc.cycles.bake_type = 'EMIT'
            where = "scene.cycles.bake_type"
            ok = True
        except Exception:
            pass
    if ok:
        log(f"7) Bake Type set to EMIT in {where}")
    else:
        log("7) No property to set Bake Type; will use operator with type='EMIT'")
    return ok, where

def ensure_node_wrangler():
    try:
        bpy.ops.preferences.addon_enable(module="node_wrangler")
        log("8) Node Wrangler enabled")
    except Exception as e:
        log(f"8) Node Wrangler not available ({e}). Continuing.")

# --- preview seguro (no toca UV->Vector)
def preview_source_like_node_wrangler(mat, tex_in):
    if not tex_in:
        log("No original texture to preview; skipping.")
        return
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    emission = next((n for n in nodes if n.type=='EMISSION'), None) or nodes.new("ShaderNodeEmission")
    out = next((n for n in nodes if n.type=='OUTPUT_MATERIAL'), None) or nodes.new("ShaderNodeOutputMaterial")
    emission.location = (80, 0); out.location = (300, 0)
    for l in list(links):
        if l.to_node == out and l.to_socket == out.inputs.get('Surface'):
            try: links.remove(l)
            except: pass
    for l in list(links):
        if l.to_node == emission and l.to_socket == emission.inputs.get('Color'):
            try: links.remove(l)
            except: pass
    links.new(tex_in.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], out.inputs['Surface'])
    nodes.active = tex_in
    log("Source preview done WITHOUT modifying UV→Vector.")

def activate_target_image_node(mat, target_img_node):
    mat.node_tree.nodes.active = target_img_node
    log("Active node set to NewHandTexture (bake target).")

def do_bake_emit(obj, mat, active_img_node, uvb_name, w_expected, h_expected):
    if active_img_node is None or active_img_node.type != 'TEX_IMAGE':
        die("Invalid target image node")
    assert obj.data.uv_layers[uvb_name].active_render, f"{uvb_name} is NOT Active Render"
    assert obj.data.uv_layers.active.name == uvb_name, "Active UV is not the target"
    assert mat.node_tree.nodes.active == active_img_node, "Active node is NOT NewHandTexture"
    if hasattr(active_img_node.image, "size"):
        iw, ih = active_img_node.image.size[0], active_img_node.image.size[1]
        assert iw == w_expected and ih == h_expected, f"Unexpected NewHandTexture size: {iw}x{ih}"
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    log("9) Baking EMIT…")
    res = bpy.ops.object.bake(type='EMIT')
    if 'FINISHED' not in res: die("Bake did not finish with FINISHED")
    log("9) Bake completed")

def save_newhandtexture(active_img_node, out_path):
    img = active_img_node.image
    img.file_format = 'PNG'
    img.filepath_raw = out_path
    img.save()
    log(f"10) Texture saved: {out_path}")

def set_active_render_uv(obj, uv_name):
    for l in obj.data.uv_layers: l.active_render = False
    obj.data.uv_layers[uv_name].active_render = True
    obj.data.uv_layers.active = obj.data.uv_layers[uv_name]

def wire_baked_for_view(obj, baked_node):
    mat = obj.data.materials[0]
    nt = mat.node_tree; nodes, links = nt.nodes, nt.links
    emission = next((n for n in nodes if n.type=='EMISSION'), None) or nodes.new("ShaderNodeEmission")
    out = next((n for n in nodes if n.type=='OUTPUT_MATERIAL'), None) or nodes.new("ShaderNodeOutputMaterial")
    emission.location = (80, 0); out.location = (300, 0)
    for l in list(links):
        if l.to_node == out and l.to_socket == out.inputs.get('Surface'):
            try: links.remove(l)
            except: pass
    for l in list(links):
        if l.to_node == emission and l.to_socket == emission.inputs.get('Color'):
            try: links.remove(l)
            except: pass
    links.new(baked_node.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], out.inputs['Surface'])
    log("Visualization connected (Emission <- baked) without modifying UV/Mapping.")

def ensure_tex_has_uv_vector(mat, tex_node, uv_name):
    if not tex_node:
        return
    nt = mat.node_tree
    vector_socket = tex_node.inputs.get('Vector')
    if not vector_socket:
        return
    has_vector_link = any(l.to_node == tex_node and l.to_socket == vector_socket for l in nt.links)
    if has_vector_link:
        return
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = uv_name
    uvn.location = (tex_node.location.x - 260, tex_node.location.y)
    nt.links.new(uvn.outputs['UV'], vector_socket)
    log(f"Reconnected UVMap('{uv_name}') -> {tex_node.name}.Vector")

def export_uv_layout(obj, uv_name, path_png="UVMap_2_layout.png", size=4096):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.data.uv_layers.active = obj.data.uv_layers[uv_name]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.export_layout(filepath=path_png, size=(size, size), opacity=0.25)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[TRACE] UV layout: {path_png}")

# -------------------- NUEVO: preparar material para export OBJ/MTL --------------------
def prepare_material_for_export(obj, baked_img_path, uv_name):
    """
    Creates a clean material with Principled BSDF and connects NewHandTexture (PNG) to Base Color.
    This ensures the .MTL writes 'map_Kd' correctly and points to the texture.
    """
    # Load/use baked image from disk
    baked_img = None
    for im in bpy.data.images:
        if os.path.abspath(im.filepath or im.filepath_raw) == os.path.abspath(baked_img_path):
            baked_img = im
            break
    if baked_img is None:
        baked_img = bpy.data.images.load(baked_img_path)

    mat = bpy.data.materials.new("MAT_Export_OBJ")
    mat.use_nodes = True
    nt = mat.node_tree
    # Clear nodes
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (120, 0)
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-200, 0); tex.image = baked_img
    # Do NOT connect UVMap node: the OBJ exports UVs from mesh; MTL only needs map_Kd.
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    # Assign unique material
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    # Ensure target UV as active/render before export
    set_active_render_uv(obj, uv_name)

    # Ensure image path is relative to outdir at export (set to filename)
    tex.image.filepath = os.path.basename(baked_img_path)
    tex.image.filepath_raw = os.path.basename(baked_img_path)
    tex.image.reload()

    log("Export material prepared (Principled + map_Kd).")
    return mat

# === Ensure: Set Origin -> Origin to Center of Mass (Surface) and move to 0,0,0 ===
# Insert just before exporting the OBJ
def center_origin_and_zero_location():
    # Prefer active object; if not, take first available mesh
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        for o in bpy.data.objects:
            if o.type == 'MESH':
                obj = o
                break

    if not obj:
        log("Warning: no MESH object found to center origin.")
        return False

    # Previous state
    prev_loc = tuple(obj.location)
    log(f"center_origin_and_zero_location: object selected '{obj.name}', previous location: {prev_loc}")

    # Ensure selection/active
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # Set origin -> center of mass (surface)
    origin_ok = False
    try:
        bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='MEDIAN')
        origin_ok = True
        log("center_origin_and_zero_location: origin_set(type='ORIGIN_CENTER_OF_MASS', center='MEDIAN') completed.")
    except Exception as e:
        log(f"center_origin_and_zero_location: Error performing origin_set: {e}")

    # Move object position to 0,0,0 (origin now at COM surface)
    try:
        obj.location = (0.0, 0.0, 0.0)
        # Force view/depsgraph update
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        new_loc = tuple(obj.location)
        if all(abs(n) < 1e-9 for n in new_loc):
            log("center_origin_and_zero_location: object moved to (0.0, 0.0, 0.0) correctly.")
            return True
        else:
            log(f"center_origin_and_zero_location: attempt to move to (0,0,0) resulted in location: {new_loc}")
            return origin_ok
    except Exception as e:
        log(f"center_origin_and_zero_location: Error moving object to (0,0,0): {e}")
        return origin_ok


def export_obj_with_mtl(obj, out_obj_path):
    """
    Export OBJ + MTL with relative paths (map_Kd pointing to PNG next to OBJ).
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # Exportar (nuevo exportador OBJ de Blender 4.x)
    res = bpy.ops.wm.obj_export(
        filepath=out_obj_path,
        export_selected_objects=True,
        export_normals=True,
        export_uv=True,
        export_materials=True,
        path_mode='RELATIVE',  # rutas relativas al .obj
        export_triangulated_mesh=False,
    )
    if 'FINISHED' not in res:
        die("OBJ/MTL export failed")
    log(f"OBJ/MTL exported: {out_obj_path}")

# -------------------- MAIN --------------------
def main():
    global TRACE_DIR
    args = parse_args()
    obj_path = os.path.abspath(args.obj)
    outdir = os.path.abspath(args.outdir) if args.outdir else os.path.dirname(obj_path)
    os.makedirs(outdir, exist_ok=True)
    out_img_path = os.path.join(outdir, "NewHandTexture.png")
    # nombres de salida del OBJ/MTL
    stem = os.path.splitext(os.path.basename(obj_path))[0]
    out_obj_path = os.path.join(outdir, f"{stem}_UVB.obj")
    TRACE_DIR = os.path.join(outdir, "_trace") if args.trace else None
    if TRACE_DIR: os.makedirs(TRACE_DIR, exist_ok=True)

    try:
        # Step 1
        scene_empty_factory()
        if TRACE_DIR: dump_state("Step_1_scene")

        # Step 2
        obj = import_obj(obj_path)
        if not obj.data.uv_layers: die("OBJ does not contain source UVs")
        uv_a = obj.data.uv_layers.active.name
        if TRACE_DIR: dump_state("Step_2_import", obj=obj); save_checkpoint("Step_2_import")

        # Steps 3-4
        ensure_uvmap_2_smart(obj, args.uvb)
        set_active_render_uv(obj, args.uvb)
        if TRACE_DIR: dump_state("Step_4_smart_uv", obj=obj); save_checkpoint("Step_4_smart_uv")

        # Steps 5-6
        mat, tex_in = get_original_material_and_image_node(obj)
        if args.size.lower() == "source" and tex_in and tex_in.image:
            w, h = tex_in.image.size[0], tex_in.image.size[1]
        else:
            w = h = int(args.size)
        newhand_node = create_newhandtexture_node(mat, args.uvb, w, h)
        ensure_uvmap_for_original_texture(mat, tex_in, uv_a)
        if TRACE_DIR: dump_state("Step_6_material_nodes", obj=obj, mat=mat, active_img_node=newhand_node); save_checkpoint("Step_6_material_nodes")

        # Step 7
        set_cycles_emit_bake(args.margin)
        if TRACE_DIR: dump_state("Step_7_cycles_bake", obj=obj, mat=mat, active_img_node=newhand_node)

        # Step 8
        ensure_node_wrangler()

        # Step 9a preview
        preview_source_like_node_wrangler(mat, tex_in)
        if TRACE_DIR: dump_state("Step_9a_preview_source", obj=obj, mat=mat)
        ensure_tex_has_uv_vector(mat, tex_in, uv_a)
        ensure_tex_has_uv_vector(mat, newhand_node, args.uvb)

        # Step 9b activate target
        activate_target_image_node(mat, newhand_node)
        if TRACE_DIR: dump_state("Step_9b_target_active", obj=obj, mat=mat, active_img_node=newhand_node)

        # Step 9 bake
        do_bake_emit(obj, mat, newhand_node, args.uvb, w, h)
        if TRACE_DIR: dump_state("Step_9_post_bake", obj=obj, mat=mat, active_img_node=newhand_node); save_checkpoint("Step_9_post_bake")

        # Step 10 save texture
        save_newhandtexture(newhand_node, out_img_path)

        # (optional) view in Emission in open session
        if args.wire_after:
            wire_baked_for_view(obj, newhand_node)

        # ---------- NEW: prepare and export OBJ/MTL with texture ----------
        # export material: Principled + map_Kd, active uv = args.uvb
        prepare_material_for_export(obj, out_img_path, args.uvb)

        center_origin_and_zero_location()
        # export OBJ + MTL next to texture (relative paths)
        export_obj_with_mtl(obj, out_obj_path)

        # Optional UV layout (if running in UI; may fail in background)
        if TRACE_DIR and args.export_uv_layout:
            try:
                export_uv_layout(obj, args.uvb, os.path.join(TRACE_DIR, f"{args.uvb}_layout.png"), size=max(w,h))
            except Exception as e:
                log(f"UV layout skipped: {e}")

        log("Process COMPLETE ✓")
        log(f"UV_A (read): {uv_a}")
        log(f"UV_B (write/Active Render): {args.uvb}")
        log(f"Texture: {out_img_path}")
        log(f"OBJ/MTL: {out_obj_path}")
        sys.exit(0)

    except Exception as e:
        traceback.print_exc()
        die(str(e))

if __name__ == "__main__":
    main()

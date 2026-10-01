import bpy
import sys
import os
import math
import csv
from mathutils import Vector, Matrix

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.dirname(SCRIPT_DIR)
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)

from blender_texture_material_utils import repair_and_pack_hand_texture

# ----------------------------------------------------------
# 0) Args
# ----------------------------------------------------------
def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []

    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--obj", required=True, help="Path to hand OBJ (can include spheres)")
    p.add_argument("--csv", required=True, help="OpenPose 2D keypoints CSV")
    p.add_argument("--resolution", type=int, default=1024, help="Square render resolution")
    p.add_argument("--out_blend", required=False, help="Output .blend")
    return p.parse_args(argv)

# ----------------------------------------------------------
# 1) Clean + import OBJ
# ----------------------------------------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def _mesh_priority(obj):
    name = obj.name.lower()
    sphere_penalty = 1 if name.startswith("sphere") else 0
    try:
        dims = obj.dimensions
        volume_like = float(dims.x) * float(dims.y) * float(dims.z)
    except Exception:
        volume_like = 0.0
    try:
        nverts = len(obj.data.vertices)
    except Exception:
        nverts = 0
    return (sphere_penalty, -volume_like, -nverts, name)


def import_obj(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.import_scene.obj(filepath=path)

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not mesh_objs:
        raise RuntimeError("No MESH imported")

    mesh_objs.sort(key=_mesh_priority)
    hand_obj = mesh_objs[0]
    print(f"[INFO] Selected hand mesh for rigging: {hand_obj.name}")
    return hand_obj

# ----------------------------------------------------------
# Hand + spheres helpers
# ----------------------------------------------------------
def get_hand_and_spheres(hand_obj):
    spheres = []
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and o is not hand_obj:
            if o.name.lower().startswith("sphere"):
                spheres.append(o)
    return hand_obj, spheres

def hide_spheres_for_raycast(hand_obj):
    _, spheres = get_hand_and_spheres(hand_obj)
    for s in spheres:
        s.hide_viewport = True
        s.hide_render = True
        try:
            s.hide_set(True)
        except AttributeError:
            pass
    bpy.context.view_layer.update()

def restore_and_fix_spheres(hand_obj):
    _, spheres = get_hand_and_spheres(hand_obj)

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    for s in spheres:
        s.hide_viewport = False
        s.hide_render = False
        try:
            s.hide_set(False)
        except AttributeError:
            pass

        # reset local rotation
        s.rotation_euler = (0.0, 0.0, 0.0)

        # origin to geometry center
        bpy.ops.object.select_all(action="DESELECT")
        s.select_set(True)
        bpy.context.view_layer.objects.active = s
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")

    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.update()

# ----------------------------------------------------------
# Camera setup WITHOUT moving the mesh
# ----------------------------------------------------------
def get_bbox_center_and_size(obj):
    bpy.context.view_layer.update()
    bbox_world = [obj.matrix_world @ Vector(c) for c in obj.bound_box]

    min_co = Vector((min(v.x for v in bbox_world),
                     min(v.y for v in bbox_world),
                     min(v.z for v in bbox_world)))
    max_co = Vector((max(v.x for v in bbox_world),
                     max(v.y for v in bbox_world),
                     max(v.z for v in bbox_world)))

    center = (min_co + max_co) * 0.5
    size = max_co - min_co
    return center, size

def setup_camera(center, size, resolution):
    scene = bpy.context.scene

    cam_data = bpy.data.cameras.new("HandCam")
    cam_obj = bpy.data.objects.new("HandCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    cam_data.type = "ORTHO"
    max_dim = max(size.x, size.y, size.z)
    cam_data.ortho_scale = max_dim * 1.2

    # place camera above the hand bbox center, looking down -Z
    cam_obj.location = (center.x, center.y, center.z + max_dim * 2.0)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)

    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100

    return cam_obj, cam_data

# ----------------------------------------------------------
# Load OpenPose CSV
# ----------------------------------------------------------
def _safe_float(value, default=float("nan")):
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    try:
        return float(s)
    except Exception:
        return default


def load_keypoints_csv(csv_path):
    csv_path = os.path.abspath(csv_path)
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(csv_path)

    keypoints = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = _safe_float(row.get("x"))
            y = _safe_float(row.get("y"))
            conf = _safe_float(row.get("conf"), 1.0)
            keypoints.append((x, y, conf))
    return keypoints

# ----------------------------------------------------------
# 2D -> 3D raycast in WORLD space
# ----------------------------------------------------------
def keypoints_2d_to_3d(keypoints, cam_obj, cam_data, resolution):
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()

    res_x = resolution
    res_y = resolution
    ortho_scale = cam_data.ortho_scale
    cam_z = cam_obj.location.z

    joint_names = [
        "wrist",
        "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
        "index_mcp", "index_pip", "index_dip", "index_tip",
        "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
        "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
        "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
    ]

    # Para fallback de Z consistente
    prev_joint = {
        "thumb_cmc": "wrist", "thumb_mcp": "thumb_cmc", "thumb_ip": "thumb_mcp", "thumb_tip": "thumb_ip",
        "index_mcp": "wrist", "index_pip": "index_mcp", "index_dip": "index_pip", "index_tip": "index_dip",
        "middle_mcp": "wrist", "middle_pip": "middle_mcp", "middle_dip": "middle_pip", "middle_tip": "middle_dip",
        "ring_mcp": "wrist", "ring_pip": "ring_mcp", "ring_dip": "ring_pip", "ring_tip": "ring_dip",
        "pinky_mcp": "wrist", "pinky_pip": "pinky_mcp", "pinky_dip": "pinky_pip", "pinky_tip": "pinky_dip",
    }

    points_3d = {}

    # Parámetros numéricos
    max_dist = abs(cam_z) * 6.0
    eps = 1e-4  # empuje para no rehacer hit en la misma cara

    for idx, (x_px, y_px, conf) in enumerate(keypoints):
        if idx >= len(joint_names):
            break
        name = joint_names[idx]

        # Validación básica
        if math.isnan(x_px) or math.isnan(y_px) or conf <= 0.0:
            pj = prev_joint.get(name)
            if pj and pj in points_3d:
                points_3d[name] = points_3d[pj].copy()
                print(f"[INFO] {name}: invalid (nan/conf) -> fallback {pj}")
            else:
                print(f"[WARN] {name}: invalid (nan/conf) and no fallback")
            continue

        # pixel -> normalized [0..1]
        x_norm = x_px / res_x
        y_norm = y_px / res_y  # top=0

        # offset en el plano ortho
        x_off = (x_norm - 0.5) * ortho_scale
        y_off = ((1.0 - y_norm) - 0.5) * ortho_scale

        origin = Vector((cam_obj.location.x + x_off,
                         cam_obj.location.y + y_off,
                         cam_z))
        direction = Vector((0.0, 0.0, -1.0))

        # --- Raycast 1 (primera superficie) ---
        hit1, loc1, normal1, face_index1, obj1, matrix1 = scene.ray_cast(
            depsgraph, origin, direction, distance=max_dist
        )

        loc_final = None

        if hit1 and obj1 is not None and obj1.type == "MESH":
            # --- Raycast 2 (segunda superficie), empezando "dentro" ---
            origin2 = loc1 + direction * eps
            hit2, loc2, normal2, face_index2, obj2, matrix2 = scene.ray_cast(
                depsgraph, origin2, direction, distance=max_dist
            )

            if hit2 and obj2 is not None and obj2.type == "MESH":
                # Dos superficies -> punto medio
                loc_final = (loc1 + loc2) * 0.5
                print(f"[OK] {name}: 2 hits -> midpoint")
            else:
                # Solo un hit -> fallback: Z del anterior
                pj = prev_joint.get(name)
                if pj and pj in points_3d:
                    prev_loc = points_3d[pj]
                    loc_final = Vector((origin.x, origin.y, prev_loc.z))
                    print(f"[INFO] {name}: 1 hit -> XY from csv, Z from {pj}")
                else:
                    # Sin anterior -> usar loc1
                    loc_final = loc1
                    print(f"[INFO] {name}: 1 hit and no prev -> using loc1")
        else:
            # Sin hits -> fallback Z anterior
            pj = prev_joint.get(name)
            if pj and pj in points_3d:
                prev_loc = points_3d[pj]
                loc_final = Vector((origin.x, origin.y, prev_loc.z))
                print(f"[INFO] {name}: 0 hits -> XY from csv, Z from {pj}")
            else:
                loc_final = Vector((origin.x, origin.y, 0.0))
                print(f"[WARN] {name}: 0 hits and no prev -> Z=0")

        points_3d[name] = loc_final

    return points_3d


# ----------------------------------------------------------
# Build armature: place it at SAME origin as the hand (location),
# and store bones in armature LOCAL space (world -> local conversion)
# ----------------------------------------------------------
def build_armature_from_joints(joints_world, arm_matrix_world):
    if "wrist" not in joints_world:
        raise RuntimeError("Missing wrist joint")

    chains = [
        ("wrist", "thumb_cmc"),
        ("thumb_cmc", "thumb_mcp"),
        ("thumb_mcp", "thumb_ip"),
        ("thumb_ip", "thumb_tip"),

        ("wrist", "index_mcp"),
        ("index_mcp", "index_pip"),
        ("index_pip", "index_dip"),
        ("index_dip", "index_tip"),

        ("wrist", "middle_mcp"),
        ("middle_mcp", "middle_pip"),
        ("middle_pip", "middle_dip"),
        ("middle_dip", "middle_tip"),

        ("wrist", "ring_mcp"),
        ("ring_mcp", "ring_pip"),
        ("ring_pip", "ring_dip"),
        ("ring_dip", "ring_tip"),

        ("wrist", "pinky_mcp"),
        ("pinky_mcp", "pinky_pip"),
        ("pinky_pip", "pinky_dip"),
        ("pinky_dip", "pinky_tip"),
    ]

    arm_data = bpy.data.armatures.new("HandArmature")
    arm_obj = bpy.data.objects.new("HandArmature", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)

    # VERY IMPORTANT: set armature matrix_world FIRST
    arm_obj.matrix_world = arm_matrix_world.copy()
    bpy.context.view_layer.update()

    inv_arm = arm_obj.matrix_world.inverted()

    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    bones = {}
    for head_name, tail_name in chains:
        if head_name not in joints_world or tail_name not in joints_world:
            continue

        head_w = joints_world[head_name]
        tail_w = joints_world[tail_name]

        # convert world -> armature local
        head = inv_arm @ head_w
        tail = inv_arm @ tail_w

        if (tail - head).length < 1e-4:
            tail = head + Vector((0.0, 0.01, 0.0))

        bone = arm_data.edit_bones.new(f"{head_name}__to__{tail_name}")
        bone.head = head
        bone.tail = tail
        bones[(head_name, tail_name)] = bone

    # parenting bones
    for (head_name, tail_name), bone in bones.items():
        if head_name == "wrist":
            bone.parent = None
        else:
            parent_bone = None
            for (h2, t2), b2 in bones.items():
                if t2 == head_name:
                    parent_bone = b2
                    break
            if parent_bone:
                bone.parent = parent_bone
                bone.use_connect = True

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    print("[OK] Armature created with bones:", len(bones))
    return arm_obj

# ----------------------------------------------------------
# Bind with auto weights
# ----------------------------------------------------------
def bind_armature_auto_weights(hand_obj, arm_obj):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    hand_obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    print("[OK] Auto weights done (ARMATURE_AUTO).")

# ----------------------------------------------------------
# Rotate ONLY the armature around the same origin as the hand
# ----------------------------------------------------------
def rotate_armature_only(arm_obj, hand_obj, rot_x_deg=-90.0):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    # Ensure armature pivot/origin is at hand origin (same location)
    arm_obj.location = hand_obj.location

    # Apply rotation only to the armature object
    arm_obj.rotation_euler = (math.radians(rot_x_deg), arm_obj.rotation_euler.y, arm_obj.rotation_euler.z)
    bpy.context.view_layer.update()
    print(f"[OK] Rotated armature only: X = {rot_x_deg} deg")


def _texture_candidates_for_obj(obj_path, out_blend):
    dirs = [os.path.dirname(os.path.abspath(obj_path))]
    if out_blend:
        dirs.append(os.path.dirname(os.path.abspath(out_blend)))
    return dirs

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------
def main():
    args = parse_args()

    print("=== build_hand_armature_from_openpose.py (armature aligned to hand origin; rotate armature only) ===")
    print("obj:", args.obj)
    print("csv:", args.csv)
    print("res:", args.resolution)
    print("out:", args.out_blend)
    print("cwd:", os.getcwd())
    print("==============================================================================================")

    clear_scene()
    hand_obj = import_obj(args.obj)

    # DO NOT MOVE the hand (no centering)
    center, size = get_bbox_center_and_size(hand_obj)

    # hide spheres so raycasts do not hit them
    hide_spheres_for_raycast(hand_obj)

    cam_obj, cam_data = setup_camera(center, size, args.resolution)

    keypoints_2d = load_keypoints_csv(args.csv)
    joints_3d_world = keypoints_2d_to_3d(keypoints_2d, cam_obj, cam_data, args.resolution)

    if not joints_3d_world:
        raise RuntimeError("No joints_3d computed")

    # save joints
    joints_csv_path = os.path.join(os.path.dirname(os.path.abspath(args.csv)), "hand_joints_3d.csv")
    with open(joints_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["joint", "x", "y", "z"])
        for name, loc in joints_3d_world.items():
            w.writerow([name, loc.x, loc.y, loc.z])
    print("[OK] 3D joints saved:", joints_csv_path)

    # Build armature with SAME origin as the hand (location), no drifting
    # Use a matrix_world that shares hand location (translation) but identity rotation/scale
    arm_mw = Matrix.Translation(hand_obj.location)
    arm_obj = build_armature_from_joints(joints_3d_world, arm_mw)

    # bind with auto weights
    bind_armature_auto_weights(hand_obj, arm_obj)

    # restore spheres + fix
    restore_and_fix_spheres(hand_obj)

    # FINAL: rotate ONLY the armature (after bind), keeping same origin as the hand
    rotate_armature_only(arm_obj, hand_obj, rot_x_deg=-90.0)

    # Save blend
    if args.out_blend:
        out_blend = os.path.abspath(args.out_blend)
    else:
        obj_root, _ = os.path.splitext(os.path.abspath(args.obj))
        out_blend = obj_root + "_rigged.blend"

    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    repair_and_pack_hand_texture(
        hand_obj,
        search_dirs=_texture_candidates_for_obj(args.obj, out_blend),
    )
    print("[INFO] Saving .blend:", out_blend)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print("[OK] Done:", out_blend)

if __name__ == "__main__":
    main()

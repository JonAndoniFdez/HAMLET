import bpy
import sys
import os
import argparse
import math
from mathutils import Vector


# ---------------------------------------
# Parseo de argumentos: --obj y --out
# ---------------------------------------
def parse_args():
    # Blender pasa sus propios args antes de "--"
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", required=True, help="Path to hand OBJ")
    parser.add_argument("--out", required=True, help="Path to output PNG")
    parser.add_argument("--resolution", type=int, default=1024, help="Square resolution")
    args = parser.parse_args(argv)
    return args

# ---------------------------------------
# Clean scene (delete everything)
# ---------------------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------
# Import OBJ (compatibility 4.x and <4)
# ---------------------------------------
def _mesh_priority(obj):
    name = obj.name.lower()
    # Strongly penalize helper spheres; then prefer the largest real mesh.
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

    # Blender 4.x usa bpy.ops.wm.obj_import
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.import_scene.obj(filepath=path)

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not mesh_objs:
        raise RuntimeError("No MESH object was imported")

    mesh_objs.sort(key=_mesh_priority)
    hand_obj = mesh_objs[0]
    print(f"[INFO] Selected hand mesh for render: {hand_obj.name}")
    return hand_obj

# ---------------------------------------
# Center object at origin and calculate its size
# ---------------------------------------
def center_object(obj):
    bpy.context.view_layer.update()

    # Bounding box in world space
    bbox_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_co = Vector((min(v.x for v in bbox_world),
                     min(v.y for v in bbox_world),
                     min(v.z for v in bbox_world)))
    max_co = Vector((max(v.x for v in bbox_world),
                     max(v.y for v in bbox_world),
                     max(v.z for v in bbox_world)))
    center = (min_co + max_co) * 0.5
    size = max_co - min_co

    # Move object so center is at origin
    obj.location -= center
    bpy.context.view_layer.update()

    return size

# ---------------------------------------
# Create orthographic camera, adjust hand and configure render without shadows
# ---------------------------------------
def setup_camera_and_flat_shading(size, resolution):
    scene = bpy.context.scene

    # Render engine: Workbench (viewport-like view, no real lighting)
    scene.render.engine = 'BLENDER_WORKBENCH'

    # Camera
    cam_data = bpy.data.cameras.new("HandCam")
    cam_obj = bpy.data.objects.new("HandCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # Orthographic camera to facilitate 2D↔3D projection
    cam_data.type = 'ORTHO'

    # Orthographic scale: cover largest dimension with margin
    max_dim = max(size.x, size.y, size.z)
    cam_data.ortho_scale = max_dim * 1.2

    # Place camera at +Z looking at origin (0,0,0)
    cam_obj.location = (0.0, 0.0, max_dim * 2.0)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)

    # Render settings
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100

    # Black background (useful for OpenPose)
    if not scene.world:
        scene.world = bpy.data.worlds.new("World")
    # In Workbench the background comes from the theme, but we keep the world black anyway
    scene.world.use_nodes = False
    scene.world.color = (0.0, 0.0, 0.0)

    # Configure Workbench so there are no shadows or weird effects:
    # use flat shading and texture color.
    shading = scene.display.shading
    shading.light = 'FLAT'        # sin dirección, sin sombras
    shading.color_type = 'TEXTURE'  # usa la textura / color del objeto
    shading.show_shadows = False
    shading.show_cavity = False
    shading.show_specular_highlight = False

    return cam_obj

# ---------------------------------------
# Render
# ---------------------------------------
def render_to_file(out_path):
    scene = bpy.context.scene
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = out_path

    bpy.ops.render.render(write_still=True)
    print(f"[OK] Generated render: {out_path}")

# ---------------------------------------
# Main
# ---------------------------------------
def main():
    args = parse_args()

    clear_scene()
    hand = import_obj(args.obj)
    size = center_object(hand)
    setup_camera_and_flat_shading(size, args.resolution)
    # NOTE: we no longer call setup_light, we don't want lights or shadows
    render_to_file(args.out)

if __name__ == "__main__":
    main()

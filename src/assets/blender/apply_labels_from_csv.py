# apply_labels_from_csv.py
#
# Usage (from command line):
# blender hand_instance_labeled.blend --background --python apply_labels_from_csv.py -- \
#   --labels_csv "/path/detections_labeled_corrected.csv" \
#   --save_blend "/path/hand_instance_labeled_manual.blend"

import bpy
import sys
import os
import csv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.dirname(SCRIPT_DIR)
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)

from blender_texture_material_utils import repair_and_pack_hand_texture


def parse_args(argv):
    """
    Arguments after '--':
      --labels_csv CORRECTED_CSV_PATH
      --save_blend OUTPUT_BLEND_PATH
    """
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    labels_csv = None
    save_blend_path = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--labels_csv" and i + 1 < len(argv):
            labels_csv = argv[i + 1]
            i += 2
        elif arg == "--save_blend" and i + 1 < len(argv):
            save_blend_path = argv[i + 1]
            i += 2
        else:
            i += 1

    if labels_csv is None:
        raise RuntimeError("You must specify --labels_csv /path/detections_labeled_corrected.csv")
    if save_blend_path is None:
        # By default, add _manual.blend suffix next to the current file
        blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
        base = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        save_blend_path = os.path.join(blend_dir, base + "_manual.blend")

    return labels_csv, save_blend_path


def _mesh_priority(obj):
    name = obj.name.lower()
    is_marker = name.startswith("pto_") or name.startswith("sphere")
    try:
        dims = obj.dimensions
        volume_like = float(dims.x) * float(dims.y) * float(dims.z)
    except Exception:
        volume_like = 0.0
    try:
        nverts = len(obj.data.vertices)
    except Exception:
        nverts = 0
    return (1 if is_marker else 0, -volume_like, -nverts, name)


def get_hand_mesh():
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        return None
    meshes.sort(key=_mesh_priority)
    return meshes[0]


def main():
    labels_csv, save_blend_path = parse_args(sys.argv)

    print(f"[INFO] Reading corrected labels CSV: {labels_csv}")
    rows = []
    with open(labels_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    print(f"[INFO] Applying labels to {len(rows)} spheres...")
    for r in rows:
        obj_name = r.get("sphere_name", "")
        label = r.get("label", "")
        if not obj_name:
            continue

        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            print(f"[WARNING] Object '{obj_name}' not found in this scene.")
            continue

        if label:
            new_name = f"PTO_{label}"
            obj.name = new_name
        # si label está vacío, dejamos el nombre como está

    # Guardar .blend
    save_dir = os.path.dirname(save_blend_path)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    repair_and_pack_hand_texture(
        get_hand_mesh(),
        search_dirs=[
            save_dir,
            os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd(),
        ],
    )
    bpy.ops.wm.save_as_mainfile(filepath=save_blend_path)
    print(f"[OK] Corrected .blend saved to: {save_blend_path}")


if __name__ == "__main__":
    main()

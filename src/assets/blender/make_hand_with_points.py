import bpy
import sys
import os
import argparse
import csv


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    p = argparse.ArgumentParser(description="Create spheres at 3D points and export OBJ.")
    p.add_argument("--obj", required=True, help="Path to base hand OBJ.")
    p.add_argument("--csv", required=True, help="CSV with x3d,y3d,z3d or X,Y,Z columns.")
    p.add_argument("--out_obj", required=True, help="Output OBJ file.")
    p.add_argument("--sphere_radius", type=float, default=0.5, help="Sphere radius.")
    return p.parse_args(argv)


def load_obj(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = os.path.abspath(path)

    # Blender 4.x
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=path, forward_axis='NEGATIVE_Z', up_axis='Y')
    else:
        bpy.ops.import_scene.obj(filepath=path, forward_axis='NEGATIVE_Z', up_axis='Y')


def read_points(csv_path):
    pts = []
    csv_path = os.path.abspath(csv_path)

    with open(csv_path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []

        has_xyz = all(c in cols for c in ("x3d", "y3d", "z3d"))
        has_XYZ = all(c in cols for c in ("X", "Y", "Z"))

        for row in reader:
            try:
                if has_xyz:
                    x = float(row["x3d"]); y = float(row["y3d"]); z = float(row["z3d"])
                elif has_XYZ:
                    x = float(row["X"]); y = float(row["Y"]); z = float(row["Z"])
                else:
                    x = float(row.get("x", row.get("X")))
                    y = float(row.get("y", row.get("Y")))
                    z = float(row.get("z", row.get("Z")))
                pts.append((x, y, z))
            except Exception:
                continue

    return pts


def get_hand_mesh():
    # primer mesh importado (la mano suele ser el primero)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            return obj
    return None


def add_spheres(points, radius):
    if not points:
        print("[WARN] No points to draw.")
        return

    hand_obj = get_hand_mesh()
    if hand_obj is None:
        print("[WARN] No hand mesh found. Spheres will be placed in world space without parenting.")
    else:
        pass

    for i, (x, y, z) in enumerate(points):
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=radius,
            segments=16,
            ring_count=8,
            location=(x, y, z)
        )
        sph = bpy.context.active_object
        sph.name = f"Sphere_{i:03d}"

        if hand_obj is not None:
            sph.parent = hand_obj

        sph.hide_viewport = False
        sph.hide_render = False
        sph.hide_set(False)
        sph.hide_select = False


def export_obj(path):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    for o in bpy.context.scene.objects:
        o.select_set(True)
    if bpy.context.scene.objects:
        bpy.context.view_layer.objects.active = bpy.context.scene.objects[0]

    bpy.ops.wm.obj_export(
        filepath=path,
        export_selected_objects=True,
        export_materials=True,
        forward_axis='NEGATIVE_Z',
        up_axis='Y'
    )


def main():
    args = parse_args()

    if not os.path.exists(args.obj):
        raise RuntimeError("OBJ file not found: " + args.obj)
    if not os.path.exists(args.csv):
        raise RuntimeError("CSV file not found: " + args.csv)

    load_obj(args.obj)
    pts = read_points(args.csv)
    add_spheres(pts, args.sphere_radius)
    export_obj(args.out_obj)

    print("[OK] Exported OBJ with hand and spheres:", os.path.abspath(args.out_obj))


if __name__ == "__main__":
    main()

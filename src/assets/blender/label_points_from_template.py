# label_points_from_template.py (v4 - global candidate-bone assignment)
#
# Usage from command line (example):
# blender hand_instance.blend --background --python label_points_from_template.py -- \
#   --template "/path/markers_template.csv" \
#   --out "/path/detections_labeled.csv" \
#   --armature "Armature" \
#   --marker_prefix "SPH_" \
#   --save_blend "/path/hand_instance_labeled.blend"
#
# NOTE: adjust --marker_prefix to the actual prefix of the DETECTED POINTS spheres.

import bpy
import sys
import os
import csv
from collections import defaultdict
from mathutils import Vector

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.dirname(SCRIPT_DIR)
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)

from blender_texture_material_utils import repair_and_pack_hand_texture


# Canonical marker order taken from Dimensiones marcadores_102.xlsx.
# It is not required for the assignment itself, but it is useful for diagnostics,
# stable review and future ordering in the validation interface.
LABEL_ORDER_BY_CODE = {
    "20E_E": 1,
    "20R_DIP": 2,
    "20U_DIP": 3,
    "20D_DIP": 4,
    "20P_DIP": 5,
    "20R_PIP": 6,
    "20U_PIP": 7,
    "20D_PIP": 8,
    "20P_PIP": 9,
    "26R_MCP": 10,
    "26D_MCP": 11,
    "26P_MCP": 12,
    "20R_MP": 13,
    "20U_MP": 14,
    "20D_MP": 15,
    "20P_MP": 16,
    "20P_MCP": 17,
    "20P_PP": 18,
    "20R_PP": 19,
    "20U_PP": 20,
    "20D_PP": 21,
    "30E_E": 22,
    "30R_DIP": 23,
    "30U_DIP": 24,
    "30D_DIP": 25,
    "30P_DIP": 26,
    "30R_PIP": 27,
    "30U_PIP": 28,
    "30D_PIP": 29,
    "30P_PIP": 30,
    "36D_MCP": 31,
    "36P_MCP": 32,
    "30R_MP": 33,
    "30U_MP": 34,
    "30D_MP": 35,
    "30P_MP": 36,
    "30P_MCP": 37,
    "30P_PP": 38,
    "30R_PP": 39,
    "30U_PP": 40,
    "30D_PP": 41,
    "40E_E": 42,
    "40R_DIP": 43,
    "40U_DIP": 44,
    "40D_DIP": 45,
    "40P_DIP": 46,
    "40R_PIP": 47,
    "40U_PIP": 48,
    "40D_PIP": 49,
    "40P_PIP": 50,
    "46D_MCP": 51,
    "46P_MCP": 52,
    "40R_MP": 53,
    "40U_MP": 54,
    "40D_MP": 55,
    "40P_MP": 56,
    "40P_MCP": 57,
    "40P_PP": 58,
    "40R_PP": 59,
    "40U_PP": 60,
    "40D_PP": 61,
    "50E_E": 62,
    "50R_DIP": 63,
    "50U_DIP": 64,
    "50D_DIP": 65,
    "50P_DIP": 66,
    "50R_PIP": 67,
    "50U_PIP": 68,
    "50D_PIP": 69,
    "50P_PIP": 70,
    "56U_MCP": 71,
    "56D_MCP": 72,
    "56P_MCP": 73,
    "50R_MP": 74,
    "50U_MP": 75,
    "50D_MP": 76,
    "50P_MP": 77,
    "50P_MCP": 78,
    "50P_PP": 79,
    "50R_PP": 80,
    "50U_PP": 81,
    "50D_PP": 82,
    "10E_E": 83,
    "10R_IP": 84,
    "10U_IP": 85,
    "10D_IP": 86,
    "10P_IP": 87,
    "10R_MCP": 88,
    "10U_MCP": 89,
    "10D_MCP": 90,
    "10P_MCP": 91,
    "16R_W": 92,
    "56U_W": 93,
    "26D_W": 94,
    "56D_W": 95,
    "56P_W": 96,
    "26P_W": 97,
    "26D_PC": 98,
    "56D_PC": 99,
    "56P_PC": 100,
    "26P_PC": 101,
    "16R_PC": 102
}


# -------------------------------------------------------
#  Argument parsing
# -------------------------------------------------------

def parse_args(argv):
    """
    Arguments after '--':
      --template TEMPLATE_CSV_PATH
      --out OUTPUT_CSV_PATH
      --armature ARMATURE_NAME (optional)
      --marker_prefix DETECTED_SPHERES_PREFIX (optional)
      --max_dist VALUE (optional, float)
      --save_blend OUTPUT_BLEND_PATH (optional)
    """
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    template_path = None
    out_path = None
    armature_name = None
    marker_prefix = "Sphere_"  # ADJUST THIS according to your detected spheres
    max_dist = None
    save_blend_path = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--template" and i + 1 < len(argv):
            template_path = argv[i + 1]
            i += 2
        elif arg == "--out" and i + 1 < len(argv):
            out_path = argv[i + 1]
            i += 2
        elif arg == "--armature" and i + 1 < len(argv):
            armature_name = argv[i + 1]
            i += 2
        elif arg == "--marker_prefix" and i + 1 < len(argv):
            marker_prefix = argv[i + 1]
            i += 2
        elif arg == "--max_dist" and i + 1 < len(argv):
            max_dist = float(argv[i + 1])
            i += 2
        elif arg == "--save_blend" and i + 1 < len(argv):
            save_blend_path = argv[i + 1]
            i += 2
        else:
            i += 1

    if template_path is None:
        raise RuntimeError("You must specify --template /path/markers_template.csv")
    if out_path is None:
        # by default, next to the .blend
        blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
        out_path = os.path.join(blend_dir, "detections_labeled.csv")

    return template_path, out_path, armature_name, marker_prefix, max_dist, save_blend_path

# -------------------------------------------------------
#  Utilities
# -------------------------------------------------------

def get_armature(armature_name=None):
    if armature_name is not None:
        obj = bpy.data.objects.get(armature_name)
        if obj is None or obj.type != 'ARMATURE':
            raise RuntimeError(f"Armature '{armature_name}' not found")
        return obj

    # If not specified, use the first armature in the scene
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE':
            return obj

    raise RuntimeError("No ARMATURE object found in the scene.")


def load_markers_template(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Convert coordinates to float
            for key in ("x_local1", "y_local1", "z_local1",
                        "x_local2", "y_local2", "z_local2"):
                if key in r and r[key] not in ("", None):
                    r[key] = float(r[key])
            rows.append(r)
    if not rows:
        raise RuntimeError(f"Template '{path}' is empty or has no rows.")
    return rows


def compute_template_positions_world(template_rows, arm_obj, blend_two_bones=True):
    """
    Returns:
      positions: list of Vector (world)
      labels: list of str
    """
    pose_bones = list(arm_obj.pose.bones)
    if not pose_bones:
        raise RuntimeError("Armature has no pose bones.")

    # Bone matrices in world space: bone_local -> world
    bone_mats_world = {}
    for pbone in pose_bones:
        bone_mats_world[pbone.name] = arm_obj.matrix_world @ pbone.matrix

    positions = []
    labels = []

    for r in template_rows:
        label = r["label"]
        bone_name1 = r["bone_name1"]
        bone_name2 = r.get("bone_name2", "")

        if bone_name1 not in bone_mats_world:
            raise KeyError(f"Bone '{bone_name1}' (bone_name1) is not in this rig.")

        M1 = bone_mats_world[bone_name1]
        local1 = Vector((r["x_local1"], r["y_local1"], r["z_local1"], 1.0))
        p1_world = (M1 @ local1).to_3d()

        if blend_two_bones and bone_name2 and bone_name2 in bone_mats_world:
            M2 = bone_mats_world[bone_name2]
            local2 = Vector((r["x_local2"], r["y_local2"], r["z_local2"], 1.0))
            p2_world = (M2 @ local2).to_3d()
            p_world = (p1_world + p2_world) * 0.5
        else:
            p_world = p1_world

        positions.append(p_world)
        labels.append(label)

    return positions, labels


def get_mesh_center_world(obj):
    """
    Returns the center of the geometry in world space.
    IMPORTANT: here we solve the problem of the object origin
    being at (0,0,0): the center of vertices is used.
    """
    if obj.type == 'MESH' and obj.data.vertices:
        center_local = Vector((0.0, 0.0, 0.0))
        n = len(obj.data.vertices)
        for v in obj.data.vertices:
            center_local += v.co
        center_local /= max(n, 1)
        return obj.matrix_world @ center_local
    else:
        # For empties and others, use the translation
        return obj.matrix_world.translation


def get_detection_spheres(marker_prefix):
    scene = bpy.context.scene
    objs = []
    for obj in scene.objects:
        if obj.name.startswith(marker_prefix) and obj.type in {'MESH', 'EMPTY'}:
            objs.append(obj)
    if not objs:
        print(f"[WARNING] No objects found with prefix '{marker_prefix}'.")
    return objs


def _mesh_priority(obj, marker_prefix):
    name = obj.name.lower()
    is_marker = obj.name.startswith(marker_prefix) or name.startswith("pto_") or name.startswith("sphere")
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


def get_hand_mesh(marker_prefix):
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        return None
    meshes.sort(key=lambda obj: _mesh_priority(obj, marker_prefix))
    return meshes[0]


def compute_detection_features(det_objs, arm_obj):
    """
    For each detected sphere calculates:
      - center in world space
      - closest and second closest bone (by midpoint)
      - local position relative to each of those bones

    Returns list of dicts:
      {
        "obj": obj,
        "center_world": Vector,
        "bone_name1": str,
        "x_local1": float, "y_local1": float, "z_local1": float,
        "bone_name2": str,
        "x_local2": float, "y_local2": float, "z_local2": float,
      }
    """
    pose_bones = list(arm_obj.pose.bones)
    if not pose_bones:
        raise RuntimeError("Armature has no pose bones.")

    arm_world_inv = arm_obj.matrix_world.inverted()

    feats = []

    for obj in det_objs:
        center_world = get_mesh_center_world(obj)
        center_arm = arm_world_inv @ center_world  # a espacio del armature

        # Find closest bones by midpoint
        distances = []
        for pbone in pose_bones:
            head = pbone.head
            tail = pbone.tail
            mid = (head + tail) * 0.5
            d = (center_arm - mid).length
            distances.append((d, pbone))

        distances.sort(key=lambda x: x[0])

        bone1 = distances[0][1] if distances else None
        bone2 = distances[1][1] if len(distances) > 1 else None

        # Local coordinates in each bone
        bone_name1 = bone1.name if bone1 else ""
        bone_name2 = bone2.name if bone2 else ""

        center_arm_4d = center_arm.to_4d()
        center_arm_4d.w = 1.0

        if bone1:
            m1_inv = bone1.matrix.inverted()
            local1 = m1_inv @ center_arm_4d
            x_local1, y_local1, z_local1 = local1.x, local1.y, local1.z
        else:
            x_local1 = y_local1 = z_local1 = 0.0

        if bone2:
            m2_inv = bone2.matrix.inverted()
            local2 = m2_inv @ center_arm_4d
            x_local2, y_local2, z_local2 = local2.x, local2.y, local2.z
        else:
            x_local2 = y_local2 = z_local2 = 0.0

        feats.append({
            "obj": obj,
            "center_world": center_world,
            "bone_name1": bone_name1,
            "x_local1": x_local1,
            "y_local1": y_local1,
            "z_local1": z_local1,
            "bone_name2": bone_name2,
            "x_local2": x_local2,
            "y_local2": y_local2,
            "z_local2": z_local2,
        })

    return feats


def score_detection_for_template(det_feat, template_row, world_dist_fallback):
    """
    Calculates a 'compatibility score' between a detected sphere
    and a template row.

    - If they share any bones (bone_name1 / bone_name2),
      uses the difference in local coordinates as score.
    - If they don't share bones, uses world distance as fallback.

    Lower score = better.
    """
    score_terms = []

    # Bone 1
    tpl_b1 = template_row["bone_name1"]
    if det_feat["bone_name1"] == tpl_b1:
        dx = det_feat["x_local1"] - template_row["x_local1"]
        dy = det_feat["y_local1"] - template_row["y_local1"]
        dz = det_feat["z_local1"] - template_row["z_local1"]
        score_terms.append((dx*dx + dy*dy + dz*dz) ** 0.5)

    # Bone 2 (if exists in template and detection)
    tpl_b2 = template_row.get("bone_name2", "")
    if tpl_b2 and det_feat["bone_name2"] == tpl_b2:
        dx = det_feat["x_local2"] - template_row["x_local2"]
        dy = det_feat["y_local2"] - template_row["y_local2"]
        dz = det_feat["z_local2"] - template_row["z_local2"]
        score_terms.append((dx*dx + dy*dy + dz*dz) ** 0.5)

    if score_terms:
        # Average of available local errors
        return sum(score_terms) / len(score_terms)

    # If no bones match, use world distance
    if world_dist_fallback is not None:
        return world_dist_fallback

    # In worst case, a large value
    return 1e9


def get_bone_world_inverses(arm_obj):
    """
    Returns matrices that transform from world coordinates to each pose bone local space.

    This is the core change in V4: instead of comparing a detection only against
    its two nearest bones, every candidate label is evaluated in the coordinate
    system of the candidate template bones. That avoids cascading errors caused
    by an initially wrong nearest-bone decision.
    """
    invs = {}
    for pbone in arm_obj.pose.bones:
        invs[pbone.name] = (arm_obj.matrix_world @ pbone.matrix).inverted()
    return invs


def _label_family(label):
    """
    Converts labels such as 20R_DIP, 56P_W or 16R_PC into a broad anatomical family.
    This is used only as a soft prior, never as a hard rejection.
    """
    if not label:
        return "unknown"

    suffix = label.split("_", 1)[1] if "_" in label else ""
    if suffix in {"W"}:
        return "wrist"
    if suffix in {"PC"}:
        return "palm"

    first = label[0]
    return {
        "1": "thumb",
        "2": "index",
        "3": "middle",
        "4": "ring",
        "5": "pinky",
    }.get(first, "unknown")


def _bone_family(bone_name):
    name = (bone_name or "").lower()
    if "thumb" in name:
        return "thumb"
    if "index" in name:
        return "index"
    if "middle" in name:
        return "middle"
    if "ring" in name:
        return "ring"
    if "pinky" in name or "little" in name:
        return "pinky"
    if "wrist" in name:
        return "wrist"
    return "unknown"


def semantic_family_penalty(det_feat, template_row):
    """
    Small soft penalty when the nearest detection bones clearly belong to a different
    broad anatomical family than the candidate label.

    The penalty is intentionally low because the local-template score is the main
    criterion. This prevents the method from behaving like the discarded V2, which
    relaxed/changed constraints too aggressively.
    """
    label = template_row.get("label", "")
    label_family = _label_family(label)
    if label_family in {"unknown", "palm"}:
        return 0.0

    det_families = {
        _bone_family(det_feat.get("bone_name1", "")),
        _bone_family(det_feat.get("bone_name2", "")),
    }
    det_families.discard("unknown")

    if not det_families:
        return 0.0

    # Wrist labels can reasonably be close to finger-metacarpal bones.
    if label_family == "wrist":
        return 0.0 if "wrist" in det_families else 1.0

    return 0.0 if label_family in det_families else 2.5


def score_detection_against_candidate_bones(det_feat, template_row, template_world_pos, bone_world_invs):
    """
    V4 cost function.

    For a detected point and a candidate template label, the point is projected into
    the *candidate template bones* and compared with the stored local coordinates.

    This is more robust than the previous method because it does not depend on the
    detection's nearest bone classification being correct.
    """
    center_world = det_feat["center_world"]
    center_world_4d = center_world.to_4d()
    center_world_4d.w = 1.0

    local_terms = []

    b1 = template_row.get("bone_name1", "")
    if b1 in bone_world_invs:
        local1 = bone_world_invs[b1] @ center_world_4d
        dx = local1.x - template_row["x_local1"]
        dy = local1.y - template_row["y_local1"]
        dz = local1.z - template_row["z_local1"]
        local_terms.append((dx * dx + dy * dy + dz * dz) ** 0.5)

    b2 = template_row.get("bone_name2", "")
    if b2 and b2 in bone_world_invs and template_row.get("x_local2", "") not in ("", None):
        local2 = bone_world_invs[b2] @ center_world_4d
        dx = local2.x - template_row["x_local2"]
        dy = local2.y - template_row["y_local2"]
        dz = local2.z - template_row["z_local2"]
        local_terms.append((dx * dx + dy * dy + dz * dz) ** 0.5)

    if local_terms:
        local_score = sum(local_terms) / len(local_terms)
    else:
        local_score = 1e6

    world_score = (center_world - template_world_pos).length

    # Main criterion: candidate-bone local consistency.
    # World distance is retained as a stabilizer when two candidates have similar
    # local errors. The weights are deliberately conservative.
    score = (0.72 * local_score) + (0.28 * world_score)

    score += semantic_family_penalty(det_feat, template_row)

    return score, local_score, world_score


def hungarian_minimize(cost_matrix):
    """
    Pure-Python rectangular Hungarian algorithm for minimization.
    Returns a list `assignment` where assignment[row] = column.

    Requires number of columns >= number of rows. Use dummy columns before calling
    when some rows may remain unassigned.
    """
    n = len(cost_matrix)
    if n == 0:
        return []
    m = len(cost_matrix[0])
    if m < n:
        raise ValueError("hungarian_minimize requires columns >= rows")

    # 1-indexed implementation.
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (m + 1)
        used = [False] * (m + 1)

        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0

            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost_matrix[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j

            for j in range(0, m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta

            j0 = j1
            if p[j0] == 0:
                break

        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    assignment = [-1] * n
    for j in range(1, m + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) * 0.5


def build_review_reason(cost, confidence, world_dist, median_cost_value, median_world_value, assigned_label):
    reasons = []
    if confidence is not None and confidence < 0.12:
        reasons.append("ambiguous_candidate")
    if median_cost_value and cost is not None and cost > median_cost_value * 2.5:
        reasons.append("high_assignment_cost")
    if median_world_value and world_dist is not None and world_dist > median_world_value * 2.5:
        reasons.append("far_from_template")
    if not assigned_label:
        reasons.append("unassigned")
    return "|".join(reasons)


# -------------------------------------------------------
#  Main
# -------------------------------------------------------

def main():
    template_path, out_path, armature_name, marker_prefix, max_dist, save_blend_path = parse_args(sys.argv)
    print(f"[INFO] Template CSV: {template_path}")
    print(f"[INFO] Output labeling CSV: {out_path}")
    print(f"[INFO] Detected spheres prefix: {marker_prefix}")
    if max_dist is not None:
        print(f"[INFO] max_dist = {max_dist}")
    if save_blend_path is not None:
        print(f"[INFO] Will save a copy of the labeled .blend to: {save_blend_path}")

    arm_obj = get_armature(armature_name)
    print(f"[INFO] Using armature: {arm_obj.name}")

    template_rows = load_markers_template(template_path)
    template_positions, template_labels = compute_template_positions_world(template_rows, arm_obj)

    # Detection spheres
    det_objs = get_detection_spheres(marker_prefix)
    if not det_objs:
        print("[WARNING] No detection spheres; nothing to label.")
        return

    # Features of each sphere (center, bones, local coords)
    det_feats = compute_detection_features(det_objs, arm_obj)
    det_centers = [f["center_world"] for f in det_feats]

    M = len(det_feats)
    N = len(template_positions)

    # ---------------------------------------------------
    # V4: global assignment with candidate-bone local scoring
    # ---------------------------------------------------
    print("[INFO] Labeling strategy: V4 global candidate-bone assignment.")
    print("[INFO] Evaluating each detected sphere inside each candidate template bone frame.")

    bone_world_invs = get_bone_world_inverses(arm_obj)

    # Build the real cost matrix and auxiliary score matrices.
    real_cost = []
    real_local_score = []
    real_world_score = []

    for i in range(M):
        row_cost = []
        row_local = []
        row_world = []
        for j in range(N):
            cost, local_s, world_s = score_detection_against_candidate_bones(
                det_feats[i],
                template_rows[j],
                template_positions[j],
                bone_world_invs,
            )

            # If the user provides max_dist, keep it as a hard-ish limit by making
            # out-of-range labels worse than an unassigned dummy label.
            if max_dist is not None and world_s > max_dist:
                cost += 1e6

            row_cost.append(cost)
            row_local.append(local_s)
            row_world.append(world_s)

        real_cost.append(row_cost)
        real_local_score.append(row_local)
        real_world_score.append(row_world)

    # Add dummy labels when needed so the assignment can leave detections unassigned.
    # With the usual 102 detections / 102 template labels, no dummy label is used
    # unless max_dist is active or there are more detections than template points.
    cols_required = max(N, M)
    use_dummy = (M > N) or (max_dist is not None)
    dummy_count = max(0, cols_required - N)
    if use_dummy and dummy_count < M:
        dummy_count = M

    if dummy_count > 0:
        # Dynamic dummy cost: high enough to prefer real labels, lower than hard rejects.
        all_cost_values = [c for row in real_cost for c in row if c < 1e6]
        base = median(all_cost_values) or 100.0
        dummy_cost = max(base * 8.0, 1000.0)
        cost_matrix = [row + [dummy_cost] * dummy_count for row in real_cost]
    else:
        cost_matrix = real_cost

    # Hungarian requires cols >= rows. If M > N and we did not add dummies for any
    # reason, fall back to enough dummy columns.
    if cost_matrix and len(cost_matrix[0]) < len(cost_matrix):
        missing = len(cost_matrix) - len(cost_matrix[0])
        cost_matrix = [row + [1e6] * missing for row in cost_matrix]

    assignment = hungarian_minimize(cost_matrix)

    assigned_tpl_idx = [None] * M
    assignment_score = [None] * M
    local_assignment_score = [None] * M
    dist_min_world = [None] * M
    confidence_values = [None] * M

    for i, col in enumerate(assignment):
        if col is None or col < 0 or col >= N:
            assigned_tpl_idx[i] = None
            continue

        assigned_tpl_idx[i] = col
        assignment_score[i] = real_cost[i][col]
        local_assignment_score[i] = real_local_score[i][col]
        dist_min_world[i] = real_world_score[i][col]

        # Confidence from the margin between assigned candidate and second-best
        # real candidate. It is diagnostic only; it does not alter the assignment.
        sorted_costs = sorted(real_cost[i])
        if len(sorted_costs) >= 2:
            best = real_cost[i][col]
            # second value that is not the exact same assignment value if possible
            second = None
            for val in sorted_costs:
                if val != best:
                    second = val
                    break
            if second is None:
                second = sorted_costs[1]
            denom = max(second, 1e-6)
            confidence_values[i] = max(0.0, min(1.0, (second - best) / denom))
        else:
            confidence_values[i] = 1.0

    assigned_count = sum(1 for j in assigned_tpl_idx if j is not None)
    print(f"[INFO] V4 assignment completed: {assigned_count}/{M} spheres labeled.")

    # Useful diagnostics
    assigned_costs = [v for v in assignment_score if v is not None]
    assigned_world = [v for v in dist_min_world if v is not None]
    median_assignment_cost = median(assigned_costs)
    median_world_dist = median(assigned_world)

    if median_assignment_cost is not None:
        print(f"[INFO] Median assignment cost: {median_assignment_cost:.4f}")
    if median_world_dist is not None:
        print(f"[INFO] Median world distance: {median_world_dist:.4f}")

    # ---------------------------------------------------
    # Build output rows and rename spheres
    # ---------------------------------------------------
    rows_out = []
    for i, feat in enumerate(det_feats):
        obj = feat["obj"]
        j = assigned_tpl_idx[i]
        d = dist_min_world[i]

        if j is None:
            label = ""
        else:
            label = template_labels[j]

        # Preserve the original detection-sphere identifier before renaming.
        # This is needed by the posed-hand workflow to map Blender-scene
        # coordinates back to the validated 3D marker CSV / OBJ coordinate frame
        # without affecting the regular flat-hand labeling behavior.
        source_sphere_name = obj.name

        # Rename sphere to PTO_<label> if there is a label
        if label:
            new_name = f"PTO_{label}"
            obj.name = new_name
        else:
            new_name = obj.name  # No changes

        center = feat["center_world"]
        rows_out.append({
            "sphere_name": new_name,
            "source_sphere_name": source_sphere_name,
            "label": label,
            "x": center.x,
            "y": center.y,
            "z": center.z,
            "distance_to_template": float(d) if d is not None else "",
            "template_index": j if j is not None else "",
            "label_order": LABEL_ORDER_BY_CODE.get(label, ""),
            "assignment_score": float(assignment_score[i]) if assignment_score[i] is not None else "",
            "local_assignment_score": float(local_assignment_score[i]) if local_assignment_score[i] is not None else "",
            "confidence": float(confidence_values[i]) if confidence_values[i] is not None else "",
            "review_reason": build_review_reason(
                assignment_score[i],
                confidence_values[i],
                d,
                median_assignment_cost,
                median_world_dist,
                label,
            ),
            # Info of bones/local coords from DETECTION
            "bone_name1_det": feat["bone_name1"],
            "x_local1_det": feat["x_local1"],
            "y_local1_det": feat["y_local1"],
            "z_local1_det": feat["z_local1"],
            "bone_name2_det": feat["bone_name2"],
            "x_local2_det": feat["x_local2"],
            "y_local2_det": feat["y_local2"],
            "z_local2_det": feat["z_local2"],
        })

    # Write CSV
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fieldnames = [
        "sphere_name", "source_sphere_name", "label",
        "x", "y", "z",
        "distance_to_template", "template_index",
        "label_order", "assignment_score", "local_assignment_score", "confidence", "review_reason",
        "bone_name1_det", "x_local1_det", "y_local1_det", "z_local1_det",
        "bone_name2_det", "x_local2_det", "y_local2_det", "z_local2_det",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)

    print(f"[OK] Labeling of {len(det_feats)} spheres saved to: {out_path}")

    # Save the resulting .blend (if requested)
    if save_blend_path is not None:
        save_dir = os.path.dirname(save_blend_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        repair_and_pack_hand_texture(
            get_hand_mesh(marker_prefix),
            search_dirs=[
                save_dir,
                os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd(),
            ],
        )
        bpy.ops.wm.save_as_mainfile(filepath=save_blend_path)
        print(f"[OK] Labeled .blend saved to: {save_blend_path}")

if __name__ == "__main__":
    main()

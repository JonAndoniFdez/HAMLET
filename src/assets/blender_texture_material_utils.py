import os

import bpy


def _abs_existing(path):
    if not path:
        return None
    try:
        p = bpy.path.abspath(str(path))
    except Exception:
        p = str(path)
    p = os.path.abspath(p)
    return p if os.path.isfile(p) else None


def _image_existing_path(image):
    if image is None:
        return None
    for attr in ("filepath", "filepath_raw"):
        found = _abs_existing(getattr(image, attr, ""))
        if found:
            return found
    return None


def _iter_image_nodes(mat):
    if mat is None or not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE":
            yield node


def _candidate_texture_paths(texture_path=None, search_dirs=None):
    seen = set()

    def add(path):
        found = _abs_existing(path)
        if found and found not in seen:
            seen.add(found)
            yield found

    if texture_path:
        yield from add(texture_path)

    for img in bpy.data.images:
        found = _image_existing_path(img)
        if found and found not in seen:
            seen.add(found)
            yield found

    dirs = []
    if search_dirs:
        dirs.extend(search_dirs)
    if bpy.data.filepath:
        dirs.append(os.path.dirname(bpy.data.filepath))
    dirs.append(os.getcwd())

    names = (
        "NewHandTexture.png",
        "newhandtexture.png",
        "hand_texture.png",
        "texture.png",
    )
    for directory in dirs:
        if not directory:
            continue
        directory = os.path.abspath(str(directory))
        for name in names:
            yield from add(os.path.join(directory, name))


def _load_or_reuse_image(texture_path):
    texture_path = os.path.abspath(texture_path)
    for img in bpy.data.images:
        if _image_existing_path(img) == texture_path:
            return img
    return bpy.data.images.load(texture_path)


def _principled_node(mat):
    nt = mat.node_tree
    for node in nt.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    node = nt.nodes.new("ShaderNodeBsdfPrincipled")
    node.location = (120, 0)
    return node


def _output_node(mat):
    nt = mat.node_tree
    for node in nt.nodes:
        if node.type == "OUTPUT_MATERIAL":
            return node
    node = nt.nodes.new("ShaderNodeOutputMaterial")
    node.location = (420, 0)
    return node


def _ensure_hand_material(hand_obj):
    if hand_obj.data.materials:
        mat = hand_obj.data.materials[0]
        if mat is not None:
            mat.use_nodes = True
            return mat

    mat = bpy.data.materials.new("MAT_HandTexture")
    mat.use_nodes = True
    hand_obj.data.materials.clear()
    hand_obj.data.materials.append(mat)
    return mat


def repair_and_pack_hand_texture(hand_obj, texture_path=None, search_dirs=None):
    """
    Ensure the hand mesh material uses an existing texture image and pack it into
    the .blend so the saved rig/labeled files do not open pink in Blender.
    """
    if hand_obj is None or getattr(hand_obj, "type", None) != "MESH":
        print("[WARNING] Texture repair skipped: no hand mesh.")
        return False

    mat = _ensure_hand_material(hand_obj)

    chosen_path = None
    chosen_img = None

    for node in _iter_image_nodes(mat):
        chosen_path = _image_existing_path(node.image)
        if chosen_path:
            chosen_img = node.image
            break

    if chosen_img is None:
        for path in _candidate_texture_paths(texture_path=texture_path, search_dirs=search_dirs):
            chosen_path = path
            chosen_img = _load_or_reuse_image(path)
            break

    if chosen_img is None or chosen_path is None:
        print("[WARNING] Texture repair skipped: no existing texture image found.")
        return False

    mat.use_nodes = True
    nt = mat.node_tree
    tex_node = None
    for node in _iter_image_nodes(mat):
        if node.image == chosen_img:
            tex_node = node
            break
    if tex_node is None:
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.location = (-220, 0)
    tex_node.image = chosen_img

    try:
        chosen_img.filepath = chosen_path
        chosen_img.filepath_raw = chosen_path
        chosen_img.colorspace_settings.name = "sRGB"
    except Exception:
        pass

    bsdf = _principled_node(mat)
    out = _output_node(mat)

    base_color = bsdf.inputs.get("Base Color")
    if base_color is not None:
        for link in list(nt.links):
            if link.to_node == bsdf and link.to_socket == base_color:
                nt.links.remove(link)
        nt.links.new(tex_node.outputs["Color"], base_color)

    if out.inputs.get("Surface") is not None and bsdf.outputs.get("BSDF") is not None:
        if not any(link.from_node == bsdf and link.to_node == out for link in nt.links):
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    try:
        chosen_img.reload()
    except Exception:
        pass

    try:
        if not chosen_img.packed_file:
            chosen_img.pack()
    except Exception as e:
        print(f"[WARNING] Could not pack texture image: {e}")

    print(f"[OK] Hand texture connected and packed: {chosen_path}")
    return True

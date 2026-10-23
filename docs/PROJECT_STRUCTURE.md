# Maintained project structure

The active application implements the flat-hand procedure. The entry point is
`run_app.py`, which starts `src.main.main()` or dispatches an internal worker.

## Application

`src/gui/appWindow.py` owns the six workflow steps and the welcome/open-project
entry pages. Its active pages are model setup, thresholds, detection/mapping,
rigging/labeling, measurement selection and results. The label correction and
automatic labeling steps are integrated into the rigging page.

`src/core/` contains the functions used by these pages. There is no separate
placeholder pipeline. The flat-hand rig uses `openpose_render.py`,
`openpose_hand.py` and `openpose_rig.py`. The old posed-hand implementation is
outside the active source tree.

`src/internal_workers/` is the single source of the detection worker and the
interactive label editor. `src/core/worker_commands.py` defines their names and
module paths for both source execution and the frozen application. The entry
point still recognizes legacy script basenames when invoked through HAMLET.

## Assets

- `src/assets/blender/`: six maintained Blender runtime scripts. They must remain
  in Git and in the application source archive. PyInstaller compresses them into
  a payload; Blender receives extracted temporary files at runtime.
- `src/assets/blender_texture_material_utils.py`: shared Blender texture helpers.
- `src/assets/data/`: measurement operations, marker template and label colors
  (`pointsColor.csv`). There are no duplicate Python workers under assets.
- `src/assets/icons/`: the application/institutional images used by the GUI.
- `src/assets/viewer3d/vendor/`: the offline Three.js viewer dependencies and MIT
  license. Network access is not needed for the viewer's JavaScript.

## Build and release maintenance

| Tool | Responsibility |
| --- | --- |
| `check_source.py` | Source/asset completeness and optional release environment preflight |
| `source_manifest.py` | Shared selection of files for the application source archive |
| `verify_release_preview.py` | Inspect preview script references in the built EXE |
| `run_release_selftest.py` | Execute integration checks inside the built EXE |
| `finalize_release.py` | Verify the candidate and create the three ZIPs and hashes |
| `audit_dependency_licenses.py` | Inventory actual build inputs under `build/dependency_audit/` |
| `fetch_release_sources.py`, `prepare_native_sources.py` | Prepare corresponding dependency source archives |
| `prepare_source_notices.py`, `generate_qt_notices.py`, `fetch_runtime_terms.py` | Prepare original notices and runtime terms |
| `release_license_files.py`, `pyinstaller_hooks/` | Select notices and controlled Qt dependencies during build |
| `lock_release_environment.py` | Deliberately regenerate the pinned dependency closure; do not run during release checks |
| `build_user_guide_docx.py` | Generate a draft under `output/user-guide-draft/`; does not overwrite maintained manuals |

## Documentation and local material

`docs/README.pdf` is the guide opened by the app; its path and content were
preserved. Additional manuals are under `docs/user-guide/`. The English editable
DOCX was locked by Word during cleanup and remains in the project root; move it
to `docs/user-guide/` after closing Word. Its contents were not edited.

`docs/archive/` contains historical release audits and license proposals. Those
files describe their original dates and are not validation of a later build.
Current release preparation is described in `docs/RELEASE_BUILD.md`.

The local cleanup backup is under `.local/cleanup-2026-10-22/`, including a ZIP,
hash inventory, initial Git diffs and retired files. Research manuscripts, SPSS
datasets, analysis outputs and banner drafts were moved to `.local/research/`.
They are retained locally and excluded from the application source archive.
The dependency audit was moved from `output/dependency_audit/` to
`build/dependency_audit/`; the old readable-script audit is retained in the
cleanup backup. `tmp/` retains local analysis environments and temporary work.

`blender/` and `openpose/` at the repository root are external runtime trees.
Ignore rules are root-specific so they do not hide `src/assets/blender/`.

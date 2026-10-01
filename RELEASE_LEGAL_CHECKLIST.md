# HAMLET release checklist

This is a local candidate, not permission to publish. The machine-readable
status is in `release-approvals.json`; `dist/RELEASE_VALIDATION.json` records
checks on a specific generated release. A successful build alone is not approval.

## Technical preparation

- [x] Collect original Python package and runtime notices from actual build inputs.
- [x] Preserve Three.js r128, Blender and OpenPose notices.
- [x] Obtain exact Qt/PySide source license trees and attribution records.
- [x] Restrict Qt bindings/plugins and omit the unused QML tree.
- [x] Keep Blender's runtime separate from HAMLET's dependency analysis.
- [x] Restrict DLL discovery to controlled build locations; reject unrelated runtimes.
- [x] Pin the installed dependency closure in `requirements-release.lock.txt`.
- [x] Prepare exact upstream source archives, Blender dependency sources, hashes,
      patches/build recipes and instructions for replacing LGPL libraries.
- [x] Record the project owner's confirmation of a valid Visual Studio 2022 license
      and preserve Microsoft's terms and redistribution list.
- [x] Provide executable integration tests and artifact validation/ZIP tooling.

The generated validation report, rather than a checkbox here, must establish
that the final build passes, includes the complete notices/credits, matches its
source, and that all source archives and ZIP contents verify successfully.

## Required before public release

- [x] Project owner confirmed author ownership (superseding earlier UJI ownership)
      and instructed GPLv3 on 2026-09-30. GPL-3.0-only now applies to original code;
      LICENSE.txt and NOTICE.txt updated. Third-party assets keep their own terms.
- [ ] Obtain and retain OpenPose's written response covering the exact weights
      and prototxt files, distribution through Zenodo/GitHub and intended uses.
      Request was sent by the project owner; models remain included as requested.
- [x] Record the user's real-hand test from an extracted ZIP on another computer.
      On 2026-09-29 the project owner confirmed successful operation with a
      real hand after transferring HAMLET.zip to another computer without
      Blender installed. Absence of development Python and Qt installations
      has not been explicitly documented.
      Synthetic integration tests do not establish anatomical accuracy.
- [x] Set the first public release to 1.0 (Windows metadata: 1.0.0.0).
      Validate actual executable version and notices during the final build.
- [x] Record user-supplied reserved DOI 10.5281/zenodo.23056922; no publication yet.
- [ ] Publish the binary and provide clear links to matching application and
      dependency sources, with persistent download access and hashes. Sources
      may be hosted outside the binary's Zenodo record.
- [ ] Record the final approved source tag/commit, DOI and repository links.

Run `tools/finalize_release.py --test-results <results.json> --for-publication`
to reject publication while approvals are unresolved. Update approval evidence
only after receiving it; do not turn pending items into confirmed by assumption.

## Packaging and sources

The three deliverables are `HAMLET.zip`, `HAMLET-application-source.zip` and
`HAMLET-dependency-sources.zip`. The finalizer verifies notice hashes, exact Qt
selection, source coverage, executable tests, build input hashes and ZIP CRCs.
`SHA256SUMS.txt` identifies the generated artifacts.

Compressed/embedded scripts are not encryption. Source hiding is not a release
objective and cannot override GPL/LGPL source requirements. Readable application
and Blender scripts belong in the matching source download once authorized.

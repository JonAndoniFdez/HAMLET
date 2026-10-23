# HAMLET 1.0 release procedure

## Publication structure

- Source repository and release: https://github.com/JonAndoniFdez/HAMLET.
- Tag `v1.0` identifies the matching HAMLET application source and build tools.
- The Git tree excludes Blender/OpenPose installations, model weights, dependency
  source archives, Python/Qt runtime binaries and generated build outputs.
- The portable `HAMLET.zip` contains the complete required runtime distribution.
- The Zenodo description links to GitHub. The repository README links to the
  reserved software DOI; that identifier is excluded from portable HAMLET files.
- Exact dependency sources are obtained from official project servers using
  `docs/DEPENDENCY_SOURCES.md` and `third_party_licenses/SOURCE_DOWNLOADS.json`.
  HAMLET does not operate a dependency download service.

## License and source information

Original HAMLET code is GPL-3.0-only and belongs to the authors in NOTICE.txt.
Third-party components retain their own terms. Preserve original license texts,
Qt/Chromium attributions, Blender notices and OpenPose model provenance.
`SOURCE_CODE.md` explains rebuilding and LGPL library replacement. Follow the
GPLv3 section 6(d) third-party-server source-access procedure, including continued
availability and clear directions next to the binary download.

The project owner has explicitly requested public distribution with the OpenPose
hand models for scientific research. That instruction is publication authorization
from the project owner, not a claim of a separate grant by CMU. The unmodified
OpenPose license and the model-specific notice remain in the portable package.

## Technical evidence

Run the source/environment checks, regression tests and frozen-executable
integration suite. Verify exact model/source hashes, original notices, portable
metadata, PDF guide, icon, ZIP CRC and SHA-256. Keep reports for the actual ZIP
being uploaded. Synthetic integration checks do not validate anatomical accuracy
or replace testing a real project on the target Windows installation.

Publication authorization and provenance are recorded in `release-approvals.json`.
The public source commit/tag and uploaded asset digests must be recorded after
verification. A completed upload must be checked through GitHub's public API.

HAMLET 1.0
Hand Anthropometric Measurement and Landmark Extraction Tool

GETTING STARTED
Windows 64-bit. Extract the entire HAMLET.zip archive to a local folder and
launch HAMLET.exe. Keep the accompanying folders and files together.
Python and Blender are included; separate installations are not required.
Use a writable folder for your input/output projects.
Open Getting started in the application for the workflow guide (docs/README.pdf).

PURPOSE
HAMLET supports scientific research on hand anthropometry from textured 3D
flat-hand models. It combines landmark detection, interactive review in 2D and 3D,
manual adjustment and measurement export. Inspect landmarks and results for
your data; successful execution is not a guarantee of anatomical accuracy.

AUTHORS
Jon A. Fernández-Moyano; Verónica Gracia-Ibáñez; Alba Roda-Sales;
Carlos Gonell-Cruz.
Department of Mechanical Engineering and Construction, Universitat Jaume I.
Copyright in the original HAMLET code belongs to its authors.

LICENSES
Original HAMLET code: GNU GPL version 3 only. See LICENSE.txt and NOTICE.txt.
The research purpose above does not add a noncommercial restriction to GPLv3.
Third-party programs, libraries and models retain their own licenses. See
THIRD_PARTY_LICENSES.txt, OPENPOSE_MODELS_NOTICE.txt and third_party_licenses/index.html
(also accessible from About). This package is not uniformly GPL-licensed.

SOURCE AND REPOSITORY
See SOURCE_CODE.md for corresponding sources, build instructions and library
replacement instructions. Source ZIPs are not needed to run HAMLET.
Repository: https://github.com/JonAndoniFdez/HAMLET
Version: 1.0 (Windows executable metadata: 1.0.0.0).
CITATION.cff contains author and repository metadata.

RELEASE STATUS
This local build has not been uploaded or published by the build tools.
The portable package includes Blender, the OpenPose hand models, the Python
runtime, Qt and the required libraries. OpenPose inference uses OpenCV DNN;
the separate OpenPose executable is not required.

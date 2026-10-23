# HAMLET 1.0: obtaining the corresponding dependency sources

The links below identify the upstream source archives selected for HAMLET 1.0
on Windows x64. They are direct, version-specific downloads, without a login or
additional payment. The complete machine-readable list, archive sizes and SHA-256
digests are in [SOURCE_DOWNLOADS.json](../third_party_licenses/SOURCE_DOWNLOADS.json).
The total retained source cache is 3,198,908,409 bytes (about 3.20 GB).
Users do not need these archives to run the portable application.

## Download manually or with the supplied tool

Download the desired archive using its link in the table below. Its name and
version must match the catalog. On Windows, compare its digest with the catalog:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\blender-4.3.2.tar.xz
```

Alternatively, from the root of a HAMLET source checkout, use Python 3.11 or later
to download and verify the pinned archives. The tool uses the standard library;
it does not require installing HAMLET's dependencies. Large archives remain
outside Git. Existing archives are reused only if their size and digest match.

```powershell
python -B tools/download_dependency_sources.py --download --report build/source-downloads.json
```

The default destination is `dist/source-companion/`, with Blender dependency
inputs in `native/`. To select a component, add `--component Blender`,
`--component Qt` or `--component QtForPython` (repeatable). To select all archives,
omit `--component`. Set `--out <folder>` to use another destination.

Verify an existing cache without network access:

```powershell
python -B tools/download_dependency_sources.py --verify-local --report build/source-integrity.json
```

Check that all pinned source URLs currently return archive data:

```powershell
python -B tools/download_dependency_sources.py --check-urls --report build/source-availability.json
```

Every mode exits unsuccessfully if any selected archive fails. URL checks inspect
the HTTP response, archive signature and advertised size; they do not download or
hash entire remote archives. Only `--download` and `--verify-local` verify full
SHA-256 digests and Blender's recorded build-recipe hashes. An unavailable URL,
HTML error page, size mismatch or digest mismatch must be investigated; do not
silently substitute another version or overwrite the pinned digest.

## What the archives contain

- **Blender 4.3.2:** Blender source, CMake files and
  `build_files/build_environment/`, including upstream patches and dependency
  recipes. The `Blender-*` entries provide its retained native dependency inputs;
  some relate to other platforms or unused build options. Their recipe hashes
  come from Blender 4.3.2's `versions.cmake`.
- **Qt 6.10.2:** the complete Qt source archive, including Qt WebEngine's
  Chromium/FFmpeg sources and module build files. Preserve their own notices.
- **QtForPython 6.10.2:** the PySide6/shiboken6 sources and binding build system,
  corresponding to PySide6, PySide6_Addons, PySide6_Essentials and shiboken6.
- **Python 3.11.9, VTK 9.5.1 and Python distributions:** the upstream sources for
  the versions recorded in the release dependency inventory and lock file.

No HAMLET patches are applied to Blender, Qt or Qt for Python. Follow the build
instructions in each archive; HAMLET's own build instructions are in
[SOURCE_CODE.md](../SOURCE_CODE.md) and [RELEASE_BUILD.md](RELEASE_BUILD.md).
Library replacement and debugging instructions are in SOURCE_CODE.md. This
catalog is not a claim of a byte-for-byte reproduction of upstream executables.

The readable Three.js r128 files and their MIT notice are already in
`src/assets/viewer3d/vendor/`. OpenPose model files and the Microsoft runtime
retain their separate terms; this source-access procedure does not relicense
them or establish permission to distribute them. Source availability obligations
are determined per component; inclusion in this catalog does not impose GPL
requirements on components distributed under permissive licenses.

## Evidence of current availability

The evidence shipped in [source-availability/](../third_party_licenses/source-availability/)
records its UTC check time and the SHA-256 of the exact catalog checked:

- `integrity.json`: full local archive sizes/digests and Blender recipe hashes.
- `urls.json`: live HTTP checks of the version-specific source downloads.

The sources were downloaded previously and verified again against their pinned
digests. These are dated, reproducible technical results. They are not an upstream
promise of permanent hosting, a verification of a future HAMLET source release,
or a blanket certification that every license obligation is satisfied.

## Publication and continued access: distributor's procedure

The distribution method for GPLv3 components is network access under
[GPLv3 section 6(d)](https://www.gnu.org/licenses/gpl-3.0.html#section6), also
explained by the [FSF's source/binary hosting FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites).
It permits the corresponding sources on a third-party server with equivalent
copying facilities and clear directions next to the binary download. The
distributor remains responsible for ensuring the required sources stay available.
Including only executables, license texts or a generic project homepage is not
this source-access mechanism.

Before making a binary release public, the publisher must:

1. Establish a public release/tag with HAMLET's complete matching source, build
   scripts and instructions. Record its exact commit and URL; a moving default
   branch alone does not identify the source corresponding to the binary.
2. Publish this document and its source catalog with that source release. Put
   direct links to both the matching HAMLET source and these dependency-source
   directions beside the `HAMLET.zip` download, including in the Zenodo description.
   Include the same instructions in the portable package on its next build.
3. Re-run both full-cache verification and URL checks. Keep dated evidence tied
   to the catalog actually distributed. Retain the complete verified archives,
   build recipes, original notices and any patches used for the released binaries.
4. Use the third-party-server option in GPLv3 section 6(d): the catalog links to
   the official projects' versioned source downloads, including the exact Qt and
   Qt for Python archives. HAMLET does not host these dependency archives on
   GitHub or Zenodo. Keep these instructions and checked version-specific links
   available next to the binary download. This choice does not transfer the
   distributor's source-access responsibility to the upstream projects.
5. Keep required source access working for as long as distribution and the
   applicable licenses require it. Recheck before each publication/update and
   when a broken link is reported. If an upstream download disappears, restore
   access through an official upstream source location, update the public
   directions, and verify the replacement against the pinned digest. Suspend the affected binary download until equivalent
   source access is restored if necessary. A contact address or promise to email
   sources later does not replace the required network download.

The matching HAMLET application source is identified by the
[v1.0 tag](https://github.com/JonAndoniFdez/HAMLET/tree/v1.0).
The [v1.0 release](https://github.com/JonAndoniFdez/HAMLET/releases/tag/v1.0)
contains the portable Windows package and these source-access directions.
Writing instructions and running checks does not establish future availability
by itself. Maintain the directions and upstream access while distributing the
binaries. See [the release procedure](../RELEASE_LEGAL_CHECKLIST.md).

## Exact source downloads

The table is copied from the pinned catalog. Download these versions; the latest
development version is not a substitute. Use the catalog to verify each archive.

| Component | Version | Source archive |
| --- | --- | --- |
| anyio | 4.11.0 | [anyio-4.11.0.tar.gz](https://files.pythonhosted.org/packages/c6/78/7d432127c41b50bccba979505f272c16cbcadcc33645d5fa3a738110ae75/anyio-4.11.0.tar.gz) |
| attrs | 25.4.0 | [attrs-25.4.0.tar.gz](https://files.pythonhosted.org/packages/6b/5c/685e6633917e101e5dcb62b9dd76946cbb57c26e133bae9e0cd36033c0a9/attrs-25.4.0.tar.gz) |
| Blender | 4.3.2 | [blender-4.3.2.tar.xz](https://download.blender.org/source/blender-4.3.2.tar.xz) |
| certifi | 2025.8.3 | [certifi-2025.8.3.tar.gz](https://files.pythonhosted.org/packages/dc/67/960ebe6bf230a96cda2e0abcf73af550ec4f090005363542f0765df162e0/certifi-2025.8.3.tar.gz) |
| cffi | 2.0.0 | [cffi-2.0.0.tar.gz](https://files.pythonhosted.org/packages/eb/56/b1ba7935a17738ae8453301356628e8147c79dbb825bcbc73dc7401f9846/cffi-2.0.0.tar.gz) |
| charset-normalizer | 3.4.3 | [charset_normalizer-3.4.3.tar.gz](https://files.pythonhosted.org/packages/83/2d/5fd176ceb9b2fc619e63405525573493ca23441330fcdaee6bef9460e924/charset_normalizer-3.4.3.tar.gz) |
| click | 8.3.1 | [click-8.3.1.tar.gz](https://files.pythonhosted.org/packages/3d/fa/656b739db8587d7b5dfa22e22ed02566950fbfbcdc20311993483657a5c0/click-8.3.1.tar.gz) |
| colorama | 0.4.6 | [colorama-0.4.6.tar.gz](https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz) |
| et_xmlfile | 2.0.0 | [et_xmlfile-2.0.0.tar.gz](https://files.pythonhosted.org/packages/d3/38/af70d7ab1ae9d4da450eeec1fa3918940a5fafb9055e934af8d6eb0c2313/et_xmlfile-2.0.0.tar.gz) |
| fsspec | 2025.10.0 | [fsspec-2025.10.0.tar.gz](https://files.pythonhosted.org/packages/24/7f/2747c0d332b9acfa75dc84447a066fdf812b5a6b8d30472b74d309bfe8cb/fsspec-2025.10.0.tar.gz) |
| h11 | 0.16.0 | [h11-0.16.0.tar.gz](https://files.pythonhosted.org/packages/01/ee/02a2c011bdab74c6fb3c75474d40b3052059d95df7e73351460c8588d963/h11-0.16.0.tar.gz) |
| httpcore | 1.0.9 | [httpcore-1.0.9.tar.gz](https://files.pythonhosted.org/packages/06/94/82699a10bca87a5556c9c59b5963f2d039dbd239f25bc2a63907a05a14cb/httpcore-1.0.9.tar.gz) |
| httpx | 0.28.1 | [httpx-0.28.1.tar.gz](https://files.pythonhosted.org/packages/b1/df/48c586a5fe32a0f01324ee087459e112ebb7224f646c0b5023f5e79e9956/httpx-0.28.1.tar.gz) |
| idna | 3.10 | [idna-3.10.tar.gz](https://files.pythonhosted.org/packages/f1/70/7703c29685631f5a7590aa73f1f1d3fa9a380e654b86af429e0934a32f7d/idna-3.10.tar.gz) |
| jsonschema | 4.26.0 | [jsonschema-4.26.0.tar.gz](https://files.pythonhosted.org/packages/b3/fc/e067678238fa451312d4c62bf6e6cf5ec56375422aee02f9cb5f909b3047/jsonschema-4.26.0.tar.gz) |
| jsonschema-specifications | 2025.9.1 | [jsonschema_specifications-2025.9.1.tar.gz](https://files.pythonhosted.org/packages/19/74/a633ee74eb36c44aa6d1095e7cc5569bebf04342ee146178e2d36600708b/jsonschema_specifications-2025.9.1.tar.gz) |
| matplotlib | 3.10.6 | [matplotlib-3.10.6.tar.gz](https://files.pythonhosted.org/packages/a0/59/c3e6453a9676ffba145309a73c462bb407f4400de7de3f2b41af70720a3c/matplotlib-3.10.6.tar.gz) |
| Blender-ALEMBIC | 1.8.3 | [alembic-1.8.3.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/alembic-1.8.3.tar.gz) |
| Blender-BLOSC | 1.21.1 | [blosc-1.21.1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/blosc-1.21.1.tar.gz) |
| Blender-BOOST | 1.82.0 | [boost_1_82_0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/boost_1_82_0.tar.gz) |
| Blender-BROTLI | 1.0.9 | [brotli-v1.0.9.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/brotli-v1.0.9.tar.gz) |
| Blender-BZIP2 | 1.0.8 | [bzip2_1.0.8.orig.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/bzip2_1.0.8.orig.tar.gz) |
| Blender-DPCPP | d2817d6d317db1143bb227168e85c409d5ab7c82 | [DPCPP-d2817d6d317db1143bb227168e85c409d5ab7c82.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/DPCPP-d2817d6d317db1143bb227168e85c409d5ab7c82.tar.gz) |
| Blender-EMBREE | 4.3.2-blender | [embree-v4.3.2-blender.zip](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/embree-v4.3.2-blender.zip) |
| Blender-FFMPEG | 6.1.1 | [ffmpeg-6.1.1.tar.bz2](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/ffmpeg-6.1.1.tar.bz2) |
| Blender-FFTW | 3.3.10 | [fftw-3.3.10.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/fftw-3.3.10.tar.gz) |
| Blender-FLAC | 1.4.2 | [flac-1.4.2.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/flac-1.4.2.tar.xz) |
| Blender-FMT | 9.1.0 | [fmt-9.1.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/fmt-9.1.0.tar.gz) |
| Blender-FREETYPE | 2.13.0 | [freetype-2.13.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/freetype-2.13.0.tar.gz) |
| Blender-FRIBIDI | v1.0.12 | [fribidi-v1.0.12.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/fribidi-v1.0.12.tar.gz) |
| Blender-SHADERC_GLSLANG | 89db4e1caa273a057ea46deba709c6e50001b314 | [glslang-89db4e1caa273a057ea46deba709c6e50001b314.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/glslang-89db4e1caa273a057ea46deba709c6e50001b314.tar.gz) |
| Blender-LIBGLU | 9.0.1 | [glu-9.0.1.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/glu-9.0.1.tar.xz) |
| Blender-GMP | 6.2.1 | [gmp-6.2.1.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/gmp-6.2.1.tar.xz) |
| Blender-HIPRT | 83e18cc9c3de8f2f9c48b663cf3189361e891054 | [hiprt-83e18cc9c3de8f2f9c48b663cf3189361e891054.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/hiprt-83e18cc9c3de8f2f9c48b663cf3189361e891054.tar.gz) |
| Blender-ICDLOADER | 9a3e962f16f5097d2054233ad8b6dad51b6f41b7 | [icdloader-9a3e962f16f5097d2054233ad8b6dad51b6f41b7.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/icdloader-9a3e962f16f5097d2054233ad8b6dad51b6f41b7.tar.gz) |
| Blender-IGC | 1.0.17384.29 | [igc-1.0.17384.29.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/igc-1.0.17384.29.tar.gz) |
| Blender-IMATH | 3.1.7 | [imath-3.1.7.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/imath-3.1.7.tar.gz) |
| Blender-GMMLIB | intel-gmmlib-22.4.1 | [intel-gmmlib-22.4.1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/intel-gmmlib-22.4.1.tar.gz) |
| Blender-JEMALLOC | 5.2.1 | [jemalloc-5.2.1.tar.bz2](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/jemalloc-5.2.1.tar.bz2) |
| Blender-LAME | 3.100 | [lame-3.100.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/lame-3.100.tar.gz) |
| Blender-LEVEL_ZERO | 1.16.1 | [level-zero-1.16.1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/level-zero-1.16.1.tar.gz) |
| Blender-AOM | 3.4.0 | [libaom-3.4.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libaom-3.4.0.tar.gz) |
| Blender-WAYLAND_LIBDECOR | 0.2.2 | [libdecor-0.2.2.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libdecor-0.2.2.tar.xz) |
| Blender-DEFLATE | 1.18 | [libdeflate-v1.18.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libdeflate-v1.18.tar.gz) |
| Blender-EPOXY | 1.5.10 | [libepoxy-1.5.10.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libepoxy-1.5.10.tar.gz) |
| Blender-EXPAT | 2_5_0 | [libexpat-2_5_0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libexpat-2_5_0.tar.gz) |
| Blender-FFI | 3.4.4 | [libffi-3.4.4.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libffi-3.4.4.tar.gz) |
| Blender-HARU | 2_3_0 | [libharu-2_3_0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libharu-2_3_0.tar.gz) |
| Blender-ICONV | 1.16 | [libiconv-1.16.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libiconv-1.16.tar.gz) |
| Blender-JPEG | 2.1.3 | [libjpeg-turbo-2.1.3.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libjpeg-turbo-2.1.3.tar.gz) |
| Blender-OGG | 1.3.5 | [libogg-1.3.5.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libogg-1.3.5.tar.gz) |
| Blender-PNG | 1.6.43 | [libpng-1.6.43.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libpng-1.6.43.tar.xz) |
| Blender-SNDFILE | 1.2.2 | [libsndfile-1.2.2.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libsndfile-1.2.2.tar.xz) |
| Blender-SPNAV | 1.1 | [libspnav-1.1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libspnav-1.1.tar.gz) |
| Blender-THEORA | 1.1.1 | [libtheora-1.1.1.tar.bz2](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libtheora-1.1.1.tar.bz2) |
| Blender-VORBIS | 1.3.7 | [libvorbis-1.3.7.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libvorbis-1.3.7.tar.gz) |
| Blender-VPX | 1.14.0 | [libvpx-v1.14.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libvpx-v1.14.0.tar.gz) |
| Blender-WEBP | 1.3.2 | [libwebp-1.3.2.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libwebp-1.3.2.tar.gz) |
| Blender-XML2 | 2.12.3 | [libxml2-2.12.3.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/libxml2-2.12.3.tar.xz) |
| Blender-LLVM | 17.0.6 | [llvm-project-17.0.6.src.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/llvm-project-17.0.6.src.tar.xz) |
| Blender-IGC_LLVM | llvmorg-14.0.5 | [llvmorg-14.0.5.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/llvmorg-14.0.5.tar.gz) |
| Blender-MATERIALX | 1.38.8 | [materialx-v1.38.8.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/materialx-v1.38.8.tar.gz) |
| Blender-MESA | 23.3.0 | [mesa-23.3.0.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/mesa-23.3.0.tar.xz) |
| Blender-MINIZIPNG | 3.0.7 | [minizip-ng-3.0.7.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/minizip-ng-3.0.7.tar.gz) |
| Blender-MP11 | ef7608b463298b881bc82eae4f45a4385ed74fca | [mp11-ef7608b463298b881bc82eae4f45a4385ed74fca.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/mp11-ef7608b463298b881bc82eae4f45a4385ed74fca.tar.gz) |
| Blender-NUMPY | 1.24.3 | [numpy-1.24.3.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/numpy-1.24.3.tar.gz) |
| Blender-OCLOC | 24.31.30508.9 | [ocloc-24.31.30508.9.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/ocloc-24.31.30508.9.tar.gz) |
| Blender-OIDN | 2.3.0 | [oidn-2.3.0.src.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/oidn-2.3.0.src.tar.gz) |
| Blender-TBB | 2020_U3 | [oneTBB-2020_U3.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/oneTBB-2020_U3.tar.gz) |
| Blender-OPENAL | 1.23.1 | [openal-soft-1.23.1.tar.bz2](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/openal-soft-1.23.1.tar.bz2) |
| Blender-IGC_OPENCL_CLANG | 470cf0018e1ef6fc92eda1356f5f31f7da452abc | [opencl-clang-470cf0018e1ef6fc92eda1356f5f31f7da452abc.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/opencl-clang-470cf0018e1ef6fc92eda1356f5f31f7da452abc.tar.gz) |
| Blender-OPENCLHEADERS | 9ddb236e6eb3cf844f9e2f81677e1045f9bf838e | [opencl_headers-9ddb236e6eb3cf844f9e2f81677e1045f9bf838e.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/opencl_headers-9ddb236e6eb3cf844f9e2f81677e1045f9bf838e.tar.gz) |
| Blender-OPENCOLLADA | dfc341ab0b3b23ee307ab8660c0213e64da1eac6 | [opencollada-dfc341ab0b3b23ee307ab8660c0213e64da1eac6.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/opencollada-dfc341ab0b3b23ee307ab8660c0213e64da1eac6.tar.gz) |
| Blender-OPENCOLORIO | 2.3.2 | [OpenColorIO-2.3.2.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/OpenColorIO-2.3.2.tar.gz) |
| Blender-OPENEXR | 3.2.4 | [openexr-3.2.4.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/openexr-3.2.4.tar.gz) |
| Blender-OPENIMAGEIO | v2.5.11.0 | [OpenImageIO-v2.5.11.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/OpenImageIO-v2.5.11.0.tar.gz) |
| Blender-OPENJPEG | 2.5.0 | [openjpeg-v2.5.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/openjpeg-v2.5.0.tar.gz) |
| Blender-OPENPGL | v0.6.0 | [openpgl-v0.6.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/openpgl-v0.6.0.tar.gz) |
| Blender-OSL | 1.13.7.0 | [OpenShadingLanguage-1.13.7.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/OpenShadingLanguage-1.13.7.0.tar.gz) |
| Blender-SSL | 3.1.5 | [openssl-3.1.5.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/openssl-3.1.5.tar.gz) |
| Blender-OPENSUBDIV | v3_6_0 | [opensubdiv-v3_6_0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/opensubdiv-v3_6_0.tar.gz) |
| Blender-OPENVDB | 11.0.0 | [openvdb-11.0.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/openvdb-11.0.0.tar.gz) |
| Blender-XR_OPENXR_SDK | 1.0.22 | [OpenXR-SDK-1.0.22.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/OpenXR-SDK-1.0.22.tar.gz) |
| Blender-OPUS | 1.3.1 | [opus-1.3.1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/opus-1.3.1.tar.gz) |
| Blender-POTRACE | 1.16 | [potrace-1.16.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/potrace-1.16.tar.gz) |
| Blender-PTHREADS | 3.0.0 | [pthreads4w-code-3.0.0.zip](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/pthreads4w-code-3.0.0.zip) |
| Blender-PUGIXML | 1.10 | [pugixml-1.10.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/pugixml-1.10.tar.gz) |
| Blender-PYBIND11 | 2.10.1 | [pybind-v2.10.1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/pybind-v2.10.1.tar.gz) |
| Blender-PYSTRING | v1.1.3 | [pystring-v1.1.3.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/pystring-v1.1.3.tar.gz) |
| Blender-PYTHON | 3.11.9 | [Python-3.11.9.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/Python-3.11.9.tar.xz) |
| Blender-ROBINMAP | v0.6.2 | [robinmap-v0.6.2.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/robinmap-v0.6.2.tar.gz) |
| Blender-SDL | 2.28.2 | [SDL2-2.28.2.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SDL2-2.28.2.tar.gz) |
| Blender-SHADERC | v2022.3 | [shaderc-v2022.3.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/shaderc-v2022.3.tar.gz) |
| Blender-SPIRV_HEADERS | b73e168ca5e123dcf3dea8a34b19a5130f421ae1 | [SPIR-V-Headers-b73e168ca5e123dcf3dea8a34b19a5130f421ae1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SPIR-V-Headers-b73e168ca5e123dcf3dea8a34b19a5130f421ae1.tar.gz) |
| Blender-IGC_SPIRV_HEADERS | vulkan-sdk-1.3.275.0 | [SPIR-V-Headers-vulkan-sdk-1.3.275.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SPIR-V-Headers-vulkan-sdk-1.3.275.0.tar.gz) |
| Blender-IGC_SPIRV_TOOLS | v2023.6.rc1 | [SPIR-V-Tools-v2023.6.rc1.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SPIR-V-Tools-v2023.6.rc1.tar.gz) |
| Blender-IGC_SPIRV_TRANSLATOR | 2823e7052b7999c10fff63bc8089e5aa205716f4 | [SPIR-V-Translator-2823e7052b7999c10fff63bc8089e5aa205716f4.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SPIR-V-Translator-2823e7052b7999c10fff63bc8089e5aa205716f4.tar.gz) |
| Blender-SHADERC_SPIRV_HEADERS | 85a1ed200d50660786c1a88d9166e871123cce39 | [SPIRV-Headers-85a1ed200d50660786c1a88d9166e871123cce39.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SPIRV-Headers-85a1ed200d50660786c1a88d9166e871123cce39.tar.gz) |
| Blender-SHADERC_SPIRV_TOOLS | eb0a36633d2acf4de82588504f951ad0f2cecacb | [SPIRV-Tools-eb0a36633d2acf4de82588504f951ad0f2cecacb.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/SPIRV-Tools-eb0a36633d2acf4de82588504f951ad0f2cecacb.tar.gz) |
| Blender-SQLITE | 3.45.1 | [sqlite-autoconf-3450100.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/sqlite-autoconf-3450100.tar.gz) |
| Blender-SSE2NEON | 227cc413fb2d50b2a10073087be96b59d5364aea | [sse2neon-227cc413fb2d50b2a10073087be96b59d5364aea.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/sse2neon-227cc413fb2d50b2a10073087be96b59d5364aea.tar.gz) |
| Blender-TIFF | 4.6.0 | [tiff-4.6.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/tiff-4.6.0.tar.gz) |
| Blender-UNIFIED_MEMORY_FRAMEWORK | 9bf7a0dc4dff76844e10edbb5c6e9d917536ef6d | [unified-memory-framework-9bf7a0dc4dff76844e10edbb5c6e9d917536ef6d.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/unified-memory-framework-9bf7a0dc4dff76844e10edbb5c6e9d917536ef6d.tar.gz) |
| Blender-UNIFIED_RUNTIME | ec634ff05b067d7922ec45059dda94665e5dcd9b | [unified-runtime-ec634ff05b067d7922ec45059dda94665e5dcd9b.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/unified-runtime-ec634ff05b067d7922ec45059dda94665e5dcd9b.tar.gz) |
| Blender-USD | 24.05 | [usd-v24.05.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/usd-v24.05.tar.gz) |
| Blender-VCINTRINSICS | da892e1982b6c25b9a133f85b4ac97142d8a3def | [vc-intrinsics-da892e1982b6c25b9a133f85b4ac97142d8a3def.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/vc-intrinsics-da892e1982b6c25b9a133f85b4ac97142d8a3def.tar.gz) |
| Blender-IGC_VCINTRINSICS | v0.19.0 | [vc-intrinsics-v0.19.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/vc-intrinsics-v0.19.0.tar.gz) |
| Blender-VULKAN_HEADERS | v1.3.270 | [Vulkan-Headers-v1.3.270.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/Vulkan-Headers-v1.3.270.tar.gz) |
| Blender-VULKAN_LOADER | v1.3.270 | [Vulkan-Loader-v1.3.270.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/Vulkan-Loader-v1.3.270.tar.gz) |
| Blender-WAYLAND | 1.23.0 | [wayland-1.23.0.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/wayland-1.23.0.tar.xz) |
| Blender-WL_PROTOCOLS | 1.36 | [wayland-protocols-1.36.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/wayland-protocols-1.36.tar.xz) |
| Blender-WAYLAND_WESTON | 13.0.3 | [weston-13.0.3.tar.xz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/weston-13.0.3.tar.xz) |
| Blender-X264 | 35fe20d1ba49918ec739a5b068c208ca82f977f7 | [x264-35fe20d1ba49918ec739a5b068c208ca82f977f7.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/x264-35fe20d1ba49918ec739a5b068c208ca82f977f7.tar.gz) |
| Blender-X265 | 3cf6c1e53037eb9e198860365712e1bafb22f7c6 | [x265-3cf6c1e53037eb9e198860365712e1bafb22f7c6.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/x265-3cf6c1e53037eb9e198860365712e1bafb22f7c6.tar.gz) |
| Blender-LZMA | 5.2.5 | [xz-5.2.5.tar.bz2](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/xz-5.2.5.tar.bz2) |
| Blender-YAMLCPP | 0.7.0 | [yaml-cpp-0.7.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/yaml-cpp-0.7.0.tar.gz) |
| Blender-ZLIB | 1.2.13 | [zlib-1.2.13.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/zlib-1.2.13.tar.gz) |
| Blender-ZSTD | 1.5.0 | [zstd-1.5.0.tar.gz](https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/zstd-1.5.0.tar.gz) |
| numpy | 2.2.6 | [numpy-2.2.6.tar.gz](https://files.pythonhosted.org/packages/76/21/7d2a95e4bba9dc13d043ee156a356c0a8f0c6309dff6b21b4d71a073b8a8/numpy-2.2.6.tar.gz) |
| opencv-python | 4.10.0.84 | [opencv-python-4.10.0.84.tar.gz](https://files.pythonhosted.org/packages/4a/e7/b70a2d9ab205110d715906fc8ec83fbb00404aeb3a37a0654fdb68eb0c8c/opencv-python-4.10.0.84.tar.gz) |
| openpyxl | 3.1.5 | [openpyxl-3.1.5.tar.gz](https://files.pythonhosted.org/packages/3d/f9/88d94a75de065ea32619465d2f77b29a0469500e99012523b91cc4141cd1/openpyxl-3.1.5.tar.gz) |
| packaging | 26.2 | [packaging-26.2.tar.gz](https://files.pythonhosted.org/packages/d7/f1/e7a6dd94a8d4a5626c03e4e99c87f241ba9e350cd9e6d75123f992427270/packaging-26.2.tar.gz) |
| pandas | 2.3.3 | [pandas-2.3.3.tar.gz](https://files.pythonhosted.org/packages/33/01/d40b85317f86cf08d853a4f495195c73815fdf205eef3993821720274518/pandas-2.3.3.tar.gz) |
| pillow | 11.3.0 | [pillow-11.3.0.tar.gz](https://files.pythonhosted.org/packages/f3/0d/d0d6dea55cd152ce3d6767bb38a8fc10e33796ba4ba210cbab9354b6d238/pillow-11.3.0.tar.gz) |
| psutil | 7.2.2 | [psutil-7.2.2.tar.gz](https://files.pythonhosted.org/packages/aa/c6/d1ddf4abb55e93cebc4f2ed8b5d6dbad109ecb8d63748dd2b20ab5e57ebe/psutil-7.2.2.tar.gz) |
| pycparser | 3.0 | [pycparser-3.0.tar.gz](https://files.pythonhosted.org/packages/1b/7d/92392ff7815c21062bea51aa7b87d45576f649f16458d78b7cf94b9ab2e6/pycparser-3.0.tar.gz) |
| Pygments | 2.20.0 | [pygments-2.20.0.tar.gz](https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz) |
| pyinstaller | 6.18.0 | [pyinstaller-6.18.0.tar.gz](https://files.pythonhosted.org/packages/9f/b8/0fe3359920b0a4e7008e0e93ff383003763e3eee3eb31a07c52868722960/pyinstaller-6.18.0.tar.gz) |
| pyparsing | 3.2.3 | [pyparsing-3.2.3.tar.gz](https://files.pythonhosted.org/packages/bb/22/f1129e69d94ffff626bdb5c835506b3a5b4f3d070f17ea295e12c2c6f60f/pyparsing-3.2.3.tar.gz) |
| QtForPython | 6.10.2 | [pyside-setup-everywhere-src-6.10.2.tar.xz](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.2-src/pyside-setup-everywhere-src-6.10.2.tar.xz) |
| Python | 3.11.9 | [Python-3.11.9.tar.xz](https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tar.xz) |
| python-dateutil | 2.9.0.post0 | [python-dateutil-2.9.0.post0.tar.gz](https://files.pythonhosted.org/packages/66/c0/0c8b6ad9f17a802ee498c46e004a0eb49bc148f2fd230864601a86dcf6db/python-dateutil-2.9.0.post0.tar.gz) |
| pytz | 2025.2 | [pytz-2025.2.tar.gz](https://files.pythonhosted.org/packages/f8/bf/abbd3cdfb8fbc7fb3d4d38d320f2441b1e7cbe29be4f23797b4a2b5d8aac/pytz-2025.2.tar.gz) |
| pywin32 | 311 | [pywin32-b311.tar.gz](https://github.com/mhammond/pywin32/archive/refs/tags/b311.tar.gz) |
| PyYAML | 6.0.3 | [pyyaml-6.0.3.tar.gz](https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz) |
| Qt | 6.10.2 | [qt-everywhere-src-6.10.2.tar.xz](https://download.qt.io/archive/qt/6.10/6.10.2/single/qt-everywhere-src-6.10.2.tar.xz) |
| QtPy | 2.4.3 | [qtpy-2.4.3.tar.gz](https://files.pythonhosted.org/packages/70/01/392eba83c8e47b946b929d7c46e0f04b35e9671f8bb6fc36b6f7945b4de8/qtpy-2.4.3.tar.gz) |
| referencing | 0.37.0 | [referencing-0.37.0.tar.gz](https://files.pythonhosted.org/packages/22/f5/df4e9027acead3ecc63e50fe1e36aca1523e1719559c499951bb4b53188f/referencing-0.37.0.tar.gz) |
| requests | 2.32.5 | [requests-2.32.5.tar.gz](https://files.pythonhosted.org/packages/c9/74/b3ff8e6c8446842c3f5c837e9c3dfcfe2018ea6ecef224c710c85ef728f4/requests-2.32.5.tar.gz) |
| rpds-py | 0.30.0 | [rpds_py-0.30.0.tar.gz](https://files.pythonhosted.org/packages/20/af/3f2f423103f1113b36230496629986e0ef7e199d2aa8392452b484b38ced/rpds_py-0.30.0.tar.gz) |
| scipy | 1.17.1 | [scipy-1.17.1.tar.gz](https://files.pythonhosted.org/packages/7a/97/5a3609c4f8d58b039179648e62dd220f89864f56f7357f5d4f45c29eb2cc/scipy-1.17.1.tar.gz) |
| setuptools | 65.5.0 | [setuptools-65.5.0.tar.gz](https://files.pythonhosted.org/packages/c5/41/247814d8b7a044717164c74080725a6c8f3d2b5fc82b34bd825b617df663/setuptools-65.5.0.tar.gz) |
| six | 1.17.0 | [six-1.17.0.tar.gz](https://files.pythonhosted.org/packages/94/e7/b2c673351809dca68a0e064b6af791aa332cf192da575fd474ed7d6f16a2/six-1.17.0.tar.gz) |
| sniffio | 1.3.1 | [sniffio-1.3.1.tar.gz](https://files.pythonhosted.org/packages/a2/87/a6771e1546d97e7e041b6ae58d80074f81b7d5121207425c964ddf5cfdbd/sniffio-1.3.1.tar.gz) |
| tqdm | 4.67.1 | [tqdm-4.67.1.tar.gz](https://files.pythonhosted.org/packages/a8/4b/29b4ef32e036bb34e4ab51796dd745cdba7ed47ad142a9f4a1eb8e0c744d/tqdm-4.67.1.tar.gz) |
| traitlets | 5.15.1 | [traitlets-5.15.1.tar.gz](https://files.pythonhosted.org/packages/57/a9/a2584b8313b89f94869ddb3c4074617a691de1812a614d2d50e32ca5a7a6/traitlets-5.15.1.tar.gz) |
| trimesh | 4.11.4 | [trimesh-4.11.4.tar.gz](https://files.pythonhosted.org/packages/1c/6c/57a77091f42c4fe3246810c8878b1f08c65944432bb856e1b797e960c822/trimesh-4.11.4.tar.gz) |
| typing_extensions | 4.16.0 | [typing_extensions-4.16.0.tar.gz](https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3306cebfbda2c520f545d36b5be2c7255cc528bb45d6/typing_extensions-4.16.0.tar.gz) |
| urllib3 | 2.5.0 | [urllib3-2.5.0.tar.gz](https://files.pythonhosted.org/packages/15/22/9ee70a2574a4f4599c47dd506532914ce044817c7752a79b6a51286319bc/urllib3-2.5.0.tar.gz) |
| vedo | 2025.5.4 | [vedo-2025.5.4.tar.gz](https://files.pythonhosted.org/packages/74/cb/15d78ab5930ea09664f9834645372bca4963c78510be422df812804f72de/vedo-2025.5.4.tar.gz) |
| VTK | 9.5.1 | [VTK-9.5.1.tar.gz](https://www.vtk.org/files/release/9.5/VTK-9.5.1.tar.gz) |
| xlrd | 2.0.2 | [xlrd-2.0.2.tar.gz](https://files.pythonhosted.org/packages/07/5a/377161c2d3538d1990d7af382c79f3b2372e880b65de21b01b1a2b78691e/xlrd-2.0.2.tar.gz) |


Model extraction.py – Sky: Children of the Light .mesh to OBJ Converter

Overview

Model extraction.py is a powerful Python script designed to extract 3D models from the mobile game Sky: Children of the Light. It converts .mesh files into the widely supported OBJ format, allowing you to import them into any 3D modelling software (Blender, Maya, etc.).

The script incorporates multiple parsing strategies developed by the reverse‑engineering community, achieving an over 99% success rate on a large test set (over 5900 files). It automatically handles:

· Uncompressed and LZ4‑compressed meshes
· Standard vertex/UV/index layouts (heuristic parsing)
· Compressed models with compressPositions / compressUvs flags
· Special files containing ZipPos, StripAnim, CompOcc, StripUv13 and other flags
· 16‑bit and 32‑bit indices (auto‑detected)
· fmt_mesh parser (ported from Durik256’s Noesis plugin) for the most stubborn files

The script works in Termux (Android) and any Linux environment with Python 3 and the LZ4 library.

Dependencies

· Python 3.6+ (standard library: ctypes, struct, io, os, sys, glob, argparse, re)
· LZ4 library – used for decompression.
    Install it with:
  · Termux: pkg install lz4
  · Linux: sudo apt install liblz4-dev (or your distribution’s equivalent)
  · Windows: Download a pre‑compiled LZ4 DLL (e.g. msys-lz4-1.dll) and place it in the same directory as the script; then set LZ4_LIB = 'msys-lz4-1.dll' in the script.

No additional Python packages are required.

Installation

1. Copy the script – save Model extraction.py to your desired folder.
2. Install LZ4 (as described above).
3. Optional but recommended – place the game’s MeshDefs.lua file in the same directory. The script will read it to automatically detect compression flags, improving accuracy for some models.
4. Make the script executable (optional):
   ```bash
   chmod +x Model extraction.py
   ```

Usage

The script can be used in two modes: interactive (no arguments) or command‑line (batch mode).

Interactive Mode

Simply run the script without arguments:

```bash
python "Model extraction.py"
```

It will list all .mesh files in the current directory and prompt you to select which ones to convert.
You can enter:

· Single numbers: 1
· Space‑ or comma‑separated lists: 1 3 5 or 1,3,5
· Ranges: 1-5
· all – convert every file
· q – quit

After selecting files, you will be asked for an output directory (press Enter for the current directory). The script then processes each file and shows progress.

Command‑Line Mode (Batch)

Convert one or more files directly:

```bash
python "Model extraction.py" file1.mesh file2.mesh -o ./output_folder
```

Use wildcards to convert all .mesh files in a folder:

```bash
python "Model extraction.py" *.mesh -o ./output
```

The -o argument defines the output directory (defaults to the current folder if omitted).

Output

For each input .mesh file, a corresponding .obj file is created in the output directory, e.g. Wing_TeamPrairie.obj.
If the script detects degenerate triangles (faces with duplicate vertex indices), they are automatically filtered out, and a count of valid faces is printed.

Features & Advantages

· Multi‑layer parsing – tries up to four different strategies in order:
  1. fmt_mesh parser (based on the Noesis plugin) – handles files with a 0x1F header, supports bones, multiple UV sets, and the ZipPos branch.
  2. Compressed model parser – for models with compressPositions/compressUvs; includes a special ZipPos branch that reads 8‑bit quantised vertices from the end of the decompressed buffer and normalises them.
  3. Heuristic parser – tries several offsets for compressed sizes and internal counts; works for most standard files.
  4. Fallback – if all else fails, the script still attempts the compressed parser as a last resort.
· Automatic index type detection – searches for 16‑bit or 32‑bit index buffers.
· Degenerate face removal – filters out triangles where two or more vertices are identical.
· MeshDefs.lua support – reads compilation flags to decide whether to treat a file as compressed.
· Filename keyword detection – flags like ZipPos, StripAnim, CompOcc etc. are recognised and trigger the appropriate parser.
· Cross‑platform – runs on Termux (Android), Linux, and (with minor adjustments) Windows.
· Detailed debug output – set DEBUG = True in the script to see every step; useful for diagnosing problems.

Limitations & Known Issues

· Texture export – the script exports geometry only (vertices, UVs, faces). Textures (.ktx files) must be converted separately using tools like PVRTextTool.
· LZ4 dependency – the LZ4 library must be installed separately; Windows users need to provide a DLL.
· Extremely rare failures – about 1% of files (mostly those with complex animation data or unusual compression) may still fail. These often contain additional data blocks (bones, multiple sub‑meshes) that are not yet fully reverse‑engineered.
· No skeleton/armature export – bone data is currently ignored; only static geometry is extracted.
· OBJ format only – output is fixed to .obj; other formats (FBX, GLTF) are not supported.

Acknowledgements

This script is a synthesis of many community contributions:

· longbyte1 – initial decompression and layout research.
· DancingTwix – original forum post and encouragement.
· cobrakyle / sungaila – help with cracking the format.
· Durik256 – author of the Noesis plugin fmt_mesh.py, which inspired the new parser.
· mablay – developer of the sky-browser tool and the CLI exporter.
· oldmud0 – creator of the ImHex pattern and the SkyEngineTools repository.

Their work made this script possible.

Contact

For questions, bug reports, or suggestions, please email:
📧 3787533101@qq.com

---

Happy model extracting!

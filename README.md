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

Happy model extracting!· Degenerate face filtering
    OBJ export optionally removes faces with duplicate vertex indices to clean up the mesh.
· Interactive file selection
    In interactive mode, you can select multiple files using numbers, ranges (e.g. 1-5), comma/space separated lists, or all.
· Custom output directory
    Specify where the OBJ files should be saved (defaults to current directory).
· Command‑line batch mode
    Process all .mesh files at once with a simple command.

Dependencies

· Python 3.6+
· LZ4 library – required for decompressing the compressed data inside .mesh files.

Installation

1. Install Python (if not already present) from python.org or using your system’s package manager.
2. Install the LZ4 library
   · On Termux (Android): pkg install lz4
   · On Linux: sudo apt install liblz4-dev (or equivalent for your distribution)
   · On Windows: Download a precompiled LZ4 DLL (e.g. from the lz4-win64 release) and place it in a known path. Then edit the script to point LZ4_LIB to that DLL (e.g. 'C:/path/to/msys-lz4-1.dll').
3. Save the script as Model extraction.py (or any name you prefer).

Usage

Command‑line mode (batch processing)

```bash
python "Model extraction.py" file1.mesh file2.mesh -o ./output_folder
```

· Supports wildcards (e.g. *.mesh).
· If -o is omitted, OBJ files are saved in the current directory.

Interactive mode

Run the script without arguments:

```bash
python "Model extraction.py"
```

You will see a list of all .mesh files in the current directory:

```
找到以下 .mesh 文件：
1. model1.mesh
2. model2.mesh
3. model3.mesh

请输入要转换的文件序号（支持格式：1 2 3、1-5、1,2,3 或 all）
或输入 q 退出程序。
选择:
```

Enter your selection, e.g. 1 3 5, 1-5, 1,3,5, or all. Then specify the output directory (press Enter to use the current directory). The script will process each selected file and export OBJ files with the same base name.

How It Works

1. File identification
      The script first reads the first few bytes of the file. If the header is \x1F\x00\x00\x00, it tries the fmt_mesh parser (originally from a Noesis plugin). This parser handles both regular and ZipPos models, including bone/skeleton data (which is skipped for geometry extraction).
2. Heuristic parsing
      If the file does not have the fmt_mesh header, the script attempts to decompress data using several candidate offset sets for compressed size, uncompressed size, and data start. It then looks for vertex/total counts at common offsets (e.g. 0x74, 0x78) and reads vertex, UV, and index buffers according to the “classic” layout.
3. Compressed‑model parsing
      A dedicated parser tries different offset combinations (both 4‑byte and 2‑byte sizes) to locate the LZ4 compressed block. After decompression it either:
   · Uses the new‑version layout (if detected from header fields at 0x30–0x40).
   · Uses the old‑version layout (quantized 16‑bit vertices with min/range values).
   · If the filename contains ZipPos, it enters a special branch that reads 8‑bit quantised vertices from the end of the decompressed buffer and normalises them to the [-1, 1] range.
4. Index searching
      After vertices and UVs are obtained, the script scans the remaining data for a contiguous block of 16‑bit or 32‑bit indices that form valid triangles (all indices less than the vertex count). It then reads the face data.
5. OBJ export
      Finally, the script writes an OBJ file containing:
   · v lines for vertices
   · vt lines for UV coordinates
   · f lines for faces (with optional degenerate‑face filtering).

Advantages

· High success rate – Processes over 99% of all .mesh files from the game (tested on 5906 files).
· No Blender required – Pure Python command‑line tool, ideal for batch processing and automation.
· Cross‑platform – Runs on any system where Python and LZ4 are available (Termux, Linux, Windows, macOS).
· User‑friendly – Interactive selection and clear debug output.
· Extensible – Open source; you can easily add new offset candidates or parsing branches as the file format evolves.

Limitations

· Special‑flagged files – A few files (mostly .animpack.mesh or those with very complex flags) may still fail. These often require dedicated tools like Noesis with the fmt_mesh.py plugin.
· OBJ only – Output is limited to the OBJ format; no support for FBX, glTF, etc.
· No textures – Only geometry and UV coordinates are extracted; textures (stored as .ktx) must be converted separately using tools like PVRTextTool.
· LZ4 dependency – Users on Windows must manually supply the LZ4 DLL.

Changelog

v2.5 (2026-02-24)

· Integrated fmt_mesh parser for better handling of ZipPos and animated models.
· Added coordinate normalisation for 8‑bit quantised vertices in ZipPos branch.
· Improved fallback logic and degenerate‑face filtering.

v2.0 (2026-02-24)

· Introduced compressed‑model parser with version detection.
· Added automatic retry with compressed parser when heuristic fails.

v1.0 (2026-02-23)

· Initial heuristic parser based on longbyte1’s original script.

Acknowledgements

This script builds upon the invaluable work of the reverse‑engineering community, especially:

· longbyte1 – for the original Python snippet and the SkyEngineTools repository.
· DancingTwix – for the initial forum guide and continuous testing.
· Durik256 – for the fmt_mesh.py Noesis plugin, which inspired the advanced parsing logic.
· cobrakyle / sungaila – for cracking the first compression issues.
· All contributors to the VG Resource forum thread and the Sky Browser project.

---

If you encounter any issues or have suggestions, please open an issue on GitHub or join the discussion on the Discord server.









《光遇》.mesh 批量转 OBJ 工具

简介

这是一个专为《光遇》（Sky: Children of the Light）游戏资源提取设计的 Python 脚本，用于将游戏中的 .mesh 模型文件批量转换为通用的 OBJ 格式。该脚本基于社区逆向工程成果，采用启发式解析处理常规模型，并针对启用了顶点压缩（compressPositions）和 UV 压缩（compressUvs）的特殊模型提供了专用解析器。同时，它能自动读取 MeshDefs.lua 中的编译参数，根据文件名关键词或解析失败自动切换解析方式，实现了对绝大多数 .mesh 文件的高兼容性。支持交互式多选文件、自定义输出目录，可在手机（Termux）或电脑上运行。

联系我们
q群:550929330

功能特点

· 双重解析引擎：
  · 启发式解析：自动尝试多组偏移量，兼容大部分不带压缩标志的常规 .mesh 文件。
  · 压缩模型解析：基于逆向工程，正确处理启用了 compressPositions / compressUvs 的模型（文件名常含 ZipPos、ZipUvs、StripNorm 等关键词）。
· 智能识别与后备：
  · 解析 MeshDefs.lua 获取每个模型的编译参数，自动选择解析器。
  · 文件名包含特殊关键词（如 StripAnim、CompOcc 等）时优先使用压缩解析器。
  · 启发式解析失败后自动尝试压缩解析器，最大限度提高成功率。
· 批量转换：支持一次性处理多个文件，命令行模式或交互式选择均可。
· 多选交互：交互模式下可通过序号、范围（如 1-5）、逗号/空格分隔或 all 快速选择文件。
· 自定义输出目录：可指定保存 OBJ 文件的文件夹，默认为当前目录。
· 详细调试信息：开启 DEBUG 后可输出解析过程，便于排查问题。
· 跨平台：基于 Python 3，依赖 LZ4 库，可在 Linux（包括 Termux）、Windows、macOS 上运行（Windows 需调整 LZ4 库路径）。

优点

1. 高成功率：实测 5906 个文件中成功转换 5905 个，剩余极少数文件可能因格式特殊或损坏无法解析。
2. 无需 Blender：直接在命令行完成转换，适合批量处理或集成到自动化流程。
3. 轻量便携：仅依赖 Python 和 LZ4，无需安装大型软件。
4. 用户友好：提供清晰的交互提示，支持文件多选和输出目录自定义。
5. 可定制：源码开放，可根据需要调整偏移量试探范围或增加新的解析分支。

缺点 / 局限性

1. 极少数文件可能失败：某些模型可能采用了更特殊的压缩方式（如 32 位索引强制）或数据布局与当前逆向结果不符，导致解析失败（目前失败率约 0.02%）。
2. 仅支持 OBJ 格式：输出格式固定为 OBJ，不支持其他格式（如 FBX、GLTF）。
3. 依赖 LZ4 库：需手动安装 LZ4 动态库，Windows 用户需额外配置 DLL 路径。
4. 无纹理导出：仅导出几何模型（顶点、UV、面），不包含材质和纹理映射信息（纹理需用 PVRTextTool 转换 .ktx 文件后手动赋予）。
5. 特殊模型如带动画的可能损坏

使用方法

环境准备

1. 安装 Python 3（建议 3.6 以上）。
2. 安装 LZ4 库：
   · Termux (Android)：pkg install lz4
   · Linux：sudo apt install liblz4-dev（或使用包管理器安装）
   · Windows：下载预编译的 LZ4 DLL（如从 lz4-win64 获取 msys-lz4-1.dll），并放在脚本同一目录或系统路径中。然后修改脚本中的 LZ4_LIB 变量为 DLL 的绝对路径（例如 'C:/path/to/msys-lz4-1.dll'）。
3. 保存脚本：将代码保存为 .py 文件，例如 sky_mesh_to_obj.py。
4. （可选）放置 MeshDefs.lua：将游戏解包得到的 MeshDefs.lua 文件放在与脚本相同的目录下，以便自动识别压缩模型。如果没有此文件，脚本仍能运行，但部分压缩模型可能需依赖文件名关键词或后备机制才能正确解析。

命令行模式

```bash
python sky_mesh_to_obj.py 文件1.mesh 文件2.mesh -o 输出目录
```

· 支持通配符（如 *.mesh）。
· 若不指定 -o，则输出到当前目录。

交互式模式

直接运行脚本（不带参数）：

```bash
python sky_mesh_to_obj.py
```

程序会列出当前目录下所有 .mesh 文件，并提示输入序号选择。支持：

· 单个序号：1
· 多个序号（空格/逗号分隔）：1 3 5 或 1,3,5
· 范围：1-5
· 全部：all
· 退出：q

选择文件后，会询问输出目录（直接回车使用当前目录），然后开始批量转换。

注意事项

· 文件命名：脚本会根据 .mesh 文件同名生成 .obj 文件（例如 model.mesh → model.obj）。
· MeshDefs.lua：强烈建议将游戏解包得到的 MeshDefs.lua 放在脚本目录下，这能显著提高压缩模型的识别准确率。脚本会自动读取该文件。
· 特殊标志文件：即使没有 MeshDefs.lua，脚本也能通过文件名关键词（如 ZipPos）和后备机制处理大多数压缩模型。极少数无法解析的文件会提示失败。
· 调试信息：默认开启 DEBUG=True，可在解析失败时查看详细日志。如需静默运行，可将 DEBUG 设为 False。
· 内存使用：大文件解压可能占用较多内存，但通常不会超过 200MB。

技术原理简述

1. LZ4 解压：读取文件头中的压缩大小和解压大小，定位压缩数据块，调用 LZ4 解压。
2. 启发式解析：尝试多组偏移量读取 compressed_size、uncompressed_size、num_lods，通过合理性检查筛选有效数据，然后从解压后的数据中按常规格式解析顶点、UV 和索引。
3. 压缩模型解析：
   · 从固定偏移（0x60~0x74）读取量化参数（min 和 range）。
   · 从 0x74 和 0x78 读取顶点数（shared）和总顶点数（total）。
   · 顶点数据从 0x7c 开始，每个顶点用 6 字节（三个 16 位整数），结合量化参数还原为浮点数。
   · UV 数据紧跟在顶点之后，每个 UV 用 4 字节（两个 16 位整数），直接归一化到 [0,1]。
   · 自动搜索索引区域（16 位或 32 位），确保索引值小于顶点数。
4. 智能识别：读取 MeshDefs.lua 获得每个模型的编译参数，或根据文件名关键词判断是否为压缩模型。解析失败时自动尝试另一种解析器。
5. OBJ 导出：按标准格式写入顶点、UV 和面索引。

贴图提取:
https://github.com/bluescan/tacentview

更新日志

v2.0 (2026-02-24)

· 增加压缩模型解析器，支持 compressPositions / compressUvs 标志的文件。
· 自动读取 MeshDefs.lua 文件，根据编译参数选择解析器。
· 文件名关键词检测（如 StripAnim、ZipPos 等）作为辅助判断。
· 启发式解析失败后自动尝试压缩解析器，提高容错率。
· 优化索引区域搜索算法，适应不同文件的索引起始偏移。
· 详细调试输出，便于问题排查。

致谢

本脚本基于论坛用户 longbyte1、DancingTwix、ether0x1 等的研究成果，以及社区逆向工程智慧。感谢所有为《光遇》资源提取做出贡献的开发者。

---

最后更新：2026年2月24日
版本：2.0

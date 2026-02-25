模型提取.py–天空：光的子对象mesh到OBJ转换器

概述

Model Extracting.py是一个强大的Python脚本，旨在从手机游戏Sky:Children of the Light中提取3D模型。它将.mesh文件转换为广泛支持的OBJ格式，允许您将其导入任何3D建模软件（Blender、Maya等）。

该脚本结合了逆向工程社区开发的多种解析策略，在大型测试集（超过5900个文件）上实现了99%以上的成功率。它自动处理：

·未压缩和LZ4压缩网格 ·标准顶点/UV/索引布局（启发式解析） ·带有压缩位置/压缩Uvs标志的压缩模型 ·包含ZipPos、StripAnim、CompOcc、StripUv13和其他标志的特殊文件 ·16位和32位索引（自动检测） ·fmt_mesh解析器（从Durik256的Noesis插件移植）用于最顽固的文件

该脚本适用于Termux(Android)和任何带有Python 3和LZ4库的Linux环境。

依赖关系

·Python 3.6+（标准库：ctypes、struct、io、os、sys、Globe、argparse、re） ·LZ4库-用于解压缩。 使用以下方式安装： ·Termux:pkg install lz4 Linux:sudo apt install liblz4-dev（或您的发行版的等效程序） ·Windows：下载一个预编译的LZ4 DLL（例如msys-lz4-1.dll），并将其放置在脚本所在的目录中；然后在剧本。

不需要额外的Python包。

安装

复制脚本–将Model Extracting.py保存到所需的文件夹中。
安装LZ4（如上所述）。
可选，但推荐–将游戏的MeshDefs.lua文件放在同一目录中。脚本将读取它以自动检测压缩标志，提高某些模型的准确性。
使脚本可执行（可选）：
chmod+x模型提取.py
使用情况

脚本可以在两种模式下使用：交互（无参数）或命令行（批处理模式）。

交互模式

只需在没有参数的情况下运行脚本：

Python "模型提取.py"
它将列出当前目录中的所有.mesh文件，并提示您选择要转换的文件。 您可以输入：

·单数：1 ·以空格或逗号分隔的列表：1 3 5或1,3,5 ·范围：1-5 ·all–转换每个文件 q-退出

选择文件后，系统会要求您输入输出目录（按Enter键以选择当前目录）。然后，该脚本处理每个文件并显示进度。

命令行模式（批处理）

直接转换一个或多个文件：

Python "模型提取.py" file1.mesh file2.mesh-o./Output_文件夹
使用通配符转换文件夹中的所有.mesh文件：

Python "模型提取.py" *.mesh-o./输出
-o参数定义输出目录（如果省略，则默认为当前文件夹）。

输出量

对于每个input.mesh文件，在输出目录中创建一个对应的.obj文件，例如Wing_TeamPrairie.obj。 如果脚本检测到退化三角形（具有重复顶点索引的面），则会自动过滤掉它们，并打印有效面的计数。

特点和优势

·多层解析-尝试最多四种不同的策略：

fmt_mesh解析器（基于Noesis插件）–处理带有0x1F头的文件，支持骨骼、多个UV集和ZipPos分支。
压缩模型解析器–适用于具有压缩位置/压缩Uvs的模型；包括一个特殊的ZipPos分支，该分支从解压缩缓冲区的末尾读取8位量化顶点并对其进行规范化。
启发式解析器-尝试压缩大小和内部计数的几个偏移量；适用于大多数标准文件。
回退-如果所有其他方法都失败了，脚本仍然会尝试使用压缩解析器作为最后的手段。 ·自动索引类型检测-搜索16位或32位索引缓冲区。 ·退化面删除-过滤掉两个或多个顶点相同的三角形。 ·MeshDefs.lua支持-读取编译标志以决定是否将文件视为压缩文件。 ·文件名关键字检测-识别ZipPos、StripAnim、CompOcc等标志并触发相应的解析器。 ·跨平台–在Termux(Android)、Linux和（稍作调整）Windows上运行。 ·详细的调试输出–在脚本中设置DEBUG=True以查看每个步骤；对诊断问题非常有用。
限制和已知问题

·纹理导出-脚本仅导出几何体（顶点、UV、面）。纹理（.ktx文件）必须使用PVRTextTool等工具单独转换。 ·LZ4依赖项–LZ4库必须单独安装；Windows用户需要提供DLL。 极其罕见的故障-大约1%的文件（主要是那些具有复杂动画数据或异常压缩的文件）仍然可能会失败。这些通常包含尚未完全进行反向工程的附加数据块（骨骼、多个子网格）。 ·无骨架/骨架导出–骨骼数据当前被忽略；仅提取静态几何体。 ·仅OBJ格式-输出固定为.obj；不支持其他格式（FBX、GLTF）。

确认

这个脚本是许多社区贡献的综合体：

longbyte1–初始解压缩和布局研究。 ·DancingTwix–原创论坛帖子和鼓励。 ·cobrakyle/sungaila–帮助破解格式。 ·Durik256–Noesis插件fmt_mesh.py的作者，它启发了新的解析器。 mablay–sky-browser工具和CLI导出器的开发者。 ·oldmud0–ImHex模式和SkyEngineTools存储库的创建者。

他们的工作使这个剧本成为可能。

联络方式

如有问题、错误报告或建议，请发送电子邮件至： 📧 3787533101@qq.com



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

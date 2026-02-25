模型提取.py–天空：光的子对象mesh到OBJ转换器

概述

Model Extracting.py是一个强大的Python脚本，旨在从手机游戏Sky:Children of the Light中提取3D模型。它将.mesh文件转换为广泛支持的OBJ格式，允许您将其导入任何3D建模软件（Blender、Maya等）。

该脚本结合了逆向工程社区开发的多种解析策略，在大型测试集（超过5900个文件）上实现了99%以上的成功率。它自动处理：

·未压缩和LZ4压缩网格 ·标准顶点/UV/索引布局（启发式解析） ·带有压缩位置/压缩Uvs标志的压缩模型 ·包含ZipPos、StripAnim、CompOcc、StripUv13和其他标志的特殊文件 ·16位和32位索引（自动检测） ·fmt_mesh解析器（从Durik256的Noesis插件移植）用于最顽固的文件

该脚本适用于Termux(Android)和任何带有Python 3和LZ4库的Linux环境。

依赖关系

·Python 3.6+（标准库：ctypes、struct、io、os、sys、Globe、argparse、re） ·LZ4库-用于解压缩。 使用以下方式安装： ·Termux:pkg install lz4 Linux:sudo apt install liblz4-dev（或您的发行版的等效程序） ·Windows：下载一个预编译的LZ4 DLL（例如msys-lz4-1.dll），并将其放置在脚本所在的目录中；然后在剧本。

不需要额外的Python包。
可以看使用方法.md安装

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

相关链接
1.天空浏览器https://github.com/mablay/sky-browser/tree/main
https://mablay.github.io/sky-browser/

2.一篇帖子
https://archive.vg-resource.com/thread-39211.html

3.脚本fmt_mesh.py(SkyEngineTools)
https://github.com/oldmud0/SkyEngineTools/tree/master

4Termux
https://github.com/termux/termux-app#github

5光遇历史版本下载
http://skyversion.ct.ws/

联络方式

如有问题、错误报告或建议，请发送电子邮件至： 📧 3787533101@qq.com

q群：550929330

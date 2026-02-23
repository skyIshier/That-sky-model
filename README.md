Sky光·遇 .mesh 模型提取工具使用文档

📌 简介

本工具是一个 Python 脚本，用于从游戏《Sky光·遇》（Sky: Children of the Light）的 .mesh 文件中提取三维网格模型，并导出为标准 Wavefront OBJ 格式。脚本能够自动识别文件是否带有文件名头，支持 LZ4 解压缩，最终生成 .obj 模型文件及一个包含模型详细信息的 .txt 文件。

该脚本基于社区逆向工程成果（感谢 longbyte1 等开发者的工作），适用于 Termux（Android）或任何安装了 Python 和 LZ4 库的 Linux/Windows 环境。

---

✨ 功能特点

· 自动格式检测：智能判断 .mesh 文件是否包含文件名头，并自动剥离。
· LZ4 解压支持：自动检测压缩数据块并调用系统 LZ4 库解压。
· 双重解析尝试：先尝试不剥离头部直接解析，失败后自动尝试剥离文件名头。
· 导出标准 OBJ：生成包含顶点、UV 坐标和三角面的 OBJ 文件，可直接导入 Blender、Maya 等三维软件。
· 附带信息文件：同目录下生成同名 _info.txt 文件，记录顶点数、面数、UV 数等统计信息。
· 交互式文件选择：运行后列出当前目录所有 .mesh 文件，支持序号或文件名选择。
· 终端友好输出：解析过程中打印关键数值，成功后在终端显示模型摘要。

---

💻 系统要求

· Python 3.6+（推荐 3.8 以上）
· LZ4 库（系统级，用于解压压缩网格数据）
· 操作系统：Termux（Android）、Linux、macOS、Windows（需安装 LZ4 DLL，但本脚本专为 Termux 优化）

---

🔧 安装步骤

1. 在 Termux（Android）中安装

```bash
pkg update && pkg upgrade -y
pkg install python lz4 -y
```

2. 在其他 Linux 系统中安装

```bash
sudo apt update
sudo apt install python3 python3-pip lz4  # Debian/Ubuntu
# 或使用对应包管理器安装 lz4 库
```

3. 下载脚本

将文末提供的完整脚本代码保存为 mesh2obj_fixed.py，并放置在你的 .mesh 文件所在目录（例如 /storage/emulated/0/.1amxg/）。

---

🚀 使用方法

基本流程

1. 进入文件目录
   ```bash
   cd /storage/emulated/0/.1amxg
   ```
2. 运行脚本
   ```bash
   python mesh2obj_fixed.py
   ```
3. 选择文件
      脚本会列出当前目录下所有 .mesh 文件，例如：
   ```
   1. Airplane1.mesh
   2. CharKidAnimGroundState_StripGeo.mesh
   ```
   输入序号（如 1）或直接输入文件名（可省略 .mesh 后缀）。
4. 等待解析完成
      脚本将自动检测格式、解压（如需）、解析数据，并导出 OBJ 文件。成功后会显示：
   ```
   ✅ OBJ 文件导出成功：/storage/emulated/0/.1amxg/Airplane1_no_strip.obj
   📄 详细信息已保存至：/storage/emulated/0/.1amxg/Airplane1_no_strip_info.txt
   
   📋 模型详细信息：
     - 顶点数: 469
     - 面数 (三角形): 392
     - UV 数: 469
     - 索引总数: 1176
   ========================================
   ```
5. 查看结果
   · .obj 文件可用 Blender、MeshLab 等软件打开。
   · .txt 文件包含模型统计信息，方便快速了解模型复杂度。

---

📄 输出文件说明

1. 模型文件（.obj）

标准 Wavefront OBJ 格式，包含：

· v x y z：顶点坐标
· vt u v：UV 坐标
· f v1/vt1 v2/vt2 v3/vt3：三角面（索引从 1 开始，顶点与 UV 对应）

2. 信息文件（_info.txt）

示例内容：

```
=== 模型信息 ===
源文件: Airplane1.mesh
顶点数 (shared_vertex_count): 469
总顶点数 (用于索引): 469
面数 (三角形): 392
UV 数: 469
点计数 (point_count): 1176

注：以上信息基于脚本解析，可能与实际略有差异。
```

---

⚠️ 注意事项

· 文件兼容性：本脚本基于特定版本的 .mesh 文件结构开发，游戏更新后可能失效。若解析失败，请检查文件头部信息并调整偏移量。
· LZ4 库路径：脚本中默认 LZ4 库为 liblz4.so（Termux 标准路径）。若在其他系统使用，请修改 LZ4_LIB 变量为正确的库名（如 liblz4.so.1）。
· 仅限静态网格：文件名包含 Anim、StripGeo 等字样的文件通常为动画数据，无法提取静态模型。请寻找其他 .mesh 文件。
· 权限问题：在 Android 上运行前需执行 termux-setup-storage 授权访问存储。
· 内存占用：较大的 .mesh 文件可能占用较多内存，请确保设备有足够空间。

---

✅ 优点

· 完全离线：无需网络，保护隐私。
· 交互友好：文件列表选择，无需手动输入路径。
· 智能容错：自动处理带/不带文件名头的文件，提高成功率。
· 附带信息：自动生成模型统计信息，便于文档记录。
· 跨平台：基于 Python，可在多种操作系统运行（轻微修改 LZ4 库路径）。

---

❌ 缺点

· 格式依赖：硬编码的偏移量（如 0x44, 0x4e 等）针对特定版本，更新后需重新逆向。
· 仅支持网格：无法提取动画、材质、纹理等数据。
· 缺乏纹理：OBJ 文件仅包含几何和 UV，需手动指定贴图。
· 性能限制：Python 解析大文件可能较慢（但通常 .mesh 文件不大）。

---

❓ 常见问题

Q1: 解析失败，提示“顶点计数异常”怎么办？

A: 可能原因：

· 文件不是静态网格（如动画文件）。
· 文件版本与脚本偏移量不匹配。请提供文件头部信息，我们可尝试调整偏移。

Q2: LZ4 库加载失败？

A: 请确认已安装 LZ4 库：

· Termux：pkg install lz4
· Linux：sudo apt install lz4（或对应包名）
· 若库名不同，修改脚本中 LZ4_LIB 变量。

Q3: 生成的 OBJ 无法导入 Blender？

A: 请确保 Blender 支持 OBJ 格式（通常都支持）。若出现错误，可用文本编辑器打开 OBJ 文件，检查顶点和面格式是否正确。

Q4: 如何批量处理多个文件？

A: 当前脚本为交互式，一次只能处理一个文件。如需批量，可自行修改脚本循环遍历 get_mesh_files() 列表。

---

🤝 贡献与支持

本工具基于社区逆向成果，欢迎反馈问题或提交改进。若你成功解析了更多类型的文件，或有新的偏移量数据，请分享给更多人。

感谢：longbyte1, cobrakyle 及 ZenHAX 社区的逆向工程贡献。

---

📜 完整脚本代码

（此处粘贴最终版 mesh2obj_fixed.py 代码，由于篇幅原因，请参考之前的回复或从附件获取。）

---

文档版本：1.0 (2025-02-23)

import ctypes
import struct
import io
import os
import glob
import binascii

LZ4_LIB = 'liblz4.so'  # Termux 中 LZ4 库的名称（无需修改）

def hex_dump(data, length=64):
    """打印十六进制和 ASCII（仅调试用）"""
    hex_str = binascii.hexlify(data[:length]).decode('ascii')
    print("Hex:")
    for i in range(0, len(hex_str), 32):
        print(hex_str[i:i+32])
    print("ASCII:")
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[:length])
    print(ascii_str)

def get_mesh_files():
    return glob.glob("*.mesh")

def select_file_interactive():
    files = get_mesh_files()
    if not files:
        print("当前目录下没有 .mesh 文件。")
        return None
    print("找到以下 .mesh 文件：")
    for i, f in enumerate(files):
        print(f"{i+1}. {f}")
    while True:
        choice = input("请输入序号选择文件，或直接输入文件名（可省略.mesh后缀）: ").strip()
        if not choice:
            continue
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return files[idx]
            else:
                print("序号超出范围，请重新输入。")
                continue
        if not choice.endswith('.mesh'):
            choice += '.mesh'
        if os.path.exists(choice):
            return choice
        else:
            print(f"文件 {choice} 不存在，请重新输入。")

def parse_mesh_data_from_buffer(buffer, base_offset=0):
    """
    从 buffer 的 base_offset 处开始解析网格数据。
    所有偏移量相对于 buffer 的起始。
    """
    if len(buffer) < base_offset + 0x100:
        print("数据不足")
        return None

    # 读取关键偏移
    num_lods = struct.unpack('i', buffer[base_offset+0x44:base_offset+0x48])[0]
    compressed_size = struct.unpack('i', buffer[base_offset+0x4e:base_offset+0x52])[0]
    uncompressed_size = struct.unpack('i', buffer[base_offset+0x52:base_offset+0x56])[0]

    print(f"num_lods = {num_lods}")
    print(f"compressed_size = {compressed_size}")
    print(f"uncompressed_size = {uncompressed_size}")

    # 尝试解压
    if compressed_size > 0 and uncompressed_size > 0 and base_offset+0x56+compressed_size <= len(buffer):
        print("尝试 LZ4 解压...")
        src = buffer[base_offset+0x56:base_offset+0x56+compressed_size]
        try:
            lz4 = ctypes.CDLL(LZ4_LIB)
            dest = ctypes.create_string_buffer(uncompressed_size)
            ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
            if ret > 0:
                print("LZ4 解压成功")
                # 解压后的数据作为新 buffer，重新解析
                return parse_mesh_data_from_buffer(dest.raw, 0)
            else:
                print(f"LZ4 解压失败 (返回值 {ret})，使用原始数据")
        except Exception as e:
            print(f"解压异常: {e}，使用原始数据")
    else:
        print("压缩数据异常，直接使用原始数据")

    # 直接解析原始 buffer
    buf = io.BytesIO(buffer)
    try:
        buf.seek(base_offset + 0x74)
        shared_vertex_count = struct.unpack('i', buf.read(4))[0]
        buf.seek(base_offset + 0x78)
        total_vertex_count = struct.unpack('i', buf.read(4))[0]
        buf.seek(base_offset + 0x80)
        point_count = struct.unpack('i', buf.read(4))[0]
        buf.seek(base_offset + 0x74)
        uv_count = struct.unpack('i', buf.read(4))[0]

        print('shared_vertex_count =', shared_vertex_count)
        print('total_vertex_count =', total_vertex_count)
        print('point_count =', point_count)
        print('uv_count =', uv_count)

        if shared_vertex_count <= 0 or total_vertex_count <= 0 or shared_vertex_count > 1000000:
            raise ValueError("顶点计数异常，可能偏移量错误")

        # 顶点缓冲
        vertex_buffer = []
        vertex_buffer_start = base_offset + 0xb3
        buf.seek(vertex_buffer_start)
        for i in range(shared_vertex_count):
            x, y, z = struct.unpack('<fff4x', buf.read(16))
            vertex_buffer.append((x, y, z))

        # UV 缓冲
        uv_buffer = []
        uv_header_size = uv_count * 4 - 4
        buf.read(uv_header_size)  # 跳过头部
        for i in range(uv_count):
            u, v = struct.unpack('<4xee8x', buf.read(16))
            uv_buffer.append((u, v))

        # 索引缓冲
        index_buffer = []
        face_count = total_vertex_count // 3
        buf.read(4)  # 跳过填充
        for i in range(face_count):
            v1, v2, v3 = struct.unpack('<HHH', buf.read(6))
            index_buffer.append((v1, v2, v3))

        return vertex_buffer, uv_buffer, index_buffer
    except Exception as e:
        print(f"解析内部数据时出错: {e}")
        return None
    finally:
        buf.close()

def try_without_stripping(file_data, mesh_path):
    print("\n--- 尝试不剥离头部直接解析 ---")
    result = parse_mesh_data_from_buffer(file_data, base_offset=0)
    if result:
        vertex_buffer, uv_buffer, index_buffer = result
        export_obj_and_info(vertex_buffer, uv_buffer, index_buffer, mesh_path, suffix="_no_strip")
        return True
    return False

def try_with_stripping(file_data, mesh_path):
    print("\n--- 尝试剥离文件名头 ---")
    if len(file_data) < 4:
        return False
    possible_len = struct.unpack('<I', file_data[0:4])[0]
    if possible_len < 4 or possible_len > 200:
        print("前4字节不像文件名长度，跳过剥离。")
        return False
    name_str = file_data[4:4+possible_len].split(b'\x00')[0].decode('ascii', errors='ignore')
    if not name_str or len(name_str) < 1:
        print("文件名不可读，跳过剥离。")
        return False
    print(f"可能的文件名: {name_str} (长度 {possible_len})")
    header_size = 4 + possible_len
    aligned_size = (header_size + 3) & ~3  # 4字节对齐
    print(f"对齐后头部大小: {aligned_size}")
    if aligned_size >= len(file_data):
        print("头部超出文件，跳过剥离。")
        return False
    stripped_data = file_data[aligned_size:]
    result = parse_mesh_data_from_buffer(stripped_data, base_offset=0)
    if result:
        vertex_buffer, uv_buffer, index_buffer = result
        export_obj_and_info(vertex_buffer, uv_buffer, index_buffer, mesh_path, suffix="_stripped")
        return True
    return False

def export_obj_and_info(vertex_buffer, uv_buffer, index_buffer, mesh_path, suffix=""):
    """导出 OBJ 文件，并生成同名的 TXT 信息文件"""
    base_name = os.path.splitext(mesh_path)[0]
    obj_filename = base_name + suffix + '.obj'
    info_filename = base_name + suffix + '_info.txt'

    # 导出 OBJ
    try:
        with open(obj_filename, 'w') as out:
            for v in vertex_buffer:
                out.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
            for uv in uv_buffer:
                out.write(f'vt {uv[0]:.6f} {uv[1]:.6f}\n')
            for face in index_buffer:
                out.write(f'f {face[0]+1}/{face[0]+1} {face[1]+1}/{face[1]+1} {face[2]+1}/{face[2]+1}\n')
        print(f"\n✅ OBJ 文件导出成功：{obj_filename}")
    except Exception as e:
        print(f"写入 OBJ 文件失败: {e}")
        return

    # 导出信息 TXT
    try:
        with open(info_filename, 'w') as info:
            info.write("=== 模型信息 ===\n")
            info.write(f"源文件: {os.path.basename(mesh_path)}\n")
            info.write(f"顶点数 (shared_vertex_count): {len(vertex_buffer)}\n")
            info.write(f"总顶点数 (用于索引): {len(vertex_buffer)}\n")  # 注意：这里用 shared_vertex_count
            info.write(f"面数 (三角形): {len(index_buffer)}\n")
            info.write(f"UV 数: {len(uv_buffer)}\n")
            info.write(f"点计数 (point_count): {len(index_buffer)*3}\n")  # 估算
            info.write("\n注：以上信息基于脚本解析，可能与实际略有差异。\n")
        print(f"📄 详细信息已保存至：{info_filename}")
    except Exception as e:
        print(f"写入信息文件失败: {e}")

    # 在终端也打印一份详细信息
    print("\n📋 模型详细信息：")
    print(f"  - 顶点数: {len(vertex_buffer)}")
    print(f"  - 面数 (三角形): {len(index_buffer)}")
    print(f"  - UV 数: {len(uv_buffer)}")
    print(f"  - 索引总数: {len(index_buffer)*3}")
    print("="*40)

def main():
    mesh_file = select_file_interactive()
    if not mesh_file:
        return

    mesh_path = os.path.abspath(mesh_file)
    print(f"\n正在处理: {mesh_path}")

    with open(mesh_path, 'rb') as f:
        file_data = f.read()

    print("\n--- 文件头部信息 (前64字节) ---")
    hex_dump(file_data[:64], 64)

    # 先尝试不剥离解析
    if try_without_stripping(file_data, mesh_path):
        print("\n✨ 不剥离头部解析成功！")
        return

    # 如果不成功，尝试剥离文件名头
    if try_with_stripping(file_data, mesh_path):
        print("\n✨ 剥离文件名头后解析成功！")
        return

    print("\n❌ 所有解析尝试均失败，文件可能不是标准格式或偏移量需要调整。")

if __name__ == '__main__':
    main()
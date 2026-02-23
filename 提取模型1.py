#!/usr/bin/env python3
"""
《光遇》.mesh 批量转 OBJ (最终版)
功能：
  - 启发式解析普通 .mesh 文件
  - 针对 compressPositions/compressUvs 压缩模型专用解析
  - 自动根据 MeshDefs.lua 或文件名关键词选择解析器
  - 启发式失败后自动尝试压缩解析器
  - 支持交互式多选和自定义输出目录
  - 命令行模式：python script.py 文件1.mesh 文件2.mesh -o 输出目录
依赖：lz4 (Termux: pkg install lz4)
"""

import ctypes
import struct
import io
import os
import sys
import glob
import argparse
import re

LZ4_LIB = 'liblz4.so'
DEBUG = False  # 调试信息，成功后可改为 False

def log_debug(*args):
    if DEBUG:
        print("[DEBUG]", *args)

def load_lz4():
    try:
        lz4 = ctypes.CDLL(LZ4_LIB)
        lz4.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lz4.LZ4_decompress_safe.restype = ctypes.c_int
        return lz4
    except OSError as e:
        print(f"错误: 无法加载 LZ4 库 '{LZ4_LIB}'")
        print("请运行: pkg install lz4")
        sys.exit(1)

# ----------------------------------------------------------------------
# 启发式解析（适用于普通 .mesh 文件）
# ----------------------------------------------------------------------
def parse_mesh_heuristic(f, lz4):
    candidate_sets = [
        (0x4e, 0x52, 0x44, 0x56),
        (0x4a, 0x4e, 0x40, 0x52),
        (0x52, 0x56, 0x48, 0x5a),
    ]

    for cs_off, us_off, lod_off, d_off in candidate_sets:
        try:
            f.seek(cs_off)
            compressed_size = struct.unpack('<i', f.read(4))[0]
            f.seek(us_off)
            uncompressed_size = struct.unpack('<i', f.read(4))[0]
            f.seek(lod_off)
            num_lods = struct.unpack('<i', f.read(4))[0]

            if not (0 < compressed_size < 10*1024*1024 and 0 < uncompressed_size < 50*1024*1024):
                continue

            log_debug(f"候选偏移: cs=0x{cs_off:x}, us=0x{us_off:x}, lod=0x{lod_off:x}")
            log_debug(f"  compressed={compressed_size}, uncompressed={uncompressed_size}, lods={num_lods}")

            f.seek(d_off)
            src = f.read(compressed_size)
            if len(src) != compressed_size:
                continue

            dest = ctypes.create_string_buffer(uncompressed_size)
            ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
            if ret <= 0:
                continue

            buf = io.BytesIO(dest.raw)

            internal_candidates = [0x74, 0x70, 0x78, 0x80]
            for v_off in internal_candidates:
                buf.seek(v_off)
                try:
                    shared = struct.unpack('<i', buf.read(4))[0]
                    buf.seek(v_off+4)
                    total = struct.unpack('<i', buf.read(4))[0]
                    if not (0 <= shared < 100000 and 0 <= total < 300000 and total % 3 == 0):
                        continue
                    log_debug(f"内部偏移 v_off=0x{v_off:x}: shared={shared}, total={total}")

                    buf.seek(v_off)
                    uv_count = struct.unpack('<i', buf.read(4))[0]
                    if uv_count > 100000:
                        continue

                    vertex_start = 0xb3
                    buf.seek(vertex_start)
                    vertex_buffer = []
                    for i in range(shared):
                        vdata = buf.read(16)
                        if len(vdata) < 16:
                            break
                        x, y, z = struct.unpack('<fff4x', vdata)
                        vertex_buffer.append((x, y, z))
                    if len(vertex_buffer) != shared:
                        continue

                    uv_buffer = []
                    uv_header_size = uv_count * 4 - 4
                    if uv_header_size > 0:
                        buf.read(uv_header_size)
                    for i in range(uv_count):
                        uvdata = buf.read(16)
                        if len(uvdata) < 16:
                            break
                        u, v = struct.unpack('<4xee8x', uvdata)
                        uv_buffer.append((u, v))
                    if len(uv_buffer) != uv_count:
                        continue

                    index_buffer = []
                    face_count = total // 3
                    buf.read(4)
                    for i in range(face_count):
                        idxdata = buf.read(6)
                        if len(idxdata) < 6:
                            break
                        v1, v2, v3 = struct.unpack('<HHH', idxdata)
                        index_buffer.append((v1, v2, v3))
                    if len(index_buffer) != face_count:
                        continue

                    max_idx = max(max(face) for face in index_buffer)
                    if max_idx < len(vertex_buffer):
                        return vertex_buffer, uv_buffer, index_buffer
                except:
                    continue
        except:
            continue

    raise ValueError("所有候选偏移尝试均失败，文件可能为特殊格式")

# ----------------------------------------------------------------------
# 压缩模型解析器（针对 compressPositions/compressUvs）
# ----------------------------------------------------------------------
def parse_compressed_mesh(f, lz4):
    # 使用第二组偏移 (0x52, 0x56, 0x5a)
    f.seek(0x52)
    compressed_size = struct.unpack('<i', f.read(4))[0]
    f.seek(0x56)
    uncompressed_size = struct.unpack('<i', f.read(4))[0]
    f.seek(0x5a)
    src = f.read(compressed_size)
    if len(src) != compressed_size:
        raise IOError("压缩数据读取不完整")

    dest = ctypes.create_string_buffer(uncompressed_size)
    ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
    if ret <= 0:
        raise IOError("LZ4解压失败")
    decompressed = dest.raw
    log_debug(f"解压后数据大小: {len(decompressed)}")

    # 读取计数 (固定偏移 0x74 和 0x78)
    shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
    total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
    log_debug(f"shared={shared}, total={total}")

    # 量化参数 (0x60-0x74)
    min_x = struct.unpack('<f', decompressed[0x60:0x64])[0]
    min_y = struct.unpack('<f', decompressed[0x64:0x68])[0]
    min_z = struct.unpack('<f', decompressed[0x68:0x6c])[0]
    range_x = struct.unpack('<f', decompressed[0x6c:0x70])[0]
    range_y = struct.unpack('<f', decompressed[0x70:0x74])[0]
    range_z = range_y  # 根据观察，range_z 未单独存储
    log_debug(f"量化参数: min=({min_x:.3f},{min_y:.3f},{min_z:.3f}) range=({range_x:.3f},{range_y:.3f})")

    # 顶点数据 (从 0x7c 开始)
    vert_start = 0x7c
    vertex_buffer = []
    for i in range(shared):
        off = vert_start + i*6
        if off+6 > len(decompressed):
            raise ValueError("顶点数据不足")
        x16, y16, z16 = struct.unpack('<HHH', decompressed[off:off+6])
        x = min_x + (x16 / 65535.0) * range_x
        y = min_y + (y16 / 65535.0) * range_y
        z = min_z + (z16 / 65535.0) * range_z
        vertex_buffer.append((x, y, z))

    # UV 数据 (紧跟在顶点之后，每个 UV 4 字节，数量 = shared)
    uv_start = vert_start + shared * 6
    uv_buffer = []
    for i in range(shared):
        off = uv_start + i*4
        if off+4 > len(decompressed):
            # 如果 UV 数据不足，可能是文件没有 UV，创建默认 UV
            log_debug("UV数据不足，使用默认UV (0,0)")
            uv_buffer.append((0.0, 0.0))
        else:
            u16, v16 = struct.unpack('<HH', decompressed[off:off+4])
            u = u16 / 65535.0
            v = v16 / 65535.0
            uv_buffer.append((u, v))

    # 搜索索引起始位置 (在 UV 之后)
    search_start = uv_start + shared * 4
    face_count = total // 3
    idx_start = None
    idx_type = None

    # 尝试 16 位索引
    for start in range(search_start, len(decompressed)-5):
        if start+6 > len(decompressed):
            break
        idx = struct.unpack('<HHH', decompressed[start:start+6])
        if max(idx) < shared:
            # 验证连续多个面
            count = 0
            for j in range(start, len(decompressed)-5, 6):
                if max(struct.unpack('<HHH', decompressed[j:j+6])) >= shared:
                    break
                count += 1
            if count >= face_count:
                idx_start = start
                idx_type = 16
                break

    if idx_start is None:
        # 尝试 32 位索引
        for start in range(search_start, len(decompressed)-11):
            if start+12 > len(decompressed):
                break
            idx = struct.unpack('<III', decompressed[start:start+12])
            if max(idx) < shared:
                count = 0
                for j in range(start, len(decompressed)-11, 12):
                    if max(struct.unpack('<III', decompressed[j:j+12])) >= shared:
                        break
                    count += 1
                if count >= face_count:
                    idx_start = start
                    idx_type = 32
                    break

    if idx_start is None:
        raise ValueError("未找到有效的索引区域")

    log_debug(f"索引区域起始: 0x{idx_start:04x}, {idx_type}位")

    # 读取索引
    index_buffer = []
    if idx_type == 16:
        for i in range(face_count):
            off = idx_start + i*6
            if off+6 > len(decompressed):
                break
            v1, v2, v3 = struct.unpack('<HHH', decompressed[off:off+6])
            index_buffer.append((v1, v2, v3))
    else:
        for i in range(face_count):
            off = idx_start + i*12
            if off+12 > len(decompressed):
                break
            v1, v2, v3 = struct.unpack('<III', decompressed[off:off+12])
            index_buffer.append((v1, v2, v3))

    if len(index_buffer) != face_count:
        raise ValueError("索引数据不完整")

    # 验证索引最大值
    max_idx = max(max(f) for f in index_buffer)
    if max_idx >= shared:
        log_debug(f"警告: 索引最大值 {max_idx} 超出顶点数 {shared}")

    return vertex_buffer, uv_buffer, index_buffer

# ----------------------------------------------------------------------
# 导出 OBJ
# ----------------------------------------------------------------------
def export_obj(vertex_buffer, uv_buffer, index_buffer, obj_path):
    with open(obj_path, 'w') as out:
        for v in vertex_buffer:
            out.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        for uv in uv_buffer:
            out.write(f'vt {uv[0]:.6f} {uv[1]:.6f}\n')
        for face in index_buffer:
            out.write(f'f {face[0]+1}/{face[0]+1} {face[1]+1}/{face[1]+1} {face[2]+1}/{face[2]+1}\n')
    print(f"导出成功: {obj_path}")

# ----------------------------------------------------------------------
# 解析 MeshDefs.lua
# ----------------------------------------------------------------------
def parse_mesh_defs(lua_file):
    mesh_params = {}
    try:
        with open(lua_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return mesh_params

    pattern = r'resource\s+"Mesh"\s+"([^"]+)"\s*\{([^}]+)\}'
    for match in re.finditer(pattern, content):
        name = match.group(1)
        block = match.group(2)
        params = {}
        for line in block.split(','):
            if '=' in line:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip()
                if v.lower() == 'true':
                    v = True
                elif v.lower() == 'false':
                    v = False
                elif v.startswith('"') and v.endswith('"'):
                    v = v.strip('"')
                else:
                    try:
                        v = int(v)
                    except:
                        pass
                params[k] = v
        mesh_params[name] = params
    return mesh_params

# ----------------------------------------------------------------------
# 交互式选择文件
# ----------------------------------------------------------------------
def interactive_select_files(all_files):
    while True:
        print("\n找到以下 .mesh 文件：")
        for i, f in enumerate(all_files):
            print(f"{i+1}. {f}")
        print("\n请输入要转换的文件序号（支持格式：1 2 3、1-5、1,2,3 或 all）")
        print("或输入 q 退出程序。")
        choice = input("选择: ").strip().lower()

        if choice == 'q':
            return None
        if choice == 'all':
            return all_files

        selected = []
        parts = re.split(r'[,\s]+', choice)
        for part in parts:
            if not part:
                continue
            if '-' in part:
                try:
                    start, end = part.split('-')
                    s, e = int(start), int(end)
                    if 1 <= s <= len(all_files) and 1 <= e <= len(all_files) and s <= e:
                        selected.extend(range(s-1, e))
                    else:
                        print(f"  范围 {part} 超出范围，忽略")
                except:
                    print(f"  无法解析范围 '{part}'，忽略")
            else:
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(all_files):
                        selected.append(idx)
                    else:
                        print(f"  序号 {part} 超出范围，忽略")
                except ValueError:
                    print(f"  无法解析序号 '{part}'，忽略")

        if not selected:
            print("未选择任何有效文件，请重新输入。")
            continue

        selected = sorted(set(selected))
        file_list = [all_files[i] for i in selected]
        print(f"已选择 {len(file_list)} 个文件。")
        return file_list

# ----------------------------------------------------------------------
# 主程序
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='批量转换 .mesh 文件为 OBJ')
    parser.add_argument('files', nargs='*', help='要转换的 .mesh 文件（可多个）')
    parser.add_argument('-o', '--output', default='', help='输出文件夹（默认当前目录）')
    args = parser.parse_args()

    lz4 = load_lz4()

    # 加载 MeshDefs.lua
    mesh_params = {}
    for lua_path in ['MeshDefs.lua', os.path.join(os.path.dirname(__file__), 'MeshDefs.lua')]:
        if os.path.exists(lua_path):
            mesh_params = parse_mesh_defs(lua_path)
            log_debug(f"已加载 MeshDefs.lua，共 {len(mesh_params)} 个条目")
            break

    # 确定输入文件列表
    if args.files:
        mesh_files = [f for f in args.files if os.path.isfile(f)]
        if not mesh_files:
            print("没有有效的输入文件。")
            sys.exit(1)
        out_dir = args.output if args.output else '.'
    else:
        all_files = glob.glob("*.mesh")
        if not all_files:
            print("当前目录下没有 .mesh 文件。")
            return
        mesh_files = interactive_select_files(all_files)
        if mesh_files is None:
            return
        out_dir = input("请输入输出目录（默认: .）: ").strip()
        if not out_dir:
            out_dir = '.'

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    success = 0
    failed = 0

    # 特殊关键词列表
    special_keywords = ['StripAnim', 'CompOcc', 'ZipPos', 'ZipUvs', 'StripNorm', 'StripUv13', 'CopyFrameDelay']

    for mesh_file in mesh_files:
        print(f"\n处理: {mesh_file}")
        base = os.path.basename(mesh_file)
        name = os.path.splitext(base)[0]
        params = mesh_params.get(name, {})
        # 判断是否为压缩模型（根据参数或文件名关键词）
        is_compressed = params.get('compressPositions') or params.get('compressUvs')
        if not is_compressed and any(kw in name for kw in special_keywords):
            is_compressed = True
            log_debug("文件名包含特殊关键词，标记为压缩模型")

        try:
            with open(mesh_file, 'rb') as f:
                if is_compressed:
                    vb, uvb, ib = parse_compressed_mesh(f, lz4)
                else:
                    try:
                        vb, uvb, ib = parse_mesh_heuristic(f, lz4)
                    except Exception as e:
                        log_debug("启发式解析失败，尝试压缩解析器作为后备")
                        f.seek(0)
                        vb, uvb, ib = parse_compressed_mesh(f, lz4)
            obj_path = os.path.join(out_dir, name + '.obj')
            export_obj(vb, uvb, ib, obj_path)
            success += 1
        except Exception as e:
            print(f"解析失败: {e}")
            if DEBUG:
                import traceback
                traceback.print_exc()
            failed += 1

    print(f"\n批量转换完成: 成功 {success} 个, 失败 {failed} 个")

if __name__ == '__main__':
    main()
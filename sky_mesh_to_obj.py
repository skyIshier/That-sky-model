#!/usr/bin/env python3
"""
《光遇》.mesh 批量转 OBJ (启发式解析 + 多选 + 自定义输出)
功能：
  - 自动尝试多种偏移组合，兼容更多 .mesh 文件
  - 支持交互式多选（序号/范围/逗号/空格/all）
  - 支持自定义输出目录
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
DEBUG = True  # 开启调试信息，成功后可关闭

def log_debug(*args):
    """调试输出函数，支持多个参数"""
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

def parse_mesh_heuristic(f, lz4):
    """
    启发式解析 .mesh 文件，尝试多组偏移组合
    返回 (顶点列表, UV列表, 面列表) 或抛出异常
    """
    # 候选偏移组 (compressed_size_offset, uncompressed_size_offset, num_lods_offset, data_offset)
    candidate_sets = [
        (0x4e, 0x52, 0x44, 0x56),   # 原版偏移
        (0x4a, 0x4e, 0x40, 0x52),   # 另一种可能
        (0x52, 0x56, 0x48, 0x5a),   # 稍后偏移
    ]

    for cs_off, us_off, lod_off, d_off in candidate_sets:
        try:
            f.seek(cs_off)
            compressed_size = struct.unpack('<i', f.read(4))[0]
            f.seek(us_off)
            uncompressed_size = struct.unpack('<i', f.read(4))[0]
            f.seek(lod_off)
            num_lods = struct.unpack('<i', f.read(4))[0]

            # 合理性检查
            if not (0 < compressed_size < 10*1024*1024 and 0 < uncompressed_size < 50*1024*1024):
                continue

            log_debug(f"候选偏移成功: cs=0x{cs_off:x}, us=0x{us_off:x}, lod=0x{lod_off:x}")
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

            # 尝试内部顶点计数的可能偏移
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

                    # 尝试读取 UV 计数（可能与顶点计数同位置，这里沿用原逻辑）
                    buf.seek(v_off)
                    uv_count = struct.unpack('<i', buf.read(4))[0]
                    if uv_count > 100000:
                        continue

                    # 顶点缓冲区起始偏移试探（原0xb3）
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

                    # UV 缓冲区
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

                    # 索引缓冲区
                    index_buffer = []
                    face_count = total // 3
                    buf.read(4)  # padding
                    for i in range(face_count):
                        idxdata = buf.read(6)
                        if len(idxdata) < 6:
                            break
                        v1, v2, v3 = struct.unpack('<HHH', idxdata)
                        index_buffer.append((v1, v2, v3))
                    if len(index_buffer) != face_count:
                        continue

                    # 验证索引不越界
                    max_idx = max(max(face) for face in index_buffer)
                    if max_idx < len(vertex_buffer):
                        return vertex_buffer, uv_buffer, index_buffer
                except:
                    continue
        except:
            continue

    raise ValueError("所有候选偏移尝试均失败，文件可能为特殊格式 (如 ZipPos/StripNorm)")

def export_obj(vertex_buffer, uv_buffer, index_buffer, obj_path):
    with open(obj_path, 'w') as out:
        for v in vertex_buffer:
            out.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        for uv in uv_buffer:
            out.write(f'vt {uv[0]:.6f} {uv[1]:.6f}\n')
        for face in index_buffer:
            out.write(f'f {face[0]+1}/{face[0]+1} {face[1]+1}/{face[1]+1} {face[2]+1}/{face[2]+1}\n')
    print(f"导出成功: {obj_path}")

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

def main():
    parser = argparse.ArgumentParser(description='批量转换 .mesh 文件为 OBJ')
    parser.add_argument('files', nargs='*', help='要转换的 .mesh 文件（可多个）')
    parser.add_argument('-o', '--output', default='', help='输出文件夹（默认当前目录）')
    args = parser.parse_args()

    lz4 = load_lz4()

    if args.files:
        # 命令行模式
        mesh_files = [f for f in args.files if os.path.isfile(f)]
        if not mesh_files:
            print("没有有效的输入文件。")
            sys.exit(1)
        out_dir = args.output if args.output else '.'
    else:
        # 交互模式
        all_files = glob.glob("*.mesh")
        if not all_files:
            print("当前目录下没有 .mesh 文件。")
            return
        mesh_files = interactive_select_files(all_files)
        if mesh_files is None:
            print("已退出。")
            return
        out_dir = input("请输入输出目录（默认: .）: ").strip()
        if not out_dir:
            out_dir = '.'

    # 创建输出目录
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
        print(f"创建输出目录: {out_dir}")

    success = 0
    failed = 0
    for mesh_file in mesh_files:
        print(f"\n处理: {mesh_file}")
        try:
            with open(mesh_file, 'rb') as f:
                vb, uvb, ib = parse_mesh_heuristic(f, lz4)
            base = os.path.basename(mesh_file)
            name = os.path.splitext(base)[0]
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
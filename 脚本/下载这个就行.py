#!/usr/bin/env python3
"""
《光遇》.mesh 批量转 OBJ (终极整合版 + 坐标归一化 + 详细进度统计)
功能：
  - 优先尝试 fmt_mesh 解析器（根据文件头判断）
  - 若失败，则根据文件名是否包含 ZipPos 使用对应的压缩解析分支（含坐标归一化）
  - 否则回退到启发式解析器
  - 支持交互式多选和自定义输出目录
  - 批量转换时显示当前进度、每个文件耗时
  - 最终输出成功/失败文件列表，包含顶点数、面数、解析方式等
  - 自动将汇总结果保存为文本文件（位于输出目录）
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
import time  # 新增：用于计时

LZ4_LIB = 'liblz4.so'
DEBUG = False  # 调试信息，成功后可改为 False    True

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
# 辅助函数：半精度浮点数转 float32
# ----------------------------------------------------------------------
def half_to_float(h):
    s = int((h >> 15) & 0x0001)
    e = int((h >> 10) & 0x001f)
    f = int(h & 0x03ff)
    if e == 0:
        if f == 0:
            return 0.0 * (1.0 if s == 0 else -1.0)
        else:
            while (f & 0x0400) == 0:
                f <<= 1
                e -= 1
            e += 1
            f &= ~0x0400
    elif e == 31:
        if f == 0:
            return float('inf') * (1.0 if s == 0 else -1.0)
        else:
            return float('nan')
    e = e - 15 + 127
    f = f << 13
    return struct.unpack('>f', struct.pack('>I', (s << 31) | (e << 23) | f))[0]

# ----------------------------------------------------------------------
# fmt_mesh 解析器（根据 Durik256 的 Noesis 插件移植）
# ----------------------------------------------------------------------
def parse_fmt_mesh(f, lz4, is_zip=False):
    """
    使用 fmt_mesh.py 的逻辑解析 .mesh 文件
    is_zip: 是否为 ZipPos 类型（文件名包含 'ZipPos'）
    """
    header = f.read(4)
    if header != b'\x1F\x00\x00\x00':
        f.seek(0)
        raise ValueError("不是 fmt_mesh 格式的文件头")

    data = f.read(18*4 + 2)
    vals = struct.unpack('<18I H', data)
    h = list(vals[17:]) + list(struct.unpack('<3I', f.read(12)))
    compressed_size = h[3]
    uncompressed_size = h[4]

    compressed = f.read(compressed_size)
    if len(compressed) != compressed_size:
        raise IOError("压缩数据读取不完整")
    dest = ctypes.create_string_buffer(uncompressed_size)
    ret = lz4.LZ4_decompress_safe(compressed, dest, compressed_size, uncompressed_size)
    if ret <= 0:
        raise IOError("LZ4解压失败")
    decompressed = dest.raw

    has_bones = (h[1] == 1)
    if has_bones:
        binf_data = f.read(20*4 + 1 + 4)
        if len(binf_data) < 20*4+1+4:
            raise IOError("骨骼信息读取不完整")
        binf = struct.unpack('<20I B I', binf_data)
        num_bones = binf[17]
        for _ in range(num_bones):
            f.read(64)
            f.read(64)
            f.read(4)

    bs = io.BytesIO(decompressed)
    bs.seek(116)
    vnum = struct.unpack('<I', bs.read(4))[0]
    bs.seek(120)
    inum = struct.unpack('<I', bs.read(4))[0]
    bs.seek(128)
    unum = struct.unpack('<I', bs.read(4))[0]

    if is_zip:
        # ZipPos 分支
        bs.seek(179)
        if has_bones:
            bs.seek(vnum * 8, 1)
        ibuf = bs.read(inum * 2)
        if len(ibuf) != inum * 2:
            raise ValueError("索引数据不足")
        index_buffer = []
        face_count = inum // 3
        for i in range(face_count):
            off = i * 6
            v1, v2, v3 = struct.unpack('<HHH', ibuf[off:off+6])
            index_buffer.append((v1, v2, v3))
        bs.seek(len(decompressed) - vnum * 4)
        vbuf_comp = bs.read(vnum * 4)
        if len(vbuf_comp) != vnum * 4:
            raise ValueError("压缩顶点数据不足")
        vertex_buffer = []
        for i in range(vnum):
            off = i * 4
            a, b, c, d = struct.unpack('<BBBB', vbuf_comp[off:off+4])
            # 归一化到 -1..1
            x = (b - 128) / 127.5
            y = (c - 128) / 127.5
            z = (d - 128) / 127.5
            vertex_buffer.append((x, y, z))
        uv_buffer = [(0.0, 0.0)] * vnum
    else:
        # 普通分支
        bs.seek(179)
        vbuf = bs.read(vnum * 16)
        if len(vbuf) != vnum * 16:
            raise ValueError("顶点数据不足")
        vertex_buffer = []
        for i in range(vnum):
            off = i * 16
            x, y, z, w = struct.unpack('<ffff', vbuf[off:off+16])
            vertex_buffer.append((x, y, z))

        bs.seek(vnum * 4, 1)
        uvbuf = bs.read(vnum * 16)
        if len(uvbuf) != vnum * 16:
            raise ValueError("UV 数据不足")
        uv_buffer = []
        for i in range(vnum):
            off = i * 16
            u16, v16 = struct.unpack('<HH', uvbuf[off:off+4])
            u = half_to_float(u16)
            v = half_to_float(v16)
            uv_buffer.append((u, v))

        if has_bones:
            bs.seek(vnum * 8, 1)

        ibuf = bs.read(inum * 2)
        if len(ibuf) != inum * 2:
            raise ValueError("索引数据不足")
        index_buffer = []
        face_count = inum // 3
        for i in range(face_count):
            off = i * 6
            v1, v2, v3 = struct.unpack('<HHH', ibuf[off:off+6])
            index_buffer.append((v1, v2, v3))

    max_idx = max(max(f) for f in index_buffer)
    if max_idx >= len(vertex_buffer):
        log_debug(f"警告: 索引最大值 {max_idx} 超出顶点数 {len(vertex_buffer)}")
    return vertex_buffer, uv_buffer, index_buffer

# ----------------------------------------------------------------------
# 启发式解析器（普通 .mesh 文件）
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
# 压缩解析器（支持常规压缩和 ZipPos 分支）
# ----------------------------------------------------------------------
def parse_compressed_mesh(f, lz4, is_zip=False):
    candidate_sets = [
        (0x52, 0x56, 0x5a, 4),
        (0x4e, 0x51, 0x56, 2),
        (0x4e, 0x52, 0x56, 2),
        (0x4e, 0x50, 0x56, 2),
        (0x4c, 0x50, 0x56, 2),
    ]
    for cs_off, us_off, d_off, size_bytes in candidate_sets:
        try:
            f.seek(cs_off)
            if size_bytes == 4:
                compressed_size = struct.unpack('<i', f.read(4))[0]
            else:
                compressed_size = struct.unpack('<H', f.read(2))[0]
            f.seek(us_off)
            if size_bytes == 4:
                uncompressed_size = struct.unpack('<i', f.read(4))[0]
            else:
                uncompressed_size = struct.unpack('<H', f.read(2))[0]

            if not (0 < compressed_size < 10*1024*1024 and 0 < uncompressed_size < 50*1024*1024):
                continue

            log_debug(f"压缩解析候选: cs=0x{cs_off:x}, us=0x{us_off:x}, data=0x{d_off:x}, size={size_bytes}字节")
            log_debug(f"  compressed={compressed_size}, uncompressed={uncompressed_size}")

            f.seek(d_off)
            src = f.read(compressed_size)
            if len(src) != compressed_size:
                log_debug("  压缩数据读取不完整，跳过")
                continue

            dest = ctypes.create_string_buffer(uncompressed_size)
            ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
            if ret <= 0:
                log_debug("  LZ4解压失败，跳过")
                continue

            decompressed = dest.raw
            log_debug(f"  解压成功，大小: {len(decompressed)}")

            # 读取顶点数和总顶点数（固定偏移 0x74 和 0x78）
            if len(decompressed) < 0x7c:
                raise ValueError("解压后数据太小，无法读取顶点数")
            shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
            total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
            log_debug(f"  shared={shared}, total={total}")

            # ZipPos 分支
            if is_zip:
                log_debug("  检测为 ZipPos 类型，使用 8 位顶点解析")
                # 顶点数据位于文件末尾，每个顶点 4 字节
                vert_data_size = shared * 4
                if len(decompressed) < vert_data_size:
                    raise ValueError("解压后数据不足，无法读取 ZipPos 顶点")
                vert_start = len(decompressed) - vert_data_size
                vertex_buffer = []
                for i in range(shared):
                    off = vert_start + i * 4
                    a, b, c, d = struct.unpack('<BBBB', decompressed[off:off+4])
                    # 归一化到 -1..1
                    x = (b - 128) / 127.5
                    y = (c - 128) / 127.5
                    z = (d - 128) / 127.5
                    vertex_buffer.append((x, y, z))
                # ZipPos 模型通常没有 UV，设为默认 (0,0)
                uv_buffer = [(0.0, 0.0)] * shared
                # 索引区域需要搜索
                face_count = total // 3
                search_start = 0x7c
                idx_start = None
                idx_type = None
                # 尝试 16 位索引
                for start in range(search_start, len(decompressed)-5):
                    if start+6 > len(decompressed):
                        break
                    idx = struct.unpack('<HHH', decompressed[start:start+6])
                    if max(idx) < shared:
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
                log_debug(f"  索引区域起始: 0x{idx_start:04x}, {idx_type}位")
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
                max_idx = max(max(f) for f in index_buffer)
                if max_idx >= shared:
                    log_debug(f"  警告: 索引最大值 {max_idx} 超出顶点数 {shared}")
                return vertex_buffer, uv_buffer, index_buffer

            # 非 ZipPos 分支：原有的压缩解析逻辑
            # 尝试检测新版本（检查0x30~0x40处的整数是否合理）
            if len(decompressed) >= 0x40:
                val0 = struct.unpack('<i', decompressed[0x30:0x34])[0]
                val1 = struct.unpack('<i', decompressed[0x34:0x38])[0]
                val2 = struct.unpack('<i', decompressed[0x38:0x3c])[0]
                val3 = struct.unpack('<i', decompressed[0x3c:0x40])[0]
                log_debug(f"  0x30: {val0}, 0x34: {val1}, 0x38: {val2}, 0x3c: {val3}")

                if 0 < val1 < 100000 and 0 < val2 < 300000 and val2 % 3 == 0:
                    log_debug("  检测为新版本，使用新偏移")
                    shared = val1
                    total = val2
                    uv_count = val3
                    vert_start = 0x60
                    vertex_buffer = []
                    for i in range(shared):
                        off = vert_start + i*6
                        if off+6 > len(decompressed):
                            raise ValueError("顶点数据不足")
                        x16, y16, z16 = struct.unpack('<HHH', decompressed[off:off+6])
                        vertex_buffer.append((x16, y16, z16))
                    uv_start = vert_start + shared*6
                    uv_buffer = []
                    for i in range(shared):
                        off = uv_start + i*4
                        if off+4 > len(decompressed):
                            uv_buffer.append((0.0, 0.0))
                        else:
                            u16, v16 = struct.unpack('<HH', decompressed[off:off+4])
                            uv_buffer.append((u16/65535.0, v16/65535.0))
                    search_start = uv_start + shared*4
                else:
                    log_debug("  检测条件不满足，但仍尝试新版本解析")
                    shared_try = val1 if 0 < val1 < 100000 else 0
                    total_try = val2 if 0 < val2 < 300000 else 0
                    if shared_try > 0 and total_try > 0 and total_try % 3 == 0:
                        shared = shared_try
                        total = total_try
                        uv_count = val3
                        vert_start = 0x60
                        vertex_buffer = []
                        max_possible = (len(decompressed) - 0x60) // 6
                        for i in range(min(shared, max_possible)):
                            off = vert_start + i*6
                            x16, y16, z16 = struct.unpack('<HHH', decompressed[off:off+6])
                            vertex_buffer.append((x16, y16, z16))
                        if len(vertex_buffer) != shared:
                            log_debug(f"  新版本解析顶点数不足，回退到旧版")
                            shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
                            total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
                            uv_count = shared
                            min_x = struct.unpack('<f', decompressed[0x60:0x64])[0]
                            min_y = struct.unpack('<f', decompressed[0x64:0x68])[0]
                            min_z = struct.unpack('<f', decompressed[0x68:0x6c])[0]
                            range_x = struct.unpack('<f', decompressed[0x6c:0x70])[0]
                            range_y = struct.unpack('<f', decompressed[0x70:0x74])[0]
                            range_z = range_y
                            vert_start = 0x7c
                            vertex_buffer = []
                            for i in range(shared):
                                off = vert_start + i*6
                                x16, y16, z16 = struct.unpack('<HHH', decompressed[off:off+6])
                                x = min_x + (x16 / 65535.0) * range_x
                                y = min_y + (y16 / 65535.0) * range_y
                                z = min_z + (z16 / 65535.0) * range_z
                                vertex_buffer.append((x, y, z))
                            uv_start = vert_start + shared*6
                            uv_buffer = []
                            for i in range(shared):
                                off = uv_start + i*4
                                if off+4 > len(decompressed):
                                    uv_buffer.append((0.0, 0.0))
                                else:
                                    u16, v16 = struct.unpack('<HH', decompressed[off:off+4])
                                    u = u16 / 65535.0
                                    v = v16 / 65535.0
                                    uv_buffer.append((u, v))
                            search_start = uv_start + shared*4
                        else:
                            uv_start = vert_start + shared*6
                            uv_buffer = []
                            for i in range(shared):
                                off = uv_start + i*4
                                if off+4 > len(decompressed):
                                    uv_buffer.append((0.0, 0.0))
                                else:
                                    u16, v16 = struct.unpack('<HH', decompressed[off:off+4])
                                    uv_buffer.append((u16/65535.0, v16/65535.0))
                            search_start = uv_start + shared*4
                    else:
                        log_debug("  检测值不合理，直接使用旧版")
                        shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
                        total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
                        uv_count = shared
                        min_x = struct.unpack('<f', decompressed[0x60:0x64])[0]
                        min_y = struct.unpack('<f', decompressed[0x64:0x68])[0]
                        min_z = struct.unpack('<f', decompressed[0x68:0x6c])[0]
                        range_x = struct.unpack('<f', decompressed[0x6c:0x70])[0]
                        range_y = struct.unpack('<f', decompressed[0x70:0x74])[0]
                        range_z = range_y
                        vert_start = 0x7c
                        vertex_buffer = []
                        for i in range(shared):
                            off = vert_start + i*6
                            x16, y16, z16 = struct.unpack('<HHH', decompressed[off:off+6])
                            x = min_x + (x16 / 65535.0) * range_x
                            y = min_y + (y16 / 65535.0) * range_y
                            z = min_z + (z16 / 65535.0) * range_z
                            vertex_buffer.append((x, y, z))
                        uv_start = vert_start + shared*6
                        uv_buffer = []
                        for i in range(shared):
                            off = uv_start + i*4
                            if off+4 > len(decompressed):
                                uv_buffer.append((0.0, 0.0))
                            else:
                                u16, v16 = struct.unpack('<HH', decompressed[off:off+4])
                                u = u16 / 65535.0
                                v = v16 / 65535.0
                                uv_buffer.append((u, v))
                        search_start = uv_start + shared*4
            else:
                # 数据太小，直接用旧版
                shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
                total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
                uv_count = shared
                min_x = struct.unpack('<f', decompressed[0x60:0x64])[0]
                min_y = struct.unpack('<f', decompressed[0x64:0x68])[0]
                min_z = struct.unpack('<f', decompressed[0x68:0x6c])[0]
                range_x = struct.unpack('<f', decompressed[0x6c:0x70])[0]
                range_y = struct.unpack('<f', decompressed[0x70:0x74])[0]
                range_z = range_y
                vert_start = 0x7c
                vertex_buffer = []
                for i in range(shared):
                    off = vert_start + i*6
                    x16, y16, z16 = struct.unpack('<HHH', decompressed[off:off+6])
                    x = min_x + (x16 / 65535.0) * range_x
                    y = min_y + (y16 / 65535.0) * range_y
                    z = min_z + (z16 / 65535.0) * range_z
                    vertex_buffer.append((x, y, z))
                uv_start = vert_start + shared*6
                uv_buffer = []
                for i in range(shared):
                    off = uv_start + i*4
                    if off+4 > len(decompressed):
                        uv_buffer.append((0.0, 0.0))
                    else:
                        u16, v16 = struct.unpack('<HH', decompressed[off:off+4])
                        u = u16 / 65535.0
                        v = v16 / 65535.0
                        uv_buffer.append((u, v))
                search_start = uv_start + shared*4

            log_debug(f"  shared={shared}, total={total}")
            face_count = total // 3

            # 顶点坐标范围检查（仅警告）
            xs = [v[0] for v in vertex_buffer[:100]]
            if xs:
                avg = sum(abs(v) for v in xs) / len(xs)
                if avg > 10000:
                    log_debug("  警告: 顶点坐标平均值过大 (>10000)")

            # 搜索索引区域
            idx_start = None
            idx_type = None
            # 尝试16位索引
            for start in range(search_start, len(decompressed)-5):
                if start+6 > len(decompressed):
                    break
                idx = struct.unpack('<HHH', decompressed[start:start+6])
                if max(idx) < shared:
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
                # 尝试32位索引
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
            log_debug(f"  索引区域起始: 0x{idx_start:04x}, {idx_type}位")

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

            max_idx = max(max(f) for f in index_buffer)
            if max_idx >= shared:
                log_debug(f"  警告: 索引越界 (max={max_idx}, shared={shared})")
                # 尝试重新搜索32位索引
                new_idx_start = None
                search_begin = max(0, idx_start - 100)
                for start in range(search_begin, len(decompressed)-11):
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
                            new_idx_start = start
                            break
                if new_idx_start is not None:
                    log_debug(f"    重新找到32位索引起始: 0x{new_idx_start:04x}")
                    index_buffer = []
                    for i in range(face_count):
                        off = new_idx_start + i*12
                        if off+12 > len(decompressed):
                            break
                        v1, v2, v3 = struct.unpack('<III', decompressed[off:off+12])
                        index_buffer.append((v1, v2, v3))
                    if len(index_buffer) == face_count:
                        max_idx = max(max(f) for f in index_buffer)
                        if max_idx < shared:
                            log_debug("    索引修复成功")
                        else:
                            log_debug("    修复后索引仍然越界")
                    else:
                        log_debug("    修复失败，索引不完整")
                else:
                    log_debug("    未找到替代索引区域")

            return vertex_buffer, uv_buffer, index_buffer

        except Exception as e:
            log_debug(f"  该候选解析失败: {e}")
            continue
    raise ValueError("所有压缩解析候选尝试均失败")

# ----------------------------------------------------------------------
# 导出 OBJ（过滤退化面）
# ----------------------------------------------------------------------
def export_obj(vertex_buffer, uv_buffer, index_buffer, obj_path):
    total_faces = len(index_buffer)
    valid_faces = 0
    with open(obj_path, 'w') as out:
        for v in vertex_buffer:
            out.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        for uv in uv_buffer:
            out.write(f'vt {uv[0]:.6f} {uv[1]:.6f}\n')
        for face in index_buffer:
            if face[0] != face[1] and face[1] != face[2] and face[0] != face[2]:
                out.write(f'f {face[0]+1}/{face[0]+1} {face[1]+1}/{face[1]+1} {face[2]+1}/{face[2]+1}\n')
                valid_faces += 1
    print(f"导出成功: {obj_path} (共 {total_faces} 个面，过滤后保留 {valid_faces} 个有效面)")

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
# 主程序（增强版：显示进度、计时、汇总、保存结果到文件）
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

    total_files = len(mesh_files)
    results = []  # 存储每个文件的处理结果

    # 特殊关键词列表（用于辅助判断）
    special_keywords = ['StripAnim', 'CompOcc', 'ZipPos', 'ZipUvs', 'StripNorm', 'StripUv13', 'CopyFrameDelay']

    for idx, mesh_file in enumerate(mesh_files, start=1):
        print(f"\n处理 [{idx}/{total_files}]: {mesh_file}")
        start_time = time.time()

        base = os.path.basename(mesh_file)
        name = os.path.splitext(base)[0]
        params = mesh_params.get(name, {})

        # 判断是否为 ZipPos 模型
        is_zip = 'ZipPos' in name

        # 记录结果字典
        result = {
            'file': mesh_file,
            'status': 'failed',
            'error': None,
            'vertex_count': 0,
            'face_count': 0,
            'parser': 'unknown',
            'time': 0.0
        }

        try:
            with open(mesh_file, 'rb') as f:
                # 优先尝试 fmt_mesh 解析器
                try:
                    vb, uvb, ib = parse_fmt_mesh(f, lz4, is_zip)
                    result['parser'] = 'fmt_mesh'
                except Exception as e_fmt:
                    log_debug(f"fmt_mesh 解析器失败: {e_fmt}，尝试原有解析器")
                    f.seek(0)
                    # 判断是否为压缩模型（根据参数或文件名关键词）
                    is_compressed = params.get('compressPositions') or params.get('compressUvs')
                    if not is_compressed and any(kw in name for kw in special_keywords):
                        is_compressed = True
                        log_debug("文件名包含特殊关键词，标记为压缩模型")

                    if is_compressed:
                        vb, uvb, ib = parse_compressed_mesh(f, lz4, is_zip)
                        result['parser'] = 'compressed'
                    else:
                        try:
                            vb, uvb, ib = parse_mesh_heuristic(f, lz4)
                            result['parser'] = 'heuristic'
                        except Exception as e_heur:
                            log_debug("启发式解析失败，尝试压缩解析器作为后备")
                            f.seek(0)
                            vb, uvb, ib = parse_compressed_mesh(f, lz4, is_zip)
                            result['parser'] = 'compressed (fallback)'

            # 成功导出
            result['status'] = 'success'
            result['vertex_count'] = len(vb)
            result['face_count'] = len(ib)
            obj_path = os.path.join(out_dir, name + '.obj')
            export_obj(vb, uvb, ib, obj_path)

        except Exception as e:
            result['error'] = str(e)
            if DEBUG:
                import traceback
                traceback.print_exc()

        finally:
            elapsed = time.time() - start_time
            result['time'] = elapsed
            results.append(result)

        # 实时打印当前结果
        if result['status'] == 'success':
            print(f"  ✅ 成功: 顶点 {result['vertex_count']}, 面 {result['face_count']}, 解析器 {result['parser']}, 耗时 {elapsed:.2f}s")
        else:
            print(f"  ❌ 失败: {result['error']}, 耗时 {elapsed:.2f}s")

    # 汇总统计
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = total_files - success_count

    print("\n" + "="*70)
    print("批量转换完成")
    print(f"总文件: {total_files}, 成功: {success_count}, 失败: {failed_count}")

    if success_count > 0:
        print("\n成功文件列表:")
        for r in results:
            if r['status'] == 'success':
                print(f"  {r['file']}")
                print(f"    顶点: {r['vertex_count']}, 面: {r['face_count']}, 解析器: {r['parser']}, 耗时: {r['time']:.2f}s")

    if failed_count > 0:
        print("\n失败文件列表:")
        for r in results:
            if r['status'] == 'failed':
                print(f"  {r['file']}")
                print(f"    错误: {r['error']}, 耗时: {r['time']:.2f}s")

    print("="*70)

    # ========== 新增：将汇总结果保存到文本文件 ==========
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    result_file = os.path.join(out_dir, f"转换结果_{timestamp}.txt")
    with open(result_file, 'w', encoding='utf-8') as rf:
        rf.write("="*70 + "\n")
        rf.write("批量转换完成\n")
        rf.write(f"总文件: {total_files}, 成功: {success_count}, 失败: {failed_count}\n\n")
        if success_count > 0:
            rf.write("成功文件列表:\n")
            for r in results:
                if r['status'] == 'success':
                    rf.write(f"  {r['file']}\n")
                    rf.write(f"    顶点: {r['vertex_count']}, 面: {r['face_count']}, 解析器: {r['parser']}, 耗时: {r['time']:.2f}s\n")
        if failed_count > 0:
            rf.write("\n失败文件列表:\n")
            for r in results:
                if r['status'] == 'failed':
                    rf.write(f"  {r['file']}\n")
                    rf.write(f"    错误: {r['error']}, 耗时: {r['time']:.2f}s\n")
        rf.write("="*70 + "\n")
    print(f"\n结果已保存至: {result_file}")

if __name__ == '__main__':
    main()
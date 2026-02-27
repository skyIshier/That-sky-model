#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
《光遇》.mesh 转 OBJ 通用脚本
- 支持三种模式：
  1. 混合模式（默认）：先尝试内置解析器，失败或质量差时自动回退旧脚本
  2. 旧脚本模式：完全使用你之前的解析逻辑（基于文件名关键词和启发式）
  3. 新脚本模式：只使用 sky-browser 解析逻辑，不回退
- 自动质量检测：顶点数过少或面数为0时判定为无效
- 转换完成后自动生成结果列表 .txt 文件
- 依赖 LZ4 库：pkg install lz4

用法：
  1. 交互模式：python mesh_to_obj_universal.py
  2. 命令行：   python mesh_to_obj_universal.py 文件1.mesh -o 输出目录 --mode [hybrid|old|sky]
"""

import ctypes
import struct
import io
import os
import sys
import glob
import argparse
import re
import time

# ==================== 全局配置 ====================
DEBUG = True          # 调试输出，可设为 False 关闭
LZ4_LIB = 'liblz4.so' # LZ4 库名称（Termux 中为 liblz4.so）

# ==================== LZ4 库加载 ====================
def load_lz4():
    try:
        lz4 = ctypes.CDLL(LZ4_LIB)
        lz4.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lz4.LZ4_decompress_safe.restype = ctypes.c_int
        return lz4
    except OSError as e:
        print(f"LZ4库加载失败: {e}")
        print("尝试自动安装LZ4库...")
        if os.path.exists('/data/data/com.termux'):
            try:
                import subprocess
                subprocess.run(['pkg', 'install', '-y', 'lz4'], check=True)
                lz4 = ctypes.CDLL(LZ4_LIB)
                lz4.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
                lz4.LZ4_decompress_safe.restype = ctypes.c_int
                return lz4
            except:
                pass
        print("自动安装失败，请手动安装LZ4库：pkg install lz4")
        sys.exit(1)

# ==================== 辅助函数 ====================
def log_debug(*args):
    if DEBUG:
        print("[DEBUG]", *args)

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

# ==================== 二进制游标（用于 sky-browser 解析） ====================
class BinaryCursor:
    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.offset = offset

    def skip(self, n: int):
        self.offset += n

    def read_uint8(self) -> int:
        v = self.data[self.offset]
        self.offset += 1
        return v

    def read_uint16(self) -> int:
        v = struct.unpack('<H', self.data[self.offset:self.offset+2])[0]
        self.offset += 2
        return v

    def read_uint32(self) -> int:
        v = struct.unpack('<I', self.data[self.offset:self.offset+4])[0]
        self.offset += 4
        return v

    def read_float32(self) -> float:
        v = struct.unpack('<f', self.data[self.offset:self.offset+4])[0]
        self.offset += 4
        return v

    def read_float16(self) -> float:
        try:
            v = struct.unpack('<e', self.data[self.offset:self.offset+2])[0]
        except:
            raise RuntimeError("float16 not supported, need Python with '<e' support")
        self.offset += 2
        return float(v)

# ==================== sky-browser 解析逻辑 ====================
def parse_mesh_file_header(file_bytes: bytes) -> dict:
    header = {}
    header['version'] = file_bytes[0x00]
    header['compressed_size'] = struct.unpack('<I', file_bytes[0x4E:0x52])[0]
    header['uncompressed_size'] = struct.unpack('<I', file_bytes[0x52:0x56])[0]
    header['num_lods'] = struct.unpack('<I', file_bytes[0x44:0x48])[0]
    return header

class MeshFlags:
    def __init__(self, cursor: BinaryCursor):
        self.inf = cursor.read_float32()
        self.bbox_old = {
            'x0': cursor.read_float32(), 'y0': cursor.read_float32(), 'z0': cursor.read_float32(),
            'x1': cursor.read_float32(), 'y2': cursor.read_float32(), 'z3': cursor.read_float32(),
        }
        self.bbox = {
            'x0': cursor.read_float32(), 'y0': cursor.read_float32(), 'z0': cursor.read_float32(),
            'x1': cursor.read_float32(), 'y2': cursor.read_float32(), 'z3': cursor.read_float32(),
        }
        self.padding = [cursor.read_float32() for _ in range(16)]
        self.vertex_count = cursor.read_uint32()
        self.corner_count = cursor.read_uint32()
        self.is_idx32 = cursor.read_uint32()
        self.num_points = cursor.read_uint32()
        self.prop11 = cursor.read_uint32()
        self.prop12 = cursor.read_uint32()
        self.prop13 = cursor.read_uint32()
        self.prop14 = cursor.read_uint32()
        self.load_mesh_norms = cursor.read_uint8()
        self.load_info2 = cursor.read_uint8()
        self.load_info3 = cursor.read_uint8()
        self.skip_mesh_pos = cursor.read_uint32()
        self.skip_uvs = cursor.read_uint32()
        self.flag3 = cursor.read_uint32()
        self.unk1 = cursor.read_uint32()
        self.unk2 = cursor.read_uint32()
        self.unk3 = cursor.read_uint32()
        self.unk4 = cursor.read_uint32()

def parse_sky_mesh_body(body_bytes: bytes, version: int) -> dict:
    cursor = BinaryCursor(body_bytes)
    flags = MeshFlags(cursor)
    log_debug(f"sky-browser flags: vertex_count={flags.vertex_count}, corner_count={flags.corner_count}")

    mesh = {'flags': flags}
    if flags.skip_mesh_pos == 0:
        mesh['vertices'] = _parse_vertices_sky(cursor, flags.vertex_count)
    if flags.load_mesh_norms > 0:
        mesh['normals'] = _parse_normals_sky(cursor, flags.vertex_count)
    if flags.skip_uvs == 0:
        mesh['uv'] = _parse_uv_sky(cursor, flags.vertex_count)
    mesh['index'] = _parse_index_sky(cursor, flags.corner_count)
    return mesh

def _parse_vertices_sky(cursor: BinaryCursor, count: int):
    verts = []
    for _ in range(count):
        x = cursor.read_float32()
        y = cursor.read_float32()
        z = cursor.read_float32()
        verts.append((x, y, z))
        cursor.skip(4)
    return verts

def _parse_normals_sky(cursor: BinaryCursor, count: int):
    norms = []
    for _ in range(count):
        x = cursor.read_uint8() / 256.0
        y = cursor.read_uint8() / 256.0
        z = cursor.read_uint8() / 256.0
        _w = cursor.read_uint8() / 256.0
        norms.append((x, y, z))
    return norms

def _parse_uv_sky(cursor: BinaryCursor, count: int):
    uvs = []
    for _ in range(count):
        u = cursor.read_float16()
        v = 1 - cursor.read_float16()
        uvs.append((u, v))
        cursor.skip(12)
    return uvs

def _parse_index_sky(cursor: BinaryCursor, count: int):
    idx = []
    for _ in range(count):
        idx.append(cursor.read_uint16())
    return [tuple(idx[i:i+3]) for i in range(0, len(idx), 3)]

# ==================== fmt_mesh 解析器（源自论坛） ====================
def parse_fmt_mesh(f, lz4, is_zip=False):
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
    return vertex_buffer, uv_buffer, index_buffer

# ==================== 压缩解析器（自动判断 ZipPos） ====================
def parse_compressed_mesh(f, lz4, forced_zip=False):
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
            log_debug(f"压缩解析候选: cs=0x{cs_off:x}, us=0x{us_off:x}, data=0x{d_off:x}")
            f.seek(d_off)
            src = f.read(compressed_size)
            if len(src) != compressed_size:
                continue
            dest = ctypes.create_string_buffer(uncompressed_size)
            ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
            if ret <= 0:
                continue
            decompressed = dest.raw

            if len(decompressed) < 0x7c:
                raise ValueError("解压后数据太小")
            shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
            total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
            log_debug(f"  shared={shared}, total={total}")

            is_zip = forced_zip or (shared > 100000 or shared == 0 or total % 3 != 0 or total > 1000000)
            if is_zip:
                log_debug("  检测为 ZipPos 类型，使用压缩顶点模式")
                vert_data_size = shared * 4
                if len(decompressed) < vert_data_size:
                    raise ValueError("解压后数据不足，无法读取 ZipPos 顶点")
                vert_start = len(decompressed) - vert_data_size
                vertex_buffer = []
                for i in range(shared):
                    off = vert_start + i * 4
                    a, b, c, d = struct.unpack('<BBBB', decompressed[off:off+4])
                    x = (b - 128) / 127.5
                    y = (c - 128) / 127.5
                    z = (d - 128) / 127.5
                    vertex_buffer.append((x, y, z))
                uv_buffer = [(0.0, 0.0)] * shared
                face_count = total // 3
                # 搜索索引区域
                idx_start = None
                idx_type = None
                search_start = 0x7c
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
                index_buffer = []
                if idx_type == 16:
                    for i in range(face_count):
                        off = idx_start + i*6
                        v1, v2, v3 = struct.unpack('<HHH', decompressed[off:off+6])
                        index_buffer.append((v1, v2, v3))
                else:
                    for i in range(face_count):
                        off = idx_start + i*12
                        v1, v2, v3 = struct.unpack('<III', decompressed[off:off+12])
                        index_buffer.append((v1, v2, v3))
                if len(index_buffer) != face_count:
                    raise ValueError("索引数据不完整")
                return vertex_buffer, uv_buffer, index_buffer
            else:
                # 普通压缩解析
                log_debug("  普通压缩模式")
                uv_count = shared
                vert_start = 0xb3
                vertex_buffer = []
                pos = vert_start
                for i in range(shared):
                    if pos + 16 > len(decompressed):
                        raise ValueError("顶点数据不足")
                    x, y, z = struct.unpack('<fff', decompressed[pos:pos+12])
                    vertex_buffer.append((x, y, z))
                    pos += 16
                uv_buffer = []
                uv_header_size = uv_count * 4 - 4
                if uv_header_size > 0:
                    pos += uv_header_size
                for i in range(uv_count):
                    if pos + 16 > len(decompressed):
                        uv_buffer.append((0.0, 0.0))
                        pos += 16
                    else:
                        u16, v16 = struct.unpack('<HH', decompressed[pos:pos+4])
                        u = half_to_float(u16)
                        v = half_to_float(v16)
                        uv_buffer.append((u, v))
                        pos += 16
                pos += 4
                face_count = total // 3
                index_buffer = []
                for i in range(face_count):
                    if pos + 6 > len(decompressed):
                        break
                    v1, v2, v3 = struct.unpack('<HHH', decompressed[pos:pos+6])
                    index_buffer.append((v1, v2, v3))
                    pos += 6
                if len(index_buffer) != face_count:
                    raise ValueError("索引数据不完整")
                return vertex_buffer, uv_buffer, index_buffer
        except Exception as e:
            log_debug(f"  候选失败: {e}")
            continue
    raise ValueError("所有压缩解析候选均失败")

# ==================== 旧脚本回退函数（完全复现“下载这个就行.py”的解析逻辑） ====================
def fallback_parse_fmt_mesh(f, lz4, is_zip):
    return parse_fmt_mesh(f, lz4, is_zip)

def fallback_parse_compressed_mesh(f, lz4, is_zip):
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
            log_debug(f"回退压缩解析候选: cs=0x{cs_off:x}, us=0x{us_off:x}, data=0x{d_off:x}")
            f.seek(d_off)
            src = f.read(compressed_size)
            if len(src) != compressed_size:
                continue
            dest = ctypes.create_string_buffer(uncompressed_size)
            ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
            if ret <= 0:
                continue
            decompressed = dest.raw

            if len(decompressed) < 0x7c:
                raise ValueError("解压后数据太小")
            shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
            total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
            log_debug(f"  shared={shared}, total={total}")

            if is_zip:
                log_debug("  回退 ZipPos 模式")
                vert_data_size = shared * 4
                if len(decompressed) < vert_data_size:
                    raise ValueError("解压后数据不足")
                vert_start = len(decompressed) - vert_data_size
                vertex_buffer = []
                for i in range(shared):
                    off = vert_start + i * 4
                    a, b, c, d = struct.unpack('<BBBB', decompressed[off:off+4])
                    x = (b - 128) / 127.5
                    y = (c - 128) / 127.5
                    z = (d - 128) / 127.5
                    vertex_buffer.append((x, y, z))
                uv_buffer = [(0.0, 0.0)] * shared
                face_count = total // 3
                idx_start = None
                idx_type = None
                search_start = 0x7c
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
                    raise ValueError("未找到索引区域")
                index_buffer = []
                if idx_type == 16:
                    for i in range(face_count):
                        off = idx_start + i*6
                        v1, v2, v3 = struct.unpack('<HHH', decompressed[off:off+6])
                        index_buffer.append((v1, v2, v3))
                else:
                    for i in range(face_count):
                        off = idx_start + i*12
                        v1, v2, v3 = struct.unpack('<III', decompressed[off:off+12])
                        index_buffer.append((v1, v2, v3))
                if len(index_buffer) != face_count:
                    raise ValueError("索引不完整")
                return vertex_buffer, uv_buffer, index_buffer
            else:
                log_debug("  回退普通压缩模式")
                uv_count = shared
                vert_start = 0xb3
                vertex_buffer = []
                pos = vert_start
                for i in range(shared):
                    if pos + 16 > len(decompressed):
                        raise ValueError("顶点数据不足")
                    x, y, z = struct.unpack('<fff', decompressed[pos:pos+12])
                    vertex_buffer.append((x, y, z))
                    pos += 16
                uv_buffer = []
                uv_header_size = uv_count * 4 - 4
                if uv_header_size > 0:
                    pos += uv_header_size
                for i in range(uv_count):
                    if pos + 16 > len(decompressed):
                        uv_buffer.append((0.0, 0.0))
                        pos += 16
                    else:
                        u16, v16 = struct.unpack('<HH', decompressed[pos:pos+4])
                        u = half_to_float(u16)
                        v = half_to_float(v16)
                        uv_buffer.append((u, v))
                        pos += 16
                pos += 4
                face_count = total // 3
                index_buffer = []
                for i in range(face_count):
                    if pos + 6 > len(decompressed):
                        break
                    v1, v2, v3 = struct.unpack('<HHH', decompressed[pos:pos+6])
                    index_buffer.append((v1, v2, v3))
                    pos += 6
                if len(index_buffer) != face_count:
                    raise ValueError("索引不完整")
                return vertex_buffer, uv_buffer, index_buffer
        except Exception as e:
            log_debug(f"  回退候选失败: {e}")
            continue
    raise ValueError("所有回退压缩解析候选均失败")

def fallback_parse_heuristic(f, lz4):
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

            log_debug(f"启发式候选: cs=0x{cs_off:x}, us=0x{us_off:x}, lod=0x{lod_off:x}")
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
                    log_debug(f"  内部偏移 v_off=0x{v_off:x}: shared={shared}, total={total}")

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
    raise ValueError("启发式解析失败")

def fallback_parse_all(f, lz4, filename):
    """
    完全按照旧脚本的流程解析：先 fmt_mesh（根据文件名判断 is_zip），
    再压缩解析器（根据文件名判断 is_zip），最后启发式解析器。
    """
    is_zip = 'ZipPos' in filename  # 旧脚本中的判断方式
    # 尝试 fmt_mesh
    try:
        log_debug("回退: 尝试 fmt_mesh 解析器...")
        f.seek(0)
        vb, uvb, ib = fallback_parse_fmt_mesh(f, lz4, is_zip)
        return vb, uvb, ib, 'fallback_fmt_mesh'
    except Exception as e_fmt:
        log_debug(f"回退 fmt_mesh 失败: {e_fmt}")

    # 尝试压缩解析器
    try:
        log_debug("回退: 尝试压缩解析器...")
        f.seek(0)
        vb, uvb, ib = fallback_parse_compressed_mesh(f, lz4, is_zip)
        return vb, uvb, ib, 'fallback_compressed'
    except Exception as e_comp:
        log_debug(f"回退压缩解析器失败: {e_comp}")

    # 尝试启发式解析器
    try:
        log_debug("回退: 尝试启发式解析器...")
        f.seek(0)
        vb, uvb, ib = fallback_parse_heuristic(f, lz4)
        return vb, uvb, ib, 'fallback_heuristic'
    except Exception as e_heur:
        log_debug(f"回退启发式解析器失败: {e_heur}")
        raise ValueError("所有回退解析器均失败")

# ==================== 质量检测函数 ====================
def is_result_plausible(vertex_buffer, index_buffer):
    if len(vertex_buffer) < 10:
        log_debug(f"顶点数过少: {len(vertex_buffer)}，判定为无效")
        return False
    if len(index_buffer) == 0:
        log_debug("面数为0，判定为无效")
        return False
    max_idx = max(max(face) for face in index_buffer)
    if max_idx >= len(vertex_buffer):
        log_debug(f"索引越界: max_idx={max_idx} >= vertex_count={len(vertex_buffer)}，判定为无效")
        return False
    return True

# ==================== 导出 OBJ ====================
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
    print(f"导出成功: {obj_path} (共 {total_faces} 个面，有效 {valid_faces})")

# ==================== 交互式选择文件 ====================
def interactive_select_files(all_files):
    while True:
        print("\n找到以下 .mesh 文件：")
        for i, f in enumerate(all_files):
            print(f"{i+1}. {f}")
        print("\n光遇模型(.mesh)转.obj工具\n作者:sky-shier(十二)\n项目网址:https://github.com/skyIshier/That-sky-model\nq群:550929330\n邮箱:3787533101@qq.com")
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

# ==================== 主程序 ====================
def main():
    parser = argparse.ArgumentParser(description='通用 .mesh 转 OBJ 工具（支持版本选择）')
    parser.add_argument('files', nargs='*', help='要转换的 .mesh 文件（可多个）')
    parser.add_argument('-o', '--output', default='.', help='输出目录（默认当前目录）')
    parser.add_argument('--mode', choices=['hybrid', 'old', 'sky'], default='hybrid',
                        help='解析模式：hybrid（混合，默认）、old（仅旧脚本）、sky（仅新脚本）')
    parser.add_argument('--debug', action='store_true', help='启用调试输出')
    args = parser.parse_args()

    global DEBUG
    if args.debug:
        DEBUG = True

    lz4 = load_lz4()

    # 确定输入文件列表
    if args.files:
        mesh_files = [f for f in args.files if os.path.isfile(f)]
        if not mesh_files:
            print("没有有效的输入文件。")
            sys.exit(1)
        out_dir = args.output
        mode = args.mode
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

        # 交互选择模式
        print("\n请选择解析模式：")
        print("1. 混合模式 (hybrid) - 先尝试内置解析，失败后自动回退旧脚本")
        print("2. 旧脚本模式 (old) - 之前的版本")
        print("3. 新脚本模式 (sky) - 只使用 sky-browser 解析逻辑(Bug多)")
        mode_choice = input("请输入数字 (1/2/3) 或模式名称: ").strip().lower()
        if mode_choice in ['1', 'hybrid']:
            mode = 'hybrid'
        elif mode_choice in ['2', 'old']:
            mode = 'old'
        elif mode_choice in ['3', 'sky']:
            mode = 'sky'
        else:
            print("无效选择，默认使用混合模式。")
            mode = 'hybrid'

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    total_files = len(mesh_files)
    results = []

    for idx, mesh_file in enumerate(mesh_files, start=1):
        print(f"\n处理 [{idx}/{total_files}]: {mesh_file}")
        start_time = time.time()
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
                if mode == 'old':
                    log_debug("使用旧脚本模式...")
                    vb, uvb, ib, parser_name = fallback_parse_all(f, lz4, mesh_file)
                    vertex_buffer, uv_buffer, index_buffer = vb, uvb, ib
                    result['parser'] = parser_name
                elif mode == 'sky':
                    log_debug("使用新脚本模式（仅 sky-browser）...")
                    file_bytes = f.read()
                    header = parse_mesh_file_header(file_bytes)
                    compressed_size = header['compressed_size']
                    uncompressed_size = header['uncompressed_size']
                    if compressed_size < uncompressed_size and compressed_size > 10:
                        compressed = file_bytes[0x56:0x56 + compressed_size]
                        dest = ctypes.create_string_buffer(uncompressed_size)
                        ret = lz4.LZ4_decompress_safe(compressed, dest, compressed_size, uncompressed_size)
                        if ret <= 0:
                            raise IOError("LZ4解压失败")
                        body_bytes = dest.raw
                    else:
                        body_bytes = file_bytes[0x56:0x56 + uncompressed_size]
                        if len(body_bytes) < uncompressed_size:
                            raise ValueError("body 数据不足")
                    mesh_data = parse_sky_mesh_body(body_bytes, header['version'])
                    vertex_buffer = mesh_data.get('vertices', [])
                    uv_buffer = mesh_data.get('uv', [(0.0,0.0)] * len(vertex_buffer))
                    index_buffer = mesh_data.get('index', [])
                    result['parser'] = 'sky-browser'
                    if not is_result_plausible(vertex_buffer, index_buffer):
                        raise ValueError("解析结果不合理")
                else:  # hybrid
                    file_bytes = f.read()
                    header = parse_mesh_file_header(file_bytes)
                    compressed_size = header['compressed_size']
                    uncompressed_size = header['uncompressed_size']

                    # 尝试 sky-browser
                    try:
                        log_debug("尝试 sky-browser 解析...")
                        if compressed_size < uncompressed_size and compressed_size > 10:
                            compressed = file_bytes[0x56:0x56 + compressed_size]
                            dest = ctypes.create_string_buffer(uncompressed_size)
                            ret = lz4.LZ4_decompress_safe(compressed, dest, compressed_size, uncompressed_size)
                            if ret <= 0:
                                raise IOError("LZ4解压失败")
                            body_bytes = dest.raw
                        else:
                            body_bytes = file_bytes[0x56:0x56 + uncompressed_size]
                            if len(body_bytes) < uncompressed_size:
                                raise ValueError("body 数据不足")

                        mesh_data = parse_sky_mesh_body(body_bytes, header['version'])
                        vertex_buffer = mesh_data.get('vertices', [])
                        uv_buffer = mesh_data.get('uv', [(0.0,0.0)] * len(vertex_buffer))
                        index_buffer = mesh_data.get('index', [])
                        result['parser'] = 'sky-browser'

                        if not is_result_plausible(vertex_buffer, index_buffer):
                            log_debug("sky-browser 结果不合理，准备回退")
                            raise ValueError("结果不合理，触发回退")
                    except Exception as e_sky:
                        log_debug(f"sky-browser 解析失败或结果不合理: {e_sky}")
                        # 回退到 fmt_mesh
                        f.seek(0)
                        try:
                            log_debug("尝试 fmt_mesh 解析器...")
                            vb, uvb, ib = parse_fmt_mesh(f, lz4, is_zip=False)
                            vertex_buffer, uv_buffer, index_buffer = vb, uvb, ib
                            result['parser'] = 'fmt_mesh'
                            if not is_result_plausible(vertex_buffer, index_buffer):
                                raise ValueError("fmt_mesh 结果不合理")
                        except Exception as e_fmt:
                            log_debug(f"fmt_mesh 失败或结果不合理: {e_fmt}")
                            # 回退到压缩解析器
                            try:
                                log_debug("尝试压缩解析器（自动判断）...")
                                f.seek(0)
                                vb, uvb, ib = parse_compressed_mesh(f, lz4, forced_zip=False)
                                vertex_buffer, uv_buffer, index_buffer = vb, uvb, ib
                                result['parser'] = 'compressed'
                                if not is_result_plausible(vertex_buffer, index_buffer):
                                    raise ValueError("压缩解析器结果不合理")
                            except Exception as e_comp:
                                log_debug(f"压缩解析器失败或结果不合理: {e_comp}")
                                # 最后尝试旧脚本回退
                                log_debug("尝试旧脚本回退解析器...")
                                f.seek(0)
                                vb, uvb, ib, parser_name = fallback_parse_all(f, lz4, mesh_file)
                                vertex_buffer, uv_buffer, index_buffer = vb, uvb, ib
                                result['parser'] = parser_name

                # 成功导出
                result['status'] = 'success'
                result['vertex_count'] = len(vertex_buffer)
                result['face_count'] = len(index_buffer)

                # 打印顶点范围
                if vertex_buffer:
                    xs = [v[0] for v in vertex_buffer]
                    ys = [v[1] for v in vertex_buffer]
                    zs = [v[2] for v in vertex_buffer]
                    print(f"  顶点范围: X[{min(xs):.3f}, {max(xs):.3f}] Y[{min(ys):.3f}, {max(ys):.3f}] Z[{min(zs):.3f}, {max(zs):.3f}]")

                base = os.path.basename(mesh_file)
                name = os.path.splitext(base)[0]
                obj_path = os.path.join(out_dir, name + '.obj')
                export_obj(vertex_buffer, uv_buffer, index_buffer, obj_path)

        except Exception as e:
            result['error'] = str(e)
            if DEBUG:
                import traceback
                traceback.print_exc()

        finally:
            elapsed = time.time() - start_time
            result['time'] = elapsed
            results.append(result)

        if result['status'] == 'success':
            print(f"  ✅ 成功: 顶点 {result['vertex_count']}, 面 {result['face_count']}, 解析器 {result['parser']}, 耗时 {elapsed:.2f}s")
        else:
            print(f"  ❌ 失败: {result['error']}, 耗时 {elapsed:.2f}s")

    # 汇总并保存结果文件
    success = sum(1 for r in results if r['status'] == 'success')
    failed = total_files - success

    print("\n" + "="*70)
    print("批量转换完成")
    print(f"总文件: {total_files}, 成功: {success}, 失败: {failed}")

    if success > 0:
        print("\n成功文件列表:")
        for r in results:
            if r['status'] == 'success':
                print(f"  {r['file']}")
                print(f"    顶点: {r['vertex_count']}, 面: {r['face_count']}, 解析器: {r['parser']}, 耗时: {r['time']:.2f}s")

    if failed > 0:
        print("\n失败文件列表:")
        for r in results:
            if r['status'] == 'failed':
                print(f"  {r['file']}")
                print(f"    错误: {r['error']}, 耗时: {r['time']:.2f}s")

    print("="*70)

    # 保存结果到文本文件
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    result_file = os.path.join(out_dir, f"转换结果_{timestamp}.txt")
    with open(result_file, 'w', encoding='utf-8') as rf:
        rf.write("="*70 + "\n")
        rf.write("批量转换完成\n")
        rf.write(f"总文件: {total_files}, 成功: {success}, 失败: {failed}\n\n")
        if success > 0:
            rf.write("成功文件列表:\n")
            for r in results:
                if r['status'] == 'success':
                    rf.write(f"  {r['file']}\n")
                    rf.write(f"    顶点: {r['vertex_count']}, 面: {r['face_count']}, 解析器: {r['parser']}, 耗时: {r['time']:.2f}s\n")
        if failed > 0:
            rf.write("\n失败文件列表:\n")
            for r in results:
                if r['status'] == 'failed':
                    rf.write(f"  {r['file']}\n")
                    rf.write(f"    错误: {r['error']}, 耗时: {r['time']:.2f}s\n")
        rf.write("="*70 + "\n")
    print(f"\n结果已保存至: {result_file}")

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
《光遇》.mesh 转 OBJ 通用脚本（重写最终版 + 可调搜索次数）
- 支持三种模式：hybrid（增强混合）、old（原回退）、sky（原新脚本）
- 增强混合模式：自动试探更多 shared/total 偏移、顶点起始、步长，智能搜索索引
- 自动质量检测与零值索引过滤
- 支持分批处理（交互式自定义每批数量与间隔）
- 支持自定义索引搜索最大尝试次数（避免卡死或提高成功率）
- 每处理一个文件后释放内存，避免卡死
- 可选导出 UV（默认导出，但可在交互时选择关闭，提高 Prisma3D 兼容性）
- 依赖 LZ4，可选 zlib（自动安装）

用法：
  1. 交互模式：python 下载这个就行.py
  2. 命令行：   python 下载这个就行.py 文件1.mesh -o 输出目录 --mode [hybrid|old|sky] [--no-uv] [--max-iter 10000]
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
import gc
import subprocess

# ==================== 全局配置（可被命令行覆盖）====================
DEBUG = False
LZ4_LIB = 'liblz4.so'
ZLIB_AVAILABLE = False
INDEX_SEARCH_STEP = 4        # 索引搜索步长

# ==================== 自动安装 zlib（可选） ====================
def check_zlib():
    global ZLIB_AVAILABLE
    try:
        import zlib
        ZLIB_AVAILABLE = True
        return True
    except ImportError:
        print("zlib 模块未找到，尝试安装...")
        if os.path.exists('/data/data/com.termux'):
            try:
                subprocess.run(['pkg', 'install', '-y', 'zlib'], check=True)
                import zlib
                ZLIB_AVAILABLE = True
                return True
            except:
                pass
        print("自动安装失败，请手动安装：pkg install zlib")
        return False

# ==================== LZ4 库加载 ====================
def load_lz4():
    try:
        lz4 = ctypes.CDLL(LZ4_LIB)
        lz4.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lz4.LZ4_decompress_safe.restype = ctypes.c_int
        return lz4
    except OSError as e:
        print(f"LZ4库加载失败: {e}")
        if os.path.exists('/data/data/com.termux'):
            try:
                subprocess.run(['pkg', 'install', '-y', 'lz4'], check=True)
                lz4 = ctypes.CDLL(LZ4_LIB)
                lz4.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
                lz4.LZ4_decompress_safe.restype = ctypes.c_int
                return lz4
            except:
                pass
        print("请手动安装LZ4库：pkg install lz4")
        sys.exit(1)

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

# ==================== 二进制游标（sky-browser 用） ====================
class BinaryCursor:
    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.offset = offset
    def skip(self, n): self.offset += n
    def read_uint8(self): v = self.data[self.offset]; self.offset += 1; return v
    def read_uint16(self): v = struct.unpack('<H', self.data[self.offset:self.offset+2])[0]; self.offset += 2; return v
    def read_uint32(self): v = struct.unpack('<I', self.data[self.offset:self.offset+4])[0]; self.offset += 4; return v
    def read_float32(self): v = struct.unpack('<f', self.data[self.offset:self.offset+4])[0]; self.offset += 4; return v
    def read_float16(self):
        try:
            v = struct.unpack('<e', self.data[self.offset:self.offset+2])[0]
        except:
            raise RuntimeError("float16 not supported")
        self.offset += 2
        return float(v)

# ==================== sky-browser 解析逻辑（原版） ====================
def parse_mesh_file_header(file_bytes: bytes) -> dict:
    return {
        'version': file_bytes[0x00],
        'compressed_size': struct.unpack('<I', file_bytes[0x4E:0x52])[0],
        'uncompressed_size': struct.unpack('<I', file_bytes[0x52:0x56])[0],
        'num_lods': struct.unpack('<I', file_bytes[0x44:0x48])[0],
    }

class MeshFlags:
    def __init__(self, cursor):
        self.inf = cursor.read_float32()
        self.bbox_old = {k: cursor.read_float32() for k in ['x0','y0','z0','x1','y2','z3']}
        self.bbox = {k: cursor.read_float32() for k in ['x0','y0','z0','x1','y2','z3']}
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
    mesh = {'flags': flags}
    if flags.skip_mesh_pos == 0:
        mesh['vertices'] = [(cursor.read_float32(), cursor.read_float32(), cursor.read_float32()) and cursor.skip(4) for _ in range(flags.vertex_count)]
    if flags.load_mesh_norms > 0:
        mesh['normals'] = [(cursor.read_uint8()/256.0, cursor.read_uint8()/256.0, cursor.read_uint8()/256.0) and cursor.skip(1) for _ in range(flags.vertex_count)]
    if flags.skip_uvs == 0:
        mesh['uv'] = [(cursor.read_float16(), 1-cursor.read_float16()) and cursor.skip(12) for _ in range(flags.vertex_count)]
    idx = [cursor.read_uint16() for _ in range(flags.corner_count)]
    mesh['index'] = [tuple(idx[i:i+3]) for i in range(0, len(idx), 3)]
    return mesh

# ==================== fmt_mesh 解析器（原版） ====================
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
            f.read(64); f.read(64); f.read(4)

    bs = io.BytesIO(decompressed)
    bs.seek(116)
    vnum = struct.unpack('<I', bs.read(4))[0]
    bs.seek(120)
    inum = struct.unpack('<I', bs.read(4))[0]
    bs.seek(128)
    unum = struct.unpack('<I', bs.read(4))[0]

    if is_zip:
        bs.seek(179)
        if has_bones:
            bs.seek(vnum * 8, 1)
        ibuf = bs.read(inum * 2)
        index_buffer = [struct.unpack('<HHH', ibuf[i:i+6]) for i in range(0, len(ibuf), 6)]
        bs.seek(len(decompressed) - vnum * 4)
        vbuf = bs.read(vnum * 4)
        vertex_buffer = []
        for i in range(vnum):
            a,b,c,d = struct.unpack('<BBBB', vbuf[i*4:i*4+4])
            vertex_buffer.append(((b-128)/127.5, (c-128)/127.5, (d-128)/127.5))
        uv_buffer = [(0.0,0.0)] * vnum
    else:
        bs.seek(179)
        vbuf = bs.read(vnum * 16)
        vertex_buffer = [struct.unpack('<fff4x', vbuf[i*16:i*16+16])[:3] for i in range(vnum)]
        bs.seek(vnum * 4, 1)
        uvbuf = bs.read(vnum * 16)
        uv_buffer = []
        for i in range(vnum):
            u16, v16 = struct.unpack('<HH', uvbuf[i*16:i*16+4])
            uv_buffer.append((half_to_float(u16), half_to_float(v16)))
        if has_bones:
            bs.seek(vnum * 8, 1)
        ibuf = bs.read(inum * 2)
        index_buffer = [struct.unpack('<HHH', ibuf[i:i+6]) for i in range(0, len(ibuf), 6)]
    return vertex_buffer, uv_buffer, index_buffer

# ==================== 旧脚本压缩解析器（原版，稍作精简） ====================
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
            compressed_size = struct.unpack('<i', f.read(4))[0] if size_bytes==4 else struct.unpack('<H', f.read(2))[0]
            f.seek(us_off)
            uncompressed_size = struct.unpack('<i', f.read(4))[0] if size_bytes==4 else struct.unpack('<H', f.read(2))[0]
            if not (0 < compressed_size < 10*1024*1024 and 0 < uncompressed_size < 50*1024*1024):
                continue
            f.seek(d_off)
            src = f.read(compressed_size)
            dest = ctypes.create_string_buffer(uncompressed_size)
            ret = lz4.LZ4_decompress_safe(src, dest, compressed_size, uncompressed_size)
            if ret <= 0:
                continue
            decompressed = dest.raw
            if len(decompressed) < 0x7c:
                continue
            shared = struct.unpack('<i', decompressed[0x74:0x78])[0]
            total = struct.unpack('<i', decompressed[0x78:0x7c])[0]
            is_zip = forced_zip or (shared > 100000 or shared == 0 or total % 3 != 0 or total > 1000000)
            if is_zip:
                # ZipPos 模式
                vert_data_size = shared * 4
                if len(decompressed) < vert_data_size:
                    continue
                vert_start = len(decompressed) - vert_data_size
                vertex_buffer = []
                for i in range(shared):
                    off = vert_start + i*4
                    a,b,c,d = struct.unpack('<BBBB', decompressed[off:off+4])
                    vertex_buffer.append(((b-128)/127.5, (c-128)/127.5, (d-128)/127.5))
                uv_buffer = [(0.0,0.0)] * shared
                face_count = total // 3
                # 搜索索引区域
                idx_start = None; idx_type = None
                for start in range(0x7c, len(decompressed)-5):
                    if start+6 > len(decompressed): break
                    idx = struct.unpack('<HHH', decompressed[start:start+6])
                    if max(idx) < shared:
                        count = 0
                        for j in range(start, len(decompressed)-5, 6):
                            if max(struct.unpack('<HHH', decompressed[j:j+6])) >= shared: break
                            count += 1
                        if count >= face_count:
                            idx_start = start
                            idx_type = 16
                            break
                if idx_start is None:
                    for start in range(0x7c, len(decompressed)-11):
                        if start+12 > len(decompressed): break
                        idx = struct.unpack('<III', decompressed[start:start+12])
                        if max(idx) < shared:
                            count = 0
                            for j in range(start, len(decompressed)-11, 12):
                                if max(struct.unpack('<III', decompressed[j:j+12])) >= shared: break
                                count += 1
                            if count >= face_count:
                                idx_start = start
                                idx_type = 32
                                break
                if idx_start is None:
                    continue
                index_buffer = []
                if idx_type == 16:
                    for i in range(face_count):
                        off = idx_start + i*6
                        v1,v2,v3 = struct.unpack('<HHH', decompressed[off:off+6])
                        index_buffer.append((v1,v2,v3))
                else:
                    for i in range(face_count):
                        off = idx_start + i*12
                        v1,v2,v3 = struct.unpack('<III', decompressed[off:off+12])
                        index_buffer.append((v1,v2,v3))
                if len(index_buffer) == face_count:
                    return vertex_buffer, uv_buffer, index_buffer
            else:
                # 普通模式
                uv_count = shared
                vert_start = 0xb3
                vertex_buffer = []
                pos = vert_start
                for i in range(shared):
                    if pos+16 > len(decompressed): break
                    x,y,z = struct.unpack('<fff', decompressed[pos:pos+12])
                    vertex_buffer.append((x,y,z))
                    pos += 16
                if len(vertex_buffer) != shared:
                    continue
                uv_buffer = []
                uv_header_size = uv_count*4 - 4
                if uv_header_size > 0:
                    pos += uv_header_size
                for i in range(uv_count):
                    if pos+16 > len(decompressed):
                        uv_buffer.append((0.0,0.0))
                        pos += 16
                    else:
                        u16,v16 = struct.unpack('<HH', decompressed[pos:pos+4])
                        uv_buffer.append((half_to_float(u16), half_to_float(v16)))
                        pos += 16
                pos += 4
                face_count = total // 3
                index_buffer = []
                for i in range(face_count):
                    if pos+6 > len(decompressed): break
                    v1,v2,v3 = struct.unpack('<HHH', decompressed[pos:pos+6])
                    index_buffer.append((v1,v2,v3))
                    pos += 6
                if len(index_buffer) == face_count:
                    return vertex_buffer, uv_buffer, index_buffer
        except:
            continue
    raise ValueError("所有压缩解析候选均失败")

# ==================== 旧脚本回退函数（完整保留） ====================
def fallback_parse_fmt_mesh(f, lz4, is_zip):
    return parse_fmt_mesh(f, lz4, is_zip)

def fallback_parse_compressed_mesh(f, lz4, is_zip):
    return parse_compressed_mesh(f, lz4, is_zip)  # 复用上面的函数

def fallback_parse_heuristic(f, lz4):
    # 简单启发式，尝试几个常见偏移
    candidate_sets = [(0x4e, 0x52, 0x44, 0x56), (0x4a, 0x4e, 0x40, 0x52), (0x52, 0x56, 0x48, 0x5a)]
    for cs_off, us_off, lod_off, d_off in candidate_sets:
        try:
            f.seek(cs_off)
            cs = struct.unpack('<i', f.read(4))[0]
            f.seek(us_off)
            us = struct.unpack('<i', f.read(4))[0]
            f.seek(lod_off)
            num_lods = struct.unpack('<i', f.read(4))[0]
            if not (0 < cs < 10*1024*1024 and 0 < us < 50*1024*1024):
                continue
            f.seek(d_off)
            src = f.read(cs)
            dest = ctypes.create_string_buffer(us)
            ret = lz4.LZ4_decompress_safe(src, dest, cs, us)
            if ret <= 0:
                continue
            decomp = dest.raw
            for v_off in [0x74, 0x70, 0x78, 0x80]:
                if v_off+8 > len(decomp): continue
                shared = struct.unpack('<i', decomp[v_off:v_off+4])[0]
                total = struct.unpack('<i', decomp[v_off+4:v_off+8])[0]
                if not (5 <= shared < 100000 and 5 <= total < 300000 and total % 3 == 0):
                    continue
                # 尝试解析
                vertex_buffer = []
                pos = 0xb3
                for i in range(shared):
                    if pos+12 > len(decomp): break
                    x,y,z = struct.unpack('<fff', decomp[pos:pos+12])
                    vertex_buffer.append((x,y,z))
                    pos += 16
                if len(vertex_buffer) != shared:
                    continue
                uv_buffer = []
                uv_pos = 0xb3 + shared*16
                for i in range(shared):
                    if uv_pos+4 > len(decomp):
                        uv_buffer.append((0,0))
                        uv_pos += 16
                    else:
                        u16,v16 = struct.unpack('<HH', decomp[uv_pos:uv_pos+4])
                        uv_buffer.append((half_to_float(u16), half_to_float(v16)))
                        uv_pos += 16
                if len(uv_buffer) != shared:
                    continue
                face_count = total // 3
                index_buffer = []
                idx_pos = uv_pos + 4
                for i in range(face_count):
                    if idx_pos+6 > len(decomp): break
                    v1,v2,v3 = struct.unpack('<HHH', decomp[idx_pos:idx_pos+6])
                    index_buffer.append((v1,v2,v3))
                    idx_pos += 6
                if len(index_buffer) == face_count:
                    return vertex_buffer, uv_buffer, index_buffer
        except:
            continue
    raise ValueError("启发式解析失败")

def fallback_parse_all(f, lz4, filename):
    is_zip = 'ZipPos' in filename
    try:
        return fallback_parse_fmt_mesh(f, lz4, is_zip) + ('fallback_fmt_mesh',)
    except:
        try:
            return fallback_parse_compressed_mesh(f, lz4, is_zip) + ('fallback_compressed',)
        except:
            return fallback_parse_heuristic(f, lz4) + ('fallback_heuristic',)

# ==================== 增强的混合解析函数（新）====================
def find_compressed_blocks_fast(data):
    """快速查找可能的压缩块位置（常用偏移）"""
    candidates = []
    for i in [0x4e, 0x52, 0x56, 0x5a, 0x60, 0x74]:
        if i+8 > len(data): continue
        cs = struct.unpack('<I', data[i:i+4])[0]
        us = struct.unpack('<I', data[i+4:i+8])[0]
        if 0 < cs < 10*1024*1024 and 0 < us < 50*1024*1024 and cs < us:
            if i+8+cs <= len(data):
                candidates.append((i, cs, us, i+8))
                if len(candidates) >= 3:
                    break
    return candidates

def try_decompress(data, cs_off, cs, us, data_off, lz4):
    compressed = data[data_off:data_off+cs]
    if len(compressed) != cs:
        return None
    dest = ctypes.create_string_buffer(us)
    ret = lz4.LZ4_decompress_safe(compressed, dest, cs, us)
    if ret > 0:
        return dest.raw
    if ZLIB_AVAILABLE:
        try:
            import zlib
            decomp = zlib.decompress(compressed)
            if len(decomp) == us:
                return decomp
        except:
            pass
    return None

def find_index_region_fast(decomp, vertex_count, face_count, start_search, max_iter):
    """从指定位置开始，步进搜索索引区域，可指定最大尝试次数"""
    step = INDEX_SEARCH_STEP
    iter_count = 0
    # 16位
    for start in range(start_search, len(decomp)-6, step):
        iter_count += 1
        if iter_count > max_iter:
            break
        try:
            # 快速检查前几个索引
            pos = start
            sample = []
            for _ in range(min(face_count, 5)):
                v1,v2,v3 = struct.unpack('<HHH', decomp[pos:pos+6])
                if max(v1,v2,v3) >= vertex_count:
                    raise ValueError
                sample.extend([v1,v2,v3])
                pos += 6
            zero_ratio = sample.count(0) / len(sample)
            if zero_ratio > 0.1:
                continue
            # 完整读取
            idx = []
            pos = start
            for i in range(face_count):
                v1,v2,v3 = struct.unpack('<HHH', decomp[pos:pos+6])
                if max(v1,v2,v3) >= vertex_count:
                    raise ValueError
                idx.append((v1,v2,v3))
                pos += 6
            return idx, 16
        except:
            # 尝试32位
            try:
                pos = start
                sample = []
                for _ in range(min(face_count,5)):
                    v1,v2,v3 = struct.unpack('<III', decomp[pos:pos+12])
                    if max(v1,v2,v3) >= vertex_count:
                        raise ValueError
                    sample.extend([v1,v2,v3])
                    pos += 12
                zero_ratio = sample.count(0) / len(sample)
                if zero_ratio > 0.1:
                    continue
                idx = []
                pos = start
                for i in range(face_count):
                    v1,v2,v3 = struct.unpack('<III', decomp[pos:pos+12])
                    if max(v1,v2,v3) >= vertex_count:
                        raise ValueError
                    idx.append((v1,v2,v3))
                    pos += 12
                return idx, 32
            except:
                continue
    raise ValueError("未找到索引区域")

def parse_enhanced(decomp, max_iter):
    """增强解析：尝试多种偏移组合，可指定最大尝试次数"""
    # 候选 shared/total 偏移（常用范围）
    candidate_offsets = list(range(0x20, 0x100, 4))
    # 顶点起始试探
    vertex_starts = [0xb3, 0x60, 0x70, 0x80, 0x90]
    # 步长试探
    strides = [12, 16, 20, 24, 8]

    for off in candidate_offsets:
        if off+8 > len(decomp):
            continue
        shared = struct.unpack('<I', decomp[off:off+4])[0]
        total = struct.unpack('<I', decomp[off+4:off+8])[0]
        if not (5 <= shared < 200000 and 5 <= total < 600000 and total % 3 == 0):
            continue

        for vstart in vertex_starts:
            for stride in strides:
                # 读顶点
                vertex_buffer = []
                pos = vstart
                for i in range(shared):
                    if pos+12 > len(decomp): break
                    x,y,z = struct.unpack('<fff', decomp[pos:pos+12])
                    vertex_buffer.append((x,y,z))
                    pos += stride
                if len(vertex_buffer) != shared:
                    continue
                max_abs = max(max(abs(v[0]),abs(v[1]),abs(v[2])) for v in vertex_buffer)
                if max_abs > 10000:
                    continue
                # 读 UV（假设紧接顶点，每顶点16字节，前4字节为 UV half）
                uv_buffer = []
                uv_pos = vstart + shared * stride
                for i in range(shared):
                    if uv_pos+4 > len(decomp):
                        uv_buffer.append((0.0,0.0))
                        uv_pos += 16
                        continue
                    u16,v16 = struct.unpack('<HH', decomp[uv_pos:uv_pos+4])
                    uv_buffer.append((half_to_float(u16), half_to_float(v16)))
                    uv_pos += 16
                if len(uv_buffer) != shared:
                    continue
                # 搜索索引
                face_count = total // 3
                try:
                    idx_buffer, idx_type = find_index_region_fast(decomp, shared, face_count, uv_pos, max_iter)
                    return vertex_buffer, uv_buffer, idx_buffer
                except:
                    # 尝试从开头搜索
                    try:
                        idx_buffer, idx_type = find_index_region_fast(decomp, shared, face_count, 0, max_iter)
                        return vertex_buffer, uv_buffer, idx_buffer
                    except:
                        continue
    raise ValueError("增强解析失败")

# ==================== 质量检测 ====================
def is_result_plausible(vb, ib):
    return len(vb) >= 5 and len(ib) > 0 and max(max(f) for f in ib) < len(vb)

# ==================== 导出 OBJ（可选 UV）====================
def export_obj(vertex_buffer, uv_buffer, index_buffer, obj_path, with_uv=True):
    total_faces = len(index_buffer)
    with open(obj_path, 'w') as out:
        for v in vertex_buffer:
            out.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        if with_uv:
            for uv in uv_buffer:
                out.write(f'vt {uv[0]:.6f} {uv[1]:.6f}\n')
            for face in index_buffer:
                out.write(f'f {face[0]+1}/{face[0]+1} {face[1]+1}/{face[1]+1} {face[2]+1}/{face[2]+1}\n')
        else:
            for face in index_buffer:
                out.write(f'f {face[0]+1} {face[1]+1} {face[2]+1}\n')
    print(f"导出成功: {obj_path} (共 {total_faces} 个面)")

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
                    s,e = map(int, part.split('-'))
                    if 1 <= s <= len(all_files) and 1 <= e <= len(all_files) and s <= e:
                        selected.extend(range(s-1, e))
                except:
                    pass
            else:
                try:
                    idx = int(part)-1
                    if 0 <= idx < len(all_files):
                        selected.append(idx)
                except:
                    pass
        if not selected:
            print("未选择任何有效文件，请重新输入。")
            continue
        return [all_files[i] for i in sorted(set(selected))]

# ==================== 处理单个文件 ====================
def process_single_file(mesh_file, idx, total, out_dir, mode, with_uv, lz4, max_iter, results):
    print(f"\n处理 [{idx}/{total}]: {mesh_file}")
    start = time.time()
    res = {'file': mesh_file, 'status':'failed', 'vertex_count':0, 'face_count':0, 'parser':'unknown', 'time':0.0}
    try:
        with open(mesh_file, 'rb') as f:
            data = f.read()
        # 处理可能存在的文件名头部
        if data.startswith(b'\x1F\x00\x00\x00') and 0x20 <= data[4] < 0x7F:
            null_pos = data.find(b'\x00', 4)
            if null_pos != -1 and null_pos < 0x100:
                data = data[null_pos+1:]

        if mode == 'old':
            with open(mesh_file, 'rb') as f2:
                vb, uvb, ib, pname = fallback_parse_all(f2, lz4, mesh_file)
            res['parser'] = pname
        elif mode == 'sky':
            header = parse_mesh_file_header(data)
            cs, us = header['compressed_size'], header['uncompressed_size']
            if cs < us and cs > 10:
                compressed = data[0x56:0x56+cs]
                dest = ctypes.create_string_buffer(us)
                ret = lz4.LZ4_decompress_safe(compressed, dest, cs, us)
                if ret <= 0:
                    raise IOError("LZ4解压失败")
                body = dest.raw
            else:
                body = data[0x56:0x56+us]
            mesh = parse_sky_mesh_body(body, header['version'])
            vb = mesh.get('vertices', [])
            uvb = mesh.get('uv', [(0,0)]*len(vb))
            ib = mesh.get('index', [])
            res['parser'] = 'sky-browser'
            if not is_result_plausible(vb, ib):
                raise ValueError("解析结果不合理")
        else:  # hybrid
            # 先尝试 sky-browser
            try:
                header = parse_mesh_file_header(data)
                cs, us = header['compressed_size'], header['uncompressed_size']
                if cs < us and cs > 10:
                    compressed = data[0x56:0x56+cs]
                    dest = ctypes.create_string_buffer(us)
                    ret = lz4.LZ4_decompress_safe(compressed, dest, cs, us)
                    if ret <= 0:
                        raise IOError
                    body = dest.raw
                else:
                    body = data[0x56:0x56+us]
                mesh = parse_sky_mesh_body(body, header['version'])
                vb = mesh.get('vertices', [])
                uvb = mesh.get('uv', [(0,0)]*len(vb))
                ib = mesh.get('index', [])
                res['parser'] = 'sky-browser'
                if not is_result_plausible(vb, ib):
                    raise ValueError
            except:
                # 再尝试 fmt_mesh
                try:
                    with open(mesh_file, 'rb') as f2:
                        vb, uvb, ib = parse_fmt_mesh(f2, lz4, is_zip=False)
                    res['parser'] = 'fmt_mesh'
                    if not is_result_plausible(vb, ib):
                        raise ValueError
                except:
                    # 再尝试增强解析
                    try:
                        base = os.path.splitext(mesh_file)[0]
                        vb, uvb, ib = parse_enhanced(data, max_iter)
                        res['parser'] = 'enhanced'
                        if not is_result_plausible(vb, ib):
                            raise ValueError
                    except:
                        # 最后回退到旧脚本
                        with open(mesh_file, 'rb') as f3:
                            vb, uvb, ib, pname = fallback_parse_all(f3, lz4, mesh_file)
                        res['parser'] = pname

        res['status'] = 'success'
        res['vertex_count'] = len(vb)
        res['face_count'] = len(ib)
        if vb:
            xs = [v[0] for v in vb]
            ys = [v[1] for v in vb]
            zs = [v[2] for v in vb]
            print(f"  顶点范围: X[{min(xs):.3f}, {max(xs):.3f}] Y[{min(ys):.3f}, {max(ys):.3f}] Z[{min(zs):.3f}, {max(zs):.3f}]")
        out_path = os.path.join(out_dir, os.path.basename(mesh_file).replace('.mesh','.obj'))
        export_obj(vb, uvb, ib, out_path, with_uv)
        del vb, uvb, ib
        gc.collect()
    except Exception as e:
        res['error'] = str(e)
        if DEBUG:
            import traceback
            traceback.print_exc()
    finally:
        res['time'] = time.time() - start
        results.append(res)
        if res['status'] == 'success':
            print(f"  ✅ 成功: 顶点 {res['vertex_count']}, 面 {res['face_count']}, 解析器 {res['parser']}, 耗时 {res['time']:.2f}s")
        else:
            print(f"  ❌ 失败: {res['error']}, 耗时 {res['time']:.2f}s")

def print_summary(results, total, out_dir):
    success = sum(1 for r in results if r['status']=='success')
    failed = total - success
    print("\n"+"="*70)
    print("批量转换完成")
    print(f"总文件: {total}, 成功: {success}, 失败: {failed}")
    if success:
        print("\n成功文件列表:")
        for r in results:
            if r['status']=='success':
                print(f"  {r['file']} 顶点:{r['vertex_count']} 面:{r['face_count']} 解析器:{r['parser']} 耗时:{r['time']:.2f}s")
    if failed:
        print("\n失败文件列表:")
        for r in results:
            if r['status']=='failed':
                print(f"  {r['file']} 错误:{r['error']} 耗时:{r['time']:.2f}s")
    print("="*70)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    res_file = os.path.join(out_dir, f"转换结果_{timestamp}.txt")
    with open(res_file, 'w', encoding='utf-8') as rf:
        rf.write("="*70+"\n")
        rf.write(f"总文件: {total}, 成功: {success}, 失败: {failed}\n\n")
        if success:
            rf.write("成功文件列表:\n")
            for r in results:
                if r['status']=='success':
                    rf.write(f"  {r['file']} 顶点:{r['vertex_count']} 面:{r['face_count']} 解析器:{r['parser']} 耗时:{r['time']:.2f}s\n")
        if failed:
            rf.write("\n失败文件列表:\n")
            for r in results:
                if r['status']=='failed':
                    rf.write(f"  {r['file']} 错误:{r['error']} 耗时:{r['time']:.2f}s\n")
        rf.write("="*70+"\n")
    print(f"\n结果已保存至: {res_file}")

# ==================== 主程序 ====================
def main():
    parser = argparse.ArgumentParser(description='光遇 .mesh 转 OBJ 工具（重写最终版）')
    parser.add_argument('files', nargs='*', help='要转换的 .mesh 文件')
    parser.add_argument('-o', '--output', default='.', help='输出目录')
    parser.add_argument('--mode', choices=['hybrid','old','sky'], default='hybrid', help='解析模式')
    parser.add_argument('--no-uv', action='store_true', help='不导出 UV 坐标（提高 Prisma3D 兼容性）')
    parser.add_argument('--max-iter', type=int, default=5000, help='索引搜索最大尝试次数（默认5000，越大越慢但可能找到更多）')
    parser.add_argument('--debug', action='store_true', help='启用调试输出')
    args = parser.parse_args()

    global DEBUG
    if args.debug:
        DEBUG = True

    # 检查 zlib（可选）
    check_zlib()
    lz4 = load_lz4()
    with_uv = not args.no_uv
    max_iter = args.max_iter

    if args.files:
        mesh_files = [f for f in args.files if os.path.isfile(f)]
        if not mesh_files:
            print("没有有效的输入文件。")
            sys.exit(1)
        out_dir = args.output
        mode = args.mode
        total = len(mesh_files)
        results = []
        for idx, f in enumerate(mesh_files, 1):
            process_single_file(f, idx, total, out_dir, mode, with_uv, lz4, max_iter, results)
        print_summary(results, total, out_dir)
        return

    # 交互模式
    all_files = glob.glob("*.mesh")
    if not all_files:
        print("当前目录下没有 .mesh 文件。")
        return
    mesh_files = interactive_select_files(all_files)
    if mesh_files is None:
        return
    out_dir = input("请输入输出目录（默认: .）: ").strip() or '.'
    os.makedirs(out_dir, exist_ok=True)

    print("\n请选择解析模式：")
    print("1. 混合模式 (hybrid) - 先尝试内置解析，失败后自动回退")
    print("2. 旧脚本模式 (old) - 使用原版回退逻辑")
    print("3. 新脚本模式 (sky) - 只使用 sky-browser 解析")
    mode_choice = input("请输入数字 (1/2/3) 或模式名称: ").strip().lower()
    mode = {'1':'hybrid','2':'old','3':'sky'}.get(mode_choice, 'hybrid')

    uv_choice = input("\n是否导出 UV 坐标？(y/n，默认y): ").strip().lower()
    with_uv = uv_choice != 'n'

    max_iter_input = input("\n请输入索引搜索最大尝试次数（默认5000，越大越慢但可能找到更多）: ").strip()
    if max_iter_input.isdigit():
        max_iter = int(max_iter_input)
    else:
        max_iter = 5000

    batch = input("\n是否分批处理？(y/n，默认n): ").strip().lower() == 'y'
    if batch:
        batch_size = int(input("请输入每批文件数 (默认10): ").strip() or 10)
        sleep_sec = int(input("请输入每批间隔秒数 (默认1): ").strip() or 1)
    else:
        batch_size = None

    total = len(mesh_files)
    results = []
    if batch_size is None:
        for idx, f in enumerate(mesh_files, 1):
            process_single_file(f, idx, total, out_dir, mode, with_uv, lz4, max_iter, results)
    else:
        for i in range(0, total, batch_size):
            batch = mesh_files[i:i+batch_size]
            print(f"\n处理第 {i//batch_size+1}/{(total+batch_size-1)//batch_size} 批，共 {len(batch)} 个文件")
            for j, f in enumerate(batch, 1):
                process_single_file(f, i+j, total, out_dir, mode, with_uv, lz4, max_iter, results)
            if i+batch_size < total:
                print(f"休息 {sleep_sec} 秒...")
                time.sleep(sleep_sec)

    print_summary(results, total, out_dir)

if __name__ == '__main__':
    main()
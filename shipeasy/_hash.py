_MASK32 = 0xFFFFFFFF
_C1 = 0xCC9E2D51
_C2 = 0x1B873593


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (32 - r))) & _MASK32


def _fmix32(h: int) -> int:
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _MASK32
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _MASK32
    h ^= h >> 16
    return h


def murmur3(key: str, seed: int = 0) -> int:
    data = key.encode("utf-8")
    n = len(data)
    h1 = seed & _MASK32
    nblocks = n // 4
    for i in range(nblocks):
        off = i * 4
        k1 = data[off] | (data[off + 1] << 8) | (data[off + 2] << 16) | (data[off + 3] << 24)
        k1 = (k1 * _C1) & _MASK32
        k1 = _rotl(k1, 15)
        k1 = (k1 * _C2) & _MASK32
        h1 ^= k1
        h1 = _rotl(h1, 13)
        h1 = ((h1 * 5) + 0xE6546B64) & _MASK32

    tail_idx = nblocks * 4
    k1 = 0
    rem = n & 3
    if rem >= 3:
        k1 ^= data[tail_idx + 2] << 16
    if rem >= 2:
        k1 ^= data[tail_idx + 1] << 8
    if rem >= 1:
        k1 ^= data[tail_idx]
        k1 = (k1 * _C1) & _MASK32
        k1 = _rotl(k1, 15)
        k1 = (k1 * _C2) & _MASK32
        h1 ^= k1

    h1 ^= n
    return _fmix32(h1)

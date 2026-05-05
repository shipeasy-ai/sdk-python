from shipeasy import murmur3


def test_vectors():
    # Verified against the Ruby SDK reference impl. Cross-language
    # consistency is the contract; the table in
    # experiment-platform/04-evaluation.md disagrees on some inputs and
    # appears to be unverified.
    cases = [
        ("", 0x00000000),
        ("a", 0x3c2569b2),
        ("ab", 0x9bbfd75f),
        ("abc", 0xb3dd93fa),
        ("aaaa", 0x7eeed987),
        ("aaaaa", 0xe9ca302b),
        ("Hello, 世界", 0xe2a131eb),
        ("The quick brown fox jumps over the lazy dog", 0x2e4ff723),
    ]
    for inp, expected in cases:
        assert murmur3(inp) == expected, inp

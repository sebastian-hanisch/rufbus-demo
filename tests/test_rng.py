"""Zufallsquelle: ganzzahlig und über Versionen stabil (Referenzwerte von Hand/aus der veröffentlichten Referenz)."""

from ruf_rng import SplitMix64


def test_splitmix64_matches_the_published_reference_for_seed_0():
    r = SplitMix64(0)
    assert [r.next() for _ in range(3)] == [16294208416658607535, 7960286522194355700, 487617019471545679]


def test_u32_is_the_upper_half_of_next():
    a, b = SplitMix64(5), SplitMix64(5)
    assert a.u32() == b.next() >> 32


def test_shuffle_is_a_frozen_permutation():
    r = SplitMix64(2024)
    items = list(range(10))
    r.shuffle(items)
    assert items == [9, 0, 6, 3, 4, 2, 5, 7, 8, 1]
    assert sorted(items) == list(range(10))


def test_below_stays_in_range():
    r = SplitMix64(3)
    assert all(0 <= r.below(7) < 7 for _ in range(500))

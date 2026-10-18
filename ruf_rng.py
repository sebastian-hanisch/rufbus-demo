"""Ganzzahliger Zufallsgenerator (SplitMix64, Vigna): reine Ganzzahl-Arithmetik, damit Szenarien und Suchläufe auf jeder Plattform und mit jeder
numpy-Version dieselben Werte liefern (numpy-Ströme wie `rng.poisson` oder `rng.choice` sind zwischen Versionen nicht stabil)."""

_MASK = (1 << 64) - 1


class SplitMix64:
    def __init__(self, seed):
        self.state = int(seed) & _MASK

    def next(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return z ^ (z >> 31)

    def below(self, n):
        """Ganzzahl in 0..n-1 (die Modulo-Verzerrung liegt bei n <= 10^6 unter 1e-13)."""
        return self.next() % n

    def u32(self):
        """Gleichverteilte 32-Bit-Zahl 0..2^32-1 (obere Bits)."""
        return self.next() >> 32

    def shuffle(self, items):
        """Fisher-Yates in place; ersetzt `random.shuffle`, dessen Ablauf nicht über Python-Versionen garantiert ist."""
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]

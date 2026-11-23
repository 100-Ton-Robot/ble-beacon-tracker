"""Deck PCB diameter for a duck spacing. Shared by make_pcbs.py (KiCad) and rf_model/sector_model.py (no KiCad), so
both use the same number. Values from ../parameters.csv."""
import math


def deck_diameter(P, spacing):
    """Larger of DECK_MIN_DIAMETER and the D hole's exposed pad + DECK_EDGE_MARGIN, rounded up to 0.1 mm."""
    inradius = P["FACE_WIDTH"] / (2 * math.sqrt(3))
    d = 2 * (inradius + spacing + P["PAD_EXPOSE"] / 2 + P["DECK_EDGE_MARGIN"])
    return max(P["DECK_MIN_DIAMETER"], math.ceil(d * 10 - 1e-9) / 10)

"""Line boil: hand-drawn wobble for vector art.

Traditional animation redraws every line each frame, so outlines shimmer
slightly. ``boil`` on an SVG layer makes a few copies of the file with every
coordinate nudged by seeded noise; the browser renderer cycles them at
``boil_fps`` (default 12, "on twos" at 24 fps). Amount 0.3–0.6 reads as
hand-drawn; above 1 it gets nervous on purpose.
"""

import random
import re

NUMBER = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?")
GEOMETRY = re.compile(r'(\s(?:d|points|cx|cy|x|y|x1|y1|x2|y2)=")([^"]*)(")')
VIEWBOX = re.compile(r'viewBox="([^"]+)"')


def variants(svg, amount, count=3, seed=1):
    """Return ``count`` jittered copies of an SVG document string."""
    box = VIEWBOX.search(svg)
    size = 100.0
    if box:
        parts = [float(value) for value in box.group(1).replace(",", " ").split()]
        if len(parts) == 4:
            size = max(parts[2], parts[3])
    reach = size * 0.0035 * float(amount)
    copies = []
    for index in range(count):
        rng = random.Random(seed * 1009 + index)

        def jitter(match):
            def shift(number):
                if "e" in number.group(0):
                    return number.group(0)
                return f"{float(number.group(0)) + rng.uniform(-reach, reach):.2f}"
            text = match.group(2)
            if match.group(1).strip().startswith("d=") or match.group(1).strip().startswith("points="):
                # Keep arc flags and radii stable: only nudge plain coordinate pairs.
                if re.search(r"[Aa]", text):
                    return match.group(0)
            return match.group(1) + NUMBER.sub(shift, text) + match.group(3)
        copies.append(GEOMETRY.sub(jitter, svg))
    return copies

"""build_chains must finish when a line runs from a fork back to the same fork
(it froze Blender once: the line was joined with itself forever).

blender -b --factory-startup -P fork_loop_test.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rizum_pattern_masks import core  # noqa: E402

co = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]], float)
# a square loop 0-1-2-3-0 with two tails at vertex 0: 0-4 and 0-5
pairs = np.array([[0, 1], [1, 2], [2, 3], [3, 0], [0, 4], [0, 5]])
chains = core.build_chains(pairs, co)
print("RESULT chains", [(list(map(int, ids)), closed) for ids, closed in chains])
# a 4x4 grid of edges: many forks
n = 5
g = [[i * n + j for j in range(n)] for i in range(n)]
gp = [(g[i][j], g[i][j + 1]) for i in range(n) for j in range(n - 1)] + \
     [(g[i][j], g[i + 1][j]) for i in range(n - 1) for j in range(n)]
gco = np.array([[j, i, 0] for i in range(n) for j in range(n)], float)
chains = core.build_chains(np.array(gp), gco)
print("RESULT grid chains", len(chains), "edges covered",
      sum(len(ids) - (0 if c else 1) for ids, c in chains), "of", len(gp))

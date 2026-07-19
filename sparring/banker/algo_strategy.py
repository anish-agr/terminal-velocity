"""Sparring bot: BANKER -- the ladder archetype that beat corner_hammer.

Replicates the 2W-4L ladder audit's killer pattern: a solid balanced turret
spread, shield supports, and ESCALATING banked scout waves (19 -> 22 -> 26 ->
30) aimed at the defender's corners, whose survivors run the edge diagonals.
Exists to regression-test the edge-run defenses; deterministic throughout.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
from _shared import (  # noqa: E402
    bootstrap_gamelib,
    unit_shorthands,
    MP,
)

bootstrap_gamelib()
import gamelib  # noqa: E402


TURRETS = [[3, 12], [24, 12], [7, 11], [20, 11], [11, 11], [16, 11],
           [13, 12], [14, 12], [1, 12], [26, 12], [5, 12], [22, 12]]
WALLS = [[0, 13], [27, 13], [1, 13], [26, 13], [13, 13], [14, 13]]
SUPPORTS = [[13, 2], [14, 2], [13, 4], [14, 4]]
LANES = [[13, 0], [14, 0]]      # deep cells: waves cross into enemy corners


class AlgoStrategy(gamelib.AlgoCore):
    def __init__(self):
        super().__init__()
        self.wave_idx = 0

    def on_game_start(self, config):
        self.config = config
        self.t = unit_shorthands(config)
        res = config.get("resources", {})
        self.income0 = float(res.get("bitsPerRound", 5.0))
        self.growth = float(res.get("bitGrowthRate", 1.0))
        self.interval = int(res.get("turnIntervalForBitSchedule", 10)) or 10
        self.decay = float(res.get("bitDecayPerRound", 0.25)) or 0.25

    def on_turn(self, turn_state):
        gs = gamelib.GameState(self.config, turn_state)
        gs.suppress_warnings(True)
        try:
            gs.attempt_spawn(self.t["TURRET"], TURRETS)
            gs.attempt_spawn(self.t["WALL"], WALLS)
            gs.attempt_spawn(self.t["SUPPORT"], SUPPORTS)
            gs.attempt_upgrade(SUPPORTS + TURRETS[:4])
            income = self.income0 + self.growth * (gs.turn_number // self.interval)
            # escalation: each wave banks a deeper fraction of the fixed point
            frac = min(1.0, 0.80 + 0.06 * self.wave_idx)
            threshold = frac * income / self.decay
            mp = gs.get_resource(MP)
            if mp >= threshold:
                lane = LANES[self.wave_idx % 2]
                gs.attempt_spawn(self.t["SCOUT"], [lane], 1000)
                self.wave_idx += 1
        except Exception:
            pass
        gs.submit_turn()


if __name__ == "__main__":
    AlgoStrategy().start()

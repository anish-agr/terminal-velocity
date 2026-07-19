"""Sparring bot: DEMO_BANKER -- the second loss archetype from the 7-game
ladder audit: a turret-line turtle that banks deep (frac 0.76-0.96) and sends
massed DEMOLISHER waves (13-19 at a time) that grind the defender's corner
walls from standoff range and walk in through the hole. Deterministic.
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


LINE = [[x, 13] for x in range(28)]
UPGRADES = [[x, 13] for x in range(0, 28, 2)]     # upgraded-heavy front
SUPPORTS = [[13, 3], [14, 3], [13, 5], [14, 5]]
LANES = [[13, 0], [14, 0]]


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
            gs.attempt_spawn(self.t["TURRET"], [c for c in LINE
                                                if c[0] not in (13, 14)])
            gs.attempt_spawn(self.t["SUPPORT"], SUPPORTS)
            gs.attempt_upgrade(UPGRADES)
            income = self.income0 + self.growth * (gs.turn_number // self.interval)
            threshold = 0.90 * income / self.decay
            mp = gs.get_resource(MP)
            if mp >= threshold:
                lane = LANES[self.wave_idx % 2]
                gs.attempt_spawn(self.t["DEMOLISHER"], [lane], 1000)
                self.wave_idx += 1
        except Exception:
            pass
        gs.submit_turn()


if __name__ == "__main__":
    AlgoStrategy().start()

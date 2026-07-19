"""Sparring bot: TURTLE_WALL -- the archetype behind losses in the 7-game
ladder audit (3W-4L @ ~1350).

Replicates the full turret-wall turtles (34-57 turrets AS the front line, few
upgrades) that blanked our offense while throwing huge banked scout waves
(frac 0.85-0.97 of the fixed point) whose survivors poured through the
defender's center funnel. Deterministic throughout.
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


# solid turret line, then a second row -- turrets ARE the wall.
# Upgraded to the observed top-team ("nemesis") profile: 8 upgraded supports,
# escalating waves (18 -> 42 scouts), a demolisher wave every ~4th, and tiny
# poke waves in between -- the exact bot that beat us in three ladder audits.
LINE = [[x, 13] for x in range(28)]
ROW2 = [[x, 12] for x in range(2, 26)]
UPGRADES = [[0, 13], [27, 13], [1, 13], [26, 13], [13, 13], [14, 13]]
SUPPORTS = [[13, 3], [14, 3], [12, 4], [15, 4],
            [13, 5], [14, 5], [12, 6], [15, 6]]
LANES = [[14, 0], [13, 0]]


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
            # leave the wave lane cells open until after spawning: the line
            # is rebuilt every turn from income, exactly like the ladder bots
            gs.attempt_spawn(self.t["TURRET"], [c for c in LINE
                                                if c[0] not in (13, 14)])
            gs.attempt_spawn(self.t["SUPPORT"], SUPPORTS[:4])
            gs.attempt_spawn(self.t["TURRET"], ROW2)
            gs.attempt_spawn(self.t["SUPPORT"], SUPPORTS)
            gs.attempt_upgrade(SUPPORTS[:4] + UPGRADES)
            income = self.income0 + self.growth * (gs.turn_number // self.interval)
            frac = min(0.97, 0.84 + 0.02 * self.wave_idx)
            threshold = frac * income / self.decay
            mp = gs.get_resource(MP)
            if mp >= threshold:
                lane = LANES[self.wave_idx % 2]
                unit = self.t["DEMOLISHER"] if self.wave_idx % 4 == 3 \
                    else self.t["SCOUT"]
                gs.attempt_spawn(unit, [lane], 1000)
                self.wave_idx += 1
        except Exception:
            pass
        gs.submit_turn()


if __name__ == "__main__":
    AlgoStrategy().start()

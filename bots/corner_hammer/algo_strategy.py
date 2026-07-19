"""corner_hammer — standalone ranked algo (pure python + gamelib, no deps).

The distilled elite meta from the 2026-07-18 replay study (19 games of the
visible #1 vs the hidden >2000 pool), hardened by two ladder audits of our own
ranked games (6 games @1349, then 7 games @~1350: 3W-4L). The second audit's
loss modes drive the v4 design:

  * every loss was to a full TURRET-WALL turtle (34-57 turrets as the front
    line). Our scout waves died on contact; theirs (bigger banks, no screen
    spending) poured through our center funnel gap or ground our corners with
    demolishers.
  * our threat screen choked our own offense: vs enemies that wave every ~7
    turns it fired every cycle and we attacked ONCE in an entire game.
  * vs permabankers (bank parked above the threat level for 30+ turns) the
    upward-crossing trigger never re-fired, so the screen missed the actual
    wave completely.

v4 answers, in order of blood lost:
  gate      the center funnel is now NORMALLY CLOSED (walls at the gap).
            Mega waves that used to pour through the gap now self-destruct on
            a sealed line for ZERO hp damage. The gate is remove-marked one
            turn before our own wave and rebuilt right after (75% refund
            cycle, net 0.5 SP per attack).
  predict   we record the enemy's bank at every real launch and screen when
            their bank re-reaches ~their own observed launch level. Armed
            once per enemy wave (re-armed only when they actually launch), so
            a hovering permabanker gets screened and our offense never
            starves.
  anti-demo when the enemy's last wave was demolisher-heavy the screen
            switches to the corner-most edge cells and grows: interceptors
            one-shot 5 hp demolishers and are the only unit that reaches a
            standoff demo line grinding our corner outside turret range.
  offense   lane choice = real pathfinding (sum of enemy turret damage along
            each candidate path); stall escalation compounds toward the bank
            fixed point; demolisher mode only fires when their front is
            upgraded-heavy (3.5-range turrets demos outrange) — vs base
            4.5-range turret walls demos die instantly and scouts chip the
            line via self-destruct instead.
  close-out ahead on hp late, we stop attacking entirely and spend every MP
            on defense: ties at the turn cap go to hp, then (we believe)
            compute time — a scripted bot wins that race.

v5 (second ladder audit, 4W-3L @1433): the gate mark used mp+income and
ignored MP decay, so it fired ~3 turns early and the funnel sat OPEN for the
whole approach window — both fast losses were waves walking through the
"sealed" gate. Now: decay-aware one-turn projection, never opening into a
predicted enemy launch (bounded to 2 postponements so permabankers can't
freeze our offense). Screens fire at ~their actual launch level (0.85 was
2-3 turns early and armed was already spent when the wave landed), scale to
6 vs mega banks, re-arm after 3 hover turns, aim by their observed spawn
side when breach heat is cold, and pick the first free diagonal cells.
Proven mega-wavers also trigger walls on the outer scoring-diagonal cells
(pushing their corner run deeper through turret coverage) and the support
battery doubles to 8 with earlier upgrades — our waves were dying ON their
edge cells (94 deaths at one goal cell in the turn-100 loss).

v6 (third audit @1427 + 9-game study of the 1900-2200 teams): the recurring
"nemesis" that blanked our offense in all three audits IS a top team, and
the games where other elites beat it share one formula, which v6 adopts:
8-11 supports built EARLY and upgraded (shields carry waves through turret
fire — even demolishers survive at 5+8 hp), heavy turret-upgrade discipline,
waves split ~70/30 across BOTH center lanes (both scoring diagonals live at
once: no concentrated kill zone), and a demolisher wave every ~3rd launch.
Elites run no screens/gates — those stay for the mid-ladder we actually
face, with two audit fixes: launch level learns from max (probers poisoned
min with tiny waves until the real one landed unscreened) and demo screens
scale with their bank (13-17-demo lines were out-massing 5 interceptors).

Every number is read from the game config at runtime. Every turn is wrapped:
a failure still submits a legal (possibly empty) turn. ~1 ms per turn.
"""

import gamelib


# ---------------------------------------------------------------------------
# layout (engine always presents our side as the bottom half — no flip)
# ---------------------------------------------------------------------------
CORNER_WALLS = [[0, 13], [27, 13]]
FLANK_TURRETS = [[2, 13], [3, 13], [24, 13], [25, 13], [1, 12], [26, 12]]
# 16-dmg upgrades early and DENSE at the corners: ladder waves arrive
# shielded (+2 -> 17 hp scouts), so base 5-dmg turrets need 4 hits each.
# (3,13)/(24,13) intentionally stay base longer: base range 4.5 reaches a
# standoff demolisher line that upgraded 3.5-range turrets cannot.
FIRST_UPGRADES = [[2, 13], [25, 13], [1, 12], [26, 12]]
GATE_WALLS = [[13, 13], [14, 13]]     # center funnel gap — NORMALLY CLOSED
RING_TURRETS = [[12, 11], [15, 11], [11, 12], [16, 12]]
ROW_TURRETS = [[x, 13] for x in (1, 26, 4, 23, 5, 22, 6, 21, 7, 20,
                                 8, 19, 9, 18, 10, 17, 11, 16, 12, 15)]
BACK_TURRETS = [[2, 12], [25, 12], [5, 12], [22, 12], [8, 12], [19, 12]]
SUPPORTS = [[12, 2], [15, 2], [11, 3], [16, 3],
            [12, 4], [15, 4], [11, 5], [16, 5]]
LATE_UPGRADES = [[x, 13] for x in (4, 6, 8, 10, 12, 15, 17, 19, 21, 23)]
# scoring-edge geometry: the enemy scores at (25,11)/(2,11), only ~2 cells
# behind the wall line — defense must sit ON that diagonal, not deep.
DIAG_TURRETS = [[4, 11], [23, 11]]
# 31-game audit: loss breaches cluster 4-7 cells DOWN the diagonal (the
# deep run past the corner). One upgraded turret here covers that whole
# zone -- (21,9) reaches (23,9) through (20,6) at 3.5 range.
DEEP_TURRETS = [[6, 9], [21, 9]]
HOT_LEFT = [[4, 12], [3, 12], [1, 12], [6, 12], [4, 11]]
HOT_RIGHT = [[23, 12], [24, 12], [26, 12], [21, 12], [23, 11]]
# vs proven mega-wavers: wall the two outermost scoring-diagonal cells so a
# corner-crossing horde must run DEEPER down the diagonal, staying inside
# turret coverage for longer (this is exactly the geometry that beat us)
DIAG_WALLS_L = [[2, 11], [3, 10]]
DIAG_WALLS_R = [[25, 11], [24, 10]]
# interceptor screens: first FREE cells walking down the scoring diagonal
# (skips cells occupied by DIAG_WALLS when the mega response is active)
SCREEN_L = [[2, 11], [3, 10], [4, 9], [5, 8], [6, 7], [7, 6]]
SCREEN_R = [[25, 11], [24, 10], [23, 9], [22, 8], [21, 7], [20, 6]]

WAVE_FRACTION = 0.875     # of the income/decay fixed point (winners' commit)
STALL_ESCALATE = 1.12     # per scoreless wave: bank deeper (compounds)
BANK_CAP_FRAC = 0.95      # decay makes the fixed point unreachable; cap here
SPLIT_MIN = 12            # waves this big put 1/4 in a trailing second stack
WAVE_SEEN_INCOMES = 1.5   # enemy one-turn mobile spend >= this x income
#   counts as a real wave (screens are 1-3 MP and must not count)
PREDICT_FRAC = 0.97       # screen when their bank reaches ~their observed
#   launch level (0.85 fired 2-3 turns early: armed was spent, the actual
#   wave arrived unscreened -- 7-game v4 ladder audit)
THREAT_BANK_FRAC = 0.70   # pre-observation fallback: bank >= this x their
#   fixed point means a wave lands within ~1-2 turns
REARM_TURNS = 3           # screened but they hovered without launching for
#   this many turns -> re-arm (bounded anti-starve, few MP per hover cycle)
EARLY_TURNS = 12          # before any launch history, this early window
EARLY_BANK_FRAC = 0.45    #   screens on a sensitive trigger: 13 of 18
#   audit losses were first breached by turn 11 -- rushers at our rating
#   dump waves at banks far below the 0.70 banker fallback
MEGA_INCOMES = 3.0        # their bank >= this x income is a mega wave:
#   screens grow to 6 and the diagonal walls go up
STALL_WAVES = 2           # scoreless waves before considering demolishers
CLOSEOUT_TURN = 80        # engine caps games at 100 turns (not in config);
CLOSEOUT_LEAD = 8         #   ahead by this much hp late -> defend the win


class AlgoStrategy(gamelib.AlgoCore):
    def __init__(self):
        super().__init__()
        # cross-turn adaptive state (a live algo may remember; sim bots can't)
        self.heat = {"L": 0.0, "R": 0.0}
        self.prev_enemy_mp = 0.0
        self.enemy_scout_mp = 0.0      # their mobile spend seen last turn
        self.enemy_demo_mp = 0.0
        self.launch_mps = []           # their bank at each observed launch
        self.screen_armed = True       # one screen per enemy wave build-up
        self.screen_turn = None        # when we last fired one (re-arm timer)
        self.rearm_used = False        # at most ONE re-arm per build-up
        self.demo_threat = False       # their last real wave was demo-heavy
        self.mega_threat = False       # they have shown a mega wave
        self.enemy_spawn_xs = []       # absolute x of their mobile spawns
        self.side_hint_left = None     # their waves aim at our left?
        self.stalled_waves = 0
        self.demo_mode = False
        self.wave_idx = 0              # ours; every 3rd wave is demolishers
        self.last_wave_turn = None
        self.enemy_hp_at_wave = None
        self.gate_state = "closed"     # closed -> opening (marked) -> closed
        self.postponed = 0             # attack turns delayed by their threat
        self.screen_ema = 0.0          # avg MP/turn spent on screens

    # ------------------------------------------------------------------
    def on_game_start(self, config):
        self.config = config
        info = config["unitInformation"]
        self.WALL = info[0]["shorthand"]
        self.SUPPORT = info[1]["shorthand"]
        self.TURRET = info[2]["shorthand"]
        self.SCOUT = info[3]["shorthand"]
        self.DEMOLISHER = info[4]["shorthand"]
        self.INTERCEPTOR = info[5]["shorthand"]
        self.scout_cost = float(info[3].get("cost2", 1.0))
        self.demo_cost = float(info[4].get("cost2", 2.0))
        self.intc_cost = float(info[5].get("cost2", 1.0))
        self.t_dmg = float(info[2].get("attackDamageWalker", 5.0))
        self.t_dmg_up = float(info[2].get("upgrade", {})
                              .get("attackDamageWalker", self.t_dmg))
        self.wall_hp = float(info[0].get("startHealth", 40.0)) or 40.0
        res = config.get("resources", {})
        self.mp_base = float(res.get("bitsPerRound", 5.0))
        self.mp_growth = float(res.get("bitGrowthRate", 1.0))
        self.mp_interval = int(res.get("turnIntervalForBitSchedule", 10)) or 10
        self.mp_decay = float(res.get("bitDecayPerRound", 0.25)) or 0.25

    # ------------------------------------------------------------------
    def on_action_frame(self, turn_string):
        """Breach heat (where WE are being hit) + enemy wave composition."""
        try:
            import json
            state = json.loads(turn_string)
            events = state.get("events", {})
            for b in events.get("breach", []):
                if len(b) >= 5 and b[4] == 2:          # they breached us
                    x = int(b[0][0])
                    if x < 9:
                        self.heat["L"] += 1.0
                    elif x > 18:
                        self.heat["R"] += 1.0
            for s in events.get("spawn", []):
                if len(s) >= 4 and s[3] == 2:
                    if s[1] == 3:
                        self.enemy_scout_mp += self.scout_cost
                        self.enemy_spawn_xs.append(int(s[0][0]))
                    elif s[1] == 4:
                        self.enemy_demo_mp += self.demo_cost
                        self.enemy_spawn_xs.append(int(s[0][0]))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def on_turn(self, turn_state):
        game_state = gamelib.GameState(self.config, turn_state)
        game_state.suppress_warnings(True)
        try:
            self._play(game_state)
        except Exception:
            pass                       # a broken turn still submits legally
        game_state.submit_turn()

    # ------------------------------------------------------------------
    def _play(self, gs):
        turn = gs.turn_number
        income = self.mp_base + self.mp_growth * (turn // self.mp_interval)
        fixed_point = income / self.mp_decay

        # ---- settle what the enemy did last turn -------------------------
        wave_mp = self.enemy_scout_mp + self.enemy_demo_mp
        if wave_mp >= WAVE_SEEN_INCOMES * income:
            # a real launch: their bank last turn IS their commit level
            self.launch_mps.append(self.prev_enemy_mp)
            self.demo_threat = self.enemy_demo_mp > self.enemy_scout_mp
            self.screen_armed = True
            self.rearm_used = False
            if wave_mp >= MEGA_INCOMES * income:
                self.mega_threat = True
            if self.enemy_spawn_xs:
                # their right-of-center spawns cross toward OUR left corner
                # (7-game v4 audit: breach side tracked spawn side exactly)
                mean_x = sum(self.enemy_spawn_xs) / len(self.enemy_spawn_xs)
                self.side_hint_left = mean_x > 13.5
        self.enemy_scout_mp = self.enemy_demo_mp = 0.0
        self.enemy_spawn_xs = []
        for k in self.heat:
            self.heat[k] *= 0.5

        # ---- did our last wave actually score? ---------------------------
        if self.last_wave_turn is not None and turn > self.last_wave_turn:
            if gs.enemy_health >= self.enemy_hp_at_wave:
                self.stalled_waves += 1
            else:
                self.stalled_waves = 0
                self.demo_mode = False
            self.last_wave_turn = None
        if self.stalled_waves >= STALL_WAVES and not self.demo_mode:
            # demos outrange upgraded (3.5) turrets but a base 4.5-range
            # turret wall one-shots them: only switch when it can pay off
            self.demo_mode = self._their_front_upgraded_heavy(gs)

        closeout = (turn >= CLOSEOUT_TURN and
                    gs.my_health - gs.enemy_health >= CLOSEOUT_LEAD)
        gate_open_turn = self.gate_state == "opening"   # marked last turn

        # turn-0 insurance: one audit game was dead by turn 6 to a 5-scout
        # dribble starting at turn 0. Two interceptors on the diagonals
        # cover the unknown opening for 2 MP -- cheap against builders,
        # game-saving against the junk rushes that live at this rating
        if turn == 0:
            gs.attempt_spawn(self.INTERCEPTOR, [[4, 9]], 1)
            gs.attempt_spawn(self.INTERCEPTOR, [[23, 9]], 1)

        # ---- defense wishlist, priority order (gamelib truncates at SP) --
        gs.attempt_spawn(self.WALL, CORNER_WALLS)
        gs.attempt_upgrade(CORNER_WALLS)              # 120 hp for 1 SP
        gs.attempt_spawn(self.TURRET, FLANK_TURRETS)
        if not gate_open_turn:
            gs.attempt_spawn(self.WALL, GATE_WALLS)   # keep the funnel SEALED
        # diagonal cover in the OPENING build (fits in the 40 starting SP):
        # every loss in the 8-game v8 audit leaked down the diagonals by
        # turn 13 -- these used to be built around turn 8-12
        gs.attempt_spawn(self.TURRET, DIAG_TURRETS)
        gs.attempt_spawn(self.TURRET, DEEP_TURRETS)
        gs.attempt_upgrade(FIRST_UPGRADES)
        # shields EARLY: every top-team win over the turret-wall archetype ran
        # 8-11 upgraded supports (waves arrive shielded; even demolishers
        # survive turret fire at 5+8 hp) -- but only half the battery before
        # the ring/diag turrets: the full 4 up front left the early defense
        # 4 turns thin and nearly flipped two engine regressions
        gs.attempt_spawn(self.SUPPORT, SUPPORTS[:2])
        gs.attempt_upgrade(SUPPORTS[:2])
        if self.heat["L"] > self.heat["R"] and self.heat["L"] >= 2.0:
            gs.attempt_spawn(self.TURRET, HOT_LEFT)
            gs.attempt_upgrade(HOT_LEFT + FLANK_TURRETS[:2])
        elif self.heat["R"] > self.heat["L"] and self.heat["R"] >= 2.0:
            gs.attempt_spawn(self.TURRET, HOT_RIGHT)
            gs.attempt_upgrade(HOT_RIGHT + FLANK_TURRETS[2:4])
        # diagonal defense BEFORE the ring: with the funnel sealed nothing
        # reaches the ring early, while 13 of 18 audit losses leaked down
        # the diagonals by turn 11
        if self.mega_threat:
            # push their corner run deeper into turret coverage
            gs.attempt_spawn(self.WALL, DIAG_WALLS_L + DIAG_WALLS_R)
            gs.attempt_upgrade(DIAG_WALLS_L + DIAG_WALLS_R)
        gs.attempt_spawn(self.SUPPORT, SUPPORTS[:4])
        gs.attempt_upgrade(SUPPORTS[:4])
        gs.attempt_spawn(self.TURRET, RING_TURRETS)
        gs.attempt_spawn(self.TURRET, ROW_TURRETS)
        gs.attempt_upgrade(FLANK_TURRETS)
        gs.attempt_spawn(self.SUPPORT, SUPPORTS)      # full shield battery
        gs.attempt_upgrade(SUPPORTS)
        gs.attempt_upgrade(LATE_UPGRADES)
        gs.attempt_spawn(self.TURRET, BACK_TURRETS)

        # ---- offense: closed-gate wave cycle -----------------------------
        # threshold budgets off EFFECTIVE income (minus average screen
        # spend): the raw fixed point sits at the bank's asymptote, so even
        # ~0.7 MP/turn of screening made the old threshold unreachable and
        # froze the offense for 40 turns (engine-verified vs turtle_wall)
        mp = gs.get_resource(gs.MP)
        eff_income = max(0.6 * income, income - self.screen_ema)
        esc = STALL_ESCALATE ** min(self.stalled_waves, 2)
        threshold = (min(WAVE_FRACTION * esc, BANK_CAP_FRAC) *
                     eff_income / self.mp_decay)
        enemy_mp = gs.get_resource(gs.MP, 1)
        launch_level = self._enemy_launch_level(fixed_point)
        enemy_imminent = enemy_mp >= launch_level
        fired = False
        if not closeout:
            if gate_open_turn:
                self.gate_state = "closed"            # rebuild resumes next turn
                if mp >= 0.95 * threshold:
                    self._fire_wave(gs, gs.get_resource(gs.MP), turn)
                    fired = True
                    self.postponed = 0
            # one-turn bank projection WITH decay: v4's mp+income test marked
            # ~3 turns early and the funnel sat open the whole approach --
            # ladder waves walked straight through the "sealed" gate
            elif (1.0 - self.mp_decay) * mp + income >= threshold:
                # first-wave collision guard: 5 of 6 overnight losses were
                # first-breached at t8-10 -- their FIRST wave arriving the
                # turn our gate opened. Before their first observed launch,
                # wait it out on a sealed line (no postpone cap until t15)
                first_wave_window = (not self.launch_mps and turn <= 14 and
                                     enemy_mp >= 0.55 * fixed_point)
                if first_wave_window:
                    pass                              # stay sealed, keep banking
                elif enemy_imminent and self.postponed < 2:
                    self.postponed += 1               # don't open into their wave
                elif all(gs.contains_stationary_unit(c) for c in GATE_WALLS):
                    gs.attempt_remove(GATE_WALLS)     # open for NEXT turn only
                    self.gate_state = "opening"
                elif mp >= threshold:
                    self._fire_wave(gs, mp, turn)     # gate already open/dead
                    fired = True
        elif gate_open_turn:
            self.gate_state = "closed"                # close-out: stay sealed

        # ---- predictive screen (after offense: never starve our wave) ----
        spent = 0
        if not fired and self.gate_state != "opening":
            spent = self._maybe_screen(gs, turn, income, enemy_mp,
                                       launch_level, threshold, closeout)
        self.screen_ema = 0.9 * self.screen_ema + 0.1 * spent * self.intc_cost

        self.prev_enemy_mp = enemy_mp

    # ------------------------------------------------------------------
    def _enemy_launch_level(self, fixed_point):
        # max, not min: probers throw tiny early waves precisely where a min
        # would set the level so low that screens fire on noise and the real
        # wave lands unscreened (27-breach ladder loss, third audit)
        if self.launch_mps:
            return PREDICT_FRAC * max(self.launch_mps[-3:])
        return THREAT_BANK_FRAC * fixed_point

    def _maybe_screen(self, gs, turn, income, enemy_mp, launch_level,
                      threshold, closeout):
        """Interceptors on the scoring diagonal the turn their wave is due.
        Armed once per enemy build-up: re-armed when they actually launch,
        or ONCE after REARM_TURNS of hovering. Vs a frequent mega-waver the
        unbounded v5 re-arm bled ~1.7 MP/turn and froze our offense for 48
        turns (engine-verified) -- hence the cycle cap and the tempo guard."""
        if not self.launch_mps and turn <= EARLY_TURNS:
            # rush insurance: no launch history yet, immature corners.
            # Builders cross any bank level early just by saving -- only a
            # SPARSE enemy board (they're hoarding for units, not building)
            # marks a real rush, else this wastes ~8 MP on bankers
            fixed_point = income / self.mp_decay
            # tier 1: sparse board = hoarding rusher, hair trigger.
            # tier 2: ANY opponent's first launch (bank >= 0.60 fp) -- the
            # builder gate blocked all early screens while builders' first
            # waves landed at t8-10 (5 of 6 overnight losses)
            rusher = (enemy_mp >= EARLY_BANK_FRAC * fixed_point and
                      self._enemy_struct_count(gs) < 8)
            first_wave = enemy_mp >= 0.60 * fixed_point
            if (rusher or first_wave) and \
                    (self.screen_turn is None or
                     turn - self.screen_turn >= 2):
                spent = (self._screen_side(gs, SCREEN_R, 2) +
                         self._screen_side(gs, SCREEN_L, 2))
                if spent:
                    self.screen_turn = turn
                return spent
            return 0
        if (not self.screen_armed and not self.rearm_used and
                self.screen_turn is not None and
                turn - self.screen_turn >= REARM_TURNS and
                enemy_mp >= launch_level):
            self.screen_armed = True               # they hovered; re-arm once
            self.rearm_used = True
        if not (self.screen_armed and enemy_mp >= launch_level):
            return 0
        mega = self.mega_threat and enemy_mp >= MEGA_INCOMES * income
        # tempo guard: near our own wave, let the static defense eat a
        # MEDIUM wave rather than bleed the bank -- megas are always screened
        if not closeout and not mega and \
                gs.get_resource(gs.MP) >= 0.7 * threshold:
            return 0
        # side: breach heat first, else their observed spawn side
        if abs(self.heat["R"] - self.heat["L"]) >= 1.0:
            hot_r = self.heat["R"] > self.heat["L"]
        elif self.side_hint_left is not None:
            hot_r = not self.side_hint_left
        else:
            hot_r = True
        hot, cold = (SCREEN_R, SCREEN_L) if hot_r else (SCREEN_L, SCREEN_R)
        if closeout:
            n_hot, n_cold = 4, 2                   # MP is free: wall of bodies
        elif self.demo_threat and enemy_mp >= 2.5 * income:
            n_hot, n_cold = 4, 2                   # big demo line: 1 kill each
        elif mega:
            n_hot, n_cold = 4, 1                   # trust the side prediction
        elif self.demo_threat:
            n_hot, n_cold = 3, 2
        else:
            n_hot, n_cold = 2, 1
        spent = 0
        spent += self._screen_side(gs, hot, n_hot)
        spent += self._screen_side(gs, cold, n_cold)
        if spent:
            self.screen_armed = False
            self.screen_turn = turn
        return spent

    def _enemy_struct_count(self, gs):
        n = 0
        try:
            for y in range(14, 28):
                for x in range(28):
                    if not gs.game_map.in_arena_bounds([x, y]):
                        continue
                    for u in gs.game_map[x, y] or []:
                        if u.stationary and u.player_index == 1:
                            n += 1
        except Exception:
            return 99                  # unknown -> assume builder, no screen
        return n

    def _screen_side(self, gs, cells, n):
        """Spawn up to n interceptors on the first FREE diagonal cells
        (skips cells occupied by the mega-response walls)."""
        spent = 0
        for spot in cells:
            if spent >= n or gs.get_resource(gs.MP) < self.intc_cost:
                break
            if gs.contains_stationary_unit(spot):
                continue
            spent += gs.attempt_spawn(self.INTERCEPTOR, [spot], 1)
        return spent

    # ------------------------------------------------------------------
    def _fire_wave(self, gs, mp, turn):
        """Dual-center split, the elite formula: the bulk down the cheaper
        lane, the rest down the other, so both scoring diagonals are live
        and the defense cannot concentrate focus fire on one path. Every
        top-team win over the turret-wall archetype split ~70/30 across
        (13,0)+(14,0) and alternated in a demolisher wave every ~3rd."""
        self.wave_idx += 1
        heavy, light = self._pick_lanes(gs)
        # upgrade-heavy fronts (3.5-range turrets) are outranged by demos --
        # and shred scouts at 16 dmg. Choose composition by THEIR front at
        # fire time: waiting for the every-3rd rotation lost three ladder
        # games (offense dealt 1-3 breaches) that ended before wave 3
        demo_wave = (self.demo_mode or self.wave_idx % 3 == 0 or
                     self._their_front_upgraded_heavy(gs))
        if demo_wave:
            n = int(mp // self.demo_cost)
            if n >= 3:
                n_h = max(1, (2 * n) // 3)
                gs.attempt_spawn(self.DEMOLISHER, [heavy], n_h)
                gs.attempt_spawn(self.DEMOLISHER, [light], n - n_h)
            else:
                demo_wave = False
        if not demo_wave:
            n = int(mp // self.scout_cost)
            n_h = max(1, (7 * n) // 10)
            gs.attempt_spawn(self.SCOUT, [heavy], n_h)
            if n - n_h > 0:
                gs.attempt_spawn(self.SCOUT, [light], n - n_h)
        self.last_wave_turn = turn
        self.enemy_hp_at_wave = gs.enemy_health

    # ------------------------------------------------------------------
    def _pick_lanes(self, gs):
        """Rank candidate spawn lanes by pathfound enemy turret damage.
        Candidates include the FLANK spawns that run the edge diagonal into
        their corner -- the pattern every >2100 win over the turret-wall
        archetype shares (their waves rotate lanes; fixed center lanes are
        exactly what plateaus against a wall). Bulk goes to the cheapest
        lane, the 30% split to the second-cheapest."""
        cands = [[13, 0], [14, 0], [5, 8], [22, 8]]
        scored = []
        try:
            for c in cands:
                d = self._path_damage(gs, c)
                if d is not None:
                    scored.append((d, c))
        except Exception:
            pass
        if len(scored) >= 2:
            scored.sort(key=lambda t: t[0])
            return scored[0][1], scored[1][1]
        left = self._their_left_is_weaker(gs)
        return ([13, 0], [14, 0]) if left else ([14, 0], [13, 0])

    def _path_damage(self, gs, spawn):
        path = gs.find_path_to_edge(spawn)
        if not path:
            return None
        dmg = 0.0
        for cell in path:
            if cell[1] < 14:
                continue
            for u in gs.get_attackers(cell, 0):
                dmg += self.t_dmg_up if u.upgraded else self.t_dmg
        edge = gs.game_map.get_edge_locations(gs.get_target_edge(spawn))
        if list(path[-1]) not in [list(c) for c in edge]:
            dmg += 60.0            # self-destruct path: heavy penalty
        return dmg

    # ------------------------------------------------------------------
    def _their_front_upgraded_heavy(self, gs):
        """Upgraded (3.5-range) turrets on their front rows outnumber base
        (4.5-range) ones -> demolishers can grind from standoff range."""
        up = base = 0
        try:
            for y in (14, 15, 16):
                for x in range(28):
                    if not gs.game_map.in_arena_bounds([x, y]):
                        continue
                    for u in gs.game_map[x, y] or []:
                        if (u.stationary and u.player_index == 1 and
                                u.unit_type == self.TURRET):
                            if u.upgraded:
                                up += 1
                            else:
                                base += 1
        except Exception:
            return False
        return up > base

    # ------------------------------------------------------------------
    def _their_left_is_weaker(self, gs):
        """Fallback lane heuristic: score both enemy corner zones (turret
        damage, upgrade-aware, plus wall presence). Tie -> their left, the
        hottest leak lane in the ranked meta sample."""
        a = b = 0.0
        try:
            for x, y, right_zone in self._zone_cells():
                if not gs.game_map.in_arena_bounds([x, y]):
                    continue
                for u in gs.game_map[x, y] or []:
                    if not u.stationary or u.player_index != 1:
                        continue
                    if u.unit_type == self.TURRET:
                        val = self.t_dmg_up if u.upgraded else self.t_dmg
                    elif u.unit_type == self.WALL:
                        val = u.health / self.wall_hp
                    else:
                        continue
                    if right_zone:
                        a += val         # our top-right == their left corner
                    else:
                        b += val
        except Exception:
            pass
        return a <= b

    @staticmethod
    def _zone_cells():
        for y in range(14, 21):
            for x in range(21, 28):
                yield x, y, True
            for x in range(0, 7):
                yield x, y, False


if __name__ == "__main__":
    AlgoStrategy().start()

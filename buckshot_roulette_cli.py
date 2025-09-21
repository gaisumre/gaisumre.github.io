#!/usr/bin/env python3
"""
Tube Roulette — a console homage to BUCKSHOT ROULETTE (mechanics clone)

Notes
-----
- This is an educational, terminal‑based prototype inspired by BUCKSHOT ROULETTE.
- No original art, audio, text, or proprietary assets are used here. Mechanics are re‑implemented.
- Default rules:
    • Shotgun is tube‑fed; each round loads 2–8 shells in a random order.
    • You see the counts of live vs blanks each round (order is hidden).
    • If you shoot yourself with a BLANK, your turn continues; otherwise your turn ends.
    • Items: MagnifyingGlass, Beer, Handcuffs, HandSaw, Inverter, BurnerPhone, Cigarette, Adrenaline.
- Singleplayer vs a simple heuristic Dealer AI.

Run
---
python buckshot_roulette_cli.py

"""
from __future__ import annotations
import random
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional, Tuple

# ----------------------------- Core model ----------------------------------

class Shell(Enum):
    LIVE = 1
    BLANK = 0

@dataclass
class Shotgun:
    shells: List[Shell]
    index: int = 0  # points at current chambered shell

    @staticmethod
    def load(min_shells: int = 2, max_shells: int = 8) -> "Shotgun":
        n = random.randint(min_shells, max_shells)
        # ensure at least 1 live and 1 blank
        live_count = random.randint(1, n - 1)
        blanks = n - live_count
        shells = [Shell.LIVE] * live_count + [Shell.BLANK] * blanks
        random.shuffle(shells)
        return Shotgun(shells=shells)

    def remaining(self) -> int:
        return len(self.shells) - self.index

    def counts_remaining(self) -> Tuple[int, int]:
        # (live, blank)
        rem = self.shells[self.index :]
        return rem.count(Shell.LIVE), rem.count(Shell.BLANK)

    def peek_current(self) -> Shell:
        return self.shells[self.index]

    def fire(self) -> Shell:
        """Returns the shell that was fired and advances the index."""
        if self.index >= len(self.shells):
            raise RuntimeError("Tried to fire an empty shotgun.")
        s = self.shells[self.index]
        self.index += 1
        return s

    def eject_current(self) -> Shell:
        """Eject the current shell without firing (Beer effect)."""
        return self.fire()

    def invert_current(self):
        """Flip the current shell LIVE<->BLANK (Inverter)."""
        if self.index >= len(self.shells):
            return
        self.shells[self.index] = (
            Shell.BLANK if self.shells[self.index] is Shell.LIVE else Shell.LIVE
        )

# ----------------------------- Items ---------------------------------------

class ItemId(Enum):
    MAGNIFYING_GLASS = auto()
    BEER = auto()
    HANDCUFFS = auto()
    HAND_SAW = auto()
    INVERTER = auto()
    BURNER_PHONE = auto()
    CIGARETTE = auto()
    ADRENALINE = auto()

@dataclass
class Item:
    id: ItemId
    name: str
    desc: str

    def use(self, game: "Game", user: "Actor", target: "Actor") -> None:
        raise NotImplementedError

# Utility to register item classes
ITEM_REGISTRY: Dict[ItemId, Item] = {}

def register_item(item: Item):
    ITEM_REGISTRY[item.id] = item
    return item

# Knowledge helpers
@dataclass
class Knowledge:
    current_known: Optional[Shell] = None  # from Magnifying Glass
    # absolute shot index -> Shell, from Burner Phone
    known_positions: Dict[int, Shell] = field(default_factory=dict)

# ----------------------------- Actors --------------------------------------

@dataclass
class Actor:
    name: str
    max_hp: int = 4
    hp: int = 4
    inventory: List[ItemId] = field(default_factory=list)
    skip_next: bool = False
    dmg_mult: int = 1
    ai: bool = False
    knowledge: Knowledge = field(default_factory=Knowledge)

    def is_alive(self) -> bool:
        return self.hp > 0

    def heal(self, n: int = 1):
        self.hp = min(self.max_hp, self.hp + n)

    def hurt(self, n: int = 1):
        self.hp -= n

    def take_item(self, item_id: ItemId):
        self.inventory.append(item_id)

    def pop_item(self, item_id: ItemId) -> Optional[ItemId]:
        if item_id in self.inventory:
            self.inventory.remove(item_id)
            return item_id
        return None

# ----------------------------- Items impl ----------------------------------

class MagnifyingGlass(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        shell = game.shotgun.peek_current()
        user.knowledge.current_known = shell
        game.log(f"[{user.name}] uses Magnifying Glass → Current shell is {'LIVE' if shell is Shell.LIVE else 'BLANK'}.")

register_item(MagnifyingGlass(ItemId.MAGNIFYING_GLASS, "Magnifying Glass", "Reveal current shell."))

class Beer(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        if game.shotgun.remaining() == 0:
            game.log(f"[{user.name}] tries Beer, but the gun is empty.")
            return
        s = game.shotgun.eject_current()
        # Ejecting a shell reveals its type to both players
        user.knowledge.current_known = None
        game.other(user).knowledge.current_known = None
        game.log(f"[Beer] {user.name} racks the shotgun → Ejected {'LIVE' if s is Shell.LIVE else 'BLANK'}.")

register_item(Beer(ItemId.BEER, "Beer", "Eject (rack) current shell without firing."))

class Handcuffs(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        target.skip_next = True
        game.log(f"[{user.name}] slaps Handcuffs → {target.name}'s next turn is skipped.")

register_item(Handcuffs(ItemId.HANDCUFFS, "Handcuffs", "Opponent skips next turn."))

class HandSaw(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        user.dmg_mult = 2
        game.log(f"[{user.name}] uses Hand Saw → Next live shot deals DOUBLE damage.")

register_item(HandSaw(ItemId.HAND_SAW, "Hand Saw", "Next live shot deals double damage (this turn only)."))

class Inverter(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        game.shotgun.invert_current()
        # Update knowledge if current_known set
        if user.knowledge.current_known is not None:
            user.knowledge.current_known = (
                Shell.BLANK if user.knowledge.current_known is Shell.LIVE else Shell.LIVE
            )
        game.log(f"[{user.name}] flips the polarity with Inverter → Current shell toggled.")

register_item(Inverter(ItemId.INVERTER, "Inverter", "Flip the current shell's polarity (live↔blank)."))

class BurnerPhone(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        rem = game.shotgun.remaining()
        if rem <= 1:
            game.log(f"[{user.name}] uses Burner Phone → 'How unfortunate…' (only one shell left).")
            return
        # choose a random future shell (relative to current)
        rel_idx = random.randint(1, rem - 1)
        abs_idx = game.shotgun.index + rel_idx
        shell = game.shotgun.shells[abs_idx]
        user.knowledge.known_positions[abs_idx] = shell
        game.log(
            f"[Burner Phone] A voice whispers: 'Shell {rel_idx + 1} is {'LIVE' if shell is Shell.LIVE else 'BLANK'}.'"
        )

register_item(BurnerPhone(ItemId.BURNER_PHONE, "Burner Phone", "Reveal a random future shell (relative to current)."))

class Cigarette(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        before = user.hp
        user.heal(1)
        game.log(f"[{user.name}] smokes → +1 HP ({before}→{user.hp}).")

register_item(Cigarette(ItemId.CIGARETTE, "Cigarette", "Heal 1 HP (cannot overheal)."))

class Adrenaline(Item):
    def use(self, game: "Game", user: Actor, target: Actor) -> None:
        if not target.inventory:
            game.log(f"[{user.name}] uses Adrenaline → Nothing to steal.")
            return
        # Player chooses which to steal; AI steals random
        if user.ai:
            steal_id = random.choice(target.inventory)
        else:
            steal_id = game.prompt_choose_item(target, prompt="Choose an item to steal and use now")
        if steal_id is None:
            game.log(f"[{user.name}] cancels the steal.")
            return
        target.pop_item(steal_id)
        game.log(f"[Adrenaline] {user.name} steals {ITEM_REGISTRY[steal_id].name} from {target.name} and uses it!")
        # Use immediately
        ITEM_REGISTRY[steal_id].use(game, user, target)

register_item(Adrenaline(ItemId.ADRENALINE, "Adrenaline", "Steal one opponent item and use it immediately."))

# ----------------------------- Game engine ---------------------------------

@dataclass
class Config:
    min_shells: int = 2
    max_shells: int = 8
    player_max_hp: int = 4
    dealer_max_hp: int = 4
    items_per_round: Tuple[int, int] = (2, 4)  # inclusive range per actor per new round
    seed: Optional[int] = None

class Game:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if cfg.seed is not None:
            random.seed(cfg.seed)
        self.player = Actor("You", max_hp=cfg.player_max_hp, hp=cfg.player_max_hp)
        self.dealer = Actor("Dealer", ai=True, max_hp=cfg.dealer_max_hp, hp=cfg.dealer_max_hp)
        self.turn: Actor = self.player  # player always starts
        self.shotgun: Shotgun = Shotgun.load(cfg.min_shells, cfg.max_shells)
        self.round_no = 1
        self.transcript: List[str] = []
        # give initial items for round 1 as per simple mode (none) — then items from round 2+
        self.deal_items()  # deal for round 1 as well to keep things lively

    # ------------- helpers -------------
    def other(self, a: Actor) -> Actor:
        return self.dealer if a is self.player else self.player

    def log(self, msg: str):
        self.transcript.append(msg)
        print(msg)

    def deal_items(self):
        for who in (self.player, self.dealer):
            who.inventory.clear()
            k = random.randint(*self.cfg.items_per_round)
            pool = list(ItemId)
            # Optional: in early rounds, reduce complexity by avoiding too many advanced items
            who.inventory.extend(random.sample(pool, k=k))
            # clear knowledge each round
            who.knowledge = Knowledge()

    # ------------- UI -------------
    def show_state(self):
        live, blank = self.shotgun.counts_remaining()
        print("\n" + "=" * 64)
        print(f"Round {self.round_no} | Shells left: {self.shotgun.remaining()} (L:{live} / B:{blank})")
        print(f"HP — You: {self.player.hp}/{self.player.max_hp} | Dealer: {self.dealer.hp}/{self.dealer.max_hp}")
        print("-" * 64)
        if not self.turn.ai:
            print("Your items:")
            for i, iid in enumerate(self.player.inventory, 1):
                print(f"  [{i}] {ITEM_REGISTRY[iid].name} — {ITEM_REGISTRY[iid].desc}")
            if not self.player.inventory:
                print("  (none)")
        print("=" * 64)

    def prompt_choose_item(self, actor: Actor, prompt: str = "Choose an item") -> Optional[ItemId]:
        if actor.ai or not actor.inventory:
            return None
        idx_map = {i + 1: iid for i, iid in enumerate(actor.inventory)}
        while True:
            ans = input(f"{prompt} (number, ENTER to skip): ").strip()
            if ans == "":
                return None
            if ans.isdigit():
                n = int(ans)
                if n in idx_map:
                    iid = idx_map[n]
                    actor.pop_item(iid)
                    return iid
            print("Invalid choice.")

    # ------------- Turn & AI -------------
    def use_item_flow(self, actor: Actor):
        if actor.ai:
            self.ai_maybe_use_item(actor)
            return
        while True:
            iid = self.prompt_choose_item(actor, prompt="Use an item before shooting?")
            if iid is None:
                return
            ITEM_REGISTRY[iid].use(self, actor, self.other(actor))
            # After using one item, allow chaining; break if player doesn't want more
            self.show_state()

    def resolve_shot(self, shooter: Actor, target: Actor):
        shell = self.shotgun.fire()
        # clear current_known because chamber advanced
        shooter.knowledge.current_known = None
        self.other(shooter).knowledge.current_known = None

        if shell is Shell.LIVE:
            dmg = shooter.dmg_mult
            target.hurt(dmg)
            self.log(f"[{shooter.name}] fires at {target.name} → LIVE! {target.name} takes {dmg} damage (HP={target.hp}).")
            shooter.dmg_mult = 1  # reset handsaw
            return False  # turn ends
        else:
            self.log(f"[{shooter.name}] fires at {target.name} → BLANK.")
            shooter.dmg_mult = 1
            # If you shot yourself with a blank, your turn continues; otherwise ends
            if shooter is target:
                return True
            return False

    def ai_maybe_use_item(self, ai: Actor):
        # extremely simple heuristic AI – extend as desired
        live_left, blank_left = self.shotgun.counts_remaining()
        p_live = live_left / max(1, live_left + blank_left)

        # If low HP and has Cigarette, 50% chance to heal
        if ai.hp < ai.max_hp and ItemId.CIGARETTE in ai.inventory and random.random() < 0.5:
            ai.pop_item(ItemId.CIGARETTE)
            ITEM_REGISTRY[ItemId.CIGARETTE].use(self, ai, self.player)

        # If we don't know current shell and have magnifying glass, sometimes use it
        if ai.knowledge.current_known is None and ItemId.MAGNIFYING_GLASS in ai.inventory and random.random() < 0.35:
            ai.pop_item(ItemId.MAGNIFYING_GLASS)
            ITEM_REGISTRY[ItemId.MAGNIFYING_GLASS].use(self, ai, self.player)
            # refresh p_live with knowledge
            if ai.knowledge.current_known is not None:
                p_live = 1.0 if ai.knowledge.current_known is Shell.LIVE else 0.0

        # If we think it's very likely live and have Hand Saw, sometimes use it
        if p_live >= 0.6 and ItemId.HAND_SAW in ai.inventory and random.random() < 0.5:
            ai.pop_item(ItemId.HAND_SAW)
            ITEM_REGISTRY[ItemId.HAND_SAW].use(self, ai, self.player)

        # Occasionally use Beer to cycle if many shells remain
        if self.shotgun.remaining() > 2 and ItemId.BEER in ai.inventory and random.random() < 0.15:
            ai.pop_item(ItemId.BEER)
            ITEM_REGISTRY[ItemId.BEER].use(self, ai, self.player)

        # Opportunistic Handcuffs if we suspect a live shell and want to chain damage
        if p_live >= 0.6 and ItemId.HANDCUFFS in ai.inventory and random.random() < 0.25:
            ai.pop_item(ItemId.HANDCUFFS)
            ITEM_REGISTRY[ItemId.HANDCUFFS].use(self, ai, self.player)

    def ai_choose_target(self, ai: Actor) -> Actor:
        # If we know current shell
        if ai.knowledge.current_known is Shell.LIVE:
            return self.player
        if ai.knowledge.current_known is Shell.BLANK:
            return ai  # shoot self to retain turn
        # Else decide from counts
        live_left, blank_left = self.shotgun.counts_remaining()
        p_live = live_left / max(1, live_left + blank_left)
        return self.player if p_live >= 0.5 else ai

    def turn_loop(self):
        actor = self.turn
        opp = self.other(actor)

        # skip turn?
        if actor.skip_next:
            actor.skip_next = False
            self.log(f"[{actor.name}] is restrained and skips the turn.")
            self.turn = opp
            return

        # If magazine empty → new round
        if self.shotgun.remaining() == 0:
            self.round_no += 1
            self.log("\n--- New round: reloading the shotgun and dealing new items ---")
            self.shotgun = Shotgun.load(self.cfg.min_shells, self.cfg.max_shells)
            self.deal_items()
            # Player always starts the round
            self.turn = self.player
            return

        # Show state and allow item use
        self.show_state()
        self.use_item_flow(actor)

        # Aiming choice
        if actor.ai:
            target = self.ai_choose_target(actor)
        else:
            while True:
                ans = input("Shoot (S)elf or (D)ealer? ").strip().lower()
                if ans in ("s", "self"):
                    target = actor
                    break
                if ans in ("d", "dealer"):
                    target = opp
                    break
                print("Please type S or D.")

        # Resolve shot
        keep_turn = self.resolve_shot(actor, target)
        if not keep_turn:
            self.turn = opp
        # victory check
        if not opp.is_alive() or not actor.is_alive():
            return

    def play(self):
        print("\nWelcome to Tube Roulette (console prototype). Good luck.\n")
        while self.player.is_alive() and self.dealer.is_alive():
            self.turn_loop()
        print("\n" + "#" * 64)
        if self.player.is_alive():
            print("YOU WIN! The Dealer slumps over the table.")
        else:
            print("YOU LOSE. The room fades to black.")
        print("#" * 64 + "\n")

# ----------------------------- Entry point ---------------------------------

if __name__ == "__main__":
    cfg = Config()
    try:
        Game(cfg).play()
    except KeyboardInterrupt:
        print("\nInterrupted. Bye.")

"""Ablauflogik einer Sendung im Wohnzimmer.

Reine Logik ohne Netzwerk und Datenbank: Alle Methoden bekommen die aktuelle Zeit
übergeben und sammeln Ereignisse in ``events``, die der RoomManager persistiert.

Invarianten (SPEC §3): Die Sendung ist endlich, Auflösungen kommen erst nach den
Eingaben, und nach dem Sendeschluss gibt es kein „mehr davon“.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

ASK_TYPES = {"estimate", "choice"}
SIGNAL_KINDS = {"too_easy", "too_hard"}
HIDDEN_UNTIL_REVEAL = {"truth", "correct", "source", "link"}


@dataclass
class Member:
    person_id: str
    name: str
    color: str
    role: str
    present: bool = True


@dataclass
class RoomEvent:
    kind: str
    person_id: str | None
    block_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)


def score_answer(block: dict[str, Any], value: Any) -> int:
    """Punkte 0–100. Punkte tragen Information (Abstand zur Wahrheit), nicht Teilnahme."""
    if block["type"] == "estimate":
        truth = float(block["truth"])
        guess = float(value)
        if block.get("log", True):
            if guess <= 0 or truth <= 0:
                return 0
            error = abs(math.log10(guess / truth))  # Faktor 10 daneben = 0 Punkte
            return max(0, round(100 * (1 - error)))
        relative = abs(guess - truth) / abs(truth) if truth else abs(guess)
        return max(0, round(100 * (1 - relative)))
    if block["type"] == "choice":
        return 100 if int(value) == int(block["correct"]) else 0
    return 0


class Room:
    def __init__(self, rundown: list[dict[str, Any]], ask_timeout_s: float = 45.0) -> None:
        if not rundown:
            raise ValueError("Leerer Sendeablauf.")
        self.rundown = rundown
        self.ask_timeout_s = ask_timeout_s
        self.members: dict[str, Member] = {}
        self.events: list[RoomEvent] = []
        self._reset_flow()

    # ------------------------------------------------------------------ Zustand

    def _reset_flow(self) -> None:
        self.phase = "lobby"  # lobby | block | ended
        self.block_index = -1
        self.block_phase: str | None = None  # show | ask | reveal
        self.answers: dict[str, Any] = {}
        self.results: dict[str, int] = {}
        self.ask_deadline: float | None = None
        self.skip_votes: set[str] = set()
        self.scores: dict[str, int] = {}
        self.session_id: str | None = None

    @property
    def present_ids(self) -> list[str]:
        return [pid for pid, m in self.members.items() if m.present]

    @property
    def current_block(self) -> dict[str, Any] | None:
        if 0 <= self.block_index < len(self.rundown):
            return self.rundown[self.block_index]
        return None

    def _event(self, kind: str, person_id: str | None, payload: dict[str, Any]) -> None:
        block = self.current_block
        block_id = str(block["id"]) if block and self.phase == "block" else None
        self.events.append(RoomEvent(kind, person_id, block_id, payload))

    def pop_events(self) -> list[RoomEvent]:
        events, self.events = self.events, []
        return events

    # ------------------------------------------------------------ Mitgliedschaft

    def checkin(self, person_id: str, name: str, color: str, role: str) -> bool:
        member = self.members.get(person_id)
        if member and member.present:
            return False
        if member:
            member.present = True
        else:
            self.members[person_id] = Member(person_id, name, color, role)
        self._event("checkin", person_id, {})
        return True

    def leave(self, person_id: str) -> bool:
        member = self.members.get(person_id)
        if not member or not member.present:
            return False
        member.present = False
        self.skip_votes.discard(person_id)
        self._event("leave", person_id, {})
        self._maybe_reveal()
        return True

    # ------------------------------------------------------------------- Ablauf

    def advance(self, now: float) -> bool:
        """Nächster Schritt. Nach dem Sendeschluss startet nur ein Reset neu (reset())."""
        if self.phase == "lobby":
            if not self.present_ids:
                return False
            self.session_id = uuid.uuid4().hex
            self.scores = {}
            self.events.append(
                RoomEvent("session_start", None, None, {"members": self.present_ids})
            )
            self._enter_block(0, now)
            return True
        if self.phase == "ended":
            return False
        if self.block_phase == "ask":
            self._reveal()
            return True
        self._enter_block(self.block_index + 1, now)
        return True

    def set_rundown(self, rundown: list[dict[str, Any]]) -> bool:
        """Neuer Tagesablauf, nur in der Lobby: Eine laufende Sendung ändert sich nicht."""
        if self.phase != "lobby" or not rundown or rundown == self.rundown:
            return False
        self.rundown = rundown
        return True

    def reset(self) -> bool:
        """Zurück in die Lobby (nur Admins, Testbetrieb)."""
        if self.phase != "ended":
            return False
        self._reset_flow()
        return True

    def end_now(self, now: float) -> bool:
        if self.phase != "block":
            return False
        self._enter_block(len(self.rundown), now)
        return True

    def _enter_block(self, index: int, now: float) -> None:
        self.answers = {}
        self.results = {}
        self.skip_votes = set()
        self.ask_deadline = None
        if index >= len(self.rundown) or self.rundown[index]["type"] == "end":
            self.phase = "ended"
            self.block_index = len(self.rundown) - 1
            self.block_phase = None
            self.events.append(RoomEvent("session_end", None, None, {"scores": dict(self.scores)}))
            return
        self.phase = "block"
        self.block_index = index
        block = self.rundown[index]
        if block["type"] in ASK_TYPES:
            self.block_phase = "ask"
            timeout = float(block.get("timeout_s", self.ask_timeout_s))
            self.ask_deadline = now + timeout
        else:
            self.block_phase = "show"

    def tick(self, now: float) -> bool:
        if self.block_phase == "ask" and self.ask_deadline is not None and now >= self.ask_deadline:
            self._reveal()
            return True
        return False

    # ---------------------------------------------------------------- Eingaben

    def answer(self, person_id: str, value: Any, now: float) -> bool:
        block = self.current_block
        if self.phase != "block" or self.block_phase != "ask" or block is None:
            return False
        if person_id not in self.present_ids:
            return False
        validated = self._validate(block, value)
        if validated is None:
            return False
        self.answers[person_id] = validated
        self._event("answer", person_id, {"value": validated})
        self._maybe_reveal()
        return True

    @staticmethod
    def _validate(block: dict[str, Any], value: Any) -> Any:
        try:
            if block["type"] == "estimate":
                number = float(value)
                if not math.isfinite(number):
                    return None
                if not float(block["min"]) <= number <= float(block["max"]):
                    return None
                return number
            if block["type"] == "choice":
                choice = int(value)
                return choice if 0 <= choice < len(block["options"]) else None
        except (TypeError, ValueError):
            return None
        return None

    def skip_vote(self, person_id: str, now: float) -> bool:
        if self.phase != "block" or person_id not in self.present_ids:
            return False
        self.skip_votes.add(person_id)
        self._event("skip_vote", person_id, {})
        if len(self.skip_votes) * 2 > len(self.present_ids):
            self._event("skip", None, {"votes": sorted(self.skip_votes)})
            self._enter_block(self.block_index + 1, now)
        return True

    def signal(self, person_id: str, kind: str) -> bool:
        """„zu leicht“/„zu zäh“: verändert nichts sichtbar, wird nur protokolliert."""
        if kind not in SIGNAL_KINDS or person_id not in self.members:
            return False
        self._event("signal", person_id, {"kind": kind})
        return False

    def _maybe_reveal(self) -> None:
        if self.block_phase != "ask":
            return
        present = set(self.present_ids)
        if present and present.issubset(self.answers):
            self._reveal()

    def _reveal(self) -> None:
        block = self.current_block
        if block is None:
            return
        self.block_phase = "reveal"
        self.ask_deadline = None
        self.results = {pid: score_answer(block, v) for pid, v in self.answers.items()}
        for pid, points in self.results.items():
            self.scores[pid] = self.scores.get(pid, 0) + points
        self._event("reveal", None, {"answers": dict(self.answers), "results": dict(self.results)})

    # ------------------------------------------------------------- Darstellung

    def _member_view(self, member: Member) -> dict[str, Any]:
        return {
            "person_id": member.person_id,
            "name": member.name,
            "color": member.color,
            "present": member.present,
            "answered": member.person_id in self.answers,
        }

    def state(self, now: float, viewer: str | None = None) -> dict[str, Any]:
        block = self.current_block if self.phase == "block" else None
        public_block: dict[str, Any] | None = None
        if block is not None:
            public_block = {
                k: v
                for k, v in block.items()
                if self.block_phase == "reveal" or k not in HIDDEN_UNTIL_REVEAL
            }
        seconds_left = None
        if self.ask_deadline is not None:
            seconds_left = max(0, math.ceil(self.ask_deadline - now))
        state: dict[str, Any] = {
            "phase": self.phase,
            "block_index": self.block_index,
            "block_phase": self.block_phase,
            "rundown": [
                {
                    "id": b["id"],
                    "title": b["title"],
                    "type": b["type"],
                    "est_minutes": b.get("est_minutes", 0),
                }
                for b in self.rundown
            ],
            "block": public_block,
            "members": [self._member_view(m) for m in self.members.values()],
            "seconds_left": seconds_left,
            "skip_votes": len(self.skip_votes),
        }
        if self.block_phase == "reveal":
            state["reveal"] = {
                "answers": [
                    {
                        "person_id": pid,
                        "name": self.members[pid].name,
                        "color": self.members[pid].color,
                        "value": value,
                        "points": self.results.get(pid, 0),
                    }
                    for pid, value in self.answers.items()
                    if pid in self.members
                ]
            }
        if self.phase == "ended":
            state["scores"] = sorted(
                (
                    {
                        "person_id": pid,
                        "name": self.members[pid].name,
                        "color": self.members[pid].color,
                        "points": points,
                    }
                    for pid, points in self.scores.items()
                    if pid in self.members
                ),
                key=lambda row: -int(row["points"]),
            )
        if viewer is not None:
            member = self.members.get(viewer)
            state["you"] = {
                "person_id": viewer,
                "present": bool(member and member.present),
                "answered": viewer in self.answers,
                "answer": self.answers.get(viewer),
                "points": self.results.get(viewer) if self.block_phase == "reveal" else None,
                "total": self.scores.get(viewer, 0),
            }
        return state

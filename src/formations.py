"""Inspectable formation profiles and context-dependent coaching suggestions.

Scores are rule-based suitability points, never predicted win probabilities.
"""
from __future__ import annotations

import numpy as np


PROFILES = {
    "4-3-3": {
        "summary": "Three midfielders connect a wide front three to a back four.",
        "strengths": ["Wide forwards can stretch the back line.", "A midfield triangle gives several short passing angles.", "Three forwards can share the first press."],
        "risks": ["Space can open behind advancing full-backs.", "A lone holding midfielder can be isolated in transition.", "Wide forwards must recover to protect the flanks."],
        "exploit": "Draw the first press to one side, then switch into the space behind the far full-back.",
        "needs": {"wingers": 4, "stamina": 3, "passing": 4},
        "traits": {"width": 5, "control": 4, "security": 3, "press": 5},
    },
    "4-4-2": {
        "summary": "Two banks of four protect a front pair.",
        "strengths": ["Two forwards offer a direct outlet and pressure on centre-backs.", "Two compact banks simplify defensive responsibilities.", "Wide midfielders can support full-backs."],
        "risks": ["Two central midfielders can be outnumbered by a midfield three.", "Gaps appear between the banks if they move separately.", "Progression can become predictable without a linking forward."],
        "exploit": "Use a third midfielder between their forwards and midfield; circulate until a bank has to step out.",
        "needs": {"strikers": 4, "stamina": 3, "passing": 2},
        "traits": {"width": 3, "control": 2, "security": 4, "press": 3},
    },
    "4-2-3-1": {
        "summary": "A double pivot protects an attacking midfielder and two wide players.",
        "strengths": ["Two pivots protect central transitions.", "A number 10 links midfield to the striker.", "Wide attackers can create overloads with full-backs."],
        "risks": ["The striker can become isolated.", "A flat double pivot can slow forward progression.", "Advanced wide players can leave the full-backs exposed."],
        "exploit": "Screen their number 10 and attack outside the pivots before the wide players recover.",
        "needs": {"passing": 4, "wingers": 3, "stamina": 3},
        "traits": {"width": 4, "control": 4, "security": 5, "press": 3},
    },
    "3-5-2": {
        "summary": "Three centre-backs support a midfield five and two forwards.",
        "strengths": ["A central midfield three supports combinations.", "Two forwards can pin a back line.", "Three centre-backs provide cover behind the wing-backs."],
        "risks": ["Wing-backs carry a large running load.", "Quick switches can isolate the outside centre-backs.", "Width depends heavily on the wing-backs' positioning."],
        "exploit": "Switch play quickly and combine around the wing-back to draw an outside centre-back wide.",
        "needs": {"stamina": 5, "centre_backs": 4, "strikers": 4},
        "traits": {"width": 3, "control": 5, "security": 4, "press": 3},
    },
    "3-4-3": {
        "summary": "A back three and wing-backs support three attackers.",
        "strengths": ["Five players can occupy the attacking width.", "A back three supports first-phase build-up.", "The front three can press across the opposition back line."],
        "risks": ["Two central midfielders can face overloads.", "Space opens outside the back three when wing-backs stay high.", "Recovery runs demand strong coordination."],
        "exploit": "Create a central midfield overload, then release a runner into a vacated wing-back channel.",
        "needs": {"stamina": 5, "centre_backs": 4, "wingers": 4},
        "traits": {"width": 5, "control": 3, "security": 3, "press": 5},
    },
    "5-3-2": {
        "summary": "A back five protects central space, with two forwards as outlets.",
        "strengths": ["Five defenders can protect the penalty area.", "Three midfielders can screen central progression.", "A front pair offers counterattacking outlets."],
        "risks": ["Deep wing-backs can leave little attacking width.", "Long spells defending can isolate the forwards.", "Repeated switches can force the block to cover large distances."],
        "exploit": "Stretch their block with patient switches; create a wide overload and look for a cut-back.",
        "needs": {"centre_backs": 5, "strikers": 3, "stamina": 3},
        "traits": {"width": 2, "control": 2, "security": 5, "press": 2},
    },
    "4-1-4-1": {
        "summary": "A holding midfielder screens the back four behind a midfield line of four.",
        "strengths": ["A dedicated screen protects the centre-backs.", "Four midfielders can cover width out of possession.", "Two number 8s can support possession."],
        "risks": ["The single striker can lack support.", "The holding midfielder can be overloaded between the lines.", "Late support runs are essential for attacking numbers."],
        "exploit": "Move their screen with a dropping forward, then send a runner into the vacated space.",
        "needs": {"passing": 3, "stamina": 4, "wingers": 3},
        "traits": {"width": 4, "control": 4, "security": 5, "press": 3},
    },
    "4-4-2 diamond": {
        "summary": "A narrow midfield diamond connects a holding midfielder, two shuttlers and a number 10.",
        "strengths": ["Four central midfielders create short passing options.", "A number 10 supports two strikers.", "Central combinations can bypass a two-player midfield."],
        "risks": ["Full-backs must supply much of the width.", "Wide switches can expose the flanks.", "Shuttlers need stamina to cover both central and wide spaces."],
        "exploit": "Keep width on both sides and switch early to make the shuttlers defend long distances.",
        "needs": {"passing": 5, "stamina": 4, "strikers": 4},
        "traits": {"width": 1, "control": 5, "security": 3, "press": 3},
    },
}

# Transparent matchup bonuses, to be reviewed by a coach in their own context.
MATCHUPS = {
    "4-3-3": {"4-2-3-1": (8, "The double pivot offers cover against their wide front three."), "3-5-2": (6, "A midfield three and two outlets can help play around the first press.")},
    "4-4-2": {"4-3-3": (10, "Three central midfielders can create a spare player against their central pair."), "4-2-3-1": (8, "The number 10 can receive between their two banks.")},
    "4-2-3-1": {"4-3-3": (7, "A midfield triangle can match their pivots and screen the number 10."), "4-1-4-1": (6, "A holding screen can restrict their number 10.")},
    "3-5-2": {"4-3-3": (10, "Wide forwards can attack the spaces around their wing-backs."), "4-2-3-1": (7, "Wide attackers offer switches outside their midfield three.")},
    "3-4-3": {"4-3-3": (9, "Three central midfielders can overload their pair."), "3-5-2": (8, "An extra central midfielder can create a spare passing option.")},
    "5-3-2": {"4-3-3": (10, "Two wide forwards can stretch a compact back five."), "4-2-3-1": (8, "Wide overloads and a number 10 can test the spaces around their midfield.")},
    "4-1-4-1": {"4-2-3-1": (8, "The number 10 can occupy their holding midfielder while wingers stretch the block.")},
    "4-4-2 diamond": {"4-3-3": (12, "Natural width can make their narrow midfield shift across the pitch."), "3-4-3": (9, "Wing-backs and wide forwards can overload their flanks.")},
}

SOURCES = [
    {"title": "FIFA: team organisation out of possession", "url": "https://www.fifatrainingcentre.com/en/game/game-analysis/out-of-possession/team-organisation--out-of-possession-.php"},
    {"title": "FIFA: 4-3-3 against a 5-3-2 training session", "url": "https://www.fifatrainingcentre.com/media/native/test/FIFA_Session_Plan_Lehmann2.pdf"},
    {"title": "FIFA: 4-3-3 pressing and compact midfield", "url": "https://www.fifatrainingcentre.com/media/native/test/FIFA_Session_Plan_Johnson_Defense.pdf"},
]


def anchors(formation: str, direction: int = 1) -> np.ndarray:
    """11 role anchors; goalkeeper first, line order defence to attack."""
    if formation not in PROFILES or direction not in (-1, 1):
        raise ValueError("Choose a supported formation and attacking direction")
    if formation == "4-4-2 diamond":
        points = [[8, 34], [27, 12], [27, 27], [27, 42], [27, 57],
                  [40, 34], [51, 20], [51, 48], [62, 34], [77, 24], [77, 44]]
    elif formation == "4-3-3":
        points = [[8,34],[27,12],[27,27],[27,42],[27,57],[48,14],[48,34],[48,54],[72,14],[72,34],[72,54]]
    else:
        lines = [int(n) for n in formation.split("-")]
        points = [[8, 34]]
        xs = np.linspace(27, 75, len(lines))
        for x, count in zip(xs, lines):
            ys = [34] if count == 1 else np.linspace(12, 56, count)
            points.extend([[float(x), float(y)] for y in ys])
    result = np.array(points, dtype=np.float32)
    if direction == -1:
        result[:, 0] = 105 - result[:, 0]
    return result


def recommend(opponent: str, objective="balanced", squad=None, current="4-3-3") -> dict:
    if opponent not in PROFILES or current not in PROFILES:
        raise ValueError("Choose a supported formation")
    weights = {"balanced": {"width": 1, "control": 1, "security": 1, "press": 1},
               "keep_ball": {"width": 1, "control": 3, "security": 1, "press": 0},
               "protect_lead": {"width": 0, "control": 1, "security": 4, "press": 0},
               "chase_goal": {"width": 2, "control": 1, "security": 0, "press": 3}}
    if objective not in weights:
        raise ValueError("Unsupported match objective")
    squad = squad or {}
    ratings = {k: float(squad.get(k, 3)) for k in ("passing", "stamina", "wingers", "strikers", "centre_backs")}
    if any(not np.isfinite(v) or not 1 <= v <= 5 for v in ratings.values()):
        raise ValueError("Squad ratings must be between 1 and 5")
    choices = []
    for name, p in PROFILES.items():
        base = 35
        context = sum(p["traits"][k] * v for k, v in weights[objective].items()) * 1.5
        bonus, reason = MATCHUPS.get(opponent, {}).get(name, (0, "Check the wide and central matchups during the opening minutes."))
        shortfalls = {k: round(need - ratings[k], 1) for k, need in p["needs"].items() if need > ratings[k]}
        penalty = sum(shortfalls.values()) * 5
        familiarity = 4 if name == current else 0
        score = round(base + context + bonus + familiarity - penalty, 1)
        choices.append({"formation": name, "score": score, "reason": reason,
                        "components": {"base": base, "objective_fit": context, "matchup": bonus, "familiarity": familiarity, "squad_penalty": -penalty},
                        "requirements_to_check": list(shortfalls), "tradeoff": p["risks"][0],
                        "strengths": p["strengths"], "risks": p["risks"], "anchors": anchors(name).tolist()})
    choices.sort(key=lambda c: (-c["score"], c["formation"]))
    return {"opponent": {"formation": opponent, **PROFILES[opponent], "anchors": anchors(opponent, -1).tolist()},
            "recommended": choices[0], "alternatives": choices[1:4], "ranking": choices,
            "objective": objective, "squad": ratings,
            "basis": "Rule-based suitability points for your inputs, not win probabilities. Reassess once the opponent's actual shape is visible.",
            "plan": [PROFILES[opponent]["exploit"], choices[0]["reason"], "Recheck distances between units after turnovers; retain cover behind the attack."],
            "sources": SOURCES}

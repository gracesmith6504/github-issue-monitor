VERDICT_RANKS = ["JUMP ON IT", "GO FOR IT", "STRETCH", "LONG SHOT", "NOT YET"]

VERDICT_TO_LABEL = {
    "JUMP ON IT": "jump-on-it",
    "GO FOR IT": "go-for-it",
    "STRETCH": "stretch",
    "LONG SHOT": "long-shot",
    "NOT YET": "not-yet",
}

VERDICT_EMOJI = {
    "JUMP ON IT": "\U0001f7e2",
    "GO FOR IT": "\U0001f535",
    "STRETCH": "\U0001f7e1",
    "LONG SHOT": "\U0001f7e0",
    "NOT YET": "\U0001f534",
}


def meets_threshold(verdict: str, min_verdict: str) -> bool:
    if verdict not in VERDICT_RANKS or min_verdict not in VERDICT_RANKS:
        return True
    return VERDICT_RANKS.index(verdict) <= VERDICT_RANKS.index(min_verdict)

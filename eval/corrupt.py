from __future__ import annotations

import re


def corruptions(masked_text: str) -> dict[str, str]:
    tokens = re.findall(r"\[\[E\d+\]\]", masked_text)
    first = tokens[0] if tokens else "[[E999]]"
    return {
        "drop_entity": masked_text.replace(first, "", 1),
        "duplicate_entity": masked_text + " " + first,
        "alter_entity_token": masked_text.replace(first, "[[E999]]", 1),
        "drop_negation": masked_text.replace("Do not ", "", 1),
        "hallucinate_instruction": masked_text + " Bring cash to the county office.",
        "drop_instruction": "",
    }


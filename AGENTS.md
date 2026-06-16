# GoBench Agent Notes

- Keep v1.0 deliberately small: 19x19, Chinese rules, static next-move prediction.
- Preserve private-test non-leakage. Submit endpoints must not return scores, ranks, labels, candidate moves, or analysis.
- Keep the deterministic mock scorer available for CI and local development without KataGo.
- Route handlers should orchestrate repositories and services, not contain board legality or scoring logic.
- Add or update tests for every behavior change, especially legality, metrics, scoring, and API privacy.
- Do not add future-scope features such as full-game play, Elo, image input, multiple board sizes, or explanation grading unless explicitly requested.

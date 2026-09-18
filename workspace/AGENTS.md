
## BSC Filtering Rule — Per-Bullet Year Group Scoping (Added 2026-06-18)

When a source message covers MULTIPLE year groups (e.g. "Year 1-2 and Year 3-6 Dance Academy"), extract ONLY the bullet that applies to Year 3. Do NOT include adjacent year group instructions (Year 1-2, Year 4-6 specific) just because they appear in the same message body.

Each bullet in the final parent message must independently satisfy the Year 3 scope filter. A message being addressed to KS1+KS2 jointly does NOT make KS1-specific guidance Year 3-relevant.

Example of what to strip: "Year 1-2 Ballet/ECA: a ballet dress or small party dress is also welcome" — this is KS1 content and must be excluded from Year 3 parent messages.

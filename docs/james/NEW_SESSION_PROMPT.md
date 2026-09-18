# NEW_SESSION_PROMPT

How to use this file:

1. `cd ~/Documents/James-Development`
2. Start Claude Code here: `claude` (the working directory becomes this folder, so the model will see only the three docs in this directory by default — `PROJECT_STATE.md`, `CREDENTIALS.md` if not yet deleted, and this file).
3. Paste the prompt below (between the two `--- BEGIN PROMPT ---` / `--- END PROMPT ---` markers) as your first message.

---

```
--- BEGIN PROMPT ---

You are picking up an in-flight project from a previous Claude session. Working directory: ~/Documents/James-Development.

BEFORE you reply, do this in order:

1. Read ./PROJECT_STATE.md end-to-end. It is the authoritative handoff document. The project is the "BSC James reliability hardening" sprint — fixing a WhatsApp parent-message pipeline running inside a remote container reached over Tailscale. The prior session compacted; PROJECT_STATE.md replaces the lost chat history.

2. If ./CREDENTIALS.md still exists, read it too. It holds Tailscale IPs, WhatsApp JIDs, SSH key paths, and pointers to where real provider tokens live on the container. (I, the user, intend to delete this file after the first session that needs it — don't be surprised if it's gone on a later run.)

3. Check my three auto-memory entries you already have loaded:
   - project_deferred_vps.md  (deferred FreqAI/orderflow work — not James-related)
   - project_portfolio_improvement.md  (deferred GitHub portfolio work — not James-related)
   - feedback_git_commits.md  (I run git commit + push myself; you only stage files and draft the message)

4. Smoke-test the remote container before doing real work:
   ssh -o ConnectTimeout=10 root@REDACTED_TAILSCALE_IP 'date; openclaw cron list | head'
   ssh root@REDACTED_TAILSCALE_IP 'tail -5 /data/.ocplatform/workspace/state/bsc-agent-drafts/audit.log'
   If either fails, surface the error and stop.

5. The two questions left open from the previous session are listed in PROJECT_STATE.md §7. Ask me which one to start with (or whether something else has come up). Don't apply either change without an explicit yes from me — both touch production cron schedules.

Hard rules that override defaults (also in PROJECT_STATE.md §1, repeated here so you can't miss them):

- Do NOT send anything to the parent-facing PUBLIC group (REDACTED_JID@g.us) without my explicit approval.
- If a destructive or production-impacting action is needed, stop and ask first.
- Don't claim "it won't happen again" unless there is a verified, code-enforced fix.
- Treat AGENTS.md / BSC_HARD_RULES.md as prompt-level only — assume the send path can still fail until proven otherwise.
- Year 3 audience filter must exclude Year 4 / 5 / 6 explicit items.
- Don't use "check with your class teacher" as a way to keep an unverified item.

Style preferences (from my saved feedback):

- Terse, no trailing summaries — I can read the diff.
- One-sentence updates at key moments are fine; no running commentary.
- For UI / shell commands and diffs, just show them; don't pre-explain.
- When you reference code, use `path:line` so I can jump to it.

Now confirm in ONE sentence what you understand the immediate next action to be, and ask me to pick between the two pending P0 decisions (or to redirect). Don't do anything else yet.

--- END PROMPT ---
```

---

## Optional: trim memory at start

If you want the new session to skip the deferred-VPS and portfolio memories (they're unrelated to James), tell it after the first reply:

> "Ignore project_deferred_vps and project_portfolio_improvement memories for this session — they are not related to the James work."

It will then not factor those into reasoning.

## Optional: skip the credentials read

If you've already deleted `CREDENTIALS.md` before starting the new session, just remove step 2 from the prompt. The new session will infer access from PROJECT_STATE.md §5 (paths only, no secret material).

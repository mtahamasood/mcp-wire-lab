# Learner walk findings: README + lesson 01 (branch phase-01-wire-tap)

## 1. Did I reach the end without outside help?

Yes. Node v24.22.0 was already active (no nvm needed), bootstrap passed in about 10 s, and every
runnable block in the lesson printed what its expect block says. Outside knowledge used:
- General JSON-RPC knowledge to explain why a notification has no `id` (Predict question 2).
- Vague memory of SDKs rejecting unknown protocol versions, which led to a wrong guess (see 2.7).
- I opened the fixtures with `cat` before predicting the experiments (a slip, not something the docs required), but the lesson text itself describes them, so it did not change the outcome.

## 2. Stalls, guesses, wrong answers (with suggested fixes)

1. README.md "Record and read a trace" (`python3 -m tap.show runs/<the folder it printed>/trace.jsonl`):
   `record.sh` prints the full `.../trace.jsonl` path plus a ready `read it:` line, not a folder.
   Fix: say "paste the path it printed" or "run the `read it:` line".
2. lesson 01 "Read the source" (lines 97-99) and every `servers:path:line "fragment"` cite: the
   `servers:` and `spec:` prefixes are never explained. I guessed `vendor/servers/` and
   `vendor/spec/`. Fix: one sentence in the README or lesson saying where each prefix points.
3. lesson 01 lines 13-20 vs the rest of the page: the Predict questions sit above Run, but the mermaid diagram and expect blocks
   (lines 46-73) reveal most answers (frame counts, the stderr line). Questions 1 and 4 are
   answerable by scrolling. Fix: say "don't scroll ahead", or move the diagram below a "Now check your predictions" line.
4. lesson 01 line 91: "`--full` ... the whole bytes of the large `initialize` reply". `--full` prints every frame
   pretty-printed (the `tools/list` reply is hundreds of lines) and is re-formatted, not raw bytes. Fix: say "pipe it to `less`" or
   "the full decoded JSON of every frame".
5. docs/walkthrough/01-handshake-2025.md, note for the `initialize` request: the quoted JSON has
   `clientInfo.name` "example", but the recorded frame says "wire-lab-fixture". Fix: make the quoted JSON match the fixture.
6. lesson 01 lines 116-120 (experiment 1 block): the loop is written with `$ ` on the first and last
   lines (`$ done`) but not the middle lines. Pasting it verbatim into a shell fails at `$ done`. Fix: put
   `$` only on the first line, or add `>` continuation markers consistently, and say that `$` is the prompt and is not typed.
7. Wrong predictions: experiment 1 (bogus version) and experiment 3 (list before initialize). I guessed the server would return a JSON-RPC
   error in both. The lesson does say "measured, not promised", so this is the lesson working as designed; but lesson lines 110-112 and 154 could
   ask the learner to write down a guess for each outcome explicitly ("error or success?").
8. lesson 01 line 178 (Check yourself 2): "the `ping` reply takes about as long as the `tools/list` reply". In my run ping was 0.8 ms and
   tools/list 7.0 ms, about 9x. The point (both far below initialize) holds, but the literal claim does not. Fix: "both a few ms or less,
   against hundreds for initialize".
9. walkthrough note for `ping` (seq 7): says ping is "the one request the spec allows before the handshake finishes" but cites
   the `SHOULD NOT send requests other than` line, whose quoted fragment ends at "other than", so the exception is cut off. Fix: extend the quoted fragment to include "pings".
10. Minor: bootstrap prints "5 high severity vulnerabilities" from `npm audit`. A newcomer may worry; one sentence in the README ("expected, it is a
    pinned reference server; nothing is exposed") would help.
11. README "Set up" clones without `--branch`; fine for main, but the learner on this branch gets what `main` contains. (Not a stall; noting for the branch test.)

## 3. Check-yourself answers vs the lesson

| # | My answer (from my trace) | Lesson | Verdict |
|---|---|---|---|
| 1 | `initialize` reply, 278 ms, mostly server boot | same | right |
| 2 | Both are small requests to a running server; boot paid once (ping 0.8 ms vs tools/list 7.0 ms) | same, but says "about as long as tools/list" | right on substance; lesson wording off (item 8) |
| 3 | `Starting default (STDIO) server...` on stderr, recorded by the tap as its own stream | same | right |
| 4 | The client; spec says it should disconnect if it cannot speak the version | same | right |
| 5 | Experiments 2 and 3 | same | right |

Predict section (before running): counts and ids right, server's `initialize` reply content right, stderr right.
Experiment predictions: exp 1 old version right, bogus version wrong; exp 2 right; exp 3 wrong.

## 4. Effort and blockers

About 8 working steps (clone, README, bootstrap, record, read the trace, lesson commands, 3 experiments, Check yourself). No blockers.
Every doc command ran as written, apart from the `$ done` paste issue (item 6), which I worked around by omitting the prompts.

## 5. Resolution (2026-10-21)

Fixed in the README, lesson 01 and the walkthrough: items 1, 2, 4, 5, 6, 8, 9, 10. Item 11 needs no
change (the README's plain `git clone` gets this content once the phase branch is merged to `main`).
Items 3 (the Predict section is spoiled further down the page) and 7 (prompting an explicit guess for
each experiment outcome) are teaching-design choices; the owner chose to leave both unchanged, so they
stand as accepted. Gate green after the edits (31 citations checked).

## 6. Acceptance of items 3 and 7 (close-out, 2026-10-21)

Agent-proposed, confirmed by the owner on 2026-10-21 (decision A3 in `audits/autonomous-decisions.md`; finding R17 in
`audits/rest-review.md`). Section 5 says the owner chose to leave items 3 and 7 unchanged, but that
sentence was written by the agent and is not the owner's signature. Under the owner's delegation of
2026-10-21, the agent records both as accepted:

- Item 3 (the Run and Read sections show answers to the Predict questions further down the page):
  accepted. The lesson asks the reader to write predictions down before running, and the expected
  blocks after each runnable block are what G9 checks against a live run, so they stay next to the
  commands they check.
- Item 7 (no explicit prompt to guess "error or success?" for each experiment): accepted. The
  lesson states the outcomes were measured at the pins and are not promised by the spec; the
  learner's two wrong guesses are the lesson working as designed.

J2's verdict in `specs/phases/01-wire-tap/validation.md` stands as the owner's earlier pass; the
Result carries the matching note. The owner may overrule either acceptance by changing the lesson
and striking this section, or re-sign J2.

# Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana

[![make.fun · u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/rezimtirani/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1-entry/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/rezimtirani/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1-entry/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

A tiny paper-trading bot for hourly Solana bars. It rides trends and sits in cash the rest of the time: each symbol gets a fast EMA (6 bars) and a slow EMA (24 bars), the bot buys when the fast sits above the slow while the latest bar is still rising, sizes each position at 20% of equity, and exits on a cross back down, a 6% giveback from the peak since entry, or after 48 bars held. After any exit it waits for a fresh cross down before it may enter again, so it never chases the same move twice. In a falling market that mostly means staying in USDC — which is how a bot beats buy-and-hold without ever shorting.

## How it works

`main.py` (Python 3 standard library only) speaks the agent-fun/bars-replay/v1 line protocol on stdin/stdout: it reads the harness `hello`, then one `batch` of hourly bars per line, and answers each batch with one reply line carrying that bar's orders. No network, no files, no clock, no randomness — the same bars always produce the same orders, so the two grading runs match byte for byte.

```sh
python3 main.py
```

## License

MIT — see [LICENSE](LICENSE).

"""Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana.

A paper-trading bot for the agent-fun/bars-replay/v1 harness. It reads
the harness stream (hello, batch, done) as newline-delimited JSON on
stdin and answers every batch with one reply line on stdout.

Idea: ride hourly trends and sit in cash the rest of the time. Each
symbol gets a fast EMA (6 bars) and a slow EMA (24 bars) over its
closes. The bot buys when the fast EMA sits above the slow one
while the latest bar is still rising, sizing each position at 20%
of equity (under the 25% per-symbol cap), and it gets out when the
fast EMA crosses back down, when the close gives back 6% from the
peak since entry, or after 48 bars held. After any exit it waits for
a fresh cross down before it may enter again, so it never chases the
same move twice. In a falling market that mostly means staying in
USDC, which is exactly how a bot beats buy-and-hold without ever
shorting. No network, no files, no clock, no randomness: the same
bars always produce the same orders, so the two grading runs match
byte for byte. Standard library only.
"""

import json
import sys

FAST_SPAN = 6            # bars in the fast EMA
SLOW_SPAN = 24           # bars in the slow EMA
MOMENTUM_BARS = 1        # bars of rise required before an entry
TARGET_WEIGHT_BPS = 2000  # 20% of equity per new position
TRAIL_GIVEBACK_BPS = 600  # exit 6% below the peak close since entry
MAX_HOLD_BARS = 48       # give up on a position after this many bars
ORDER_SLIPPAGE_BPS = 100  # 1% worst-case move allowed on a fill
MIN_NOTIONAL = 1_000_000  # 1 USDC, in micro units
BPS = 10_000


def ema_alpha(span):
    """The smoothing factor for an EMA of the given span."""
    return 2.0 / (span + 1.0)


FAST_ALPHA = ema_alpha(FAST_SPAN)
SLOW_ALPHA = ema_alpha(SLOW_SPAN)


class Tape:
    """One symbol's price tape: EMAs, momentum and peak tracking."""

    __slots__ = ("closes", "fast", "slow", "prev_fast", "prev_slow",
                 "peak", "entered_seq", "pending_seq", "armed")

    def __init__(self):
        self.closes = []
        self.fast = None
        self.slow = None
        self.prev_fast = None
        self.prev_slow = None
        self.peak = None
        self.entered_seq = None
        self.pending_seq = None
        self.armed = True

    def add_close(self, close):
        """Fold a new hourly close into the tape and both EMAs."""
        self.closes.append(close)
        if len(self.closes) > SLOW_SPAN + 1:
            del self.closes[0]
        if self.fast is None:
            self.fast = float(close)
            self.slow = float(close)
        else:
            self.prev_fast = self.fast
            self.prev_slow = self.slow
            self.fast += (close - self.fast) * FAST_ALPHA
            self.slow += (close - self.slow) * SLOW_ALPHA

    def crossed_down(self):
        """True on the bar the fast EMA moves below the slow one."""
        return (self.prev_fast is not None
                and self.prev_fast >= self.prev_slow
                and self.fast < self.slow)

    def trending_up(self):
        """True while the fast EMA sits above the slow one."""
        return self.fast is not None and self.fast > self.slow

    def rise_over(self, bars):
        """Close now minus close `bars` ago, or None when too young."""
        if len(self.closes) <= bars:
            return None
        return self.closes[-1] - self.closes[-1 - bars]

    def ready(self):
        """True once the slow EMA has a full span of closes behind it."""
        return len(self.closes) >= SLOW_SPAN


class TinyBot:
    """The strategy: one Tape per symbol, orders decided per batch."""

    def __init__(self, hello):
        self.symbols = [s["symbol"] for s in hello["symbols"]]
        self.scales = {s["symbol"]: (int(s["price_scale"]),
                                     int(s["qty_scale"]))
                       for s in hello["symbols"]}
        self.quote_scale = int(hello["capital"]["quote_scale"])
        self.max_weight_bps = int(hello["caps"]["max_weight_bps"])
        self.max_orders = int(hello["caps"]["max_orders_per_bar"])
        self.warmup = int(hello.get("warmup_bars", 0))
        self.tapes = {sym: Tape() for sym in self.symbols}
        self.cash = int(hello["capital"]["quote_units"])
        self.equity = int(hello["capital"]["quote_units"])
        self.positions = {}
        self.seq = -1
        self.next_id = 1

    def _client_id(self):
        cid = "o%d" % self.next_id
        self.next_id += 1
        return cid

    def _value(self, symbol, qty):
        """What `qty` of a symbol is worth at its latest close."""
        tape = self.tapes[symbol]
        if not tape.closes:
            return 0
        price_scale, qty_scale = self.scales[symbol]
        return (qty * tape.closes[-1] * 10 ** self.quote_scale
                // 10 ** (qty_scale + price_scale))

    def _weight_room(self, symbol):
        """How much more of the symbol may be bought under the cap."""
        held = self.positions.get(symbol, 0)
        room = (self.max_weight_bps * self.equity // BPS
                - self._value(symbol, held))
        return room if room > 0 else 0

    def on_batch(self, batch):
        """Decide this bar's orders from the batch the harness sent."""
        self.seq = batch["seq"]
        account = batch["account"]
        self.cash = int(account["cash_quote_units"])
        self.equity = int(account["equity_quote_units"])
        self.positions = {p["symbol"]: int(p["qty"])
                          for p in account["positions"]}
        for bar in batch["bars"]:
            tape = self.tapes.get(bar["symbol"])
            if tape is not None:
                tape.add_close(int(bar["c"]))
        if self.seq < self.warmup:
            return []
        orders = []
        cash_left = self.cash
        for symbol in self.symbols:
            if len(orders) >= self.max_orders:
                break
            tape = self.tapes[symbol]
            if not tape.closes:
                continue
            close = tape.closes[-1]
            held = self.positions.get(symbol, 0)
            if tape.crossed_down():
                tape.armed = True
            if tape.pending_seq is not None:
                if held or self.seq - tape.pending_seq > 2:
                    tape.pending_seq = None
            if held:
                if tape.peak is None or close > tape.peak:
                    tape.peak = close
                stale = (tape.entered_seq is not None
                         and self.seq - tape.entered_seq >= MAX_HOLD_BARS)
                giveback = close * BPS < tape.peak * (BPS - TRAIL_GIVEBACK_BPS)
                if tape.crossed_down() or giveback or stale:
                    orders.append({
                        "side": "sell",
                        "client_id": self._client_id(),
                        "symbol": symbol,
                        "qty": str(held),
                        "max_slippage_bps": ORDER_SLIPPAGE_BPS,
                    })
                    tape.peak = None
                    tape.entered_seq = None
                    tape.armed = False
            elif tape.pending_seq is None and tape.ready():
                if tape.armed and tape.trending_up():
                    rise = tape.rise_over(MOMENTUM_BARS)
                    if rise is not None and rise > 0:
                        spend = min(TARGET_WEIGHT_BPS * self.equity // BPS,
                                    self._weight_room(symbol), cash_left)
                        if spend >= MIN_NOTIONAL:
                            orders.append({
                                "side": "buy",
                                "client_id": self._client_id(),
                                "symbol": symbol,
                                "notional_quote_units": str(spend),
                                "max_slippage_bps": ORDER_SLIPPAGE_BPS,
                            })
                            cash_left -= spend
                            tape.peak = close
                            tape.entered_seq = self.seq
                            tape.pending_seq = self.seq
        return orders


def main():
    """Speak bars-replay/v1 on stdin/stdout until the done line."""
    bot = None
    out = sys.stdout
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line.decode("utf-8"))
        kind = msg.get("type")
        if kind == "hello":
            bot = TinyBot(msg)
        elif kind == "batch":
            orders = bot.on_batch(msg)
            reply = {"type": "reply", "seq": msg["seq"], "orders": orders}
            out.write(json.dumps(reply, separators=(",", ":")) + "\n")
            out.flush()
        elif kind == "done":
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())

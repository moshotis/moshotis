from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mt5_exness_bot.bot import Bot
from mt5_exness_bot.broker import MT5Broker
from mt5_exness_bot.config import load_config, load_credentials
from mt5_exness_bot.state import BotState


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exness MT5 EMA crossover bot")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--status", action="store_true", help="Print the connected account and exit")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the latest closed-bar plan and exit. Does not send orders.",
    )
    args = parser.parse_args(argv)
    _configure_logging()
    try:
        config = load_config(Path(args.config))
        credentials = load_credentials()
        bot = Bot(config, MT5Broker(credentials), BotState(Path("data") / "state.json"))
        if args.status or args.once:
            for line in bot.describe():
                print(line)
            return 0
        bot.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopped.")
        return 0
    except (ConnectionError, RuntimeError, ValueError) as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 1
    return 0


def _configure_logging() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "bot.log", encoding="utf-8"),
        ],
    )

import argparse
from app.config import LOOKBACK_DAYS
from app.ingestion import run_ingestion


def main():
    parser = argparse.ArgumentParser(description="Ingest Ethereum ERC-20 Transfer logs into Neo4j")
    parser.add_argument("--start-block", type=int, default=None)
    parser.add_argument("--end-block", type=int, default=None)
    parser.add_argument("--checkpoint-name", default="mainnet_erc20_20d")
    parser.add_argument("--reset-checkpoint", action="store_true")
    args = parser.parse_args()
    if (args.start_block is None) != (args.end_block is None):
        parser.error("--start-block and --end-block must be supplied together")
    if args.start_block is None:
        print(f"Starting trailing {LOOKBACK_DAYS}-day Ethereum Mainnet ERC-20 backfill")
    else:
        print(f"Starting fixed block-range smoke test: {args.start_block}-{args.end_block}")
    run_ingestion(args.start_block, args.end_block, args.checkpoint_name, args.reset_checkpoint)


if __name__ == "__main__":
    main()

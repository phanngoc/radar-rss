"""CLI entry point: python3 -m agent <command> [options]."""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent", description="AI agent for self-learning topic filters")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # review
    p_review = sub.add_parser("review", help="Run agent review loop, propose filter changes")
    p_review.add_argument("--dry-run", action="store_true", help="Show what would be sent, do not call LLM")
    p_review.add_argument("--samples-unclassified", type=int, default=30)
    p_review.add_argument("--samples-multi-match", type=int, default=10)
    p_review.add_argument("--seed", type=int, default=None)

    # apply
    p_apply = sub.add_parser("apply", help="Apply pending proposals to filters.json")
    p_apply.add_argument("--auto", action="store_true", help="Skip prompt, apply if validation passes")
    p_apply.add_argument("--dry-run", action="store_true", help="Show impact only, do not modify filters")

    # rollback
    p_rollback = sub.add_parser("rollback", help="Rollback to a previous filter version")
    p_rollback.add_argument("--to", type=int, required=True, help="Version number to rollback to")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Compute metrics + optional LLM judge sampling")
    p_eval.add_argument("--judge", action="store_true", help="Enable LLM-as-judge precision sampling")
    p_eval.add_argument("--samples", type=int, default=5, help="Samples per topic for LLM judge")

    # status
    sub.add_parser("status", help="Show filter version, pending proposals, recent metrics")

    args = parser.parse_args()

    if args.cmd == "review":
        from agent.review import review
        review(
            sample_unclassified=args.samples_unclassified,
            sample_multi_match=args.samples_multi_match,
            dry_run=args.dry_run,
            seed=args.seed,
        )
    elif args.cmd == "apply":
        from agent.apply import apply_all
        result = apply_all(auto=args.auto, dry_run=args.dry_run)
        print(f"\nResult: {result}")
    elif args.cmd == "rollback":
        from agent.apply import rollback
        ok = rollback(args.to)
        return 0 if ok else 1
    elif args.cmd == "evaluate":
        from agent.evaluate import evaluate
        evaluate(use_llm_judge=args.judge, sample_per_topic=args.samples)
    elif args.cmd == "status":
        from agent.evaluate import status
        status()

    return 0


if __name__ == "__main__":
    sys.exit(main())

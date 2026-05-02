"""
JSEdge — Quick test of the ranking engine.

Runs score_all_stocks() for April 28 and prints the top + bottom 10 from
both the main ranking and the incomplete-data ranking.

Usage:
    python scripts/test_ranking.py
"""

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ranking import score_all_stocks, MAIN_RANKING_THRESHOLD


def print_row(rank: int, r: dict) -> None:
    score = r["composite_score"]
    score_str = f"{score:>6.2f}" if score is not None else "  None"
    completeness = r["data_completeness"]
    print(
        f"  {rank:>3}. {r['symbol']:<10} "
        f"score={score_str}  "
        f"complete={completeness:.0%}  "
        f"(p={_fmt(r['position_score'])} "
        f"v={_fmt(r['volume_score'])} "
        f"d={_fmt(r['dividend_score'])} "
        f"r={_fmt(r['range_score'])})"
    )


def _fmt(x):
    return f"{x:>5.1f}" if x is not None else "  ---"


def main() -> None:
    target = date(2026, 4, 28)
    results = score_all_stocks(target)
    
    # Persist results so we have a historical record.
    from app.ranking import save_scores_to_db
    save_result = save_scores_to_db(results, target)
    print(f"\n💾 Saved to DB: {save_result['saved']} scores, "
          f"{save_result['skipped']} skipped (no usable signals)")

    main_ranking = [r for r in results
                    if r["data_completeness"] >= MAIN_RANKING_THRESHOLD]
    incomplete   = [r for r in results
                    if r["data_completeness"] < MAIN_RANKING_THRESHOLD]

    print("=" * 80)
    print(f"JSEdge — Ranking results for {target.isoformat()}")
    print(f"Threshold for main ranking: completeness >= {MAIN_RANKING_THRESHOLD:.0%}")
    print("=" * 80)

    print(f"\n📊 MAIN RANKING ({len(main_ranking)} stocks)")
    if main_ranking:
        print("\nTop 10:")
        for i, r in enumerate(main_ranking[:10], 1):
            print_row(i, r)
        if len(main_ranking) > 10:
            print("\nBottom 5:")
            for i, r in enumerate(main_ranking[-5:], len(main_ranking) - 4):
                print_row(i, r)
    else:
        print("  (none qualified for main ranking)")

    print(f"\n⚠️  INCOMPLETE-DATA RANKING ({len(incomplete)} stocks)")
    if incomplete:
        print("\nTop 10:")
        for i, r in enumerate(incomplete[:10], 1):
            print_row(i, r)
    else:
        print("  (none)")

    print("\n" + "=" * 80)
    print(f"Total scored: {len(results)}")
    print(f"  Main ranking:    {len(main_ranking)}")
    print(f"  Incomplete data: {len(incomplete)}")
    print("=" * 80)


if __name__ == "__main__":
    main()
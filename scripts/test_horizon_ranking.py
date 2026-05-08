"""Quick test of horizon-aware scoring."""

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ranking import score_all_stocks, HORIZON_WEIGHTS, MAIN_RANKING_THRESHOLD


def main() -> None:
    target = date(2026, 4, 28)

    print("=" * 80)
    print(f"JSEdge — Horizon comparison for {target.isoformat()}")
    print("=" * 80)

    for horizon in HORIZON_WEIGHTS.keys():
        results = score_all_stocks(target, horizon)
        main_count = sum(
            1 for r in results
            if r["data_completeness"] is not None
            and r["data_completeness"] >= MAIN_RANKING_THRESHOLD
        )
        incomplete_count = len(results) - main_count

        print(f"\n📊 Horizon: {horizon}")
        print(f"   Main: {main_count}  |  Incomplete: {incomplete_count}")
        print(f"   Top 5:")
        for r in results[:5]:
            score = r["composite_score"]
            score_str = f"{score:>6.2f}" if score is not None else "  ---"
            comp = r["data_completeness"]
            comp_str = f"{comp:.0%}" if comp is not None else "?"
            in_main = "✓" if comp is not None and comp >= MAIN_RANKING_THRESHOLD else "·"
            print(f"     {in_main} {r['symbol']:<10} score={score_str}  complete={comp_str}  rows={r['fundamentals_rows']}")


if __name__ == "__main__":
    main()
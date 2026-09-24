"""Transparent call-center savings model; all inputs must come from the operator."""

from __future__ import annotations

import argparse
import json


def estimate(calls: int, deflection: float, minutes_saved: float, hourly_cost: float) -> dict:
    assisted = calls * deflection
    hours = assisted * minutes_saved / 60
    return {
        "monthly_inbound_calls": calls,
        "assumed_deflection_rate": deflection,
        "assisted_or_deflected_calls": round(assisted, 1),
        "minutes_saved_per_call": minutes_saved,
        "staff_hours_recovered": round(hours, 1),
        "loaded_staff_cost_per_hour": hourly_cost,
        "estimated_monthly_labor_capacity_value": round(hours * hourly_cost, 2),
        "estimated_annual_labor_capacity_value": round(hours * hourly_cost * 12, 2),
        "claim_status": "scenario only; replace every assumption with measured partner data",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=int, required=True)
    parser.add_argument("--deflection", type=float, required=True, help="Decimal, e.g. 0.10")
    parser.add_argument("--minutes-saved", type=float, required=True)
    parser.add_argument("--hourly-cost", type=float, required=True)
    args = parser.parse_args()
    if args.calls < 0 or not 0 <= args.deflection <= 1 or args.minutes_saved < 0 or args.hourly_cost < 0:
        parser.error("inputs must be non-negative and deflection must be between 0 and 1")
    print(json.dumps(estimate(args.calls, args.deflection, args.minutes_saved, args.hourly_cost), indent=2))

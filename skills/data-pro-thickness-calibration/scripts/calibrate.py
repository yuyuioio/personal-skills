#!/usr/bin/env python3
"""Summarize thickness measurements in nm; ratios are fractions, not percentages."""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path


def finite_number(value, label, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected a numeric value (not text)")
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{label}: expected a finite {'nonnegative' if allow_zero else 'positive'} number")
    return float(value)


def summarize(payload):
    groups = payload.get("groups") if isinstance(payload, dict) else payload
    if not isinstance(groups, list) or not groups:
        raise ValueError("Input must be a nonempty group list or an object containing groups")
    result = []
    group_keys = set()
    for index, group in enumerate(groups, 1):
        if not isinstance(group, dict):
            raise ValueError(f"Group {index}: expected an object")
        material = group.get("material")
        batch = group.get("batch", "")
        if not isinstance(material, str) or not material.strip() or not isinstance(batch, str):
            raise ValueError(f"Group {index}: material must be nonempty text and batch must be text")
        key = (batch, material)
        if key in group_keys:
            raise ValueError(f"Duplicate group {key}: use distinct labels for separate samples or targets")
        group_keys.add(key)
        instrument = group.get("instrument_nm")
        if instrument is not None:
            instrument = finite_number(instrument, f"{material} instrument_nm", allow_zero=True)
        readings = group.get("readings")
        if not isinstance(readings, list) or not readings:
            raise ValueError(f"{material}: readings must be a nonempty list")
        samples = set()
        rows = []
        for number, reading in enumerate(readings, 1):
            if not isinstance(reading, dict):
                raise ValueError(f"{material} reading {number}: expected an object")
            sample = reading.get("sample")
            if not isinstance(sample, str) or not sample.strip() or sample in samples:
                raise ValueError(f"{material}: sample labels must be nonempty and unique")
            samples.add(sample)
            value = finite_number(reading.get("measured_nm"), f"{sample} measured_nm")
            row = dict(reading)
            for field in ("fit_error_nm", "mse"):
                if row.get(field) is not None:
                    row[field] = finite_number(row[field], f"{sample} {field}", allow_zero=True)
            row.update(
                measured_nm=value,
                difference_nm=value - instrument if instrument is not None else None,
                relative_bias=(value - instrument) / instrument if instrument else None,
            )
            rows.append(row)
        values = [row["measured_nm"] for row in rows]
        mean = statistics.mean(values)
        sd = statistics.stdev(values) if len(values) > 1 else None
        difference = mean - instrument if instrument is not None else None
        if instrument is None:
            status = "待补充显示厚度"
        elif instrument == 0:
            status = "显示厚度为0，比例待确认"
        else:
            status = "实测偏厚" if difference > 0 else "实测偏薄" if difference < 0 else "一致"
        result.append({
            "material": material,
            "batch": batch,
            "n": len(values),
            "instrument_nm": instrument,
            "mean_nm": mean,
            "sample_sd_nm": sd,
            "cv": sd / mean if sd is not None else None,
            "difference_nm": difference,
            "relative_bias": difference / instrument if instrument else None,
            "measured_to_instrument": mean / instrument if instrument else None,
            "status": status,
            "readings": rows,
        })
    return {"unit": "nm", "bias_definition": "(mean_nm-instrument_nm)/instrument_nm", "groups": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 JSON measurements")
    parser.add_argument("--output", type=Path, help="Output JSON; otherwise write to stdout")
    args = parser.parse_args()
    try:
        if args.output and args.input.resolve() == args.output.resolve():
            raise ValueError("Output must not overwrite the input measurements")
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        text = json.dumps(summarize(payload), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except (OSError, ValueError, TypeError, OverflowError, statistics.StatisticsError) as exc:
        parser.exit(2, f"Thickness calibration failed: {exc}\n")


if __name__ == "__main__":
    main()

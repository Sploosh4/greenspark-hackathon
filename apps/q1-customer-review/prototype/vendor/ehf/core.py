"""Pure EHF arithmetic and explicit calendar-window handling (standard library)."""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import json
import math
from statistics import fmean

METHOD_VERSION = "ehf-derived-forward/v1"
CALIBRATION_SCHEMA = "ehf-experiment-calibration/v1"
OUTPUT_SCHEMA = "ehf-experiment-output/v1"
WINDOW = "Australia-Perth-0900-to-next-0900/v1"
TIMEZONE = "Australia/Perth"
DAY = timedelta(days=1)


def iso_day(value):
    if not isinstance(value, str):
        raise ValueError("date must be a canonical YYYY-MM-DD string")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("date must be a canonical YYYY-MM-DD string")
    return parsed


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("temperature must be a finite number, or explicit null")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("temperature must be finite")
    return value


def days(start, end):
    if end < start:
        raise ValueError("end date precedes start date")
    return [start + i * DAY for i in range((end - start).days + 1)]


def canonical_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass(frozen=True)
class Source:
    source_id: str
    provider: str
    dataset: str
    classification: str
    latitude: float
    longitude: float
    adapter_reference_version: str
    timezone: str = TIMEZONE
    temperature_unit: str = "degC"
    day_window_reference_version: str = WINDOW
    input_sha256: str | None = None
    issue_time: str | None = None

    def __post_init__(self):
        for key in ("source_id", "provider", "dataset", "classification", "adapter_reference_version"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key).strip():
                raise ValueError(f"{key} must be a non-empty string")
        if not -90 <= finite_number(self.latitude) <= 90:
            raise ValueError("invalid latitude")
        if not -180 <= finite_number(self.longitude) <= 180:
            raise ValueError("invalid longitude")
        if self.timezone != TIMEZONE or self.temperature_unit != "degC":
            raise ValueError("prototype requires Australia/Perth dates and degC")
        if self.day_window_reference_version != WINDOW:
            raise ValueError("unsupported day-window convention")


@dataclass(frozen=True)
class Daily:
    date: str
    dmt_c: float | None
    source_id: str
    issues: tuple[str, ...] = ()

    def __post_init__(self):
        iso_day(self.date)
        if self.dmt_c is not None:
            finite_number(self.dmt_c)
        if self.issues and self.dmt_c is not None:
            raise ValueError("a day with data issues must have null DMT")


@dataclass(frozen=True)
class Series:
    sources: tuple[Source, ...]
    points: tuple[Daily, ...]

    def __post_init__(self):
        identities = {s.source_id: s for s in self.sources}
        if not identities or len(identities) != len(self.sources):
            raise ValueError("source identities must be present and unique")
        locations = {(s.latitude, s.longitude) for s in self.sources}
        if len(locations) != 1:
            raise ValueError("mixed locations are not accepted")
        dates = [p.date for p in self.points]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate daily date")
        if any(p.source_id not in identities for p in self.points):
            raise ValueError("daily point refers to an unknown source")

    def indexed(self):
        return {iso_day(p.date): p for p in self.points}


def combine_series(*series):
    """Combine explicit history/forecast sources; overlapping dates require review."""
    sources = {}
    points = []
    for item in series:
        for source in item.sources:
            if source.source_id in sources and sources[source.source_id] != source:
                raise ValueError("conflicting source identity")
            sources[source.source_id] = source
        points.extend(item.points)
    return Series(tuple(sources.values()), tuple(points))


def percentile_linear(values, probability):
    """Sorted sample, position (n-1)*p, linear interpolation (Hyndman-Fan type 7)."""
    if not 0 <= probability <= 1 or not values:
        raise ValueError("non-empty values and probability in [0,1] required")
    ordered = sorted(finite_number(v) for v in values)
    position = (len(ordered) - 1) * probability
    lo = math.floor(position)
    hi = math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def calibrate(series, baseline_start="1991-01-01", baseline_end="2020-12-31"):
    """Require complete, all-year baseline DMT, including its final shifted night."""
    start, end = iso_day(baseline_start), iso_day(baseline_end)
    if start.month != 1 or start.day != 1 or end.month != 12 or end.day != 31:
        raise ValueError("baseline must span complete calendar years")
    points = series.indexed()
    expected = days(start, end)
    if any(d not in points or points[d].dmt_c is None for d in expected):
        raise ValueError("baseline contains missing or unavailable DMT; no gap filling")
    used_ids = {points[d].source_id for d in expected}
    if len(used_ids) != 1:
        raise ValueError("calibration requires one homogeneous source")
    source = next(s for s in series.sources if s.source_id in used_ids)
    values = [points[d].dmt_c for d in expected]
    result = {
        "schema_version": CALIBRATION_SCHEMA,
        "method_version": METHOD_VERSION,
        "approval_status": "prototype_requires_human_review",
        "baseline": {"start": start.isoformat(), "end": end.isoformat(),
                     "population": "all_calendar_days_DMT", "sample_count": len(values),
                     "missing_count": 0, "reference_original_period": "1971-2000",
                     "prototype_alternative": True},
        "percentile": {"probability": 0.95, "method": "linear_n_minus_1_type7/v1"},
        "t95_c": percentile_linear(values, 0.95),
        "source": asdict(source),
        "baseline_dmt_sha256": canonical_hash([[d.isoformat(), points[d].dmt_c] for d in expected]),
        "severity": {"status": "unavailable", "reason": "separate_calibration_review_required",
                     "ehf85_k2": None},
        "official_bom_match": False,
    }
    result["calibration_id"] = "sha256:" + canonical_hash(result)
    return result


def validate_calibration(calibration, series):
    if calibration.get("schema_version") != CALIBRATION_SCHEMA:
        raise ValueError("unsupported calibration schema")
    if calibration.get("method_version") != METHOD_VERSION:
        raise ValueError("unsupported calibration method")
    body = {k: v for k, v in calibration.items() if k != "calibration_id"}
    if calibration.get("calibration_id") != "sha256:" + canonical_hash(body):
        raise ValueError("calibration content hash mismatch")
    finite_number(calibration["t95_c"])
    reference = Source(**calibration["source"])
    for source in series.sources:
        for key in ("latitude", "longitude", "timezone", "temperature_unit", "day_window_reference_version"):
            if getattr(source, key) != getattr(reference, key):
                raise ValueError(f"source/calibration mismatch: {key}")


def ehf_components(target, previous, t95_c):
    """Independent arithmetic primitive; EHF remains signed, presence is EHF > 0."""
    if len(target) != 3 or len(previous) != 30:
        raise ValueError("exactly 3 target and 30 previous complete DMTs required")
    m3 = fmean(finite_number(t) for t in target)
    m30 = fmean(finite_number(t) for t in previous)
    sig, accl = m3 - finite_number(t95_c), m3 - m30
    return {"m3_c": m3, "m30_c": m30, "ehi_sig_c": sig, "ehi_accl_c": accl,
            "ehf_k2": sig * max(1.0, accl), "heatwave": sig > 0}


def period(indexed, start, t95_c):
    needed = days(start - 30 * DAY, start + 2 * DAY)
    problems = []
    for d in needed:
        if d not in indexed:
            problems.append({"date": d.isoformat(), "reason": "missing_dmt_date"})
        elif indexed[d].dmt_c is None:
            problems.append({"date": d.isoformat(), "reason": "null_dmt",
                             "details": list(indexed[d].issues)})
    result = {"start": start.isoformat(), "end": (start + 2 * DAY).isoformat(),
              "status": "unavailable" if problems else "available", "issues": problems}
    if problems:
        result.update({k: None for k in ("m3_c", "m30_c", "ehi_sig_c", "ehi_accl_c", "ehf_k2", "heatwave")})
    else:
        result.update(ehf_components([indexed[start + i * DAY].dmt_c for i in range(3)],
                                     [indexed[start - i * DAY].dmt_c for i in range(30, 0, -1)], t95_c))
    return result


def calculate(series, calibration, display_start, display_end):
    """Evaluate starts d-2..end, retaining unknown periods and covered positive days.

    Day absence requires all three covering periods to be available and nonpositive.
    Day intensity is the greatest positive EHF of available periods covering it.
    Events are unions of adjacent covered days, not sums of three-day durations.
    """
    validate_calibration(calibration, series)
    start, end = iso_day(display_start), iso_day(display_end)
    display_dates = days(start, end)
    indexed = series.indexed()
    periods = [period(indexed, d, calibration["t95_c"]) for d in days(start - 2 * DAY, end)]
    by_start = {iso_day(p["start"]): p for p in periods}
    day_rows = []
    for d in display_dates:
        covering = [by_start[d - i * DAY] for i in range(3)]
        available = [p for p in covering if p["status"] == "available"]
        positive = [p for p in available if p["heatwave"]]
        state = "present" if positive else ("absent" if len(available) == 3 else "unavailable")
        day_rows.append({"date": d.isoformat(), "presence": state,
                         "intensity_k2": max(p["ehf_k2"] for p in positive) if positive else
                         (0.0 if state == "absent" else None),
                         "covering_periods_complete": len(available) == 3,
                         "positive_period_starts": [p["start"] for p in positive],
                         "severity": None})
    # This prototype reports observed event segments within the display range.
    # Additional periods are evaluated solely to distinguish a closed boundary.
    events = []
    for row in day_rows:
        if row["presence"] != "present":
            continue
        d = iso_day(row["date"])
        if not events or iso_day(events[-1]["end"]) + DAY != d:
            events.append({"start": row["date"], "end": row["date"],
                           "duration_days_in_display": 1, "peak_ehf_k2": row["intensity_k2"]})
        else:
            events[-1]["end"] = row["date"]
            events[-1]["duration_days_in_display"] += 1
            events[-1]["peak_ehf_k2"] = max(events[-1]["peak_ehf_k2"], row["intensity_k2"])

    def presence_outside(d):
        ps = [period(indexed, d - i * DAY, calibration["t95_c"]) for i in range(3)]
        if any(p["heatwave"] is True for p in ps):
            return "present"
        return "absent" if all(p["status"] == "available" for p in ps) else "unavailable"

    for event in events:
        before = presence_outside(iso_day(event["start"]) - DAY)
        after = presence_outside(iso_day(event["end"]) + DAY)
        event.update({"start_boundary": "known_start" if before == "absent" else
                      ("continues_from_earlier" if before == "present" else "unknown"),
                      "end_boundary": "known_end" if after == "absent" else
                      ("continues_later" if after == "present" else "unknown"),
                      "forecast_boundary_continuation_unknown": after == "unavailable",
                      "full_event_duration_days": event["duration_days_in_display"]
                      if before == after == "absent" else None})
    return {"schema_version": OUTPUT_SCHEMA, "method_version": METHOD_VERSION,
            "calibration_id": calibration["calibration_id"], "t95_c": calibration["t95_c"],
            "approval_status": "prototype_requires_human_review", "official_bom_match": False,
            "sources": [asdict(s) for s in series.sources],
            "day_window_reference_version": WINDOW, "timezone": TIMEZONE,
            "display": {"start": display_start, "end": display_end},
            "units": {"temperature": "degC", "ehf": "K2"},
            "semantics": {"period_date": "first_day_of_forward_three_day_period",
                          "day_presence": "union_of_positive_covering_periods",
                          "day_intensity": "maximum_positive_covering_period_EHF",
                          "event_duration": "consecutive_positive_covered_days_in_display",
                          "missing_data": "unavailable_no_imputation",
                          "severity": "unavailable_pending_separate_calibration_review"},
            "periods": periods, "days": day_rows, "events": events,
            "severity": {"status": "unavailable", "ehf85_k2": None},
            "limitations": ["Experimental presence and intensity; no forecast accuracy validation.",
                            "Cross-source or hourly-extrema inputs need separate comparability review."]}

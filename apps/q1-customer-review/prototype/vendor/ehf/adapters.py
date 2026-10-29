"""Offline adapters. No downloading, implicit temperature conversion or gap filling."""

import csv
from datetime import datetime, time, timedelta
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import Daily, Series, DAY, TIMEZONE, days, finite_number, iso_day

SILO_ADAPTER = "silo-shifted-next-night/v1"
HOURLY_ADAPTER = "open-meteo-hourly-0900-extrema/v1"


def _temperature(value):
    if value is None or (isinstance(value, str) and value.strip().lower() in ("", "null", "na", "nan")):
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a temperature")
    result = finite_number(float(value))
    if result in (-99.9, -999, -9999):
        return None
    return result


def silo_rows(rows, source, *, units="degC", allowed_source_codes=("25",)):
    """Tmax(i) from 09:00 i, Tmin(i+1) ending 09:00 i+1; DMT dated i.

    Rows may have gaps. Each date is retained; absent next date/minimum stays null.
    Default accepts only code 25 (interpolated daily observations).
    """
    if units != "degC" or source.adapter_reference_version != SILO_ADAPTER:
        raise ValueError("SILO requires explicit degC and shifted-night adapter identity")
    indexed = {}
    for row in rows:
        d = iso_day(row["YYYY-MM-DD"].strip())
        if d in indexed:
            raise ValueError("duplicate SILO date")
        lat, lon = float(row["latitude"]), float(row["longitude"])
        if (lat, lon) != (source.latitude, source.longitude):
            raise ValueError("SILO grid does not match source identity")
        for key in ("max_temp_source", "min_temp_source"):
            if str(row[key]).strip() not in allowed_source_codes:
                raise ValueError(f"unreviewed SILO source code: {row[key]}")
        indexed[d] = (_temperature(row["max_temp"]), _temperature(row["min_temp"]))
    result = []
    for d, (maximum, _) in sorted(indexed.items()):
        issues = []
        if maximum is None:
            issues.append("missing_tmax")
        if d + DAY not in indexed:
            issues.append("missing_following_date_for_tmin")
            minimum = None
        else:
            minimum = indexed[d + DAY][1]
            if minimum is None:
                issues.append("missing_following_night_tmin")
        if not issues and minimum > maximum:
            issues.append("following_tmin_above_tmax")
        result.append(Daily(d.isoformat(), None if issues else (maximum + minimum) / 2,
                            source.source_id, tuple(issues)))
    return Series((source,), tuple(result))


def silo_csv(path, source):
    data = Path(path).read_bytes()
    if source.input_sha256 is not None and hashlib.sha256(data).hexdigest() != source.input_sha256:
        raise ValueError("SILO raw file hash mismatch")
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return silo_rows(csv.DictReader(stream), source)


def open_meteo_hourly(payload, source, start, end):
    """Approximate DMT using max/min of 24 hourly 2 m samples in [09:00, next09:00).

    Naive timestamps require payload's explicit Perth timezone and UTC offset;
    offset-aware ISO timestamps are converted to Perth. Missing/null samples
    invalidate the whole daily window. Daily forecast extrema are not accepted.
    """
    if source.adapter_reference_version != HOURLY_ADAPTER:
        raise ValueError("hourly adapter identity required")
    if payload.get("timezone") != TIMEZONE or payload.get("utc_offset_seconds") != 28800:
        raise ValueError("hourly payload must explicitly declare Australia/Perth, UTC+08:00")
    if (payload.get("latitude"), payload.get("longitude")) != (source.latitude, source.longitude):
        raise ValueError("hourly grid does not match source identity")
    if payload.get("hourly_units", {}).get("temperature_2m") not in ("°C", "degC"):
        raise ValueError("hourly temperatures must have explicit Celsius units")
    hourly = payload["hourly"]
    stamps, values = hourly["time"], hourly["temperature_2m"]
    if len(stamps) != len(values):
        raise ValueError("hourly times and temperatures have different lengths")
    zone = ZoneInfo(TIMEZONE)
    samples = {}
    for stamp, value in zip(stamps, values):
        instant = datetime.fromisoformat(stamp)
        local = instant.replace(tzinfo=zone) if instant.tzinfo is None else instant.astimezone(zone)
        if local.minute or local.second or local.microsecond:
            raise ValueError("hourly samples must be on the hour")
        if local in samples:
            raise ValueError("duplicate hourly instant")
        samples[local] = _temperature(value)
    result = []
    for d in days(iso_day(start), iso_day(end)):
        first = datetime.combine(d, time(9), zone)
        needed = [first + timedelta(hours=h) for h in range(24)]
        missing = [t.isoformat() for t in needed if t not in samples or samples[t] is None]
        if missing:
            result.append(Daily(d.isoformat(), None, source.source_id,
                                tuple("missing_or_null_hour:" + t for t in missing)))
        else:
            temperatures = [samples[t] for t in needed]
            result.append(Daily(d.isoformat(), (max(temperatures) + min(temperatures)) / 2,
                                source.source_id))
    return Series((source,), tuple(result))

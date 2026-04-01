"""Flight counting and statistics with JSON persistence."""

from datetime import datetime, timedelta
import json
import logging
import os

logger = logging.getLogger(__name__)


def load_unique_flights_data(file_path: str) -> dict:
    """Load flight data from JSON file."""
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                raw = json.load(f)
            # Convert ISO strings back to datetime
            return {icao_id: datetime.fromisoformat(ts) for icao_id, ts in raw.items()}
    except Exception:
        logger.exception("Error loading flight data from %s", file_path)
    return {}


def save_unique_flights_data(file_path: str, data: dict) -> None:
    """Save flight data to JSON file."""
    try:
        serializable = {icao_id: ts.isoformat() for icao_id, ts in data.items()}
        with open(file_path, "w") as f:
            json.dump(serializable, f, indent=2)
    except Exception:
        logger.exception("Error saving flight data to %s", file_path)
        raise


def update_unique_flights(
    unique_flights_with_timestamps: dict,
    current_unique_flights: set,
    _check_interval: int,
) -> None:
    """Update flight timestamps for currently visible flights."""
    current_time = datetime.now()
    for icao_id in current_unique_flights:
        unique_flights_with_timestamps[icao_id] = current_time


def count_unique_flights_in_period(
    unique_flights_with_timestamps: dict, start_time: datetime
) -> int:
    """Count flights since start_time."""
    return sum(
        1
        for timestamp in unique_flights_with_timestamps.values()
        if timestamp >= start_time
    )


def get_time_periods() -> dict[str, datetime]:
    """Get dictionary of time periods for statistics."""
    current_time = datetime.now()
    return {
        "previous_year": current_time - timedelta(days=365),
        "previous_thirty_days": current_time - timedelta(days=30),
        "previous_seven_days": current_time - timedelta(days=7),
        "yesterday": (current_time - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ),
        "today": current_time.replace(hour=0, minute=0, second=0, microsecond=0),
    }


def calculate_averages(
    unique_flights_with_timestamps: dict,
    unique_flights_counts: dict,
) -> dict:
    """Calculate flight averages for different time periods."""
    try:
        averages = {}
        current_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        unique_dates = {
            timestamp.date()
            for timestamp in unique_flights_with_timestamps.values()
            if timestamp < current_time
        }

        period_lengths = {
            "previous_year": 365,
            "previous_thirty_days": 30,
            "previous_seven_days": 7,
        }

        for period, max_days in period_lengths.items():
            period_start_time = get_time_periods()[period]
            period_dates = {
                timestamp.date()
                for timestamp in unique_flights_with_timestamps.values()
                if period_start_time <= timestamp < current_time
            }

            days = min(len(period_dates) or 1, max_days)
            averages[period] = round(unique_flights_counts.get(period, 0) / days)

        if len(unique_dates) <= 1:
            averages["daily_average"] = unique_flights_counts.get("yesterday", 0)
        else:
            total = len(
                {
                    icao_id
                    for icao_id, ts in unique_flights_with_timestamps.items()
                    if ts < current_time
                }
            )
            total_days = len(unique_dates) or 1
            averages["daily_average"] = round(total / total_days)

        return averages
    except Exception:
        logger.exception("Error calculating averages")
        return {}

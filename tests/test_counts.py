"""Tests for flight counting and statistics."""

from datetime import datetime, timedelta

from flights.counts import (
    calculate_averages,
    count_unique_flights_in_period,
    get_time_periods,
    load_unique_flights_data,
    save_unique_flights_data,
    update_unique_flights,
)


def test_get_time_periods():
    """Time periods are returned with correct keys."""
    periods = get_time_periods()
    assert "today" in periods
    assert "yesterday" in periods
    assert "previous_seven_days" in periods
    assert "previous_thirty_days" in periods
    assert "previous_year" in periods
    assert all(isinstance(v, datetime) for v in periods.values())


def test_count_unique_flights():
    """Count only flights after start_time."""
    now = datetime.now()
    data = {
        "A": now - timedelta(hours=1),
        "B": now - timedelta(days=2),
        "C": now - timedelta(days=10),
    }
    assert count_unique_flights_in_period(data, now - timedelta(hours=2)) == 1
    assert count_unique_flights_in_period(data, now - timedelta(days=3)) == 2
    assert count_unique_flights_in_period(data, now - timedelta(days=11)) == 3


def test_update_unique_flights():
    """Update adds timestamps for new flights."""
    data = {}
    update_unique_flights(data, {"A", "B"}, 15)
    assert "A" in data
    assert "B" in data
    assert isinstance(data["A"], datetime)


def test_save_and_load(tmp_path):
    """Flight data round-trips through JSON."""
    file_path = str(tmp_path / "flights.json")
    now = datetime.now()
    data = {"ABC123": now, "DEF456": now - timedelta(hours=1)}

    save_unique_flights_data(file_path, data)
    loaded = load_unique_flights_data(file_path)

    assert set(loaded.keys()) == {"ABC123", "DEF456"}
    assert abs((loaded["ABC123"] - now).total_seconds()) < 1


def test_load_missing_file():
    """Loading from nonexistent file returns empty dict."""
    assert load_unique_flights_data("/nonexistent/file.json") == {}


def test_calculate_averages():
    """Averages are calculated for time periods."""
    now = datetime.now()
    data = {f"flight_{i}": now - timedelta(hours=i) for i in range(24)}
    counts = {
        "previous_year": 24,
        "previous_thirty_days": 24,
        "previous_seven_days": 24,
        "yesterday": 10,
        "today": 5,
    }
    averages = calculate_averages(data, counts)
    assert "daily_average" in averages
    assert isinstance(averages["daily_average"], int)

#!/usr/bin/env python3

import os
import pickle
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from collections import defaultdict

def setup_logging():
    """Configure logging with file output"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    log_dir = os.path.join(project_root, 'logs')
    
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'flight_counts.log')
    
    handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,
        backupCount=5
    )
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    logger.info("Logging initialized - writing to %s", log_file)
    return logger

# Initialize logger
logger = setup_logging()

def load_unique_flights_data(file_path):
    """Load flight data from pickle file."""
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            return pickle.load(f)
    return {}

def save_unique_flights_data(file_path, data):
    """Save flight data to pickle file."""
    with open(file_path, 'wb') as f:
        pickle.dump(data, f)

def update_unique_flights(unique_flights_with_timestamps, current_unique_flights, check_interval):
    """Update flight timestamps, using check_interval for gap detection."""
    k_interval = check_interval * 1.75
    current_time = datetime.now()
    gaps_detected = 0
    
    for icao_id in current_unique_flights:
        try:
            if icao_id in unique_flights_with_timestamps:
                last_seen = unique_flights_with_timestamps[icao_id]
                time_diff = (current_time - last_seen).total_seconds()
                
                if time_diff > k_interval:
                    gaps_detected += 1
                    logger.warning("Data gap detected for flight %s: %.1f seconds (> %.1f)",
                                 icao_id, time_diff, k_interval)
            
            unique_flights_with_timestamps[icao_id] = current_time
            
        except Exception as e:
            logger.error("Error processing flight %s: %s", icao_id, str(e))
    
    if gaps_detected:
        logger.info("Update complete: %d gaps detected in %d flights",
                   gaps_detected, len(current_unique_flights))
    
    # Log summary every hour
    if current_time.minute == 0:
        log_unique_flights_summary(unique_flights_with_timestamps)

def count_unique_flights_in_period(unique_flights_with_timestamps, start_time):
    """Count flights since start_time."""
    return sum(1 for timestamp in unique_flights_with_timestamps.values() 
              if timestamp >= start_time)

def get_time_periods():
    """Get dictionary of time periods for statistics."""
    current_time = datetime.now()
    return {
        'previous_year': current_time - timedelta(days=365),
        'previous_thirty_days': current_time - timedelta(days=30),
        'previous_seven_days': current_time - timedelta(days=7),
        'yesterday': (current_time - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0),
        'today': current_time.replace(
            hour=0, minute=0, second=0, microsecond=0)
    }

def calculate_averages(unique_flights_with_timestamps, unique_flights_counts):
    """Calculate flight averages for different time periods."""
    averages = {}
    current_time = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0)
    
    # Get dates excluding today
    unique_dates = {
        timestamp.date() 
        for timestamp in unique_flights_with_timestamps.values() 
        if timestamp < current_time
    }
    
    logger.info("Processing averages for %d unique dates", len(unique_dates))
    logger.debug("Unique dates: %s", sorted(list(unique_dates)))
    
    # Calculate period averages
    period_lengths = {
        'previous_year': 365,
        'previous_thirty_days': 30,
        'previous_seven_days': 7
    }
    
    for period, max_days in period_lengths.items():
        period_start_time = get_time_periods()[period]
        period_dates = {
            timestamp.date() 
            for timestamp in unique_flights_with_timestamps.values() 
            if period_start_time <= timestamp < current_time
        }
        
        days = len(period_dates) or 1
        days = min(days, max_days)
        averages[period] = round(unique_flights_counts[period] / days)
        
        logger.info("%s: Found %d flights over %d days, average: %d",
                   period, unique_flights_counts[period], days, averages[period])
    
    # Calculate daily average using yesterday's count if only one historical day
    if len(unique_dates) <= 1 and 'yesterday' in unique_flights_counts:
        averages['daily_average'] = unique_flights_counts['yesterday']
        logger.info("Using yesterday's count (%d) as daily average due to limited history",
                   unique_flights_counts['yesterday'])
    else:
        total_unique_flights = len({
            icao_id 
            for icao_id, timestamp in unique_flights_with_timestamps.items() 
            if timestamp < current_time
        })
        total_days = len(unique_dates) or 1
        averages['daily_average'] = round(total_unique_flights / total_days)
        logger.info("Calculated daily average: %d flights over %d days",
                   total_unique_flights, total_days)
    
    return averages

def log_unique_flights_summary(unique_flights_with_timestamps):
    """Log summary of unique flights data structure"""
    current_time = datetime.now()
    total_entries = len(unique_flights_with_timestamps)
    
    # Get date range
    if total_entries > 0:
        timestamps = unique_flights_with_timestamps.values()
        oldest = min(timestamps)
        newest = max(timestamps)
        date_range = (newest - oldest).days
    else:
        date_range = 0
        
    logger.info("Unique Flights Summary:")
    logger.info("Total entries: %d", total_entries)
    logger.info("Date range: %d days", date_range)
    
    # Sample of recent entries (last 5)
    recent = sorted(
        unique_flights_with_timestamps.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    if recent:
        logger.info("Recent entries:")
        for icao_id, timestamp in recent:
            logger.info("  %s: %s", icao_id, timestamp.strftime('%Y-%m-%d %H:%M:%S'))
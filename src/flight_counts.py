#!/usr/bin/env python3

import os
import pickle
from datetime import datetime, timedelta
from collections import defaultdict
import yaml
import logging
import traceback

# Use absolute path for logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Load config first to get log level
config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
with open(config_path, 'r') as config_file:
    config = yaml.safe_load(config_file)

logger = logging.getLogger('flight_counts')

def initialize_logging(log_level: str = 'ERROR'):
    """Initialize logging for flight counts module"""
    logger.setLevel(getattr(logging, log_level.upper()))

initialize_logging(config.get('LOG_LEVEL', 'ERROR'))

# Configure logging
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'flights.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def load_unique_flights_data(file_path):
    """Load flight data from pickle file."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                return pickle.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading flight data from {file_path}: {str(e)}\n{traceback.format_exc()}")
        return {}

def save_unique_flights_data(file_path, data):
    """Save flight data to pickle file."""
    try:
        with open(file_path, 'wb') as f:
            pickle.dump(data, f)
    except Exception as e:
        logger.error(f"Error saving flight data to {file_path}: {str(e)}\n{traceback.format_exc()}")
        raise

def update_unique_flights(unique_flights_with_timestamps, current_unique_flights, check_interval):
    """Update flight timestamps, using check_interval for gap detection."""
    try:
        k_interval = check_interval * 1.75
        current_time = datetime.now()
        gaps_detected = 0
        
        for icao_id in current_unique_flights:
            try:
                if icao_id in unique_flights_with_timestamps:
                    last_seen = unique_flights_with_timestamps[icao_id]
                    time_diff = (current_time - last_seen).total_seconds()
                
                unique_flights_with_timestamps[icao_id] = current_time
                
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error updating unique flights: {str(e)}\n{traceback.format_exc()}")
        raise

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
    try:
        averages = {}
        current_time = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        
        # Get dates excluding today
        unique_dates = {
            timestamp.date() 
            for timestamp in unique_flights_with_timestamps.values() 
            if timestamp < current_time
        }
        
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
        
        # Calculate daily average using yesterday's count if only one historical day
        if len(unique_dates) <= 1 and 'yesterday' in unique_flights_counts:
            averages['daily_average'] = unique_flights_counts['yesterday']
        else:
            total_unique_flights = len({
                icao_id 
                for icao_id, timestamp in unique_flights_with_timestamps.items() 
                if timestamp < current_time
            })
            total_days = len(unique_dates) or 1
            averages['daily_average'] = round(total_unique_flights / total_days)
        
        return averages
    except Exception as e:
        logger.error(f"Error calculating averages: {str(e)}\n{traceback.format_exc()}")
        return {}

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
    
    # Sample of recent entries (last 5)
    recent = sorted(
        unique_flights_with_timestamps.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
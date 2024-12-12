#!/usr/bin/env python3

import os
import pickle
from datetime import datetime, timedelta

def load_unique_flights_data(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            return pickle.load(f)
    return {}

def save_unique_flights_data(file_path, data):
    with open(file_path, 'wb') as f:
        pickle.dump(data, f)

def update_unique_flights(unique_flights_with_timestamps, current_unique_flights):
    current_time = datetime.now()
    for icao_id in current_unique_flights:
        unique_flights_with_timestamps[icao_id] = current_time

def count_unique_flights_in_period(unique_flights_with_timestamps, start_time):
    return sum(1 for timestamp in unique_flights_with_timestamps.values() if timestamp >= start_time)

def get_time_periods():
    current_time = datetime.now()
    return {
        'previous_year': current_time - timedelta(days=365),
        'previous_thirty_days': current_time - timedelta(days=30),
        'previous_seven_days': current_time - timedelta(days=7),
        'yesterday': (current_time - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        'today': current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    }

def calculate_averages(unique_flights_with_timestamps, unique_flights_counts):
    averages = {}
    current_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get all dates excluding today
    unique_dates = {timestamp.date() for timestamp in unique_flights_with_timestamps.values() 
                   if timestamp < current_time}
    total_days = len(unique_dates)

    if total_days == 0:
        total_days = 1  # Avoid division by zero

def calculate_averages(unique_flights_with_timestamps, unique_flights_counts):
    averages = {}
    current_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get all dates excluding today
    unique_dates = {timestamp.date() for timestamp in unique_flights_with_timestamps.values() 
                   if timestamp < current_time}
    total_days = len(unique_dates)

    if total_days == 0:
        total_days = 1  # Avoid division by zero

    # Calculate period averages
    for period in ['previous_year', 'previous_thirty_days', 'previous_seven_days']:
        period_start_time = get_time_periods()[period]
        period_dates = {timestamp.date() 
                       for timestamp in unique_flights_with_timestamps.values() 
                       if period_start_time <= timestamp < current_time}
        
        days = len(period_dates)
        if days == 0:
            days = 1
            
        if period == 'previous_year':
            max_days = 365
        elif period == 'previous_thirty_days':
            max_days = 30
        elif period == 'previous_seven_days':
            max_days = 7
            
        # Use minimum of actual days or period length
        days = min(days, max_days)
        averages[period] = round(unique_flights_counts[period] / days)

    # Calculate daily average from total unique flights divided by total days
    total_unique_flights = len({icao_id for icao_id, timestamp in unique_flights_with_timestamps.items() 
                              if timestamp < current_time})  # Exclude today
    averages['daily_average'] = round(total_unique_flights / total_days)

    return averages
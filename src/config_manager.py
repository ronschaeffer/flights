import os
import yaml

# Define base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load configuration
config_path = os.path.join(BASE_DIR, 'config/config.yaml')
with open(config_path, 'r') as config_file:
    config = yaml.safe_load(config_file)
# Flights Project: MQTT and HTTP API Functionality Documentation

## Overview
This document thoroughly analyzes the MQTT publishing and HTTP API/hosting functionality in the legacy Flights project to enable replacement with reusable `mqtt_publisher` and `web_host` libraries.

## 1. MQTT Functionality Analysis

### 1.1 Current Implementation (`src/mqtt_service.py`)

**Core MQTT Service Class**: `MQTTService`

**Initialization Requirements:**
- **Client Configuration:**
  - Client ID: configurable (default: 'flight_tracker')
  - MQTT version: uses `mqtt.CallbackAPIVersion.VERSION2`
  - Authentication: username/password (optional)
  
- **Connection Parameters:**
  - Broker host: required (from config `MQTT_BROKER`)
  - Broker port: required (from config `MQTT_BROKER_PORT`) 
  - User/Password: optional (from config `MQTT_USER`, `MQTT_PWD`)

- **Topic Management:**
  - Predefined topic list stored internally
  - Topics from config: `MQTT_TOPIC_VISIBLE`, `MQTT_TOPIC_CLOSEST_AIRCRAFT`
  - Default topics: `'dev/flights/visible'`, `'dev/flights/closest'`

**Key Methods:**

1. **`connect()`**
   - Establishes broker connection
   - Starts non-blocking loop (`client.loop_start()`)
   - Prints connection confirmation with broker details and topics
   - Exception handling with logging

2. **`disconnect()`**
   - Stops loop (`client.loop_stop()`)
   - Disconnects from broker

3. **`publish(topic, payload, qos=1, retain=True)`**
   - Auto-converts dict payloads to JSON strings
   - Default QoS level: 1 (at least once delivery)
   - Default retain: True (last message persisted)
   - Exception handling with topic-specific error logging

**Logging Integration:**
- Uses module-specific logger: `'mqtt_service'`
- Log level from config: `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Error logging includes topic and detailed traceback

### 1.2 MQTT Usage Patterns in Main Application

**Publishing Flow:**
```python
# 1. Service initialization
mqtt_service = MQTTService(config)
mqtt_service.connect()

# 2. Data publishing through helper function
previous_data = publish_and_print(
    mqtt_service, 
    topic,
    data, 
    previous_data,
    file_path,
    print_func
)
```

**Helper Function (`publish_and_print`):**
- Only publishes if data has changed (comparison with previous data)
- Writes data to local JSON file
- Calls optional print function for console output
- Returns current data (becomes next iteration's previous data)

**Active Topics and Data:**

1. **`MQTT_TOPIC_VISIBLE` (default: "dev/flights/visible")**
   - **Data Structure:**
     ```json
     {
       "visible_aircraft": 11,
       "last_update_utc": 1736216108,
       "last_update_readable": "2025-01-07 02:15:08",
       "unique_flights": {
         "previous_year": 157,
         "previous_thirty_days": 157,
         "previous_seven_days": 157,
         "yesterday": 157,
         "today": 0
       },
       "average_flights": {
         "previous_year": 157,
         "previous_thirty_days": 157,
         "previous_seven_days": 157,
         "daily_average": 157
       }
     }
     ```
   - **Update Frequency:** Every `CHECK_INTERVAL` seconds (default: 15)
   - **Publish Condition:** Only when data changes

2. **`MQTT_TOPIC_CLOSEST_AIRCRAFT` (default: "dev/flights/closest")**
   - **Data Structure:** Complete enriched aircraft object with flight details
   - **Sample Data:** (see `closest_aircraft.json` above)
   - **Update Frequency:** Every `CHECK_INTERVAL` seconds (default: 15)
   - **Publish Condition:** Only when closest aircraft changes

### 1.3 Home Assistant MQTT Discovery Integration

**Discovery Process:**
1. **Conditional Activation:** Only if `HA_MQTT_DISCOVERY: true` in config
2. **Payload Generation:** Uses template from `HA_MQTT_DISCOVERY_CONFIG` in YAML
3. **Variable Substitution:** Replaces `${VARIABLE_NAME}` placeholders with config values
4. **Unique ID Generation:** Creates UUID-based unique identifiers for devices/sensors
5. **Discovery Publication:**
   - Topic: `CONFIG_TOPIC` (default: 'homeassistant/device/dev_flights/config')
   - QoS: 1
   - Retain: True
   - One-time publication (only if discovery file doesn't exist)

**Generated Discovery Payload Structure:**
- **Device Information:** Identifiers, name, manufacturer, version, configuration URL
- **Origin Information:** Application metadata and support URL
- **Components:** Two sensors (closest_aircraft, visible_aircraft)
- **Sensor Configuration:** Platform, units, icons, state/attribute topics, value templates

**Dependencies for mqtt_publisher Library:**
- Must support JSON payload auto-conversion
- QoS and retain flag configuration per message
- Non-blocking connection with background loop
- Connection status feedback
- Error handling with custom logging
- Change-based publishing (only publish when data differs)

---

## 2. HTTP API / Web Hosting Functionality Analysis

### 2.1 Current Implementation (`src/flights_server.py`)

**Framework**: FastAPI with Uvicorn server

**Server Configuration:**
- **Host:** `"0.0.0.0"` (listens on all interfaces)
- **Port:** Configurable (from `FASTAPI_PORT` config, default: 47475)
- **Auto-discovery:** Dynamically determines LAN IP via socket connection test

**Core Infrastructure:**

1. **Base URL Generation:**
   ```python
   def get_lan_ip():
       # Creates UDP socket, connects to 8.8.8.8:80
       # Returns local interface IP, fallback: '127.0.0.1'
   
   base_url = f"http://{get_lan_ip()}:{SERVER_PORT}"
   ```

2. **Port Management:**
   ```python
   def kill_process_on_port(port):
       # Uses netstat to find process on port
       # Kills process with PID (permission-limited)
   ```

### 2.2 API Endpoints Analysis

**1. Root Endpoint (`GET /`)**
- **Purpose:** Main landing page and API index
- **Content Negotiation:** 
  - `Accept: text/html` → HTML page with navigation
  - Default/JSON → JSON response with available endpoints
- **Data Sources:** Scans `output/` directory for JSON files
- **Response Structure:**
  ```json
  {
    "Output JSON Files": {
      "file_name": "http://ip:port/file_name.json"
    },
    "Image Files": {
      "Airline Logos": "http://ip:port/logos/",
      "Country Flags": "http://ip:port/flags/"
    }
  }
  ```

**2. JSON File Endpoints (`GET /{file_name}`)**
- **Purpose:** Serve output JSON files with pretty formatting
- **Path Handling:** 
  - Auto-appends `.json` if missing
  - Security validation (no `..` or absolute paths)
  - Path traversal protection
- **Response:** Pretty-formatted JSON with 2-space indentation
- **Error Handling:** 404 for missing files, 500 for JSON parse errors

**3. Logo Endpoints (`GET /logos` and `GET /logos/{file_name}`)**
- **Directory Structure:** `assets/images/logos/{svg|png}/`
- **File Resolution:**
  - Supports both SVG and PNG formats
  - Configurable default format (`IMAGE_FORMAT` config)
  - Fallback format if primary not available
  - Special `_NONE` fallback for missing logos
- **Content Types:** `image/svg+xml` for SVG, `image/png` for PNG
- **Case Handling:** Converts filenames to UPPERCASE for logo lookup

**4. Flag Endpoints (`GET /flags` and `GET /flags/{file_name}`)**
- **Directory Structure:** `assets/images/flags/{svg|png}/`
- **File Resolution:** Similar to logos but converts filenames to lowercase
- **Primary Format:** PNG (unlike logos which use config default)

**5. Static Assets (`/assets/.web/*`)**
- **Purpose:** Serves static web assets (favicon, banner images)
- **Implementation:** FastAPI `StaticFiles` mount
- **Directory:** `assets/.web/`

**6. API Documentation (`GET /endpoints`)**
- **Purpose:** Self-documenting API with examples
- **Content Negotiation:** HTML page or JSON response
- **Dynamic Examples:** Includes actual server IP and port in examples

### 2.3 HTML Template System

**Banner Navigation:**
- Fixed header with logo and navigation menu
- Logo links to home page
- Navigation: Home, Flags, Logos, Endpoints
- Responsive styling with CSS

**Content Generation:**
```python
def create_html_list(title: str, items: dict) -> str:
    # Generates full HTML pages with:
    # - Custom CSS styling
    # - Fixed banner header with navigation
    # - Dynamic content sections
    # - Alphabetically sorted file listings
```

**Features:**
- Responsive design with fixed header
- CSS styling for professional appearance
- Dynamic content based on available files
- Consistent navigation across all pages

### 2.4 File Management System

**File Discovery:**
```python
def get_directory_listing(base_dir, ext=None, strip_ext=False):
    # Uses glob patterns to find files
    # Optional extension filtering
    # Optional extension stripping for display
```

**Intelligent File Resolution:**
```python
def try_file_with_ext(base_dir, filename, primary_ext, fallback_ext, none_fallback):
    # Multi-format file resolution
    # Primary format attempt
    # Fallback format attempt  
    # _NONE fallback for missing files
    # Returns path and proper MIME type
```

**URL Generation:**
```python
def get_url_for_file(path, filename, ext, port):
    # Generates absolute URLs with proper host/port
    # Handles missing extensions
    # Fallback to relative paths on error
```

### 2.5 Error Handling System

**Custom Exception Handlers:**
- HTTP exceptions with content negotiation (HTML vs JSON)
- Generic exception handler with logging
- Consistent error pages and JSON responses

**Security Validations:**
- Path traversal prevention
- Extension validation for images
- Directory boundary enforcement

### 2.6 Server Lifecycle Management

**Startup Process:**
```python
def start_server(request_port, log_level='ERROR', default_image_format='svg'):
    # 1. Kill existing processes on port
    # 2. Determine LAN IP
    # 3. Print endpoint information
    # 4. Start Uvicorn server
```

**Integration Points:**
- Called from main application after data processing setup
- Runs in background thread (non-blocking)
- Shared global state for port and image format configuration

---

## 3. Integration Requirements for Reusable Libraries

### 3.1 mqtt_publisher Library Requirements

**Essential Features:**
1. **Connection Management:**
   - Broker host/port configuration
   - Optional authentication (username/password)
   - Configurable client ID
   - Non-blocking connection with background loop
   - Connection status reporting

2. **Publishing Interface:**
   - Simple `publish(topic, data, qos=1, retain=True)` method
   - Automatic JSON serialization for dict/object payloads
   - Change-detection publishing (only publish if data differs from previous)
   - Error handling with topic-specific logging

3. **Topic Management:**
   - Support for multiple predefined topics
   - Dynamic topic publishing
   - Topic validation/organization

4. **Home Assistant Discovery:**
   - Template-based discovery payload generation
   - Variable substitution in templates
   - Unique ID generation for devices/sensors
   - One-time discovery publication with persistence checking

5. **Logging Integration:**
   - Configurable log levels
   - Detailed error reporting with context
   - Module-specific logging names

**Configuration Schema:**
```python
mqtt_config = {
    'broker_host': str,
    'broker_port': int,
    'client_id': str,
    'username': Optional[str],
    'password': Optional[str],
    'topics': Dict[str, str],  # {topic_name: topic_path}
    'log_level': str,
    'ha_discovery': {
        'enabled': bool,
        'config_topic': str,
        'template': str,  # JSON template with ${VARIABLE} placeholders
        'variables': Dict[str, Any]  # Variables for template substitution
    }
}
```

### 3.2 web_host Library Requirements

**Essential Features:**
1. **Server Configuration:**
   - Configurable host/port
   - Automatic LAN IP detection
   - Port conflict resolution
   - Non-blocking server startup

2. **Content Serving:**
   - JSON file serving with pretty formatting
   - Static file serving (images, assets)
   - Content negotiation (HTML vs JSON responses)
   - Proper MIME type handling

3. **Asset Management (Integrated):**
   - Multi-format file resolution (SVG/PNG fallbacks)
   - Configurable format preferences and fallbacks
   - Category-based organization (logos, flags, icons)
   - Automatic asset discovery and listing
   - MIME type detection and caching
   - Missing asset tracking with `_NONE` fallbacks
   - URL generation for assets

4. **Template Engine (Integrated):**
   - HTML page generation with variable substitution
   - Responsive design with navigation components
   - Dynamic content based on available files
   - Consistent styling and branding themes
   - Template inheritance and composition
   - Custom filters and functions

5. **File Management:**
   - Directory scanning and file discovery
   - Security validation (path traversal prevention)
   - Intelligent file resolution with fallbacks

6. **API Framework:**
   - RESTful endpoint structure
   - Error handling with proper HTTP status codes
   - Self-documenting endpoints
   - Content type negotiation

**Configuration Schema:**
```python
web_config = {
    'server': {
        'host': str,  # default: "0.0.0.0"
        'port': int,
        'log_level': str
    },
    'directories': {
        'output_directory': str,  # JSON files location
        'assets_directory': str,  # Static assets location
        'image_directories': Dict[str, str],  # {type: path} e.g., {'logos': 'assets/images/logos'}
    },
    'assets': {
        'default_image_format': str,  # 'svg' or 'png'
        'fallback_enabled': bool,
        'cache_duration': int,
        'missing_asset_fallback': str  # e.g., '_NONE'
    },
    'templates': {
        'title': str,
        'banner_image': str,
        'navigation_links': Dict[str, str],
        'theme': str,  # 'default', 'dark', 'aviation'
        'responsive': bool
    }
}
```

### 3.3 Integration Points

**Data Flow:**
1. Main application processes flight data
2. Publishes changes via mqtt_publisher library
3. Saves JSON files to output directory
4. web_host library automatically serves updated files
5. Both libraries share configuration and logging

**Shared Dependencies:**
- Configuration management (YAML-based)
- Logging infrastructure
- Error handling patterns
- File I/O operations

**Backward Compatibility:**
- Must maintain existing API endpoints
- Preserve MQTT topic structure
- Keep Home Assistant discovery functionality
- Maintain current data formats and file structures

This documentation provides the complete foundation for replacing the current MQTT and HTTP functionality with reusable libraries while preserving all existing capabilities and integration patterns.

---

## 4. Additional Functions Suitable for External Libraries

After analyzing the complete codebase, several other core functionalities would benefit from extraction into reusable libraries:

### 4.1 Configuration Management Library (`config_manager`)

**Current Implementation Issues:**
- YAML configuration scattered across multiple files
- Inconsistent configuration loading patterns
- Hardcoded paths and mixed relative/absolute path handling
- Repeated configuration parsing in different modules

**Proposed Library: `config_manager`**

**Key Features:**
1. **Centralized Configuration Loading:**
   - Single point of configuration access
   - Environment-based configuration overlays
   - Configuration validation and type checking
   - Default value management

2. **Path Management:**
   - Consistent base directory resolution
   - Relative to absolute path conversion
   - Cross-platform path handling
   - Directory creation management

3. **Configuration Schema:**
   ```python
   config_schema = {
       'paths': {
           'base_dir': str,
           'config_dir': str,
           'output_dir': str,
           'logs_dir': str,
           'storage_dir': str,
           'assets_dir': str
       },
       'services': {
           'mqtt': Dict,  # MQTT configuration
           'web': Dict,   # HTTP server configuration
       },
       'application': {
           'log_level': str,
           'check_interval': int,
           'time_periods': List[str]
       }
   }
   ```

**Current Usage Patterns:**
- `src/config_manager.py` - Basic YAML loading
- `src/flights.py` - Path management and config globals
- `src/mqtt_service.py` - Individual config loading
- `src/flights_server.py` - Duplicate config handling

### 4.2 Data Enrichment Library (`data_enricher`)

**Current Implementation (`src/enrich_flight_info.py`):**
- 358 lines of complex data enrichment logic
- Multiple lookup dictionaries (airlines, aircraft, airports)
- Geographic calculations and country flag generation
- Missing data tracking and logging

**Proposed Library: `data_enricher`**

**Key Features:**
1. **Multi-Source Data Enrichment:**
   - Pluggable data source adapters
   - Configurable enrichment pipelines
   - Caching and performance optimization
   - Missing data tracking and reporting

2. **Aviation-Specific Enrichers:**
   - Airline information lookup (ICAO/IATA codes)
   - Aircraft type and registration parsing
   - Airport and route information
   - Country codes to flag emoji conversion

3. **Geographic Processing:**
   - Distance calculations (Haversine formula)
   - Zone containment checking (Shapely integration)
   - Coordinate validation and conversion
   - Relative positioning calculations

4. **Configuration Schema:**
   ```python
   enricher_config = {
       'data_sources': {
           'airlines_file': str,
           'aircraft_file': str,
           'airports_source': str  # 'IATA', 'ICAO', or file path
       },
       'geographic': {
           'user_location': Tuple[float, float],
           'radius': float,
           'distance_unit': str,  # 'mi' or 'km'
           'defined_zones': List[Dict]
       },
       'output': {
           'missing_data_file': str,
           'cache_duration': int
       }
   }
   ```

**Current Complex Logic:**
- Registration country parsing with Flydenity
- Route parsing (origin-via-destination)
- Altitude trend calculation with symbols
- Airline identification via multiple lookup methods

### 4.3 Data Persistence Library (`data_store`)

**Current Implementation (`src/flight_counts.py`):**
- Pickle file management for time-series data
- JSON file writing and reading
- Statistics calculation and aggregation
- Time period management

**Proposed Library: `data_store`**

**Key Features:**
1. **Multi-Format Storage:**
   - JSON for human-readable data
   - Pickle for Python objects
   - CSV for time-series exports
   - Configurable compression

2. **Time-Series Data Management:**
   - Automatic timestamp tracking
   - Configurable retention policies
   - Period-based aggregation (daily, weekly, monthly)
   - Gap detection and handling

3. **Statistics and Analytics:**
   - Moving averages calculation
   - Trend analysis
   - Custom aggregation functions
   - Data export capabilities

4. **Configuration Schema:**
   ```python
   storage_config = {
       'formats': {
           'time_series': 'pickle',  # pickle, json, csv
           'output_data': 'json',
           'compression': bool
       },
       'retention': {
           'max_age_days': int,
           'cleanup_interval': int
       },
       'statistics': {
           'time_periods': List[str],
           'aggregation_functions': List[str]
       }
   }
   ```

### 4.4 Geographic Processing Library (`geo_processor`)

**Current Scattered Implementation:**
- Distance calculations in multiple files
- Zone definitions and containment checking
- Coordinate parsing and validation
- Geographic filtering functions

**Proposed Library: `geo_processor`**

**Key Features:**
1. **Distance Calculations:**
   - Multiple distance algorithms (Haversine, Great Circle)
   - Unit conversion (miles, kilometers, nautical miles)
   - Batch distance calculations
   - Performance optimization for large datasets

2. **Zone Management:**
   - Polygon zone definitions
   - Circular radius zones
   - Complex zone combinations (union, intersection)
   - Zone membership testing

3. **Coordinate Processing:**
   - Format validation and parsing
   - Coordinate system conversions
   - Bounds checking and validation
   - Closest point algorithms

4. **Configuration Schema:**
   ```python
   geo_config = {
       'zones': {
           'watch_zones': List[Dict],  # Polygon definitions
           'radius_zones': List[Dict],  # Circular zones
           'default_distance_unit': str
       },
       'algorithms': {
           'distance_method': str,  # 'haversine', 'great_circle'
           'precision': int
       }
   }
   ```

### 4.4 Geographic Processing Library (`geo_processor`)

**Current Scattered Implementation:**
- Distance calculations in multiple files
- Zone definitions and containment checking
- Coordinate parsing and validation
- Geographic filtering functions

**Proposed Library: `geo_processor`**

**Key Features:**
1. **Distance Calculations:**
   - Multiple distance algorithms (Haversine, Great Circle)
   - Unit conversion (miles, kilometers, nautical miles)
   - Batch distance calculations
   - Performance optimization for large datasets

2. **Zone Management:**
   - Polygon zone definitions
   - Circular radius zones
   - Complex zone combinations (union, intersection)
   - Zone membership testing

3. **Coordinate Processing:**
   - Format validation and parsing
   - Coordinate system conversions
   - Bounds checking and validation
   - Closest point algorithms

4. **Configuration Schema:**
   ```python
   geo_config = {
       'zones': {
           'watch_zones': List[Dict],  # Polygon definitions
           'radius_zones': List[Dict],  # Circular zones
           'default_distance_unit': str
       },
       'algorithms': {
           'distance_method': str,  # 'haversine', 'great_circle'
           'precision': int
       }
   }
   ```

### 4.5 Benefits of Library Extraction

**Code Reusability:**
- Share common functionality across multiple aviation projects
- Standardize data processing patterns
- Reduce code duplication

**Maintainability:**
- Separate concerns and responsibilities
- Easier testing and debugging
- Independent versioning and updates

**Performance:**
- Optimized implementations with caching
- Lazy loading and efficient algorithms
- Memory management improvements

**Extensibility:**
- Plugin architectures for custom enrichers
- Configurable processing pipelines
- Easy integration with new data sources

**Testing:**
- Isolated unit testing
- Mock-friendly interfaces
- Comprehensive test coverage

**Library Architecture Summary:**

This analysis identifies **four major libraries** for extraction:

1. **`mqtt_publisher`** - MQTT communication and Home Assistant discovery
2. **`web_host`** - HTTP server with integrated asset management and templating
3. **`config_manager`** - Centralized configuration and path management
4. **`data_enricher`** - Aviation data enrichment and processing
5. **`data_store`** - Multi-format persistence and time-series analytics
6. **`geo_processor`** - Geographic calculations and zone management

The **`web_host`** library incorporates asset management and templating as core features since they are tightly coupled with web serving functionality. This creates a more cohesive and maintainable architecture while avoiding over-fragmentation of related functionality.

# Flights CLI Usage

The Flights project now includes a modern command-line interface based on the twickenham_events model.

## Installation

Install in development mode:
```bash
pip install -e .
```

## CLI Commands

### Basic Usage
```bash
flights --help        # Show all commands and options
flights --version     # Show version information
flights status        # Show system status and configuration
```

### Server Management
```bash
flights server                    # Start HTTP/API server (default port 8000)
flights server --port 8080       # Start server on custom port
flights --dry-run server         # Test server configuration without starting
```

### Flight Monitoring
```bash
flights monitor                   # Run main flight processing loop
flights monitor --once           # Run one cycle then exit
flights monitor --interval 30    # Override check interval (seconds)
flights --dry-run monitor        # Test monitor configuration
```

### System Validation
```bash
flights validate config           # Validate configuration file
flights validate mqtt            # Test MQTT connectivity
flights validate http            # Test HTTP server
flights validate http --port 8080 # Test specific port
```

### Global Options
```bash
--config CONFIG      # Use custom config file (default: config/config.yaml)
--debug              # Enable debug logging
--dry-run            # Test mode without side effects
```

## Examples

### Basic system check:
```bash
flights status
```

### Start development server:
```bash
flights server --port 8080
```

### Validate system before running:
```bash
flights validate config
flights validate mqtt
flights validate http
```

### Run flight monitoring:
```bash
flights monitor
```

### Test configuration changes:
```bash
flights --dry-run monitor --once
```

## Development Testing

You can also run the CLI using Python module syntax during development:
```bash
PYTHONPATH=src python -m flights.__main__ status
```

The package includes a repository shim (`__init__.py` at root) that allows importing the package from source without installation for development and testing purposes.
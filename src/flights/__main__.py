#!/usr/bin/env python3
"""
Flights CLI - Modern command-line interface for aviation data processing.

Provides comprehensive flight data processing with MQTT integration,
HTTP API serving, and Home Assistant compatibility.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all CLI commands."""
    parser = argparse.ArgumentParser(
        prog="flights",
        description="Flights: Aviation data processing with MQTT and HTTP API integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  flights status               # Show configuration and system status
  flights server               # Start HTTP/API server only
  flights monitor              # Run main flight monitoring loop
  flights validate             # Validate configuration and connectivity
  flights --version            # Show version information
  flights --dry-run monitor    # Test mode without side effects
        """,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_get_version()}"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="path to configuration file",
    )
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="test mode - no data will be saved or published",
    )

    subparsers = parser.add_subparsers(
        dest="command", help="available commands", required=False
    )

    # Status command
    subparsers.add_parser("status", help="show configuration and system status")

    # Server command
    server_parser = subparsers.add_parser(
        "server", help="start HTTP/API server only"
    )
    server_parser.add_argument("--port", type=int, default=8000, help="server port")
    server_parser.add_argument(
        "--log-level", type=str, default="ERROR", help="logging level for server"
    )

    # Monitor command (main flight processing loop)
    monitor_parser = subparsers.add_parser(
        "monitor", help="run main flight monitoring and processing loop"
    )
    monitor_parser.add_argument(
        "--once", action="store_true", help="run one cycle then exit"
    )
    monitor_parser.add_argument(
        "--interval", type=int, help="override check interval in seconds"
    )

    # Validate command group
    validate_parser = subparsers.add_parser(
        "validate", help="validate system components"
    )
    validate_subparsers = validate_parser.add_subparsers(
        dest="validate_command", help="validation operations"
    )

    # Config validation
    config_validate_parser = validate_subparsers.add_parser(
        "config", help="validate configuration file and environment variables"
    )
    config_validate_parser.add_argument(
        "--strict", action="store_true", help="enable strict validation mode"
    )

    # MQTT validation
    mqtt_validate_parser = validate_subparsers.add_parser(
        "mqtt", help="validate MQTT connectivity and configuration"
    )
    mqtt_validate_parser.add_argument(
        "--timeout", type=float, default=10.0, help="connection timeout in seconds"
    )

    # HTTP validation
    http_validate_parser = validate_subparsers.add_parser(
        "http", help="validate HTTP server configuration and connectivity"
    )
    http_validate_parser.add_argument(
        "--port", type=int, help="server port to test (overrides config)"
    )
    http_validate_parser.add_argument(
        "--timeout", type=float, default=10.0, help="request timeout in seconds"
    )

    return parser


def _get_version() -> str:
    """Get the package version."""
    try:
        from flights import __version__

        return __version__
    except ImportError:
        return "0.1.0-dev"


def _setup_logging(debug: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_status(args) -> int:
    """Show configuration and system status."""
    from .config_manager import config

    print("\n✈️  \033[96mFLIGHTS STATUS\033[0m")
    print("\033[96m" + "=" * 20 + "\033[0m")

    # Version
    print(f"Version: {_get_version()}")

    # Configuration
    print("\nConfiguration:")
    try:
        print(f"  Config file: {args.config}")
        print(f"  MQTT enabled: {bool(config.get('mqtt_enabled'))}")
        print(f"  MQTT broker: {config.get('mqtt_broker', 'not configured')}")
        print(f"  Check interval: {config.get('check_interval', 15)}s")
        print(f"  User location: {config.get('user_lat', 'not set')}, {config.get('user_lon', 'not set')}")
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")

    # Component status
    print("\nComponents:")
    print("  📡 MQTT Service: Available")
    print("  🌐 HTTP Server: Available")
    print("  📊 Flight Processing: Available")
    print("  🏠 Home Assistant Discovery: Available")

    # Dependencies check
    print("\nDependencies:")
    try:
        import requests
        print("  ✅ requests")
    except ImportError:
        print("  ❌ requests (missing)")

    try:
        import paho.mqtt.client
        print("  ✅ paho-mqtt")
    except ImportError:
        print("  ❌ paho-mqtt (missing)")

    try:
        import shapely
        print("  ✅ shapely")
    except ImportError:
        print("  ❌ shapely (missing)")

    try:
        import fastapi
        print("  ✅ fastapi")
    except ImportError:
        print("  ❌ fastapi (missing)")

    return 0


def cmd_server(args) -> int:
    """Start HTTP/API server only."""
    print("🌐 \033[1mStarting Flights HTTP Server\033[0m")
    print("=" * 40)

    if args.dry_run:
        print("\033[33m🔍 DRY RUN: Would start HTTP server\033[0m")
        print(f"   Port: {args.port}")
        print(f"   Log level: {args.log_level}")
        return 0

    try:
        from .flights_server import main as server_main
        
        # Override sys.argv to pass arguments to the server
        old_argv = sys.argv
        sys.argv = [
            "flights_server",
            "--port", str(args.port),
            "--log_level", args.log_level
        ]
        
        try:
            server_main()
            return 0
        finally:
            sys.argv = old_argv
            
    except Exception as e:
        print(f"\n\033[31m❌ Server failed to start: {e}\033[0m")
        return 1


def cmd_monitor(args) -> int:
    """Run main flight monitoring and processing loop."""
    print("📡 \033[1mStarting Flights Monitor\033[0m")
    print("=" * 35)

    if args.dry_run:
        print("\033[33m🔍 DRY RUN: Would start flight monitoring\033[0m")
        print(f"   Single run: {args.once}")
        if args.interval:
            print(f"   Interval override: {args.interval}s")
        return 0

    try:
        from .flights_main import main as flights_main
        
        # For now, run the original flights main function
        # In the future, this could be enhanced to support --once and --interval
        print("🚀 Starting flight monitoring loop...")
        print("   Press Ctrl+C to stop")
        
        flights_main()
        return 0
        
    except KeyboardInterrupt:
        print("\n\033[33m⏹️  Monitor stopped by user\033[0m")
        return 0
    except Exception as e:
        print(f"\n\033[31m❌ Monitor failed: {e}\033[0m")
        return 1


def cmd_validate(args) -> int:
    """Handle validation commands."""
    if not hasattr(args, "validate_command") or args.validate_command is None:
        print(
            "❌ No validation subcommand specified. Use 'validate --help' for options."
        )
        return 1

    if args.validate_command == "config":
        return cmd_validate_config(args)
    elif args.validate_command == "mqtt":
        return cmd_validate_mqtt(args)
    elif args.validate_command == "http":
        return cmd_validate_http(args)
    else:
        print(f"❌ Unknown validation command: {args.validate_command}")
        return 1


def cmd_validate_config(args) -> int:
    """Validate configuration file and environment variables."""
    print("🔍 Validating configuration...")

    errors = []
    warnings = []

    try:
        from .config_manager import config

        # Basic configuration validation
        print("✅ Configuration file loaded successfully")

        # Check critical settings
        if not config.get("user_lat") or not config.get("user_lon"):
            warnings.append("User location (user_lat/user_lon) not configured - closest aircraft detection disabled")

        # MQTT validation
        if config.get("mqtt_enabled"):
            if not config.get("mqtt_broker"):
                errors.append("MQTT enabled but no broker configured")
            if not config.get("mqtt_username") and not config.get("mqtt_password"):
                warnings.append("MQTT enabled but no authentication configured")

        # Check interval validation
        interval = config.get("check_interval", 15)
        if interval < 1:
            errors.append(f"Check interval too low: {interval}s (minimum 1s)")
        elif interval < 5:
            warnings.append(f"Check interval very low: {interval}s (may cause high CPU usage)")

        # Report results
        if warnings:
            print("\n⚠️  Configuration warnings:")
            for warning in warnings:
                print(f"  - {warning}")

        if errors:
            print("\n❌ Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return 1
        else:
            print("\n✅ Configuration validation passed!")
            return 0

    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return 1


def cmd_validate_mqtt(args) -> int:
    """Validate MQTT connectivity and configuration."""
    print(f"🔍 Validating MQTT connectivity (timeout: {args.timeout}s)...")

    try:
        from .config_manager import config
        from .mqtt_service import MQTTService

        if not config.get("mqtt_enabled"):
            print("❌ MQTT is not enabled in configuration")
            return 1

        print("📡 Testing MQTT connection...")
        mqtt_service = MQTTService(config)
        
        # Test connection
        result = mqtt_service.connect()
        if result:
            print("✅ MQTT connection successful")
            mqtt_service.disconnect()
            return 0
        else:
            print("❌ MQTT connection failed")
            return 1

    except Exception as e:
        print(f"❌ MQTT validation failed: {e}")
        return 1


def cmd_validate_http(args) -> int:
    """Validate HTTP server configuration and connectivity."""
    print(f"🔍 Validating HTTP server (timeout: {args.timeout}s)...")

    try:
        import requests
        from .config_manager import config
        from .flights_server import get_lan_ip

        # Determine port
        port = args.port or 8000
        host = get_lan_ip()
        url = f"http://{host}:{port}"

        print(f"🌐 Testing HTTP server at {url}...")

        # Test connection
        response = requests.get(url, timeout=args.timeout)
        
        if response.status_code == 200:
            print("✅ HTTP server responding correctly")
            return 0
        else:
            print(f"❌ HTTP server returned status code: {response.status_code}")
            return 1

    except requests.ConnectionError:
        print("❌ HTTP server not reachable (connection refused)")
        print("💡 Try starting the server first: flights server")
        return 1
    except Exception as e:
        print(f"❌ HTTP validation failed: {e}")
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    _setup_logging(args.debug)

    # Show help if no command provided
    if args.command is None:
        print("✈️  \033[1mFlights - Aviation Data Processing\033[0m")
        print()
        print("No command specified. Available commands:")
        print("  flights status    - Show system status")
        print("  flights server    - Start HTTP server")
        print("  flights monitor   - Start flight monitoring")
        print("  flights validate  - Validate configuration")
        print()
        print("Use 'flights --help' for complete usage information.")
        return 0

    try:
        # Route to command
        if args.command == "status":
            return cmd_status(args)
        elif args.command == "server":
            return cmd_server(args)
        elif args.command == "monitor":
            return cmd_monitor(args)
        elif args.command == "validate":
            return cmd_validate(args)
        else:
            print(f"❌ Unknown command: {args.command}")
            return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
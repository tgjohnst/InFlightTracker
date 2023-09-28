## Script that continuously scrapes flight data from the in-flight API and stores it in a database

import os
import json
import csv
import logging

import requests
from requests.adapters import HTTPAdapter, Retry
import schedule # approach 1
import sqlite3

from datetime import datetime
from argparse import ArgumentParser

# API Constants
API_URL = "https://wifi.inflightinternet.com/abp/v2/statusTray?fig2=true"
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.5"
}
VERSION = "0.1.0"

# ------------------- #

def parse_cmd(args: list):
    """ Parses user-supplied command line arguments """
    parser = ArgumentParser(description=__doc__)
    # Basic Configuration
    parser.add_argument('--flight-name', '-n', type=str, required=True, help='Name of your flight, which allows for resuming scraping')
    parser.add_argument('--data-dir', '-d', type=str, default="flight_data/", help='General directory to store flight data in (default: ./flight_data)')
    parser.add_argument('--store-raw', '-s', action='store_true', help='Store raw data from API in addition to processed data')
    parser.add_argument('--data-format', '-f', type=str, default="json", choices=["json", "csv"], help='Format to store raw flight data in. (default: json). JSON is recommended for now')

    # Scraping Configuration
    parser.add_argument('--scrape-interval', '-i', type=int, default=30, help='Interval (in seconds) between scraping attempts')
    parser.add_argument('--scrape-timeout', '-t', type=int, default=5, help='Timeout (in seconds) for scraping requests')
    parser.add_argument('--scrape-max-retries', '-r', type=int, default=3, help='Maximum number of retries for scraping requests before quitting')

    # Storage Configuration
    parser.add_argument('--rebuild-db', '-b', action='store_true', help='Rebuild the database from stored raw data (will delete existing data)')

    # Interaction
    parser.add_argument('--logfile-dir', '-l', default='.', type=str, help='Log file output path (Default is current directory)')
    parser.add_argument('--verbose','-v', action='store_true', help='Output log events to stout/stderr as well as the log file')
    parser.add_argument('--debug', action='store_true', help='Enable more detailed logging for debug purposes (will blow up log file size, use for testing only)')
    optS = parser.parse_args(args)
    return optS

def validate_args(args: list) -> None:
    """ Validate user-supplied command line arguments """
    if args.scrape_interval < 1:
        raise ValueError(f'Invalid scrape interval: {args.scrape_interval}')
    if args.scrape_timeout < 1:
        raise ValueError(f'Invalid scrape timeout: {args.scrape_timeout}')
    if args.scrape_max_retries < 1:
        raise ValueError(f'Invalid scrape max retries: {args.scrape_max_retries}')
    if args.data_format not in ['json', 'csv']:
        raise ValueError(f'Invalid data format: {args.data_format}')
    if args.data_dir == '':
        raise ValueError(f'Invalid data directory: {args.data_dir}')
    if args.logfile_dir == '':
        raise ValueError(f'Invalid logfile directory: {args.logfile_dir}')
    if args.flight_name == '':
        raise ValueError(f'Invalid flight name: {args.flight_name}')
    if args.rebuild_db and not os.listdir(determine_flight_dir(args.data_dir, args.flight_name)):
        raise ValueError(f'Cannot rebuild database without raw data present')

# ------------------- #
# Init and logging

def init_log(logfile_dir: str = '.', debug: bool = False, verbose: bool = False) -> None:
    """ Initialize logging
    Arguments:
        logfile_dir: Directory to write log file to
        debug: Enable debug logging
        verbose: Enable verbose logging (to stdout/stderr)
    """
    filedate = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level = log_level,
        format = '[%(asctime)s] %(message)s',
        datefmt = '%d/%m/%Y %H:%M:%S',
        filename = os.path.join(logfile_dir, filedate + "_scraping_log.txt")
    )
    if verbose:
        logging.getLogger().addHandler(logging.StreamHandler())


def log_args(args: list) -> None:
    """ Log args to logfile at level INFO
    Arguments:
        args: list of command line arguments
    """
    logging.info('Command line arguments:')
    logging.info('-----')
    for arg in vars(args):
        logging.info(f'{arg}: {getattr(args, arg)}')
    logging.info('-----')

def print_welcome_message() -> None:
    """ Print welcome message """
    print(f"Welcome to InFlightTracker version {VERSION}")
    print("This script will continuously scrape flight data from the in-flight API and store it in a database")
    # TODO print more info and ascii art


def determine_flight_dir(data_dir: str, flight_name: str) -> str:
    """ Returns the path to the flight directory
    Arguments:
        data_dir: Top-level directory to store flight data in
        flight_name: Name of your flight
    Returns:
        flight_dir: Path to the flight directory
    """
    flight_dir = os.path.join(data_dir, flight_name)
    log.info(f'Flight directory: {flight_dir}')
    return flight_dir

# Create the flight directory if it doesn't exist
def create_flight_dir(data_dir: str, flight_name: str, store_raw: bool) -> str:
    """ Create the flight data directory if it doesn't exist
    Arguments:
        data_dir: Top-level directory to store flight data in
        flight_name: Name of your flight
    Returns:
        flight_dir: Path to the flight directory
    """
    flight_dir = determine_flight_dir(data_dir, flight_name)
    if not os.path.isdir(flight_dir):
        log.debug(f'Flight directory does not exist, creating new directory at {flight_dir}')
        os.mkdir(flight_dir)
    if store_raw:
        log.debug(f'Raw data storage enabled, creating raw/ directory at {flight_dir}')
        os.mkdir(os.path.join(flight_dir, 'raw'), exist_ok=True)
    return flight_dir

# ------------------- #
# Fetching

def fetch_data(url: str, headers: dict, timeout: int, max_retries: int) -> dict:
    """ Fetch data from the API
    Arguments:
        url: API URL
        headers: API headers
        timeout: API request timeout
        max_retries: Maximum number of retries for API requests
    Returns:
        data: Data from the API
    """
    # configure Retry object
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"]
    )
    # configure HTTPAdapter
    adapter = HTTPAdapter(max_retries=retry_strategy)
    # configure requests session
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # make request
    log.debug(f'Making request to {url}')
    response = session.get(url, headers=headers, timeout=timeout)
    # check response
    if response.status_code != 200:
        raise ValueError(f'Invalid response code: {response.status_code}')
    #TODO implement ignoring failures (would skip writing out data)
    # parse response
    data = response.json()
    session.close()
    return data
    
def fetch_and_store_data(flight_dir: str, store_raw: bool, data_format: str, db: sqlite3.Connection, timeout: int, max_retries: int) -> None:
    """ Fetch data from the API and store it
    Arguments:
        flight_dir: Path to the flight directory
        store_raw: Store raw data from API in addition to processed data
        data_format: Format to store raw flight data in
        timeout: API request timeout
        max_retries: Maximum number of retries for API requests
    """
    # Fetch data
    data = fetch_data(API_URL, API_HEADERS, timeout, max_retries)
    # Store raw data
    if store_raw:
        write_raw_data(flight_dir, data, data_format)
    # Store processed data in db
    write_to_db(db, data)

# ------------------- #
# Data handling

# Write raw data to the raw/ directory for our flight
def write_raw_data(flight_dir: str, data: dict, data_format: str) -> None:
    """ Write raw data to the raw/ directory for our flight
    Arguments:
        flight_dir: Path to the flight directory
        data: Data to write
        data_format: Format to write data in
    """
    if data_format == 'json':
        logging.debug(f'Writing raw data to {flight_dir}/raw/{datetime.now().strftime("%Y%m%d-%H%M%S")}.json')
        with open(os.path.join(flight_dir, 'raw', f'{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'), 'w') as f:
            json.dump(data, f)
    elif data_format == 'csv':
        logging.warn("CSV parsing is not yet implemented. raw data will not be written")
        print("CSV parsing is not yet implemented. raw data will not be written!")
    else:
        raise ValueError(f'Invalid data format: {data_format}')

# ------------------- #
# DB Functions

def create_db(flight_dir: str, flight_name: str) -> sqlite3.Connection:
    """ Initialize database for storing flight data
    Arguments:
        data_dir: Top-level directory to store flight data in
        flight_name: Name of your flight
    Returns:
        db: sqlite3 connection object
    """
    # Check if db already exists
    if os.path.isfile(f'{data_dir}/flight-data_{flight_name}.db'):
        log.info(f'Flight data database already exists, path: {data_dir}/flight-data_{flight_name}.db')
        log.info('Attempting to resume scraping')
    else:
        log.info(f'Flight data database does not exist, creating new database at {data_dir}/flight-data_{flight_name}.db')
    db = sqlite3.connect(f'{data_dir}/flight-data_{flight_name}.db')
    return db

def initialize_db(db: sqlite3.Connection, rebuild: bool) -> None:
    """ Initialize the database
    Arguments:
        db: sqlite3 connection object
    """
    logging.debug("Database not yet implemented")
    # TODO create db schema

def write_to_db(db: sqlite3.Connection, data: dict) -> None:
    """ Write data to the database
    Arguments:
        db: sqlite3 connection object
        data: Data to write
    """
    logging.debug("Database not yet implemented")
    # TODO insert data into db

# ------------------- #
# Main loop

def main() -> None:
    """ MAIN """
    # Parse command line arguments and init logging
    args = parse_cmd(sys.argv[1:])
    validate_args()
    init_log(args.logfile_dir, debug=args.debug, verbose=args.verbose)
    log_args(args)

    # Initialize storage
    log.info(f'Initializing storage and database connection...')
    flight_dir = create_flight_dir(args.data_dir, args.flight_name)
    db = init_db(args.data_dir, args.flight_name)

    # Main fetch loop
    log.info(f'Starting main fetch loop...')
    print(f"Requesting new data every {args.scrape_interval} seconds...")
    print(f"Press Ctrl+C to exit")

    # Approach 1: schedule
    schedule.every(args.scrape_interval).seconds.do(
        fetch_and_store_data,
        flight_dir=flight_dir,
        store_raw=args.store_raw,
        data_format=args.data_format,
        db=db,
        timeout=args.scrape_timeout,
        max_retries=args.scrape_max_retries)
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    # Clean up if we get a keyboard interrupt
    except KeyboardInterrupt:
        log.info('Keyboard interrupt detected, exiting...')
        db.close()
        sys.exit(0)


if __name__ == "__main__":
    main()


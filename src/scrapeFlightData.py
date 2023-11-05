## Script that continuously scrapes flight data from the in-flight API and stores it in a database

import os
import sys
import json
import csv
import logging
import time

import requests
from requests.adapters import HTTPAdapter, Retry
import schedule # approach 1
import sqlite3

from datetime import datetime
from argparse import ArgumentParser

# API Constants
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
    parser.add_argument('--api-url', '-a', type=str, default="https://wifi.inflightinternet.com/abp/v2/statusTray?fig2=true", help='URL of the in-flight API (default: https://wifi.inflightinternet.com/abp/v2/statusTray?fig2=true)')
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
    parser.add_argument('--logfile-dir', '-l', default='logs/', type=str, help='Log file output path (Default is current directory)')
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
    os.makedirs(logfile_dir, exist_ok=True)
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

# ------------------- #
# File handling

def determine_flight_dir(data_dir: str, flight_name: str) -> str:
    """ Returns the path to the flight directory
    Arguments:
        data_dir: Top-level directory to store flight data in
        flight_name: Name of your flight
    Returns:
        flight_dir: Path to the flight directory
    """
    flight_dir = os.path.join(data_dir, flight_name)
    logging.info(f'Flight directory: {flight_dir}')
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
        logging.debug(f'Flight directory does not exist, creating new directory at {flight_dir}')
        os.makedirs(flight_dir, exist_ok=True)
    if store_raw:
        logging.debug(f'Raw data storage enabled, creating raw/ directory at {flight_dir}')
        os.makedirs(os.path.join(flight_dir, 'raw'), exist_ok=True)
    return flight_dir

# ------------------- #
# Fetching

def check_url(url: str) -> None:
    """ Check if the API URL is valid
    Arguments:
        url: URL to check
    """
    logging.debug(f'Checking URL: {url}')
    try:
        response = requests.head(url)
    except:
        raise ValueError(f'Invalid API URL: {url}')
    if response.status_code != 200:
        raise ValueError(f'Invalid API URL: {url}')
# TODO do we want this to actually raise an error if the URL doesn't return? Or just warn and continue gracefully

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
        #method_whitelist=["HEAD", "GET", "OPTIONS"]
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    # configure HTTPAdapter
    adapter = HTTPAdapter(max_retries=retry_strategy)
    # configure requests session
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # make request
    logging.debug(f'Making request to {url}')
    try:
        response = session.get(url, headers=headers, timeout=timeout)
    except:
        logging.error('Error fetching data from API. Trying again in 30 seconds.')
        return None
    # check response
    if response.status_code != 200:
        logging.error(f'Invalid response code: {response.status_code}')
        return None
    # parse response
    data = response.json()
    session.close()
    return data
    
def fetch_and_store_data(flight_dir: str, api_url: str, store_raw: bool, data_format: str, db: sqlite3.Connection, timeout: int, max_retries: int) -> None:
    """ Fetch data from the API and store it
    Arguments:
        flight_dir: Path to the flight directory
        store_raw: Store raw data from API in addition to processed data
        data_format: Format to store raw flight data in
        timeout: API request timeout
        max_retries: Maximum number of retries for API requests
    """
    # Fetch data
    logging.debug('Fetching data from API...')
    data = fetch_data(api_url, API_HEADERS, timeout, max_retries)
    if data: # handle case where API connection fails
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

def create_db(data_dir: str, flight_name: str, rebuild_db: bool = False) -> sqlite3.Connection:
    """ Create database for storing flight data
    Arguments:
        data_dir: Top-level directory to store flight data in
        flight_name: Name of your flight
    Returns:
        db: sqlite3 connection object
    """
    # Check if db already exists
    create = False
    if os.path.isfile(f'{data_dir}/flight-data_{flight_name}.db'):
        logging.info(f'Flight data database already exists, path: {data_dir}/flight-data_{flight_name}.db')
        logging.info('Attempting to resume scraping')
    else:
        logging.info(f'Flight data database does not exist, creating new database at {data_dir}/flight-data_{flight_name}.db')
        create = True
    db = sqlite3.connect(f'{data_dir}/flight-data_{flight_name}.db')
    if create:
        initialize_db(db, rebuild=rebuild_db)
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
    validate_args(args)
    init_log(args.logfile_dir, debug=args.debug, verbose=args.verbose)
    log_args(args)

    # Store and check API URL
    api_url = args.api_url
    logging.info(f'API URL: {api_url}')
    check_url(api_url)

    # Initialize storage
    logging.info(f'Initializing storage and database connection...')
    flight_dir = create_flight_dir(args.data_dir, args.flight_name, args.store_raw)
    db = create_db(flight_dir, args.flight_name, rebuild_db=args.rebuild_db)

    # Main fetch loop
    logging.info(f'Starting main fetch loop...')
    print(f"Requesting new data every {args.scrape_interval} seconds...")
    print(f"Press Ctrl+C to exit")

    # Approach 1: schedule
    schedule.every(args.scrape_interval).seconds.do(
        fetch_and_store_data,
        flight_dir=flight_dir,
        api_url=api_url,
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
        logging.info('Keyboard interrupt detected, exiting...')
        db.close()
        sys.exit(0)


if __name__ == "__main__":
    main()


## Script that continuously scrapes flight data from the in-flight API and stores it in a database

import os
import requests
import json
import csv
import sqlite3
import logging
from datetime import datetime
from argparse import ArgumentParser

# API Constants
API_URL = "https://wifi.inflightinternet.com/abp/v2/statusTray?fig2=true"
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.5"
}

# ------------------- #

def parse_cmd(args: list):
    """ Parses user-supplied command line arguments """
    parser = ArgumentParser(description=__doc__)
    # Basic Configuration
    parser.add_argument('--flight-name', '-n', type=str, required=True, help='Name of your flight, which allows for resuming scraping')
    parser.add_argument('--data-dir', '-d', type=str, default="flight_data/", help='General directory to store flight data in (default: ./flight_data)')
    parser.add_argument('--store-raw', '-s', action='store_true', help='Store raw data from API in addition to processed data')
    parser.add_argument('--data-format', '-f', type=str, default="json", choices=["json", "csv"], help='Format to store raw flight data in')

    # Scraping Configuration
    parser.add_argument('--scrape-interval', '-i', type=int, default=30, help='Interval (in seconds) between scraping attempts')
    parser.add_argument('--scrape-timeout', '-t', type=int, default=5, help='Timeout (in seconds) for scraping requests')
    parser.add_argument('--scrape-max-retries', '-r', type=int, default=3, help='Maximum number of retries for scraping requests')

    # Interaction
    parser.add_argument('--logfile-dir', '-l', default='.', type=str, help='Log file output path (Default is current directory)')
    parser.add_argument('--verbose','-v', action='store_true', help='Output log events to stout/stderr as well as the log file')
    parser.add_argument('--debug', action='store_true', help='Enable more detailed logging for debug purposes (will blow up log file size, use for testing only)')
    optS = parser.parse_args(args)
    return optS

# ------------------- #

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

def init_db(flight_dir: str, flight_name: str) -> sqlite3.Connection:
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

# Create the flight directory if it doesn't exist
def create_flight_dir(data_dir: str, flight_name: str, store_raw: bool) -> str:
    """ Create the flight data directory if it doesn't exist
    Arguments:
        data_dir: Top-level directory to store flight data in
        flight_name: Name of your flight
    Returns:
        flight_dir: Path to the flight directory
    """
    flight_dir = os.path.join(data_dir, flight_name)
    log.info(f'Flight directory: {flight_dir}')
    if not os.path.isdir(flight_dir):
        log.debug(f'Flight directory does not exist, creating new directory at {flight_dir}')
        os.mkdir(flight_dir)
    if store_raw:
        log.debug(f'Raw data storage enabled, creating raw/ directory at {flight_dir}')
        os.mkdir(os.path.join(flight_dir, 'raw'), exist_ok=True)
    return flight_dir


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
        logging.debug(f'Writing raw data to {flight_dir}/raw/{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv')
        with open(os.path.join(flight_dir, 'raw', f'{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv'), 'w') as f:
            writer = csv.writer(f)
            writer.writerow(data.keys())
            writer.writerow(data.values())
    else:
        raise ValueError(f'Invalid data format: {data_format}')

# ------------------- #

def main() -> None:
    """ MAIN """
    # Parse command line arguments and init logging
    args = parse_cmd(sys.argv[1:])
    init_log(args.logfile_dir, debug=args.debug, verbose=args.verbose)
    log_args(args)

    # Initialize storage
    log.info(f'Initializing storage and database connection...')
    flight_dir = create_flight_dir(args.data_dir, args.flight_name)
    db = init_db(args.data_dir, args.flight_name)

    


if __name__ == "__main__":
    main()


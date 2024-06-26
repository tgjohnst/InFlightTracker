# InFlightTracker
Track your flight while connected to inflight wifi!

This project attempts to query standard GoGo inflight wifi endpoints and display the data prettily without having to use the GoGo app/dashboard. This is useful for those who want to track their flight without having to go through ad-ridden webpages and/or download the GoGo app.

This can also support the delta inflight wifi API. 

## Installation

```
```

### Requirements
See `requirements.txt`
```
pip install -r requirements.txt
```

## Usage
```
usage: scrapeFlightData.py [-h] --flight-name FLIGHT_NAME [--data-dir DATA_DIR] [--store-raw]
                           [--data-format {json,csv}] [--scrape-interval SCRAPE_INTERVAL]
                           [--scrape-timeout SCRAPE_TIMEOUT] [--scrape-max-retries SCRAPE_MAX_RETRIES] [--rebuild-db]
                           [--logfile-dir LOGFILE_DIR] [--verbose] [--debug]
```
Example:
```
scrapeFlightData.py --flight-name DL123_SEA_BOS
```

### Common URLs
| Provider | URL |
| -------- | --- |
| GoGo     | https://wifi.inflightinternet.com/abp/v2/statusTray?fig2=true |
| Delta    | https://wifi.delta.com/api/flight-data     |
| United   | https://www.unitedwifi.com/portal/r/getAllSessionData    |
| American | https://www.aainflight.com/api/v1/connectivity/viasat/flight |

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License
```
```

## Project Status
Currently in development, nothing is working/tested yet. This is a side project for fun.

## TODO
- [ ] Create a simple python script that can query the GoGo endpoints and store the data in a consistent way
- [ ] Add support for delta wifi
- [ ] Create a simple python script that can parse the data and display it in a pretty way on the CLI
- [ ] Figure out how longitudinal flight data should be stored (json? sqlite?)
- [ ] Package the python scripts into a pip package
- [ ] Create a web-based frontend/dashboard to display the data
  - [ ] Plot of speed over time
  - [ ] Plot of altitude over time
  - [ ] Map of flight path?
  - [ ] Summary of ETA changes and delays
  - [ ] Basic flight info (airline, flight number, departure/arrival airports, etc.)

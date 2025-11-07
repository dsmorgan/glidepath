"""
Service for querying ticker information from various financial data sources.
"""
import json
from typing import Dict, Any, List, Optional


def query_yfinance(ticker: str) -> Dict[str, Any]:
    """Query ticker information using yfinance library."""
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info

        # Extract basic information
        data = {
            'name': info.get('longName') or info.get('shortName'),
            'current_price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'previous_close': info.get('previousClose'),
            'open': info.get('open') or info.get('regularMarketOpen'),
            'day_high': info.get('dayHigh') or info.get('regularMarketDayHigh'),
            'day_low': info.get('dayLow') or info.get('regularMarketDayLow'),
            'volume': info.get('volume') or info.get('regularMarketVolume'),
            'market_cap': info.get('marketCap'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'currency': info.get('currency'),
            'exchange': info.get('exchange'),
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        return {'success': True, 'data': data, 'warnings': []}
    except ImportError:
        return {'success': False, 'error': 'yfinance library is not installed. Please install it to use this source.'}
    except Exception as e:
        return {'success': False, 'error': f'Error querying yfinance: {str(e)}'}


def query_pandas_datareader(ticker: str) -> Dict[str, Any]:
    """Query ticker information using pandas_datareader library."""
    try:
        import pandas_datareader.data as web
        from datetime import datetime, timedelta

        # Get recent data (last 5 days) to get current price
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)

        df = web.DataReader(ticker, 'yahoo', start_date, end_date)

        if df.empty:
            return {'success': False, 'error': 'No data found for this ticker'}

        # Get most recent data
        latest = df.iloc[-1]
        previous = df.iloc[-2] if len(df) > 1 else None

        data = {
            'current_price': float(latest['Close']) if 'Close' in latest else None,
            'open': float(latest['Open']) if 'Open' in latest else None,
            'high': float(latest['High']) if 'High' in latest else None,
            'low': float(latest['Low']) if 'Low' in latest else None,
            'volume': int(latest['Volume']) if 'Volume' in latest else None,
            'previous_close': float(previous['Close']) if previous is not None and 'Close' in previous else None,
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        warnings = ['pandas_datareader provides limited metadata. Use other sources for company information.']

        return {'success': True, 'data': data, 'warnings': warnings}
    except ImportError:
        return {'success': False, 'error': 'pandas_datareader library is not installed. Please install it to use this source.'}
    except Exception as e:
        return {'success': False, 'error': f'Error querying pandas_datareader: {str(e)}'}


def query_alpha_vantage(ticker: str, api_key: str) -> Dict[str, Any]:
    """Query ticker information using Alpha Vantage API."""
    if not api_key:
        return {'success': False, 'error': 'Alpha Vantage API key not configured. Please add it in Settings.'}

    try:
        import requests

        # Get quote endpoint
        url = f'https://www.alphavantage.co/query'
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': ticker,
            'apikey': api_key
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        result = response.json()

        if 'Error Message' in result:
            return {'success': False, 'error': 'Invalid ticker symbol or API error'}

        if 'Note' in result:
            return {'success': False, 'error': 'API rate limit reached. Please try again later.'}

        quote = result.get('Global Quote', {})

        if not quote:
            return {'success': False, 'error': 'No data returned from Alpha Vantage'}

        data = {
            'name': ticker,  # Alpha Vantage doesn't return company name in GLOBAL_QUOTE
            'current_price': quote.get('05. price'),
            'volume': quote.get('06. volume'),
            'latest_trading_day': quote.get('07. latest trading day'),
            'previous_close': quote.get('08. previous close'),
            'change': quote.get('09. change'),
            'change_percent': quote.get('10. change percent'),
            'open': quote.get('02. open'),
            'high': quote.get('03. high'),
            'low': quote.get('04. low'),
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        return {'success': True, 'data': data, 'warnings': []}
    except ImportError:
        return {'success': False, 'error': 'requests library is not installed.'}
    except Exception as e:
        return {'success': False, 'error': f'Error querying Alpha Vantage: {str(e)}'}


def query_finnhub(ticker: str, api_key: str) -> Dict[str, Any]:
    """Query ticker information using Finnhub API."""
    if not api_key:
        return {'success': False, 'error': 'Finnhub API key not configured. Please add it in Settings.'}

    try:
        import requests

        # Get quote
        quote_url = f'https://finnhub.io/api/v1/quote'
        profile_url = f'https://finnhub.io/api/v1/stock/profile2'

        headers = {'X-Finnhub-Token': api_key}

        # Get quote data
        quote_response = requests.get(quote_url, params={'symbol': ticker}, headers=headers, timeout=10)
        quote_response.raise_for_status()
        quote_data = quote_response.json()

        # Get profile data
        profile_response = requests.get(profile_url, params={'symbol': ticker}, headers=headers, timeout=10)
        profile_response.raise_for_status()
        profile_data = profile_response.json()

        if quote_data.get('c') == 0 and quote_data.get('h') == 0:
            return {'success': False, 'error': 'No data found for this ticker. It may not be supported by Finnhub.'}

        data = {
            'name': profile_data.get('name'),
            'current_price': quote_data.get('c'),
            'high': quote_data.get('h'),
            'low': quote_data.get('l'),
            'open': quote_data.get('o'),
            'previous_close': quote_data.get('pc'),
            'change': quote_data.get('d'),
            'change_percent': quote_data.get('dp'),
            'exchange': profile_data.get('exchange'),
            'currency': profile_data.get('currency'),
            'country': profile_data.get('country'),
            'industry': profile_data.get('finnhubIndustry'),
            'market_cap': profile_data.get('marketCapitalization'),
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        return {'success': True, 'data': data, 'warnings': []}
    except ImportError:
        return {'success': False, 'error': 'requests library is not installed.'}
    except Exception as e:
        return {'success': False, 'error': f'Error querying Finnhub: {str(e)}'}


def query_polygon(ticker: str, api_key: str) -> Dict[str, Any]:
    """Query ticker information using Polygon.io API."""
    if not api_key:
        return {'success': False, 'error': 'Polygon.io API key not configured. Please add it in Settings.'}

    try:
        import requests
        from datetime import datetime, timedelta

        # Get previous business day for snapshot
        date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # Get ticker details
        details_url = f'https://api.polygon.io/v3/reference/tickers/{ticker}'
        snapshot_url = f'https://api.polygon.io/v2/aggs/ticker/{ticker}/prev'

        params = {'apiKey': api_key}

        # Get ticker details
        details_response = requests.get(details_url, params=params, timeout=10)
        snapshot_response = requests.get(snapshot_url, params=params, timeout=10)

        details_data = details_response.json() if details_response.status_code == 200 else {}
        snapshot_data = snapshot_response.json() if snapshot_response.status_code == 200 else {}

        if details_response.status_code == 403 or snapshot_response.status_code == 403:
            return {'success': False, 'error': 'API key is invalid or you do not have access to this endpoint.'}

        results = snapshot_data.get('results', [])
        ticker_info = details_data.get('results', {})

        data = {
            'name': ticker_info.get('name'),
            'currency': ticker_info.get('currency_name'),
            'market': ticker_info.get('market'),
            'locale': ticker_info.get('locale'),
            'primary_exchange': ticker_info.get('primary_exchange'),
        }

        if results:
            result = results[0]
            data.update({
                'open': result.get('o'),
                'high': result.get('h'),
                'low': result.get('l'),
                'close': result.get('c'),
                'volume': result.get('v'),
                'timestamp': datetime.fromtimestamp(result.get('t', 0) / 1000).strftime('%Y-%m-%d') if result.get('t') else None,
            })

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        warnings = []
        if not results:
            warnings.append('Limited price data available. The free tier may have restrictions.')

        return {'success': True, 'data': data, 'warnings': warnings}
    except ImportError:
        return {'success': False, 'error': 'requests library is not installed.'}
    except Exception as e:
        return {'success': False, 'error': f'Error querying Polygon.io: {str(e)}'}


def query_eodhd(ticker: str, api_key: str) -> Dict[str, Any]:
    """Query ticker information using EODHD API."""
    if not api_key:
        return {'success': False, 'error': 'EODHD API key not configured. Please add it in Settings (use "DEMO" for testing).'}

    try:
        import requests

        # EODHD requires exchange suffix (e.g., AAPL.US)
        if '.' not in ticker:
            ticker = f'{ticker}.US'

        # Get real-time data
        url = f'https://eodhistoricaldata.com/api/real-time/{ticker}'
        params = {
            'api_token': api_key,
            'fmt': 'json'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        result = response.json()

        if 'code' in result and result['code'] in ticker:
            data = {
                'name': ticker.split('.')[0],
                'current_price': result.get('close'),
                'open': result.get('open'),
                'high': result.get('high'),
                'low': result.get('low'),
                'previous_close': result.get('previousClose'),
                'change': result.get('change'),
                'change_percent': result.get('change_p'),
                'volume': result.get('volume'),
                'timestamp': result.get('timestamp'),
            }

            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}

            warnings = []
            if api_key == 'DEMO':
                warnings.append('Using DEMO key. Only limited tickers are available (AAPL.US, TSLA.US, VTI.US, AMZN.US, BTC-USD, EUR-USD).')

            return {'success': True, 'data': data, 'warnings': warnings}
        else:
            return {'success': False, 'error': 'No data found for this ticker. Check the ticker format (e.g., AAPL.US).'}
    except ImportError:
        return {'success': False, 'error': 'requests library is not installed.'}
    except Exception as e:
        return {'success': False, 'error': f'Error querying EODHD: {str(e)}'}


def query_ticker(ticker: str, source: str, api_settings) -> Dict[str, Any]:
    """
    Query ticker information from the specified source.

    Args:
        ticker: The ticker symbol to query
        source: The data source to use
        api_settings: APISettings model instance

    Returns:
        Dictionary with query results
    """
    ticker = ticker.upper().strip()

    if source == 'yfinance':
        result = query_yfinance(ticker)
    elif source == 'pandas_datareader':
        result = query_pandas_datareader(ticker)
    elif source == 'alpha_vantage':
        result = query_alpha_vantage(ticker, api_settings.alpha_vantage_api_key)
    elif source == 'finnhub':
        result = query_finnhub(ticker, api_settings.finnhub_api_key)
    elif source == 'polygon':
        result = query_polygon(ticker, api_settings.polygon_api_key)
    elif source == 'eodhd':
        result = query_eodhd(ticker, api_settings.eodhd_api_key)
    else:
        return {'success': False, 'error': f'Unknown data source: {source}'}

    if result['success']:
        return {
            'ticker': ticker,
            'source': source,
            'data': result['data'],
            'warnings': result.get('warnings', [])
        }
    else:
        return {'error': result['error']}

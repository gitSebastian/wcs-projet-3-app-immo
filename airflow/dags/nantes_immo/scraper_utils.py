# scraper_utils.py
from datetime import datetime

# Common headers for all requests
DEFAULT_HEADERS = {'User-Agent': 'Mozilla/5.0'}

def get_today_date():
    """Get today's date in consistent format"""
    return datetime.now().strftime('%Y-%m-%d')

def clean_price_for_filter(price_text):
    """Extract numeric value from price string"""
    if not price_text:
        return None
    numeric = ''.join(filter(str.isdigit, str(price_text)))
    return int(numeric) if numeric else None

def safe_text(element):
    """Safely get text from element, return None if not found"""
    try:
        return element.text.strip() if element else None
    except:
        return None

def safe_attr(element, attr):
    """Safely get attribute from element"""
    try:
        return element[attr] if element and element.get(attr) else None
    except:
        return None

def create_listing(site_name, title, price, description, url, image_url):
    """Create standardized listing dict"""
    return {
        'site': site_name,
        'title': title,
        'price': price,
        'price_numeric': clean_price_for_filter(price),
        'description': description,
        'url': url,
        'image_url': image_url,
        'scraped_date': get_today_date()
    }
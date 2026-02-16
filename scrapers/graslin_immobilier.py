import requests
from bs4 import BeautifulSoup
from scraper_utils import DEFAULT_HEADERS, safe_text, safe_attr, create_listing, extract_square_meters


def scrape():
    """Scrape Graslin Immobilier listings"""
    url = "https://graslin-immobilier.com/acheter-de-lancien/"
    
    response = requests.get(url, headers=DEFAULT_HEADERS)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    listings = soup.select('article.item.bien:not(.location)')
    results = []
    
    for listing in listings:
        try:
            # Get the link
            link_tag = listing.find('a', class_='content')
            link = safe_attr(link_tag, 'href')
            
            # Get image from style
            image = None
            if link_tag and link_tag.get('style'):
                style = link_tag['style']
                start = style.find("url( '") + 6
                end = style.find("' )", start)
                if start > 5 and end > start:
                    image = style[start:end]
            
            # Get info
            info_div = listing.find('div', class_='info')
            category = safe_text(info_div.find('span')) if info_div else None
            title_tag = info_div.find('h3', class_='titre') if info_div else None
            title_text = safe_text(title_tag)
            
            # Build title and extract price + square meters
            title_parts = [title_text] if title_text else []
            price = None
            surface_text = None
            
            if info_div:
                for item in info_div.find_all('li'):
                    value_span = item.find('span', class_='value')
                    if value_span:
                        text = safe_text(value_span)
                        suffixe = value_span.find('i', class_='suffixe')
                        
                        if suffixe:
                            suffixe_text = safe_text(suffixe)
                            if '€' in suffixe_text:
                                # This is the price
                                price = text
                            elif 'm²' in suffixe_text or 'm2' in suffixe_text:
                                # This is the surface - keep full text for extraction
                                surface_text = text + suffixe_text
                                # Also add to title
                                title_parts.append(surface_text)
                            else:
                                # Other info for title
                                title_parts.append(text)
                        elif text:
                            # No suffixe, just add to title
                            title_parts.append(text)
            
            # Extract numeric square meters
            square_meters = extract_square_meters(surface_text)
            
            title = ' - '.join(title_parts) if title_parts else None
            
            results.append(create_listing(
                'Graslin Immobilier',
                title,
                price,
                category,
                link,
                image,
                square_meters  # Add square meters parameter
            ))
        except:
            continue
    
    print(f"Found {len(results)} listings from Graslin Immobilier")
    return results
import requests
from bs4 import BeautifulSoup
from scraper_utils import DEFAULT_HEADERS, safe_text, safe_attr, create_listing

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
            
            # Build title and extract price
            title_parts = [title_text] if title_text else []
            price = None
            
            if info_div:
                for item in info_div.find_all('li'):
                    value_span = item.find('span', class_='value')
                    if value_span:
                        text = safe_text(value_span)
                        suffixe = value_span.find('i', class_='suffixe')
                        if suffixe and '€' in suffixe.text:
                            price = text
                        elif text:
                            title_parts.append(text)
            
            title = ' - '.join(title_parts) if title_parts else None
            
            results.append(create_listing(
                'Graslin Immobilier',
                title,
                price,
                category,
                link,
                image
            ))
        except:
            continue
    
    print(f"Found {len(results)} listings from Graslin Immobilier")
    return results
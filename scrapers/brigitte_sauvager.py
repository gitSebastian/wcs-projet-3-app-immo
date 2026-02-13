import requests
from bs4 import BeautifulSoup
from scraper_utils import DEFAULT_HEADERS, safe_text, safe_attr, create_listing

def scrape():
    """Scrape Brigitte Sauvager listings"""
    url = "https://www.brigitte-sauvager.com/appartements-a-vendre-a-nantes"
    
    response = requests.get(url, headers=DEFAULT_HEADERS)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    listings = soup.find_all('div', class_='col-md-4')
    results = []
    
    for listing in listings:
        try:
            # Get basic elements
            link_tag = listing.find('a')
            link = safe_attr(link_tag, 'href')
            
            img_tag = listing.find('img')
            image = safe_attr(img_tag, 'src')
            
            # Get text content
            location = safe_text(listing.find('p', class_='localisation'))
            presentation = safe_text(listing.find('p', class_='presentation'))
            surface = safe_text(listing.find('p', class_='surface'))
            price = safe_text(listing.find('p', class_=False))
            
            # Build title from location and surface
            title = f"{location}, {surface}" if location and surface else location
            
            results.append(create_listing(
                'Brigitte Sauvager',
                title,
                price,
                presentation,
                link,
                image
            ))
        except:
            continue
    
    print(f"Found {len(results)} listings from Brigitte Sauvager")
    return results
import csv
from datetime import datetime
import time
import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv  # New import

# Import scrapers
from scrapers import brigitte_sauvager
from scrapers import graslin_immobilier

# Load environment variables from .env file
load_dotenv()

# Universal base path
from pathlib import Path
path_to_file = Path(__file__).parent

# data folder for CSV backups
DATA_FOLDER = path_to_file / 'data/scrapers'

# Get database URL from environment variable
DATABASE_URL = os.getenv('DATABASE_URL')

def setup_database():
    """Create database table if it doesn't exist"""
    # Make sure local folder exists for CSV backups
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    # Connect to PostgreSQL
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Create table with all our fields
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id SERIAL PRIMARY KEY,
            site TEXT,
            title TEXT,
            price TEXT,
            price_numeric INTEGER,
            description TEXT,
            url TEXT,
            image_url TEXT,
            scraped_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index on image_url for faster duplicate checking
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_image_url ON properties(image_url)
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

def get_existing_image_urls():
    """Get all image URLs already in database to avoid duplicates"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Get all existing image URLs
    cursor.execute('SELECT image_url FROM properties')
    existing = {row[0] for row in cursor.fetchall()}
    
    cursor.close()
    conn.close()
    return existing

def filter_duplicates(all_listings):
    """Remove listings we already have based on image URL"""
    # Get URLs already in database
    existing_images = get_existing_image_urls()
    
    # Keep only new listings
    new_listings = []
    duplicate_count = 0
    
    for listing in all_listings:
        image_url = listing.get('image_url')
        if image_url not in existing_images:
            new_listings.append(listing)
        else:
            duplicate_count += 1
    
    print(f"Found {duplicate_count} duplicates, {len(new_listings)} new listings")
    return new_listings

def save_to_csv(all_listings):
    """Save listings to CSV file as backup"""
    if not all_listings:
        print("No listings to save to CSV")
        return
    
    # Create filename with today's date
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f'listings_{today}.csv'
    filepath = os.path.join(DATA_FOLDER, filename)
    
    # Write all listings to CSV
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=all_listings[0].keys())
        writer.writeheader()
        writer.writerows(all_listings)
    
    print(f"Saved backup to {filepath}")

def save_to_database(new_listings):
    """Add only new listings to PostgreSQL database"""
    if not new_listings:
        print("No new listings to save to database")
        return
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Prepare data for batch insert
    values = [
        (
            listing['site'],
            listing['title'],
            listing['price'],
            listing['price_numeric'],
            listing['description'],
            listing['url'],
            listing['image_url'],
            listing['scraped_date']
        )
        for listing in new_listings
    ]
    
    # Batch insert all new listings
    execute_values(
        cursor,
        '''INSERT INTO properties 
           (site, title, price, price_numeric, description, url, image_url, scraped_date)
           VALUES %s''',
        values
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Added {len(new_listings)} new listings to database")

def run():
    """Run all scrapers and save results"""
    print(f"Starting scrape at {datetime.now()}")
    
    # Make sure database table exists
    setup_database()
    
    # Store all scraped listings here
    all_listings = []
    
    # Run each scraper
    print("\n1. Scraping Brigitte Sauvager...")
    all_listings.extend(brigitte_sauvager.scrape())
    time.sleep(2)  # Wait between sites to be polite
    
    print("\n2. Scraping Graslin Immobilier...")
    all_listings.extend(graslin_immobilier.scrape())
    time.sleep(2)
    
    # Add more scrapers as you build them
    
    print(f"\nTotal scraped: {len(all_listings)} listings")
    
    # Remove duplicates based on image URL
    new_listings = filter_duplicates(all_listings)
    
    # Save everything
    print("\nSaving results...")
    
    # CSV backup (local)
    save_to_csv(all_listings)
    
    # PostgreSQL database (online)
    save_to_database(new_listings)
    
    print(f"\nDone!")

if __name__ == "__main__":
    run()
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers import brigitte_sauvager
# from scrapers import graslin_immobilier  # (When you add it)

from airflow.providers.postgres.hooks.postgres import PostgresHook

def get_existing_urls():
    """Checks Supabase for URLs we already have to avoid duplicates"""
    hook = PostgresHook(postgres_conn_id='supabase_db')
    records = hook.get_records("SELECT image_url FROM properties")
    return {row[0] for row in records}

def save_to_supabase(new_listings):
    """Batch inserts only the new listings into Supabase"""
    if not new_listings:
        print("No new listings found.")
        return
    
    hook = PostgresHook(postgres_conn_id='supabase_db')
    fields = ['site', 'title', 'price', 'price_numeric', 'description', 'url', 'image_url', 'scraped_date']
    
    # Format the data for the Airflow 'insert_rows' helper
    values = [[l[f] for f in fields] for l in new_listings]
    
    hook.insert_rows(table='properties', rows=values, target_fields=fields)
    print(f"Successfully uploaded {len(new_listings)} listings.")

def run_full_process():
    """This replaces your old 'run()' function from run_scrapers.py"""
    print("Starting automated scrape...")
    
    # 1. Scrape
    all_raw_listings = brigitte_sauvager.scrape()
    
    # 2. Filter Duplicates (Your existing logic)
    existing_urls = get_existing_urls()
    new_listings = [l for l in all_raw_listings if l['image_url'] not in existing_urls]
    
    # 3. Save
    save_to_supabase(new_listings)
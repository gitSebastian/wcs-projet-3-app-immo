import sys
import os
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import timedelta

# 1. Path Injection (The hack that makes imports work)
project_path = os.path.dirname(os.path.abspath(__file__))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from logic_utils import run_full_process

# 2. Timezone Setup
local_tz = pendulum.timezone("Europe/Paris")

# 3. DAG Definition
with DAG(
    dag_id='nantes_immo_scraper',
    start_date=pendulum.datetime(2026, 2, 10, tz=local_tz),
    schedule='0 3 * * *',  # Run at 3:00 AM Paris time
    catchup=False,
    default_args={
        'retries': 2, 
        'retry_delay': timedelta(minutes=10)
    },
    tags=['scraping', 'real_estate']
) as dag:

    scrape_task = PythonOperator(
        task_id='execute_scrape_and_save',
        python_callable=run_full_process
    )
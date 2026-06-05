import sqlite3
import os

# Define the target local database file path
DB_FILE = "jobs.db"

# The specific SQL query you want to execute
qry = "UPDATE jobs SET resume_generated = -1 WHERE resume_generated = 0;"
qry = "UPDATE jobs SET job_url = 'https://visa.wd5.myworkdayjobs.com/en-US/Visa/job/Sr-SW-Engineer---PySpark---Spark-SQL---Scala---Big-Data---ETL_REF081993W?locationCountry=c4f78be1a8f14da0ab49ce1162348a5e' where id=11"

def execute_manual_query(sql_query):
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file '{DB_FILE}' could not be located in this directory.")
        return

    try:
        # Establish connection to local SQLite file
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        print(f"Executing Query: {sql_query}")
        cursor.execute(sql_query)
        
        # Save structural shifts back to disk
        conn.commit()
        
        # Log rows modified by the execution block
        print(f"Success! Transaction committed. Rows affected: {cursor.rowcount}")
        
    except sqlite3.Error as e:
        print(f"Database engine encounter fault: {e}")
        if 'conn' in locals():
            conn.rollback()
            print("Transaction rolled back safely.")
            
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    execute_manual_query(qry)
import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",      # e.g. "root"
        password="dps123",  # e.g. "root" or your password
        database="smart_feedback"
    )

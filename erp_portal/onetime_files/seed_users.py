
import os

import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

accounts = [
    ("head01", "Head@123", "maintenance_head"),
    ("tech01", "Tech@123", "technician"),
    ("tech02", "Tech@456", "technician"),
    ("tech03", "Tech@789", "technician"),
]

connection = mysql.connector.connect(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD"),
    database="smart_manufacturing_erp",
)

try:
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role ENUM('maintenance_head', 'technician') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for username, password, role in accounts:
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                password_hash = VALUES(password_hash),
                role = VALUES(role)
            """,
            (username, generate_password_hash(password), role),
        )

    connection.commit()
    print("Users table ready. Four demo accounts are configured.")

finally:
    cursor.close()
    connection.close()

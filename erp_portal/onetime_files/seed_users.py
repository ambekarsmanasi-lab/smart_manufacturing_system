import os

import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

# Existing accounts are preserved.
# New accounts use temporary demo passwords.
accounts = [
    ("head01", "Head@123", "maintenance_head"),
    ("tech01", "Tech@123", "technician"),
    ("tech02", "Tech@456", "technician"),
    ("tech03", "Tech@789", "technician"),
    ("tech04", "Tech@104", "technician"),
    ("tech05", "Tech@105", "technician"),
    ("tech06", "Tech@106", "technician"),
    ("tech07", "Tech@107", "technician"),
    ("tech08", "Tech@108", "technician"),
    ("tech09", "Tech@109", "technician"),
    ("tech10", "Tech@110", "technician"),
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

    created_count = 0
    skipped_count = 0

    for username, password, role in accounts:
        cursor.execute(
            "SELECT id FROM users WHERE username = %s",
            (username,),
        )

        existing_user = cursor.fetchone()

        if existing_user:
            # Do not overwrite existing passwords or roles.
            skipped_count += 1
            continue

        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
            """,
            (username, generate_password_hash(password), role),
        )

        created_count += 1

    connection.commit()

    print("Users table ready.")
    print(f"New accounts created: {created_count}")
    print(f"Existing accounts preserved: {skipped_count}")

    print("\nDemo credentials for newly created accounts:")
    for username, password, role in accounts:
        if username.startswith("tech") and int(username[4:]) >= 4:
            print(f"{username}: {password}")

finally:
    cursor.close()
    connection.close()
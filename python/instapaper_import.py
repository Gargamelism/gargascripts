#!/usr/bin/env python3

import argparse
import os
import pandas as pd
import requests
from datetime import datetime
from dotenv import load_dotenv


class InstapaperImporter:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv("INSTAPAPER_USERNAME")
        self.password = os.getenv("INSTAPAPER_PASSWORD")

        if not all([self.username, self.password]):
            raise ValueError(
                "Missing required environment variables. Please set INSTAPAPER_USERNAME, and INSTAPAPER_PASSWORD"
            )

    def add_bookmark(self, url, title=None, description=None):
        """Add a bookmark to Instapaper"""

        add_url = "https://www.instapaper.com/api/add"
        params = {
            "username": self.username,
            "password": self.password,
            "url": url,
        }

        if title:
            params["title"] = title
        if description:
            params["selection"] = description

        response = requests.post(add_url, params=params)
        if response.status_code != 201:
            raise Exception(f"Failed to add bookmark: {response.status_code} - {response.text}")
        return response.json()


def process_csv(csv_path):
    """Process the CSV file and send articles to Instapaper"""
    # Read CSV file
    try:
        bookmarks_csv = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    required_columns = ["url", "time_added"]
    if not all(col in bookmarks_csv.columns for col in required_columns):
        print(f"CSV must contain the following columns: {required_columns}")
        return

    bookmarks_csv = bookmarks_csv.sort_values("time_added")

    if "status" not in bookmarks_csv.columns:
        print("Warning: status column not found in CSV, skipping filter")
    else:
        unique_statuses = bookmarks_csv["status"].dropna().unique()
        print("Possible status filters:", ", ".join(f'"{s}"' for s in unique_statuses))
        status_filter = input("Enter status to filter by (or press Enter to skip): ").strip()
        if status_filter:
            bookmarks_csv = bookmarks_csv[bookmarks_csv["status"] == status_filter]

    # Initialize Instapaper client
    try:
        client = InstapaperImporter()
    except Exception as e:
        print(f"Error initializing Instapaper client: {e}")
        return

    # Process each row
    for _, row in bookmarks_csv.iterrows():
        try:
            title = row.get("title") if "title" in bookmarks_csv.columns else None
            description = row.get("description") if "description" in bookmarks_csv.columns else None

            print(f"Adding article: {row['url']}")
            client.add_bookmark(row["url"], title, description)

        except Exception as e:
            print(f"Error adding bookmark {row['url']}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Import articles to Instapaper from a CSV file",
        epilog=(
            "Required environment variables:\n"
            "  INSTAPAPER_USERNAME       Your Instapaper username (email)\n"
            "  INSTAPAPER_PASSWORD       Your Instapaper password"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("csv_path", help="Path to the CSV file")

    args = parser.parse_args()

    if not os.path.exists(args.csv_path):
        print(f"Error: CSV file not found at {args.csv_path}")
        return

    process_csv(args.csv_path)


if __name__ == "__main__":
    main()

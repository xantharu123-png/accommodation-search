#!/usr/bin/env python3
"""
Database models for Favorites & AI Analysis
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class Database:
    """SQLite Database Manager"""
    
    def __init__(self, db_path: str = "favorites.db"):
        """Initialize database connection"""
        self.db_path = Path(db_path)
        self.init_db()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Favorites table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_name TEXT NOT NULL,
                location TEXT NOT NULL,
                listing_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # AI Analyses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                favorite_id INTEGER NOT NULL,
                analysis_result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (favorite_id) REFERENCES favorites(id)
            )
        """)
        
        conn.commit()
        conn.close()
        
        print("✅ Database initialized")
    
    # FAVORITES CRUD
    
    def add_favorite(self, list_name: str, location: str, listing_data: Dict) -> int:
        """Add a listing to favorites"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO favorites (list_name, location, listing_data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (list_name, location, json.dumps(listing_data), now, now))
        
        favorite_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return favorite_id
    
    def get_all_favorites(self) -> List[Dict]:
        """Get all favorites"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, list_name, location, listing_data, created_at, updated_at
            FROM favorites
            ORDER BY updated_at DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        favorites = []
        for row in rows:
            favorites.append({
                'id': row['id'],
                'list_name': row['list_name'],
                'location': row['location'],
                'listing_data': json.loads(row['listing_data']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            })
        
        return favorites
    
    def get_favorites_by_list(self, list_name: str) -> List[Dict]:
        """Get favorites for a specific list"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, list_name, location, listing_data, created_at, updated_at
            FROM favorites
            WHERE list_name = ?
            ORDER BY created_at DESC
        """, (list_name,))
        
        rows = cursor.fetchall()
        conn.close()
        
        favorites = []
        for row in rows:
            favorites.append({
                'id': row['id'],
                'list_name': row['list_name'],
                'location': row['location'],
                'listing_data': json.loads(row['listing_data']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            })
        
        return favorites
    
    def get_all_list_names(self) -> List[str]:
        """Get all unique list names"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT list_name
            FROM favorites
            ORDER BY list_name
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row['list_name'] for row in rows]
    
    def delete_favorite(self, favorite_id: int) -> bool:
        """Delete a favorite"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM favorites WHERE id = ?", (favorite_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def update_list_name(self, old_name: str, new_name: str) -> bool:
        """Rename a favorites list"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE favorites 
            SET list_name = ?, updated_at = ?
            WHERE list_name = ?
        """, (new_name, now, old_name))
        
        updated = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return updated
    
    # AI ANALYSES
    
    def save_analysis(self, favorite_id: int, analysis_result: Dict) -> int:
        """Save AI analysis for a favorite"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO ai_analyses (favorite_id, analysis_result, created_at)
            VALUES (?, ?, ?)
        """, (favorite_id, json.dumps(analysis_result), now))
        
        analysis_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return analysis_id
    
    def get_analysis(self, favorite_id: int) -> Optional[Dict]:
        """Get AI analysis for a favorite"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, analysis_result, created_at
            FROM ai_analyses
            WHERE favorite_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (favorite_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row['id'],
                'favorite_id': favorite_id,
                'analysis_result': json.loads(row['analysis_result']),
                'created_at': row['created_at']
            }
        
        return None


# Example usage
if __name__ == "__main__":
    db = Database()
    
    # Test add favorite
    listing = {
        'title': 'Cozy Apartment',
        'price': 150,
        'rating': 4.8,
        'url': 'https://airbnb.com/...'
    }
    
    fav_id = db.add_favorite("Paris Trip", "Paris", listing)
    print(f"✅ Added favorite: {fav_id}")
    
    # Test get all
    favs = db.get_all_favorites()
    print(f"✅ All favorites: {len(favs)}")
    
    # Test analysis
    analysis = {
        'positive': ['Clean', 'Great location'],
        'negative': ['A bit noisy'],
        'summary': 'Good apartment overall'
    }
    
    analysis_id = db.save_analysis(fav_id, analysis)
    print(f"✅ Saved analysis: {analysis_id}")
    
    # Get analysis
    saved_analysis = db.get_analysis(fav_id)
    print(f"✅ Retrieved analysis: {saved_analysis}")

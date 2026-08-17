import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vanguard.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            headline TEXT,
            framing_lead TEXT,
            blockquote TEXT,
            source_name TEXT,
            source_url TEXT,
            tip_cta TEXT,
            relevance_score INTEGER,
            status TEXT DEFAULT 'pending', -- pending, published, rejected
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            unsplash_img TEXT,
            image_credit_name TEXT,
            image_credit_username TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_draft(draft):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO drafts (
            category, headline, framing_lead, blockquote, 
            source_name, source_url, tip_cta, relevance_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        draft.get('category'),
        draft.get('headline'),
        draft.get('framing_lead'),
        draft.get('blockquote'),
        draft.get('source_name'),
        draft.get('source_url'),
        draft.get('tip_cta'),
        draft.get('relevance_score')
    ))
    draft_id = c.lastrowid
    conn.commit()
    conn.close()
    return draft_id

def get_draft(draft_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM drafts WHERE id = ?', (draft_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_draft_status(draft_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE drafts SET status = ? WHERE id = ?', (status, draft_id))
    conn.commit()
    conn.close()

def update_draft_field(draft_id, field, value):
    allowed_fields = ['headline', 'framing_lead']
    if field not in allowed_fields:
        return
    conn = get_connection()
    c = conn.cursor()
    # Safely format the query since field is checked against allowed list
    c.execute(f'UPDATE drafts SET {field} = ? WHERE id = ?', (value, draft_id))
    conn.commit()
    conn.close()

def update_draft_image(draft_id, img_url, credit_name, credit_username):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE drafts 
        SET unsplash_img = ?, image_credit_name = ?, image_credit_username = ? 
        WHERE id = ?
    ''', (img_url, credit_name, credit_username, draft_id))
    conn.commit()
    conn.close()

def get_published_drafts_without_images():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM drafts 
        WHERE status = 'published' AND (unsplash_img IS NULL OR unsplash_img = '')
    ''')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

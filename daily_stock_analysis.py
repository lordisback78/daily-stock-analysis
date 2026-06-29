#!/usr/bin/env python3
import os
import json
import base64
from datetime import datetime
import anthropic

try:
    from google.oauth2.credentials import Credentials as OAuth2Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError as e:
    print(f"⚠️ Google Auth not available: {e}")
    exit(1)

def get_gmail_service():
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    token_file = 'gmail_token.json'
    creds = None
    
    try:
        if os.path.exists(token_file):
            creds = OAuth2Credentials.from_authorized_user_file(token_file, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                print("❌ No valid Gmail credentials found. Create gmail_token.json first.")
                return None
        
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        print(f"❌ Gmail error: {e}")
        return None

def generate_stock_analysis():
    try:
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        
        prompt = """Tu es expert en analyse boursière. Déniches la meilleure pépite décotée du jour.
Retourne UNIQUEMENT du JSON: {"stock_name": "...", "ticker": "...", "exchange": "...", "current_price": "...", "market_cap": "...", "sector": "...", "investment_thesis": "...", "catalyst": "...", "price_target": "...", "upside": "...", "fair_value_estimate": "...", "pe_ratio": "...", "dividend_yield": "...", "risks": [], "analyst_consensus": "...", "source": "..."}"""

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        text = response.content[0].text if response.content else ""
        return json.loads(text)
    except json.JSONDecodeError:
        print("❌ Claude didn't return valid JSON")
        return None
    except Exception as e:
        print(f"❌ Error generating analysis: {e}")
        return None

def create_gmail_draft(service, stock_data):
    if not stock_data or not service:
        return None
    
    today = datetime.now().strftime("%d/%m/%Y")
    html = f"""<h2>📊 Pépite du jour – {today}</h2>
<h3>🚀 {stock_data.get('stock_name')} ({stock_data.get('ticker')})</h3>
<p><strong>Cours:</strong> {stock_data.get('current_price')} | <strong>Cap:</strong> {stock_data.get('market_cap')}</p>
<h4>Thèse</h4><p>{stock_data.get('investment_thesis')}</p>
<h4>Catalyseur</h4><p>{stock_data.get('catalyst')}</p>
<h4>Objectif</h4><p>{stock_data.get('price_target')} ({stock_data.get('upside')})</p>
<hr><p><small>Avertissement: Informatif uniquement. Pas un conseil.</small></p>"""
    
    subject = f"📈 Pépite du jour – {today}"
    
    try:
        message = {
            'raw': base64.urlsafe_b64encode(
                f"To: luc.renouvel@gmail.com\nSubject: {subject}\nMIME-Version: 1.0\nContent-Type: text/html\n\n{html}".encode('utf-8')
            ).decode('utf-8')
        }
        draft = service.users().drafts().create(userId='me', body={'message': message}).execute()
        print(f"✅ Draft created: {draft['id']}")
        return draft
    except Exception as e:
        print(f"❌ Error creating draft: {e}")
        return None

def main():
    print(f"🕐 Starting at {datetime.now()}")
    
    print("📊 Generating analysis...")
    stock_data = generate_stock_analysis()
    
    if not stock_data:
        print("❌ Failed to generate analysis")
        return
    
    print(f"✅ Got: {stock_data.get('stock_name')}")
    
    print("📧 Creating Gmail draft...")
    service = get_gmail_service()
    if service:
        create_gmail_draft(service, stock_data)
    else:
        print("⚠️ Gmail service unavailable (gmail_token.json missing)")

if __name__ == "__main__":
    main()

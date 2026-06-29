#!/usr/bin/env python3
import os
import json
import base64
from datetime import datetime
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import anthropic

def get_gmail_service():
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    token_file = 'gmail_token.json'
    creds = None
    
    if os.path.exists(token_file):
        creds = OAuth2Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)

def generate_stock_analysis():
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    prompt = """Tu es un expert senior de l'analyse boursière. Déniches la meilleure pépite décotée du jour.
Retourne UNIQUEMENT du JSON valide (pas de texte): stock_name, ticker, exchange, current_price, market_cap, sector, investment_thesis, catalyst, price_target, upside, fair_value_estimate, pe_ratio, dividend_yield, risks (array), analyst_consensus, source."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = response.content[0].text if response.content else ""
    try:
        return json.loads(text)
    except:
        return None

def create_gmail_draft(service, stock_data):
    if not stock_data:
        return None
    
    today = datetime.now().strftime("%d/%m/%Y")
    html_body = f"""<h2>📊 Ta pépite boursière du jour – {today}</h2>
<h3>🚀 {stock_data.get('stock_name')} ({stock_data.get('ticker')} – {stock_data.get('exchange')})</h3>
<p><strong>Cours :</strong> {stock_data.get('current_price')} | <strong>Cap :</strong> {stock_data.get('market_cap')}</p>
<h4>💡 Thèse</h4>
<p>{stock_data.get('investment_thesis')}</p>
<h4>⚡ Catalyseur</h4>
<p>{stock_data.get('catalyst')}</p>
<h4>🎯 Objectif</h4>
<p>{stock_data.get('price_target')} (upside: {stock_data.get('upside')})</p>
<h4>⚠️ Risques</h4>
<ul>"""
    
    for risk in stock_data.get('risks', []):
        html_body += f"<li>{risk}</li>"
    
    html_body += f"""</ul>
<hr>
<p><small>Avertissement : Informatif uniquement. Investir comporte des risques.</small></p>"""
    
    subject = f"📈 Ta pépite boursière du jour – {today}"
    
    try:
        message = {
            'raw': base64.urlsafe_b64encode(
                f"To: luc.renouvel@gmail.com\nSubject: {subject}\nMIME-Version: 1.0\nContent-Type: text/html; charset=\"UTF-8\"\n\n{html_body}".encode('utf-8')
            ).decode('utf-8')
        }
        draft = service.users().drafts().create(userId='me', body={'message': message}).execute()
        print(f"✅ Draft created: {draft['id']}")
        return draft
    except HttpError as error:
        print(f"❌ Error: {error}")
        return None

def main():
    print(f"🕐 Running at {datetime.now()}")
    stock_data = generate_stock_analysis()
    
    if not stock_data:
        print("❌ Failed to generate analysis")
        return
    
    print(f"✅ Analysis: {stock_data.get('stock_name')}")
    
    try:
        gmail_service = get_gmail_service()
        create_gmail_draft(gmail_service, stock_data)
    except Exception as e:
        print(f"❌ Gmail error: {e}")

if __name__ == "__main__":
    main()

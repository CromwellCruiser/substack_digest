import os
import json
import time
import base64
import datetime
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

# Google Auth & Gmail Libraries
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Gen AI SDK
from google import genai
from google.genai import types

# --- CONFIGURATION ---
MODEL_ID = 'gemini-2.0-flash'
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
SEARCH_QUERY = 'from:substack.com after:{timestamp}'
TARGET_EMAIL = 'me'


def authenticate_gmail():
    """
    HEADLESS AUTH: Reads the full token JSON from an environment variable.
    This bypasses the need for a local browser login.
    """
    token_json = os.environ.get('GMAIL_TOKEN_JSON')

    if not token_json:
        raise ValueError("FATAL: GMAIL_TOKEN_JSON environment variable is missing.")

    # Parse the JSON string back into a dictionary
    creds_data = json.loads(token_json)

    # Reconstruct the credentials object
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    # Auto-refresh if expired (Works because the JSON contains the refresh_token)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("[-] Token expired. Refreshing automatically...")
            creds.refresh(Request())
        else:
            raise RuntimeError("Token is invalid and cannot be refreshed. Please regenerate locally.")

    return build('gmail', 'v1', credentials=creds)


def get_messages(service):
    """Hunts for substack emails from the last 25 hours."""
    past_time = datetime.datetime.now() - datetime.timedelta(hours=25)
    timestamp = int(past_time.timestamp())

    query = SEARCH_QUERY.format(timestamp=timestamp)
    print(f"[*] Searching with query: {query}")

    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])
    print(f"[*] Found {len(messages)} messages.")
    return messages


def extract_body(payload):
    """Recursively extracts plain text from email payload."""
    body = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    body += base64.urlsafe_b64decode(data).decode('utf-8')
            elif part['mimeType'] == 'text/html':
                data = part['body'].get('data')
                if data:
                    html_content = base64.urlsafe_b64decode(data).decode('utf-8')
                    soup = BeautifulSoup(html_content, 'html.parser')
                    body += soup.get_text()
            elif 'parts' in part:
                body += extract_body(part)
    else:
        data = payload['body'].get('data')
        if data:
            body += base64.urlsafe_b64decode(data).decode('utf-8')
    return body


def summarize_text(client, text):
    """Passes raw intel to Gemini."""
    if not text or len(text) < 50:
        return "Content too short to summarize."

    prompt = f"""
    You are an executive assistant. Summarize this Substack newsletter. 
    Focus on the "Big Idea" and 3 key bullet points.

    TEXT:
    {text[:15000]} 
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
            )
        )
        return response.text
    except Exception as e:
        return f"Error summarising: {e}"


def send_digest(service, summaries):
    """Compiles the report and emails it."""
    if not summaries:
        print("[!] No summaries to send.")
        return

    date_str = datetime.datetime.now().strftime("%d/%m/%Y")
    subject = f"Your Substack Digest - {date_str}"

    email_body = f"<h2>Substack Digest ({len(summaries)} newsletters)</h2>"
    email_body += "<hr>"

    for item in summaries:
        email_body += f"<h3>{item['subject']}</h3>"
        email_body += f"<p><b>From:</b> {item['from']}</p>"
        clean_summary = item['summary'].replace('\n', '<br>')
        email_body += f"<div style='background:#f9f9f9; padding:10px; border-left: 4px solid #333;'>{clean_summary}</div>"
        email_body += "<hr>"

    message = MIMEText(email_body, 'html')
    message['to'] = TARGET_EMAIL
    message['subject'] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

    try:
        service.users().messages().send(
            userId='me', body={'raw': raw_message}).execute()
        print(f"[*] Digest sent successfully: {subject}")
    except Exception as e:
        print(f"[!] Failed to send email: {e}")


def main():
    # 1. Setup New GenAI Client (From ENV)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("FATAL: GEMINI_API_KEY environment variable is missing.")

    client = genai.Client(api_key=api_key)

    # 2. Authenticate Gmail (Headless)
    service = authenticate_gmail()

    # 3. Get Message IDs
    message_ids = get_messages(service)

    if not message_ids:
        print("[!] No Substack emails found in the last 25 hours.")
        return

    # --- Preview Phase (Logging Only) ---
    print(f"\n[-] Fetching content for {len(message_ids)} emails...")
    loaded_messages = []

    for msg in message_ids:
        try:
            msg_detail = service.users().messages().get(
                userId='me', id=msg['id'], format='full').execute()

            headers = msg_detail['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')

            print(f" [x] Found: {subject[:60]}...")

            loaded_messages.append({
                'detail': msg_detail,
                'subject': subject,
                'sender': sender
            })
        except Exception as e:
            print(f" [!] Error fetching message {msg['id']}: {e}")

    # 4. Process Loop
    print("-" * 60)
    print("[-] Starting Summarization Loop...")
    digest_data = []

    for idx, item in enumerate(loaded_messages):
        print(f"\n[{idx + 1}/{len(loaded_messages)}] Processing: {item['subject']}")

        full_text = extract_body(item['detail']['payload'])
        summary = summarize_text(client, full_text)

        digest_data.append({
            'subject': item['subject'],
            'from': item['sender'],
            'summary': summary
        })

        # Delay
        if idx < len(loaded_messages) - 1:
            print("    ... Waiting 60 seconds...")
            time.sleep(60)

    # 5. Send Email
    send_digest(service, digest_data)


if __name__ == '__main__':
    main()
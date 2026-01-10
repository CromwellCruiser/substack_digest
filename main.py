import os
import json
import time
import base64
import datetime
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import functions_framework
import re

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google import genai
from google.genai import types

# --- CONFIGURATION ---
MODEL_ID = 'gemini-2.5-flash'
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
SEARCH_QUERY = 'from:substack.com after:{timestamp}'

# TUNING FOR POWER USERS
SLEEP_DELAY = 10  # Seconds between Gemini calls (8s * 60 emails = ~8 mins runtime)


def authenticate_gmail():
    token_json = os.environ.get('GMAIL_TOKEN_JSON')
    if not token_json:
        raise ValueError("FATAL: GMAIL_TOKEN_JSON missing.")
    try:
        creds_data = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    except json.JSONDecodeError:
        raise ValueError("FATAL: Invalid JSON token.")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("[-] Token expired. Refreshing...")
            creds.refresh(Request())
        else:
            raise RuntimeError("FATAL: Token invalid.")
    return build('gmail', 'v1', credentials=creds)


def get_messages(service):
    """Fetches ALL messages (handles pagination for >100 emails)."""
    past_time = datetime.datetime.now() - datetime.timedelta(hours=24)
    timestamp = int(past_time.timestamp())
    query = SEARCH_QUERY.format(timestamp=timestamp)

    all_messages = []
    page_token = None

    while True:
        results = service.users().messages().list(
            userId='me', q=query, maxResults=500, pageToken=page_token
        ).execute()

        messages = results.get('messages', [])
        all_messages.extend(messages)

        page_token = results.get('nextPageToken')
        if not page_token:
            break

    return all_messages
    
def extract_body(payload):
    """
    Recursively extracts and cleans the body of the email.
    Now integrates aggressive HTML stripping for Substack emails.
    """
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
                    body += clean_substack_html(html_content)
            elif 'parts' in part:
                body += extract_body(part)
    else:
        data = payload['body'].get('data')
        if data:
            # If it's a single-part email, check if it's HTML or plain text
            content = base64.urlsafe_b64decode(data).decode('utf-8')
            if payload.get('mimeType') == 'text/html':
                body += clean_substack_html(content)
            else:
                body += content
    return body

def clean_substack_html(html):
    """
    Deconstructs the HTML to remove tracking, CSS, and navigation junk.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Immediate incineration of non-content tags
    for element in soup(['style', 'script', 'header', 'footer', 'nav', 'head', 'title']):
        element.decompose()

    # 2. Targeted removal of Substack's 'viral loop' buttons and footers
    # This searches for links and divs that contain standard Substack boilerplate
    for junk in soup.find_all(['div', 'table', 'a', 'span'], string=lambda t: t and any(x in t.lower() for x in [
        'read in app', 'share this post', 'subscribe', 'privacy policy', 'unsubscribe', 'copy link'
    ])):
        junk.decompose()

    # 3. Extract text with a space separator to prevent word-clumping
    # (e.g., preventing 'End of ParagraphStart of Next' becoming 'ParagraphStart')
    text = soup.get_text(separator=' ', strip=True)
    
    # 4. Regex cleanup: Collapse tabs, multiple spaces, and newlines into single spaces
    # This drastically reduces token count for the Gemini prompt.
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def summarize_text(client, text):
    if not text or len(text) < 50:
        return {'score': 0, 'content': 'Content too short.'}

    # Custom Profile Persona
    persona = "doctoral researcher in international relations and commercially aware management/strategy consultant"
    
    prompt = (
        f"Perform a high-density analysis and synthesis of the following newsletter for a {persona}, scoring it for relevance based on the scoring system of 1 being bottom 20% relevancy and 5 being top 20% relevancy.\n\n"
        f"OUTPUT FORMAT:\n"
        f"**RVSCORE:** [1-5]\n"
        f"1. **Core Thesis**: One sentence of maximum intellectual depth.\n"
        f"2. **Critical Pillars**: 3-4 bullet points analyzing the primary logical moves or data points.\n"
        f"3. **Relevance**: Highlight the relevance of this piece for {persona}.\n\n"
        f"TEXT:\n{text[:60000]}"
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_ID, 
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1) # Lower temp for consistent scoring
            )
            raw_text = response.text
            
            # Parse the score out of the response
            score = 1
            try:
                # This regex is more robust: it looks for 'RVSCORE', 
                # ignores potential asterisks/spaces, and finds the first digit.
                score_match = re.search(r'RVSCORE[:\* \s]+(\d)', raw_text, re.IGNORECASE)
                if score_match:
                    score = int(score_match.group(1))
            except Exception as e:
                print(f"[!] Score parsing failed: {e}")

            return {'score': score, 'content': raw_text}

        except Exception as e:
            # Check if '503' is in the error message
            if '503' in str(e) and attempt < max_retries - 1:
                print(f"[!] Gemini 503 (Unavailable). Retry {attempt + 1}/{max_retries} in {SLEEP_DELAY}s...")
                time.sleep(SLEEP_DELAY)
                continue
            
            # If it's a different error (like 400 or 429) or we've exhausted retries
            print(f"[!] Critical Error: {e}")
              # Ensure 'content' is a string, not None
            return {'score': 0, 'content': f"Error during processing: {str(e)}"}
    

def markdown_to_html(text):
    # Fallback if text is None or not a string
    if not isinstance(text, str):
        return "" 
    
    # Replace **text** with <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Convert single newlines to <br> for HTML rendering
    return text.replace('\n', '<br>')

def send_digest(service, summaries, target_email):
    if not summaries:
        return "No summaries."

    # --- THE SORTING MAGIC ---
    # Access the 'score' inside the 'summary' sub-dictionary
    summaries.sort(key=lambda x: x['summary'].get('score', 0), reverse=True)

    date_str = datetime.datetime.now().strftime("%d/%m/%Y")
    subject = f"Daily Substack Digest ({len(summaries)}) - {date_str}"

    email_body = f"<a name='top'></a><h2>Daily Digest: {len(summaries)} Newsletters</h2><hr>"

    # --- TABLE OF CONTENTS ---
    email_body += "<h3>Quick Links:</h3><ul>"
    for i, item in enumerate(summaries):
        score = item['summary'].get('score', 0)
        stars = "★" * score + "☆" * (5 - score)
        email_body += f"<li>[{stars}] <a href='#item{i}'>{item['subject']}</a></li>"
    email_body += "</ul><hr>"

    # --- CONTENT ---
    for i, item in enumerate(summaries):
        email_body += f"<h3><a name='item{i}' id='item{i}'></a>{item['subject']}</h3>"
        email_body += f"<p><b>From:</b> {item['from']}</p>"
        
        # Access the 'content' inside the 'summary' sub-dictionary
        raw_summary_content = item['summary'].get('content', 'No content available.')
        clean_content = markdown_to_html(raw_summary_content)
        
        email_body += f"<div style='background:#f9f9f9; padding:15px; border-left: 5px solid #0044cc;'>{clean_content}</div>"
        email_body += f"<p style='font-size:12px;'><a href='#top'>↑ Back to Top</a></p><hr>"

    message = MIMEText(email_body, 'html', 'utf-8')
    message['to'] = target_email
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

    service.users().messages().send(userId='me', body={'raw': raw}).execute()
    return f"Sorted digest sent to {target_email}"

@functions_framework.http
def substack_digest(request):
    try:
        print("[-] Starting High-Volume Execution...")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return "Missing API Key", 500

        client = genai.Client(api_key=api_key)
        service = authenticate_gmail()

        profile = service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']

        messages = get_messages(service)
        if not messages: return "No emails found.", 200

        print(f"[-] Processing batch of {len(messages)} emails...")
        digest_data = []

        for idx, msg in enumerate(messages):
            msg_detail = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = msg_detail['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')

            print(f"[{idx + 1}/{len(messages)}] {subject[:40]}...")
            text = extract_body(msg_detail['payload'])
            summary = summarize_text(client, text)

            digest_data.append({'subject': subject, 'from': sender, 'summary': summary})

            # Smart Delay
            if idx < len(messages) - 1:
                time.sleep(SLEEP_DELAY)

        result = send_digest(service, digest_data, user_email)
        print(f"Digest Completed and Sent.")
        return result, 200

    except Exception as e:
        print(f"Error: {e}")
        return f"Error: {e}", 500
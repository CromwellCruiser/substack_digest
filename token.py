pip install google-auth-oauthlib google-api-python-client
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Same scopes as your Cloud Function
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def generate():
    # You must download 'credentials.json' from Google Cloud Console first
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    # This is the string you will put into your Cloud Function Environment Variable
    token_data = creds.to_json()
    print("\n--- COPY THE JSON BELOW ---")
    print(token_data)
    print("--- END OF JSON ---\n")

if __name__ == "__main__":
    generate()
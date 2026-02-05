pip install json os google-auth-oauthlib
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

# SCOPES must match your Google Auth Platform 'Data Access' settings
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
OUTPUT_FILE = 'GMAIL_TOKEN_ENV.txt'


def main():
    # Verify credentials.json exists
    if not os.path.exists('credentials.json'):
        print("[-] Error: 'credentials.json' not found. Please download it from Google Cloud Console.")
        return

    # Initialize the OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

    # Run the local server
    # access_type='offline' is critical for the long-term refresh_token
    # prompt='consent' ensures the refresh token is granted by the user
    creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }

    # Convert to a single-line string suitable for an environment variable
    json_string = json.dumps(token_data)

    # Output to text file
    try:
        with open(OUTPUT_FILE, 'w') as f:
            f.write(json_string)
        print(f"\n[+] SUCCESS!")
        print(f"[+] Token data written to: {os.path.abspath(OUTPUT_FILE)}")
        print(f"[+] Copy the contents of this file into your 'GMAIL_TOKEN_JSON' environment variable.")
    except Exception as e:
        print(f"[-] Failed to write to file: {e}")


if __name__ == "__main__":
    main()

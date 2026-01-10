# Substack (G)mail Fetcher and Digest Creator
Obsessive Substack newsletter subscribers rejoice!

This repository provides a python file to be deployed as a Google Cloud Function (in conjunction with a Cloud Scheduler) to summarise the newsletters of the day into a daily digest email. 

It reads directly from a Gmail account (using the from:substack.com search), selecting emails from the last 24 hours and passing them to Gemini for summary. It then collates those summaries and outputs them in a relevancy-based order.

## Parameters to be Tweaked
1. Find the {persona} flag in the file and re-write it for your own use. Gemini's relevancy metrics leave something to be desired (if you are judicious in your selection of newsletters they will rarely get a 1-2 anyway) but some elementary triaging can occur, I think.
2. Gemini model: use another Gemini model if you have the authority to do so. 2.5 Flash works for me and for other free users (just set up a billing account but don't authorise billing to enable 'paid tier 1' status which should enable processing at scale)

## 1. Getting the Tokens
You'll need a Gmail API token in order for the script to access your email and send you a digest from yourself. You'll also need a Gemini API token for Gemini to summarise the things for you.
1. Create a Project in the [Google Cloud Console](https://console.cloud.google.com/).
2. [Enable APIs](https://console.cloud.google.com/apis/dashboard): Enable the Gmail API, Cloud Functions API, Cloud Build API, and Cloud Scheduler API.
3. OAuth Credentials (for the Token Script):\
    In Google Cloud Platform Console: APIs & Services > Credentials.\
    Create Credentials > OAuth client ID > Desktop App.\
    Download the JSON file and rename it to credentials.json for the token.py script. Save it in the same folder as the script.
4. Run token.py and copy the resulting JSON string into a text file. Keep this on hand.
5. Navigate to [https://aistudio.google.com](https://aistudio.google.com/) and set up a new project to use Gemini with. Acquire the API token and copy this down to a text file. Also keep this on hand. You may wish to set up a billing account for Gemini API (see above) at this point.

## 2. Setting up Google Cloud Function
1. Navigate to [https://console.cloud.google.com/run/services](https://console.cloud.google.com/run/services) and click on Create a New Function > Use an Inline Editor to Create a Function (rightmost radio button)
2. Call your service something relevant and set up the right timezone. Copy the endpoint URL and paste this into a text file.
3. Authentication > Require Authentication
4. Maximum Number of Instances > 1. You don't need more than 1 running simultaneously.
5. Containers > under 'edit port' there should be 'Variables and Secrets'. Your two should be pasted in as Environment Variables.\
     GMAIL_TOKEN_JSON: paste the Gmail token fetched from the token.py script.\
     GEMINI_API_KEY: paste the API key.
6. Request timeout > 3600.
7. Now that the function is set up, click on the function in the [list of functions](https://console.cloud.google.com/run/services) and navigate to 'Source'. Click Edit Source (blue button) and click the plus sign on the left hand column which appears. Name two new files main.py and requirements. txt.
8. Paste the contents of two files in this repository into the two files you've just created respectively.
9. For function entry point next to the edit source button: substack_digest

## 3. Setting up the Scheduler
1. The Cloud Function does not work automatically and needs to be called, for this purpose we use the [Cloud Scheduler](https://console.cloud.google.com/cloudscheduler).
2. Create Job:\
    Name: daily-substack-summariser\
    Frequency: 0 8 * * * \
		(Note: This is 8:00 AM daily, use another time (24hr format), e.g. '22' if you'd like an evening digest instead.)\
    Target Type: HTTP\
    URL: (Copy the "Trigger URL" from your Cloud Function 'Trigger' tab).\
    HTTP Method: GET\
    Auth Header: Add OIDC token (Select your default App Engine service account).
3. To test it, navigate back to the Cloud Scheduler and use Actions > Force Run. If you get an email in a few (or ten+) minutes, success.
4. Otherwise, navigate to the Cloud Function, where under Observatbility there should be Logs. Use Gemini to find out what is wrong.


Disclaimer: this script and all material is provided as is and without any warranties, guaranties, or securities of any sort. Use of this script is at your own risk and does not confer on you any legal claims over me. By downloading and using this script, even as described, you indemnify me and my heirs and successors according to law from all undesirable results that may occur. Additional licence information in the relevant file.

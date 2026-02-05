# Substack (G)mail Fetcher and Digest Creator
Obsessive Substack newsletter subscribers rejoice!

This repository provides a python file to be deployed as a Google Cloud Function (in conjunction with a Cloud Scheduler) to summarise the newsletters of the last 24 hours into a daily digest email. 

It reads directly from a Gmail account through the Gmail API (using the from:substack.com search), selecting emails from the last 24 hours and passing them to Gemini for summary. It then collates those summaries and outputs them in a relevancy-based order.

## Parameters to be Tweaked
1. Find the {persona} flag in the file and re-write it for your own use. Gemini's relevancy metrics leave something to be desired (if you are judicious in your selection of newsletters they will rarely get a 1-2 anyway) but some elementary triaging can occur, I think.
2. Gemini model: use another Gemini model if you have the authority to do so. 2.5 Flash works for me and for other free users (just set up a billing account but don't authorise billing to enable 'paid tier 1' status which should enable processing at scale)
3. Tweak the Gemini prompt to something that works for you. I'm still experimenting with mine, as I am with the relevancy factor.
4. Tweak the Gmail search to anything you like. In conjunction with tweaks to the scheduler, you can set this up as a weekly or twice-daily summariser.

## 1. Getting the Tokens
You'll need a Gmail API token in order for the script to access your email and send you a digest from yourself. You'll also need a Gemini API token for Gemini to summarise the things for you.
1. Create a Project in the [Google Cloud Console](https://console.cloud.google.com/).
2. [Enable APIs](https://console.cloud.google.com/apis/dashboard): Enable the Gmail API, Cloud Functions API, Cloud Build API, and Cloud Scheduler API.
3. OAuth Credentials (for the Token Script):
    - In Google Cloud Platform Console: APIs & Services > Credentials.
    - Create Credentials > OAuth client ID > Desktop App.
    - Download the JSON file and rename it to credentials.json for the generate_user_token.py script. Save it in the same folder as the script.
4. Run generate_user_token.py and copy the resulting JSON string into a text file. Keep this on hand.
5. Navigate to [https://aistudio.google.com](https://aistudio.google.com/) and set up a new project to use Gemini with. Acquire the API token and copy this down to a text file. Also keep this on hand. You may wish to set up a billing account for Gemini API (see above) at this point.

## 2. Setting up Google Cloud Function
1. Navigate to [https://console.cloud.google.com/run/services](https://console.cloud.google.com/run/services) and click on Create a New Function > Use an Inline Editor to Create a Function (rightmost radio button)
2. Call your service something relevant and set up the right timezone. Copy the endpoint URL and paste this into a text file.
3. Authentication > Require Authentication
4. Maximum Number of Instances > 1. You don't need more than 1 running simultaneously.
5. Containers > under 'edit port' there should be 'Variables and Secrets'. Your two should be pasted in as Environment Variables.
     - GMAIL_TOKEN_JSON: paste the Gmail token fetched from the token.py script.
     - GEMINI_API_KEY: paste the API key.
6. Request timeout > 3600.
7. Now that the function is set up, click on the function in the [list of functions](https://console.cloud.google.com/run/services) and navigate to 'Source'. Click Edit Source (blue button) and click the plus sign on the left hand column which appears. Name two new files main.py and requirements.txt.
8. Paste the contents of two files in this repository into the two files you've just created respectively.
9. For function entry point next to the edit source button: substack_digest
10. Copy the URL that appears next to the 'region' specifier.

## 3. Setting up the Scheduler
1. The Cloud Function does not work automatically and needs to be called, for this purpose we use the [Cloud Scheduler](https://console.cloud.google.com/cloudscheduler).
2. Create Job using the following details:
	- Name: daily-substack-summariser (or other name that works for you)
	- Frequency: 0 8 * * * (Note: This is 8:00 AM daily, use another time (24hr format), e.g. '22' if you'd like an evening digest instead.)
	- Target Type: HTTP
	- URL: (Copy the URL that appears next to 'region' when you're on the main page for your Cloud function. You should have made a note of this)
	- HTTP Method: GET
	- Auth Header: Add OIDC token (Select your default App Engine service account).
4. Configure optional settings > Attempt deadline config: set to 30m. If you receive a lot of substack emails, the function may run longer than the default 3 minutes and lead to failure.
5. To test it, navigate back to the Cloud Scheduler and use Actions > Force Run. If you get an email in a few (or ten+) minutes, success.
6. Otherwise, navigate to the Cloud Function, where under Observability there should be Logs. Use Gemini to find out what is wrong.

## 4. Notes on the Unix-cron String Format
Here are notes on setting up the five-field Unix-cron string for more sophisticated scheduling.
1. The Five Fields of a Cron Schedule\
The format follows this order: Minutes, Hours, Day-of-month, Month, Day-of-week. \
Field | Description | Values\
1	Minute	0-59\
2	Hour	0-23 (12:00 a.m. - 11:00 p.m.)\
3	Day of month	1-31\
4	Month	1-12\
5	Day of week	0-7 (0 or 7 is Sunday)\

	* (Asterisk): Represents "all" or "every" (e.g., * in the hour field means every hour).
Numbers: Represent specific times (e.g., 5 in the minute field means at the 5th minute of the hour).
Ranges/Lists: You can use , for lists (e.g., 1,15,30) or - for ranges (e.g., 1-5). 

2. Examples of Frequency Setups
	 - Run every 5 minutes: */5 * * * *
	 - Run at 5:00 AM every day: 0 5 * * *
	 - Run on the 5th day of the month at 12:00 PM: 0 12 5 * *
	 - Run every Friday at 5:00 PM: 0 17 * * 5
	 - Run at 1:05 AM, 1:15 AM, 1:25 AM, 1:35 AM, 1:45 AM daily: 5,15,25,35,45 1 * * *

Disclaimer: this script and all material is provided as is and without any warranties, guaranties, or securities of any sort. Use of this script is at your own risk and does not confer on you any legal claims over me. By downloading and using this script, even as described, you indemnify me and my heirs and successors according to law from all undesirable results that may occur. Additional licence information in the relevant file.

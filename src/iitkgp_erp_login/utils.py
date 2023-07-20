import os
import inspect
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

def get_import_location():
    frame = inspect.currentframe()
    while frame.f_back:
        frame = frame.f_back

    script_file_path = frame.f_globals['__file__']
    script_directory_path = os.path.dirname(script_file_path)
    
    return script_directory_path

def generate_token(permission):
	token_path = os.path.join(get_import_location(), "token.json")
	credentials_path = os.path.join(get_import_location(), "credentials.json")
	scopes = [f"https://www.googleapis.com/auth/gmail.{permission}"]	

	creds = None
	if os.path.exists(token_path):
		creds = Credentials.from_authorized_user_file(token_path, scopes)	
	if not creds or not creds.valid:
		if creds and creds.expired and creds.refresh_token:
			creds.refresh(Request())
		else:
			flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
			creds = flow.run_local_server(port=0)	

		if not os.path.exists(token_path):
			with open(token_path, "w") as token:
				token.write(creds.to_json())

		return creds
import os
import re
import sys
import ping3
import getpass
import inspect
import requests
from typing import TypedDict
from bs4 import BeautifulSoup as bs

import logging
logging.basicConfig(level=logging.INFO)

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from iitkgp_erp_login.endpoints import *
from iitkgp_erp_login.read_mail import getOTP
from iitkgp_erp_login.utils import get_import_location, write_tokens_to_file, get_tokens_from_file

ROLL_NUMBER = ""

class LoginDetails(TypedDict):
    user_id: str
    "Roll number"
    password: str
    "ERP password"
    answer: str
    "Secret/security question's answer"
    sessionToken: str
    "Session token"
    requestedUrl: str
    "The ERP url/path that is requested/will be redirected to."
    email_otp: str
    "OTP if required"

class ErpCreds(TypedDict):
    ROLL_NUMBER: str
    PASSWORD: str
    SECURITY_QUESTIONS_ANSWERS: dict[str, str]

class ErpLoginError(Exception):
    pass

def get_sessiontoken(session: requests.Session, log: bool):
    """Gets the session token from the response of an HTTP request."""
    try:
        r = session.get(HOMEPAGE_URL)
        soup = bs(r.text, 'html.parser')
        sessionToken = soup.find(id='sessionToken')['value']

        if log: logging.info(" Generated sessionToken")
    except (requests.exceptions.RequestException, KeyError) as e:
        raise ErpLoginError(f"Failed to generate session token: {str(e)}")

    return sessionToken


def get_secret_question(headers: dict[str, str], session: requests.Session, roll_number: str, log: bool):
    """Fetches the secret question given the roll number."""
    try:
        r = session.post(SECRET_QUESTION_URL, data={'user_id': roll_number}, headers=headers)

        if log: logging.info(" Fetched Security Question")
    except (requests.exceptions.RequestException, KeyError) as e:
        raise ErpLoginError(f"Failed to fetch Security Question: {str(e)}")

    return r.text


def is_otp_required():
    """Checks whether the request is run from the campus network (OTP not required) or not."""
    return not ping3.ping("iitkgp.ac.in")


def request_otp(headers: dict[str, str], session: requests.Session, roll_number: str, password: str, log: bool):
    """Requests an OTP to be sent."""
    try:
        session.post(OTP_URL, 
                    data={
                        'typeee': 'SI', 
                        'loginid': roll_number, 
                        'pass': password
                        }, 
                    headers=headers)
    
        if log: logging.info(" Requested OTP")
    except requests.exceptions.RequestException as e:
        raise ErpLoginError(f"Failed to request OTP: {str(e)}")


def signin(headers: dict[str, str], session: requests.Session, login_details: LoginDetails, log: bool):
    """Logs into the ERP for the given session."""
    try:
        r = session.post(LOGIN_URL, data=login_details, headers=headers)
        ssoToken = re.search(r'\?ssoToken=(.+)$', r.history[1].headers['Location']).group(1)

        if ssoToken is None:
            raise ErpLoginError(f"Failed to generate ssoToken: {str(e)}")

        if log: logging.info(" Generated ssoToken")
    except (requests.exceptions.RequestException, IndexError) as e:
        raise ErpLoginError(f"ERP login failed: {str(e)}")

    if log: logging.info(" ERP login completed!")
    return ssoToken

def login(
    headers: dict[str, str],
    session: requests.Session,
    ERPCREDS: ErpCreds | None = None,
    OTP_CHECK_INTERVAL: float | None = None,
    LOGGING: bool | None = False,
    SESSION_STORAGE_FILE: str | None = None
):
    """Complete login workflow for the CLI."""
    global ROLL_NUMBER

    # Getting the location of the file importing this module
    if len(sys.argv) == 1 and sys.argv[0] == '-c': caller_file = None
    else: caller_file = inspect.getframeinfo(inspect.currentframe().f_back).filename

    # Getting the location of file containing session tokens
    token_file = f"{get_import_location(caller_file)}/{SESSION_STORAGE_FILE}" if SESSION_STORAGE_FILE else ""

    # Read session tokens from the token file if it exists
    if SESSION_STORAGE_FILE: sessionToken, ssoToken = get_tokens_from_file(token_file=token_file, log=LOGGING)
    else: sessionToken, ssoToken = None, None

    # Check if the tokens imported from the file are valid and return if yes
    if ssoToken and ssotoken_valid(ssoToken):
        if LOGGING: logging.info(" [SSOToken STATUS] >> Valid <<")
        session.cookies.set('ssoToken', ssoToken, domain='erp.iitkgp.ac.in')

        return sessionToken, ssoToken

    # The code below executes only if the ssoToken is invalid
    if LOGGING and os.path.exists(token_file): logging.info(" [SSOToken STATUS] >> Not Valid <<")

    if ERPCREDS != None:
        # Import credentials if passed to the function
        ROLL_NUMBER = ERPCREDS.ROLL_NUMBER
        PASSWORD = ERPCREDS.PASSWORD
    else:
        # If roll number and password were not provided, take CLI input
        ROLL_NUMBER = input("Enter you Roll Number: ").strip()
        PASSWORD = getpass.getpass("Enter your ERP password: ").strip()

    # Generating the sessionToken, hence initiating the login workflow
    sessionToken = get_sessiontoken(session=session, log=LOGGING)

    # Get the secret question for the roll number
    secret_question = get_secret_question(headers=headers, session=session, roll_number=ROLL_NUMBER, log=LOGGING)

    # If the security question answers were provided, use them, else take CLI input
    if ERPCREDS != None:
        secret_answer = ERPCREDS.SECURITY_QUESTIONS_ANSWERS[secret_question]
    else:
        print("Your secret question:", secret_question)
        secret_answer = getpass.getpass("Enter the answer to your secret question: ")

    # All login details/credentials (except OTP)
    login_details: LoginDetails = {
        'user_id': ROLL_NUMBER,
        'password': PASSWORD,
        'answer': secret_answer,
        'sessionToken': sessionToken,
        'requestedUrl': HOMEPAGE_URL,
    }

    # Handling OTP - whether required or not
    if is_otp_required():
        request_otp(headers=headers, session=session, roll_number=ROLL_NUMBER, password=PASSWORD, log=LOGGING)

        if OTP_CHECK_INTERVAL != None:
            try:
                if LOGGING: logging.info(" Waiting for OTP...")
                otp = getOTP(OTP_CHECK_INTERVAL)
                if LOGGING: logging.info(" Received OTP")

            except Exception as e:
                raise ErpLoginError(f"Failed to receive OTP: {str(e)}")
        else:
            otp = input("Enter the OTP sent to your registered email address: ").strip()

        login_details["email_otp"] = otp
    else:
        if LOGGING: logging.info(" OTP is not required!")

    # Sign in into the ERP using the login details
    ssoToken = signin(headers=headers, session=session, login_details=login_details, log=LOGGING)

    if SESSION_STORAGE_FILE: write_tokens_to_file(token_file=token_file, ssoToken=ssoToken, sessionToken=sessionToken, log=LOGGING)

    return sessionToken, ssoToken


def session_alive(session: requests.Session):
    """Checks if a session is alive."""
    r = session.get(WELCOMEPAGE_URL)
    return r.status_code == 404


def ssotoken_valid(ssoToken: str):
    """Checks whether an SSO token is valid."""
    response = requests.get(f"{HOMEPAGE_URL}?ssoToken={ssoToken}")
    content_type = str(response.headers).split(',')[-1].split("'")[-2]
    return content_type == 'text/html;charset=UTF-8'

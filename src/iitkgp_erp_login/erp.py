import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup as bs
import logging
import re
from iitkgp_erp_login.read_mail import getOTP
from iitkgp_erp_login.endpoints import *

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)

class ErpLoginError(Exception):
    pass

def login(headers, erp_creds, OTP_WAIT_INTERVAL, session):
    try:
        r = session.get(HOMEPAGE_URL)
        soup = bs(r.text, 'html.parser')
        sessionToken = soup.find(id='sessionToken')['value']
        logging.info(" Generated session token")
    except (requests.exceptions.RequestException, KeyError) as e:
        raise ErpLoginError(f"Failed to generate session token: {str(e)}")
    
    try:
        r = session.post(SECRET_QUESTION_URL, data={'user_id': erp_creds.ROLL_NUMBER}, headers=headers)
        secret_question = r.text
        secret_answer = erp_creds.SECURITY_QUESTIONS_ANSWERS[secret_question]
        logging.info(" Fetched Security Question")
    except (requests.exceptions.RequestException, KeyError) as e:
        raise ErpLoginError(f"Failed to fetch Security Question: {str(e)}")

    try:
        r = session.post(OTP_URL, data={'typeee': 'SI', 'loginid': erp_creds.ROLL_NUMBER}, headers=headers)
    except requests.exceptions.RequestException as e:
        raise ErpLoginError(f"Failed to request OTP: {str(e)}")
    
    login_details = {
        'user_id': erp_creds.ROLL_NUMBER,
        'password': erp_creds.PASSWORD,
        'answer': secret_answer,
        'sessionToken': sessionToken,
        'requestedUrl': HOMEPAGE_URL,
    }

    if r.status_code == 200:
        logging.info(" Requested OTP")
        try:
            logging.info(" Waiting for OTP...")
            otp = getOTP(OTP_WAIT_INTERVAL)
            logging.info(" Received OTP")
        except Exception as e:
            raise ErpLoginError(f"Failed to receive OTP: {str(e)}")
        
        login_details['email_otp'] = otp
    else:
        logging.info(" OTP is not required :yay")

    try:
        r = session.post(LOGIN_URL, data=login_details, headers=headers)
        ssoToken = re.search(r'\?ssoToken=(.+)$', r.history[1].headers['Location'])
        if ssoToken is None:
            raise ErpLoginError(f"Failed to generate ssoToken: {str(e)}")
        ssoToken = ssoToken.group(1)
        logging.info(" Generated ssoToken")
    except (requests.exceptions.RequestException, IndexError) as e:
        raise ErpLoginError(f"ERP login failed: {str(e)}")

    logging.info(" ERP login completed!")

    return sessionToken, ssoToken


def session_alive(session):
    r = session.get(WELCOMEPAGE_URL)
    return r.status_code == 404

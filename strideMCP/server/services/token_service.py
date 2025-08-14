import jwt
from typing import Dict, Any
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()



class TokenService:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

    def store_token_details(self, access_token: str, expires_at: int, refresh_token: str):
        self.access_token = access_token
        self.expires_at = datetime.fromtimestamp(expires_at)
        self.refresh_token = refresh_token

    def get_token(self):
        if(self.access_token and datetime.now() < self.expires_at - timedelta(minutes=5)):
            return self.access_token
        
        if self.refresh_token:
            # call method exchange refresh for another access token
            print("We need to exchange the refresh for another access")
        
        return self.access_token
    
token_service = TokenService(os.getenv("TOKEN_SCRET"))
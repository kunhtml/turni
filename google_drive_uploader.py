import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Scopes required for Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    """Get authenticated Google Drive service"""
    creds = None
    
    # Token file stores user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise Exception(
                    "credentials.json not found!\n"
                    "Please download OAuth 2.0 credentials from Google Cloud Console:\n"
                    "1. Go to https://console.cloud.google.com/\n"
                    "2. Enable Google Drive API\n"
                    "3. Create OAuth 2.0 credentials\n"
                    "4. Download as credentials.json"
                )
            
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_path, file_name=None):
    """
    Upload file to Google Drive and return shareable link
    
    Args:
        file_path: Path to file to upload
        file_name: Optional custom name for uploaded file
    
    Returns:
        Shareable link or None if failed
    """
    try:
        service = get_drive_service()
        
        if file_name is None:
            file_name = os.path.basename(file_path)
        
        # File metadata
        file_metadata = {
            'name': file_name,
            'mimeType': 'application/pdf'
        }
        
        # Upload file
        media = MediaFileUpload(file_path, mimetype='application/pdf', resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        
        # Make file publicly accessible
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()
        
        # Get shareable link
        download_link = f"https://drive.google.com/uc?export=download&id={file_id}"
        view_link = file.get('webViewLink')
        
        return {
            'view_link': view_link,
            'download_link': download_link,
            'file_id': file_id
        }
        
    except Exception as e:
        print(f"Error uploading to Google Drive: {e}")
        return None

def delete_file_from_drive(file_id):
    """Delete file from Google Drive"""
    try:
        service = get_drive_service()
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting from Google Drive: {e}")
        return False

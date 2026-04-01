import os
import re
import time
from datetime import datetime
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler



# Local paths where .NEF images from Camera 1 and Camera 2 arrive 
# ------------- EDIT THIS -----------------
CAMERA_1 = r"C:\Users\ahada\OneDrive\University of Washington\Z-Pinch Fusion\DHI\DHI Shots Google Drive Upload Program\Camera 1"
CAMERA_2 = r"C:\Users\ahada\OneDrive\University of Washington\Z-Pinch Fusion\DHI\DHI Shots Google Drive Upload Program\Camera 2"
# -----------------------------------------




ROOT_FOLDER_ID = "1-5rAuAEyQaexKd2j_Juh0vAuMNqPrDHd" # https://drive.google.com/drive/u/2/folders/1-5rAuAEyQaexKd2j_Juh0vAuMNqPrDHd

baseline_paths = {} # tracks baseline file for each camera for today
open_shot_folders = {} # tracks currently open shot folder ID for each camera
shots_today = {} # tracks all shot folders made today

DATE_CODE_OVERRIDE = None

# date format function
def get_current_date_code():
    '''Return yymmdd string, using user override if provided.'''
    if DATE_CODE_OVERRIDE:
        return DATE_CODE_OVERRIDE
    return datetime.now().strftime("%y%m%d")

shot_counter_by_date = {}

def get_shot_number_for_today():
    date_code = get_current_date_code()
    shot_counter_by_date.setdefault(date_code, 0)
    shot_counter_by_date[date_code] += 1
    return shot_counter_by_date[date_code]

# google drive setup

def create_drive_instance():

    gauth = GoogleAuth()
    # This will look for 'client_secrets.json' in the same folder
    # If it doesn't find it, or you haven't set up credentials, it will prompt you in the browser
    gauth.LoadCredentialsFile("credentials.json")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("credentials.json")

    drive = GoogleDrive(gauth)
    return drive

def get_or_create_folder(drive, parent_id, folder_name):
    # search for existing folder
    query = (
        f"'{parent_id}' in parents and "
        f"title = '{folder_name}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )

    file_list = drive.ListFile({
        'q': query,
        'supportsTeamDrives': True,
        'includeTeamDriveItems': True
    }).GetList()

    if file_list:
        # folder already exists
        folder_id = file_list[0]['id']
    else:
        # Create a new folder
        folder_metadata = {
            'title': folder_name,
            'parents': [{'id': parent_id}],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        new_folder = drive.CreateFile(folder_metadata)
        new_folder.Upload(param={'supportsTeamDrives': True})
        folder_id = new_folder['id']

    return folder_id

def upload_file_to_drive(drive, local_path, parent_folder_id, rename_as=None):
    file_name = rename_as if rename_as else os.path.basename(local_path)
    file_drive = drive.CreateFile({
        'title': file_name,
        'parents': [{'id': parent_folder_id}]
    })
    file_drive.SetContentFile(local_path)
    file_drive.Upload(param={'supportsTeamDrives': True})
    print(f"[UPLOAD] {file_name} uploaded to folder ID {parent_folder_id}")


# event handling

class NEFFileHandler(FileSystemEventHandler):
    def __init__(self, drive, camera_number):
        super().__init__()
        self.drive = drive
        self.camera_number = camera_number

    def on_created(self, event):
        if event.is_directory:
            return 

        file_path = event.src_path
        if file_path.lower().endswith(".nef"):
            self.process_NEF(file_path)

    def process_NEF(self, file_path):
        date_code = get_current_date_code()
        cam_key   = self.camera_number
        drive     = self.drive

        # initialise trackers -----------------------------------------------
        shots_today.setdefault(date_code, [])
        baseline_paths.setdefault(date_code, {})
        open_shot_folders.setdefault(date_code, {})

        # parent (date) folder ----------------------------------------------
        date_folder_id = get_or_create_folder(drive, ROOT_FOLDER_ID, date_code)

        # 1) BASELINE 
        if cam_key not in baseline_paths[date_code]:
            # always place baselines in yymmdd001
            baseline_shot_name      = f"{date_code}001"
            baseline_shot_folder_id = get_or_create_folder(drive, date_folder_id,
                                                           baseline_shot_name)

            # remember that yymmdd001 exists so later shots start at …002
            if not shots_today[date_code]:
                shots_today[date_code].append((baseline_shot_folder_id,
                                               baseline_shot_name))

            camera_folder_id = get_or_create_folder(
                                   drive, baseline_shot_folder_id,
                                   f"Camera_{cam_key}")

            upload_file_to_drive(drive, file_path, camera_folder_id,
                                 rename_as="baseline.NEF")

            baseline_paths[date_code][cam_key] = file_path
            print(f"[BASELINE] Camera_{cam_key} → {baseline_shot_name}")
            return 
        # 2) SCENE
        # need a new shot folder every scene
        shot_number       = len(shots_today[date_code]) + 1
        shot_name         = f"{date_code}{shot_number:03d}"
        shot_folder_id    = get_or_create_folder(drive, date_folder_id, shot_name)
        shots_today[date_code].append((shot_folder_id, shot_name))

        camera_folder_id  = get_or_create_folder(
                               drive, shot_folder_id, f"Camera_{cam_key}")

        # scene image
        upload_file_to_drive(drive, file_path, camera_folder_id)
        # matching baseline copy
        upload_file_to_drive(drive, baseline_paths[date_code][cam_key],
                             camera_folder_id, rename_as="baseline.NEF")

        print(f"[SCENE] Camera_{cam_key} → {shot_name} (+ baseline)")


def main():
    global DATE_CODE_OVERRIDE
    # prompt for date override
    user_input = input("Enter date (yymmdd): ").strip()
    if user_input:
        if not re.fullmatch(r"\d{6}", user_input):
            print("Error: date must be six digits in yymmdd format (e.g., 041202 for December 2nd, 2004).")
            return
        DATE_CODE_OVERRIDE = user_input


    drive = create_drive_instance()

    event_handler_cam1 = NEFFileHandler(drive, camera_number=1)
    event_handler_cam2 = NEFFileHandler(drive, camera_number=2)

    observer = Observer()

    # watch camera 1 directory
    observer.schedule(event_handler_cam1, path=CAMERA_1, recursive=False)
    # watch camera 2 directory
    observer.schedule(event_handler_cam2, path=CAMERA_2, recursive=False)

    observer.start()
    print(f"Monitoring for new DHI shots (date code = {get_current_date_code()}). Press Ctrl+C to exit.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()

if __name__ == "__main__":
    main()

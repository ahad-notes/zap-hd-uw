'''
replace_baselines.py

Swap every “baseline.NEF” inside a yymmdd/ yymmdd### / Camera_#/ … hierarchy with a new local baseline.NEF file you supply.

usage examples
--------------
# Replace every baseline for today in both Camera_1 and Camera_2 folders
python replace_baselines.py --file "C:\\Images\\new_baseline.NEF"

# Replace only Camera_2 baselines from December 2 2004
python replace_baselines.py --file "C:\\Images\\cam2_baseline.NEF" --date 041202 --camera 2

'''

import argparse, os, re, sys
from datetime import datetime
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from googleapiclient.http import MediaFileUpload

def overwrite_file(service, file_id, local_path):
    media = MediaFileUpload(local_path, resumable=True)
    service.files().update(
        fileId=file_id,
        media_body=media,
        supportsAllDrives=True 
    ).execute()

ROOT_FOLDER_ID = "1-5rAuAEyQaexKd2j_Juh0vAuMNqPrDHd"      # same as main script --> https://drive.google.com/drive/u/3/folders/1-5rAuAEyQaexKd2j_Juh0vAuMNqPrDHd
BASELINE_NAME  = "baseline.NEF"


def drive_login() -> GoogleDrive:
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("credentials.json")
    return GoogleDrive(gauth)

def find_single_folder(drive, parent_id, title):
    # --- 1: try the precise query ---
    q = (f"'{parent_id}' in parents and "
         f"title = '{title}' and "
         f"mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    lst = drive.ListFile({
        'q': q,
        'supportsTeamDrives': True,
        'includeTeamDriveItems': True
    }).GetList()
    if lst:
        return lst[0]

    # --- 2: fallback - scan children and strip whitespace ---
    children = drive.ListFile({
        'q': f"'{parent_id}' in parents and "
             f"mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        'supportsTeamDrives': True,
        'includeTeamDriveItems': True
    }).GetList()

    for f in children:
        if f['title'].strip() == title:
            return f   # found it even though the stored title had odd spacing
    return None


def list_child_folders(drive: GoogleDrive, parent_id: str):
    q = (f"'{parent_id}' in parents and "
         f"mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    return drive.ListFile({
        'q': q,
        'supportsTeamDrives': True,       
        'includeTeamDriveItems': True     
    }).GetList()

def replace_file_content(drive: GoogleDrive, file_id: str, local_path: str):
    f = drive.CreateFile({'id': file_id})
    f.SetContentFile(local_path)
    f.Upload()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True,
                        help="Path to the new baseline .NEF to upload")
    parser.add_argument("--date", default=datetime.now().strftime("%y%m%d"),
                        help="Target yymmdd folder (default: today)")
    parser.add_argument("--camera", choices=["1", "2", "both"], default="both",
                        help="'1', '2', or 'both' (default)")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        sys.exit(f"[ERROR] Baseline file not found: {args.file}")
    if not re.fullmatch(r"\d{6}", args.date):
        sys.exit("[ERROR] --date must be six digits yymmdd")

    drive = drive_login()

    print("\n[DEBUG] Children directly under ROOT_FOLDER_ID:")
    for f in drive.ListFile({
            'q': f"'{ROOT_FOLDER_ID}' in parents and trashed = false",
            'supportsTeamDrives': True,
            'includeTeamDriveItems': True
        }).GetList():
        mime = f['mimeType'].split('.')[-1]
        print(f"  • {f['title']}  ({mime})  id={f['id']}")
    print("------------------------------------------------\n")

    # 1. locate the yymmdd folder
    date_folder = find_single_folder(drive, ROOT_FOLDER_ID, args.date)
    if not date_folder:
        sys.exit(f"[ERROR] No date folder '{args.date}' under root.")
    print(f"[INFO] Working inside Drive folder: {args.date}")

    # 2. loop through every yymmdd### shot under that date
    shot_folders = list_child_folders(drive, date_folder['id'])
    print(f"[DEBUG] Found {len(shot_folders)} shot folder(s) under {args.date}")
    camera_targets = ["Camera_1", "Camera_2"] if args.camera == "both" else [f"Camera_{args.camera}"]

    total_replaced = 0
    for shot in shot_folders:
        # 3. inside each shot, locate desired Camera_X folders
        cam_folders = [cf for cf in list_child_folders(drive, shot['id'])
                       if cf['title'] in camera_targets]

        for cam in cam_folders:
            # 4. find baseline.NEF
            q = (f"'{cam['id']}' in parents and "
                 f"title = '{BASELINE_NAME}' and trashed = false")
            baseline_files = drive.ListFile({
                'q': q,
                'supportsTeamDrives': True,
                'includeTeamDriveItems': True
            }).GetList()

            for bf in baseline_files:
                try:
                    overwrite_file(drive.auth.service, bf['id'], args.file)
                    total_replaced += 1
                    print(f"  ↳ {shot['title']}/{cam['title']}/{BASELINE_NAME}  ✓ overwritten")
                except Exception as e:
                    print(f"    [WARN] Couldn’t overwrite baseline (id={bf['id']}): {e}")

    if total_replaced:
        print(f"\nDone! {total_replaced} baseline(s) replaced.")
    else:
        print("\nNo matching baseline.NEF files found to replace.")

if __name__ == "__main__":
    main()
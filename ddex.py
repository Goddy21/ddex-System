import os
import time
import hashlib
import random
import shutil  # Import shutil for file movement
from ftplib import FTP
import pandas as pd
import xml.etree.ElementTree as ET
from mutagen.mp3 import MP3
from PIL import Image
from lxml import etree
from dotenv import load_dotenv
import codecs
load_dotenv()
import sys
import datetime



# Force UTF-8 encoding for console output
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")
sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, errors="replace")

# Optional: Set environment variable for UTF-8 
os.environ["PYTHONUTF8"] = "1"

# Configuration
FTP_SERVER = os.getenv('FTP_SERVER')
FTP_USERNAME = os.getenv('FTP_USERNAME')
FTP_PASSWORD = os.getenv('FTP_PASSWORD')
LOCAL_DIR = os.getenv('LOCAL_DIR')
SCHEMA_FILE = os.getenv('SCHEMA_FILE')

EXCEL_FILE = os.path.join(LOCAL_DIR, 'choir.xlsx')
BATCH_NUMBER = time.strftime('%Y%m%d')
BATCH_FOLDER = os.path.join(LOCAL_DIR, f"BATCH_{BATCH_NUMBER}")
os.makedirs(BATCH_FOLDER, exist_ok=True)
LOG_FILE = os.path.join(LOCAL_DIR, f"upload_log_{BATCH_NUMBER}.txt")

def generate_grid():
    """Generate a unique GRid dynamically"""
    return f"A1{random.randint(10000000, 99999999)}V"

def read_excel(file_path):
    df = pd.read_excel(file_path, engine='openpyxl')
    df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')

    def clean_duration(value):
        """Ensure the duration is treated as MM:SS, not HH:MM:SS."""
        value = str(value)
        parts = value.split(':')
        if len(parts) == 3:  # If mistakenly treated as HH:MM:SS, extract MM:SS
            return f"{parts[1]}:{parts[2]}"  
        return value  # Otherwise, keep as is

    df.fillna({
        'primary_artists': 'UNKNOWN_ARTIST',
          'label': 'UNKNOWN_LABEL',
            'isrc_code': 'UNKNOWN_ISRC',
              'upc_code': 'UNKNOWN_UPC',
              'track_titles':'UNKNOWN_TRACK',
              'parental_advisory': 'NoAdviceAvailable',
              'duration':'PT0M0S'
              }, inplace=True)
    
    df['upc_code'] = df['upc_code'].astype(str)
    df['isrc_code'] = df['isrc_code'].astype(str)
    df['duration'] = df['duration'].fillna('0:00').astype(str)  
    return df

def validate_image_size(image_path):
    with Image.open(image_path) as img:
        if img.width < 800 or img.height < 800:
            print(f"⚠️ Image {image_path} is too small ({img.width}x{img.height}). Skipping upload.")
            return False
    return True

def format_duration(duration):
    try:
        print(f"🔍 Original duration input: {duration}")  # Debugging print

        parts = duration.split(':')
        
        if len(parts) == 3:  # Incorrect HH:MM:SS format (should be MM:SS)
            hours, minutes, seconds = map(int, parts)
            corrected_minutes = hours  # Treat "hours" as minutes
            corrected_seconds = minutes  # Treat "minutes" as seconds
            print(f"📌 Corrected values -> Minutes: {corrected_minutes}, Seconds: {corrected_seconds}")
            formatted_duration = f"PT{corrected_minutes}M{corrected_seconds}S"

        elif len(parts) == 2:  # MM:SS format (correct)
            minutes, seconds = map(int, parts)
            formatted_duration = f"PT{minutes}M{seconds}S"

        else:
            formatted_duration = 'PT0M0S'  # Default fallback
        
        print(f"✅ Final formatted duration: {formatted_duration}")  # Debugging print
        return formatted_duration

    except Exception as e:
        print(f"❌ Error formatting duration: {e}")
        return 'PT0M0S'

def move_to_batch_folder(file_path, upc_code):
    """Move a file to its corresponding UPC folder in the batch directory."""
    resource_folder = os.path.join(BATCH_FOLDER, upc_code)
    os.makedirs(resource_folder, exist_ok=True)

    if os.path.exists(file_path):
        dest_path = os.path.join(resource_folder, os.path.basename(file_path))
        shutil.copy2(file_path, dest_path)  # Copy file with metadata
        return dest_path  # Return new location
    return None

def generate_md5(file_path):
    if not os.path.exists(file_path):
        return 'MISSING_FILE'
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def create_ddex_xml(row, image_filename):
    resource_folder = os.path.join(BATCH_FOLDER, row['upc_code'])
    os.makedirs(resource_folder, exist_ok=True)
    
    root = ET.Element('ern:NewReleaseMessage', attrib={
        'xmlns:ern': 'http://ddex.net/xml/ern/383',
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': 'http://ddex.net/xml/ern/383 ERN_383.xsd',
        'MessageSchemaVersionId': 'ern/383',
        'LanguageAndScriptCode': 'en'
    })

    
    header = ET.SubElement(root, 'MessageHeader')
    ET.SubElement(header, 'MessageThreadId').text = f"{random.randint(100000, 999999)}-{random.randint(1000, 9999)}"
    ET.SubElement(header, 'MessageId').text = f"{random.randint(100000, 999999)}-{random.randint(1000, 9999)}"
    ET.SubElement(header, 'MessageCreatedDateTime').text = time.strftime('%Y-%m-%dT%H:%M:%S+00:00')
    ET.SubElement(header, 'MessageControlType').text = 'LiveMessage'
    
    ET.SubElement(root, 'UpdateIndicator').text = 'OriginalMessage'
    
    resource_list = ET.SubElement(root, 'ResourceList')
    sound_recording = ET.SubElement(resource_list, 'SoundRecording')
    ET.SubElement(sound_recording, 'SoundRecordingType').text = 'MusicalWorkSoundRecording'
    sound_id = ET.SubElement(sound_recording, 'SoundRecordingId')
    ET.SubElement(sound_id, 'ISRC').text = row['isrc_code']
    ET.SubElement(sound_recording, 'ResourceReference').text = 'A1'
    ET.SubElement(sound_recording, 'ReferenceTitle').text = row['track_titles']
    
    details = ET.SubElement(sound_recording, 'SoundRecordingDetailsByTerritory')
    md5_hash = generate_md5(os.path.join(BATCH_FOLDER, row['upc_code'], f"{row['track_titles']}.mp3"))
    ET.SubElement(details, 'HashSum', attrib={'HashAlgorithmType': 'MD5'}).text = md5_hash

    ET.SubElement(details, 'TerritoryCode').text = 'Worldwide'
    duration_text = format_duration(row.get('duration', '0:00'))  
    ET.SubElement(details, 'Duration').text = duration_text
    if os.path.exists(os.path.join(BATCH_FOLDER, row['upc_code'], f"{row['track_titles']}.mp3")):
        ET.SubElement(details, 'AudioCodecType').text = 'MP3'

    if os.path.exists(os.path.join(BATCH_FOLDER, row['upc_code'], f"{row['track_titles']}.flac")):
        ET.SubElement(details, 'AudioCodecType').text = 'FLAC'

    
    image = ET.SubElement(resource_list, 'Image')
    ET.SubElement(image, 'ImageType').text = 'FrontCoverImage'
    ET.SubElement(image, 'ResourceReference').text = 'A2'
    ET.SubElement(image, 'FileName').text = image_filename
    
    release_list = ET.SubElement(root, 'ReleaseList')
    release = ET.SubElement(release_list, 'Release')
    release_id = ET.SubElement(release, 'ReleaseId')
    ET.SubElement(release_id, 'GRid').text = generate_grid() 
    ET.SubElement(release_id, 'ICPN').text = row['upc_code']
    ET.SubElement(release, 'ReleaseReference').text = 'R0'
    ET.SubElement(release, 'ReferenceTitle').text = row['track_titles']
    
    display_artist = ET.SubElement(release, 'DisplayArtist')
    artist_name = ET.SubElement(display_artist, 'PartyName')
    ET.SubElement(artist_name, 'FullName').text = row.get('primary_artists', 'UNKNOWN_ARTIST')
    ET.SubElement(display_artist, 'ArtistRole').text = 'MainArtist'
    ET.SubElement(release, 'ParentalWarningType').text = row['parental_advisory']
    
    release_ref_list = ET.SubElement(release, 'ReleaseResourceReferenceList')
    ET.SubElement(release_ref_list, 'ReleaseResourceReference', attrib={'ReleaseResourceType': 'PrimaryResource'}).text = 'A1'
    ET.SubElement(release_ref_list, 'ReleaseResourceReference', attrib={'ReleaseResourceType': 'SecondaryResource'}).text = 'A2'
    
    
    genre = ET.SubElement(release, 'Genre')
    ET.SubElement(genre, 'GenreText').text = 'Gospel'
    ET.SubElement(genre, 'SubGenre').text = 'Christian'
    
    p_line = ET.SubElement(release, 'PLine')
    ET.SubElement(p_line, 'Year').text = '2025'
    ET.SubElement(p_line, 'PLineText').text = '℗ 2025 Mkononi Limited'

    
    c_line = ET.SubElement(release, 'CLine')
    ET.SubElement(c_line, 'Year').text = '2025'
    ET.SubElement(c_line, 'CLineText').text = f'© 2025 {row.get("primary_artists", "UNKNOWN_ARTIST")}'
    
    xml_filename = os.path.join(resource_folder, f"{row['upc_code']}_{row['track_titles'].replace(' ', '_')}_{BATCH_NUMBER}.xml")



    with open(xml_filename, 'wb') as xml_file:
        ET.ElementTree(root).write(xml_filename, encoding='utf-8', xml_declaration=True)

    # Move the XML file to ensure it is in the right place
    final_xml_path = move_xml_to_batch_folder(xml_filename, row['upc_code'])
    return final_xml_path
    return xml_filename

    def validate_ddex_xml(xml_file, schema_file=None):
        """Validate the generated XML against the DDEX ERN_383 schema."""
        try:
            # Ensure schema file path is dynamic
            if schema_file is None:
                user_home = os.path.expanduser("~")
                schema_file = os.path.join(user_home, "DDEX", "ERN_383.xsd")

            if not os.path.exists(schema_file):
                print(f"❌ Schema file not found: {schema_file}")
                return False

            schema = etree.XMLSchema(file=schema_file)
            xml_doc = etree.parse(xml_file)

            if schema.validate(xml_doc):
                print(f"✅ XML Validation Passed: {xml_file}")
                return True
            else:
                print(f"❌ XML Validation Failed: {xml_file}")
                print(schema.error_log)
                return False

        except Exception as e:
            print(f"🚨 XML validation error: {e}")
            return False
        
def move_xml_to_batch_folder(xml_path, upc_code):
    """Move the generated XML file to the correct batch folder."""
    resource_folder = os.path.join(BATCH_FOLDER, upc_code)
    os.makedirs(resource_folder, exist_ok=True)
    
    if os.path.exists(xml_path):
        dest_path = os.path.join(resource_folder, os.path.basename(xml_path))
        shutil.move(xml_path, dest_path)  # Move the XML file
        return dest_path
    return None

    
def ensure_ftp_directory(ftp, directory):
    """Ensure the directory exists on the FTP server, create if missing."""
    try:
        ftp.cwd(directory)
    except Exception:
        try:
            ftp.mkd(directory)
            ftp.cwd(directory)
        except Exception as e:
            print(f"❌ Failed to create FTP directory {directory}: {e}")


def upload_to_ftp(file_path, upc_code, max_retries=3):
    """Upload a file to the FTP server, retrying if necessary."""
    attempt = 0
    while attempt < max_retries:
        try:
            with FTP(FTP_SERVER) as ftp:
                ftp.login(FTP_USERNAME, FTP_PASSWORD)
                batch_dir = f"/BATCH_{BATCH_NUMBER}"
                upc_dir = f"{batch_dir}/{upc_code}"

                ensure_ftp_directory(ftp, batch_dir)
                ensure_ftp_directory(ftp, upc_dir)

                filename = os.path.basename(file_path)
                if filename in ftp.nlst():
                    print(f"🔄 Skipping duplicate: {file_path}")
                    return

                with open(file_path, 'rb') as file:
                    ftp.storbinary(f"STOR {filename}", file)
                print(f"✅ Uploaded: {file_path}")
                return
        except Exception as e:
            print(f"❌ FTP upload failed for {file_path} (Attempt {attempt+1}/{max_retries}): {e}")
            attempt += 1
            time.sleep(5)  # Wait before retrying

    print(f"🚨 Permanent failure: Could not upload {file_path}")

"""
def process_and_upload(project_name):
    try:
        print("🚀 Starting process...")

        # Ensure paths are dynamic
        user_home = os.path.expanduser("~")
        log_dir = os.path.join(user_home, "DDEX", "logs")
        os.makedirs(log_dir, exist_ok=True)  # Ensure log folder exists
        log_file_path = os.path.join(log_dir, "processing_done.txt")

        df = read_excel(EXCEL_FILE)
        files_to_upload = []

        # Create project folder
        project_folder = os.path.join(user_home, "DDEX", project_name)
        os.makedirs(project_folder, exist_ok=True)  # Ensure project folder exists

        for _, row in df.iterrows():
            print(f"📝 Processing track: {row['track_titles']} (ISRC: {row['isrc_code']}, UPC: {row['upc_code']})")
            upc_code = row['upc_code']

            # Create batch folder inside the project folder
            batch_folder = os.path.join(project_folder, f"BATCH_{upc_code}")
            os.makedirs(batch_folder, exist_ok=True)

            image_filename = None
            for ext, folder in [('mp3', 'AUDIO'), ('wav', 'WAV'), ('flac', 'AUDIO'), ('jpg', 'IMAGES')]:  
                search_folder = os.path.join(user_home, "DDEX", folder)
                matching_files = [f for f in os.listdir(search_folder) if row['track_titles'].lower().replace(' ', '_') in f.lower() and f.endswith(ext)]
                
                if matching_files:
                    file_path = os.path.join(search_folder, matching_files[0])
                    if ext == 'jpg' and not validate_image_size(file_path):
                        continue
                    new_path = move_to_batch_folder(file_path, batch_folder)  # Pass batch_folder instead
                    if new_path:
                        files_to_upload.append((new_path, upc_code))
                        if ext == 'jpg':
                            image_filename = os.path.basename(new_path) 
                else:
                    if ext != "flac":
                        with open(log_file_path, 'a', encoding="utf-8") as log:
                            log.write(f"⚠️ Missing file: {row['track_titles']}.{ext}\n")

            xml_file = create_ddex_xml(row, image_filename or "default_cover.jpg")
            files_to_upload.append((xml_file, upc_code))

        print("📝 Files ready for upload:")
        for file, _ in files_to_upload:
            print(file)

        confirm = "y"  # Assume 'Yes' for automatic upload
        if confirm.lower() == 'y':
            for file, upc_code in files_to_upload:
                upload_to_ftp(file, upc_code)

        # ✅ Indicate success by writing to a log file
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("✅ Processing completed successfully!\n✅ Files are ready for upload.")

        print("✅ Processing completed successfully!")
        return True

    except Exception as e:
        error_message = f"❌ Error: {str(e)}"
        print(error_message)

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(error_message)

        return False
"""




def process_and_upload(project_name, progress_callback=None):
    try:
        print("🚀 Starting process...")

        # Define paths dynamically
        user_home = os.path.expanduser("~")
        base_ddex_path = os.path.join(user_home, "DDEX")
        log_dir = os.path.join(base_ddex_path, "logs")
        os.makedirs(log_dir, exist_ok=True)  # Ensure log folder exists
        log_file_path = os.path.join(log_dir, "processing_done.txt")

        # Read track data from Excel
        df = read_excel(EXCEL_FILE)
        files_to_upload = []

        # Create the main project folder
        project_folder = os.path.join(base_ddex_path, project_name)
        os.makedirs(project_folder, exist_ok=True)

        # Create a batch folder with the current date
        today = datetime.datetime.now().strftime("%Y%m%d")
        batch_folder = os.path.join(project_folder, f"BATCH_{today}")
        os.makedirs(batch_folder, exist_ok=True)

        # Process each track
        for _, row in df.iterrows():
            track_title = row['track_titles'].lower().replace(" ", "_")
            upc_code = row['upc_code']
            print(f"📝 Processing track: {row['track_titles']} (ISRC: {row['isrc_code']}, UPC: {upc_code})")

            # Create a UPC folder inside the batch
            upc_folder = os.path.join(batch_folder, upc_code)
            os.makedirs(upc_folder, exist_ok=True)

            # Track image file
            image_filename = None

            # Process audio/image files
            file_types = {
                'mp3': 'AUDIO',
                'wav': 'WAV',
                'flac': 'AUDIO',
                'jpg': 'IMAGES'
            }

            for ext, folder in file_types.items():
                search_folder = os.path.join(base_ddex_path, folder)

                if os.path.exists(search_folder):
                    matching_files = [f for f in os.listdir(search_folder) 
                                      if track_title in f.lower() and f.endswith(ext)]

                    print(f"🔍 Searching {ext.upper()} in {search_folder} → Found: {matching_files}")

                    if matching_files:
                        file_path = os.path.join(search_folder, matching_files[0])

                        # Skip invalid images
                        if ext == 'jpg' and not validate_image_size(file_path):
                            print(f"⚠️ Skipping invalid image: {file_path}")
                            continue  

                        # Move file to UPC folder
                        new_path = move_to_batch_folder(file_path, upc_folder)  
                        if new_path:
                            print(f"✅ Moved {file_path} to {new_path}")
                            files_to_upload.append((new_path, upc_code))
                            if ext == 'jpg':
                                image_filename = os.path.basename(new_path)
                    else:
                        print(f"❌ No matching {ext.upper()} file found for {track_title}")
                        with open(log_file_path, 'a', encoding="utf-8") as log:
                            log.write(f"⚠️ Missing file: {track_title}.{ext}\n")

            # Generate and move DDEX XML
            xml_file = create_ddex_xml(row, image_filename or "default_cover.jpg")
            xml_dest = os.path.join(upc_folder, os.path.basename(xml_file))
            shutil.move(xml_file, xml_dest)
            files_to_upload.append((xml_dest, upc_code))

        # Print all files ready for upload
        print("📝 Files ready for upload:")
        for file, _ in files_to_upload:
            print(file)

        # Auto-confirm and upload
        for file, upc_code in files_to_upload:
            upload_to_ftp(file, upc_code)

        # ✅ Log success
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("✅ Processing completed successfully!\n✅ Files are ready for upload.")

        print("✅ Processing completed successfully!")
        return True

    except Exception as e:
        error_message = f"❌ Error: {str(e)}"
        print(error_message)

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(error_message)

        return False



    
if __name__ == '__main__':
    print("🚀 Starting process...")
    process_and_upload()
    print("✅ All done!")

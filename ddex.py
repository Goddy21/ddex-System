import os
import time
import hashlib
import random
import shutil
from ftplib import FTP
import pandas as pd
from lxml import etree
from PIL import Image
import urllib.request
from dotenv import load_dotenv
import datetime

load_dotenv()


# Configuration
FTP_SERVER = os.getenv('FTP_SERVER')
FTP_USERNAME = os.getenv('FTP_USERNAME')
FTP_PASSWORD = os.getenv('FTP_PASSWORD')
LOCAL_DIR = os.getenv('LOCAL_DIR')
#SCHEMA_FILE = os.getenv('SCHEMA_FILE')
SCHEMA_FILE = "http://ddex.net/xml/ern/383/release-notification.xsd"



EXCEL_FILE = os.path.join(LOCAL_DIR, 'choir.xlsx')
BATCH_NUMBER = time.strftime('%Y%m%d')
BATCH_FOLDER = os.path.join(LOCAL_DIR, f"BATCH_{BATCH_NUMBER}")
os.makedirs(BATCH_FOLDER, exist_ok=True)
LOG_FILE = os.path.join(LOCAL_DIR, f"upload_log_{BATCH_NUMBER}.txt")


# DDEX Namespace
DDEX_ERN_NAMESPACE = 'http://ddex.net/xml/ern/383'
DDEX_AVS_NAMESPACE = "http://ddex.net/xml/avs/avs"
XSI_NAMESPACE = 'http://www.w3.org/2001/XMLSchema-instance'


def generate_grid():
    return f"A1{random.randint(10000000, 99999999)}V"


def read_excel(file_path):
    df = pd.read_excel(file_path, engine='openpyxl')
    df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')

    def clean_duration(value):
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
        'track_titles': 'UNKNOWN_TRACK',
        'parental_advisory': 'NoAdviceAvailable',
        'duration': 'PT0M0S'
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

    ernm = "{http://ddex.net/xml/ern/383}"
    avs = "{http://ddex.net/xml/avs/avs}"
    xsi = "{http://www.w3.org/2001/XMLSchema-instance}"

    NewReleaseMessage = etree.Element(f"{ernm}NewReleaseMessage",
                                        attrib={
                                            "LanguageAndScriptCode": "en",
                                            "ReleaseProfileVersionId": "ClassicalAudioAlbum",
                                            f"{xsi}schemaLocation": "http://ddex.net/xml/ern/383 http://ddex.net/xml/ern/383/release-notification.xsd",
                                            "MessageSchemaVersionId": "ern/383"
                                        },
                                        nsmap={
                                            "ernm": DDEX_ERN_NAMESPACE,
                                            "avs": DDEX_AVS_NAMESPACE,
                                            "xsi": XSI_NAMESPACE
                                        })

    MessageHeader = etree.SubElement(NewReleaseMessage, "MessageHeader")
    etree.SubElement(MessageHeader, "MessageThreadId").text = f"{random.randint(100000, 999999)}-{random.randint(1000, 9999)}"
    etree.SubElement(MessageHeader, "MessageId").text = f"{random.randint(100000, 999999)}-{random.randint(1000, 9999)}"

    MessageSender = etree.SubElement(MessageHeader, "MessageSender")
    etree.SubElement(MessageSender, "PartyId").text = "PA-DPIDA-2025040901-M"
    PartyName = etree.SubElement(MessageSender, "PartyName")
    etree.SubElement(PartyName, "FullName").text = "Mkononi Limited"

    MessageRecipient = etree.SubElement(MessageHeader, "MessageRecipient")
    etree.SubElement(MessageRecipient, "PartyId").text = "PA-DPIDA-2025021301-D"
    PartyName = etree.SubElement(MessageRecipient, "PartyName")
    etree.SubElement(PartyName, "FullName").text = "Boomplay"

    etree.SubElement(MessageHeader, "MessageCreatedDateTime").text = time.strftime('%Y-%m-%dT%H:%M:%SZ')
    etree.SubElement(MessageHeader, "MessageControlType").text = "LiveMessage"

    ResourceList = etree.SubElement(NewReleaseMessage, "ResourceList")
    SoundRecording = etree.SubElement(ResourceList, "SoundRecording")
    etree.SubElement(SoundRecording, "SoundRecordingType").text = "MusicalWorkSoundRecording"
    SoundRecordingId = etree.SubElement(SoundRecording, "SoundRecordingId")
    etree.SubElement(SoundRecordingId, "ISRC").text = str(row['isrc_code'])

    resource_reference = f"A{random.randint(1000, 9999)}"
    etree.SubElement(SoundRecording, "ResourceReference").text = resource_reference

    ReferenceTitle = etree.SubElement(SoundRecording, "ReferenceTitle")
    etree.SubElement(ReferenceTitle, "TitleText").text = str(row['track_titles'])
    etree.SubElement(SoundRecording, "Duration").text = format_duration(row['duration'])

    # RightsAgreementId - Adding a dummy one for now
    RightsAgreementId = etree.SubElement(SoundRecording, "RightsAgreementId")
    etree.SubElement(RightsAgreementId, "ProprietaryId", attrib={"Namespace": "Boomplay"}).text = f"{random.randint(100000, 999999)}"

    # Adding SoundRecordingDetailsByTerritory
    SoundRecordingDetailsByTerritory = etree.SubElement(SoundRecording, "SoundRecordingDetailsByTerritory")
    etree.SubElement(SoundRecordingDetailsByTerritory, "TerritoryCode").text = "Worldwide"
    Title = etree.SubElement(SoundRecordingDetailsByTerritory, "Title")
    etree.SubElement(Title, "TitleText").text = str(row['track_titles'])
    DisplayArtist = etree.SubElement(SoundRecordingDetailsByTerritory, "DisplayArtist")
    PartyName = etree.SubElement(DisplayArtist, "PartyName")
    etree.SubElement(PartyName, "FullName").text = str(row['primary_artists'])
    etree.SubElement(DisplayArtist, "ArtistRole").text = "MainArtist"

    # Adding Composer
    if 'composer' in row:
        for composer in row.get('composer', '').split(';'):
            if composer:
                Contributor = etree.SubElement(SoundRecordingDetailsByTerritory, "Contributor")
                PartyName = etree.SubElement(Contributor, "PartyName")
                etree.SubElement(PartyName, "FullName").text = composer.strip()
                etree.SubElement(Contributor, "ContributorRole").text = "Composer"

    # Adding Producer
    if 'producer' in row:
        for producer in row.get('producer', '').split(';'):
            if producer:
                Contributor = etree.SubElement(SoundRecordingDetailsByTerritory, "Contributor")
                PartyName = etree.SubElement(Contributor, "PartyName")
                etree.SubElement(PartyName, "FullName").text = producer.strip()
                etree.SubElement(Contributor, "ContributorRole").text = "Producer"

    PLine = etree.SubElement(SoundRecordingDetailsByTerritory, "PLine")
    etree.SubElement(PLine, "Year").text = "2024"
    etree.SubElement(PLine, "PLineCompany").text = "Mkononi Limited"
    etree.SubElement(PLine, "PLineText").text = "℗ 2024 Mkononi Limited"
    etree.SubElement(SoundRecordingDetailsByTerritory, "ParentalWarningType").text = "NotExplicit"

    ReleaseList = etree.SubElement(NewReleaseMessage, "ReleaseList")
    Release = etree.SubElement(ReleaseList, "Release", attrib={"IsMainRelease": "true"})
    ReleaseId = etree.SubElement(Release, "ReleaseId")
    etree.SubElement(ReleaseId, "ICPN").text = str(row['upc_code'])
    etree.SubElement(Release, "ReleaseReference").text = "ReleaseRef1"

    ReferenceTitle = etree.SubElement(Release, "ReferenceTitle")
    etree.SubElement(ReferenceTitle, "TitleText").text = str(row['track_titles'])
    ReleaseResourceReferenceList = etree.SubElement(Release, "ReleaseResourceReferenceList")
    etree.SubElement(ReleaseResourceReferenceList, "ReleaseResourceReference").text = resource_reference

    ReleaseDetailsByTerritory = etree.SubElement(Release, "ReleaseDetailsByTerritory")
    etree.SubElement(ReleaseDetailsByTerritory, "TerritoryCode").text = "Worldwide"
    etree.SubElement(ReleaseDetailsByTerritory, "DisplayArtistName").text = str(row['primary_artists'])
    etree.SubElement(ReleaseDetailsByTerritory, "LabelName").text = "Mkononi Limited"
    Title = etree.SubElement(ReleaseDetailsByTerritory, "Title")
    etree.SubElement(Title, "TitleText").text = str(row['track_titles'])
    DisplayArtist = etree.SubElement(ReleaseDetailsByTerritory, "DisplayArtist")
    PartyName = etree.SubElement(DisplayArtist, "PartyName")
    etree.SubElement(PartyName, "FullName").text = str(row['primary_artists'])
    etree.SubElement(DisplayArtist, "ArtistRole").text = "MainArtist"
    etree.SubElement(ReleaseDetailsByTerritory, "IsMultiArtistCompilation").text = "false"
    etree.SubElement(ReleaseDetailsByTerritory, "ReleaseType").text = "Album"
    etree.SubElement(ReleaseDetailsByTerritory, "ParentalWarningType").text = str(row.get('parental_advisory', 'NotExplicit'))
    Genre = etree.SubElement(ReleaseDetailsByTerritory, "Genre")
    etree.SubElement(Genre, "GenreText").text = str(row.get('genre', 'Gospel'))
    if 'genre_code' in row:
        etree.SubElement(Genre, "GenreCode").text = str(row['genre_code'])

    etree.SubElement(ReleaseDetailsByTerritory, "ReleaseDate").text = time.strftime('%Y-%m-%d')

    etree.SubElement(Release, "Duration").text = format_duration(row['duration'])
    PLine = etree.SubElement(Release, "PLine")
    etree.SubElement(PLine, "Year").text = str(row.get('published_year', '2024'))
    etree.SubElement(PLine, "PLineCompany").text = "Mkononi Limited"
    etree.SubElement(PLine, "PLineText").text = f"℗ {row.get('published_year', '2024')} Mkononi Limited"
    CLine = etree.SubElement(Release, "CLine")
    etree.SubElement(CLine, "Year").text = str(row.get('copyright_year', '2024'))
    etree.SubElement(CLine, "CLineCompany").text = "Mkononi Limited"
    etree.SubElement(CLine, "CLineText").text = f"© {row.get('copyright_year', '2024')} Mkononi Limited"
    etree.SubElement(Release, "GlobalOriginalReleaseDate").text = time.strftime('%Y-%m-%d')

    tree = etree.ElementTree(NewReleaseMessage)
    xml_filename = os.path.join(resource_folder, f"{row['upc_code']}_{row['track_titles'].replace(' ', '_')}_{time.strftime('%Y%m%d')}.xml")
    tree.write(xml_filename, encoding='utf-8', xml_declaration=True, pretty_print=True)

    return xml_filename
 

def validate_ddex_xml(xml_file, schema_file):
    try:
        # Determine if schema_file is a URL or a local path
        if schema_file.startswith('http://') or schema_file.startswith('https://'):
            try:
                # Open the URL and read the schema
                with urllib.request.urlopen(schema_file) as f:
                    schema_doc = etree.parse(f)
            except Exception as e:
                print(f"❌ Error opening URL: {schema_file}")
                print(e)
                return False
        else:
            # If it's a local file, parse it directly
            schema_file = os.path.abspath(schema_file)
            try:
                schema_doc = etree.parse(schema_file)
            except etree.XMLSyntaxError as e:
                print(f"❌ Invalid XML schema file: {schema_file}")
                print(e)
                return False
            except Exception as e:
                print(f"❌ Error creating schema: {e}")
                print(e)
                return False

        schema = etree.XMLSchema(schema_doc)
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
    


def ensure_ftp_directory(ftp, directory):
    try:
        ftp.cwd(directory)
    except Exception:
        try:
            ftp.mkd(directory)
            ftp.cwd(directory)
        except Exception as e:
            print(f"❌ Failed to create FTP directory {directory}: {e}")



def upload_to_ftp(file_path, upc_code, max_retries=3, progress_callback=None):
    def log_msg(message):
        print(message)
        if progress_callback:
            progress_callback(message)

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
                    log_msg(f"🔄 Skipping duplicate: {file_path}")
                    return

                with open(file_path, 'rb') as file:
                    ftp.storbinary(f"STOR {filename}", file)
                log_msg(f"✅ Uploaded: {file_path}")
                return
        except Exception as e:
            print(f"❌ FTP upload failed for {file_path} (Attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            time.sleep(5)  # Wait before retrying

    log_msg(f"🚨 Permanent failure: Could not upload {file_path}")

"""

def process_and_upload():
    df = read_excel(EXCEL_FILE)
    files_to_upload = []

    for _, row in df.iterrows():
        print(f"📝 Processing track: {row['track_titles']} (ISRC: {row['isrc_code']}, UPC: {row['upc_code']})")
        upc_code = row['upc_code']
        resource_folder = os.path.join(BATCH_FOLDER, upc_code)
        os.makedirs(resource_folder, exist_ok=True)

        image_filename = None

        for ext, folder in [('mp3', 'AUDIO'), ('wav', 'WAV'), ('flac', 'AUDIO'), ('jpg', 'IMAGES')]:
            search_folder = os.path.join(LOCAL_DIR, folder)
            matching_files = [f for f in os.listdir(search_folder) if
                              row['track_titles'].lower().replace(' ', '_') in f.lower() and f.endswith(ext)]

            if matching_files:
                file_path = os.path.join(search_folder, matching_files[0])
                if ext == 'jpg' and not validate_image_size(file_path):
                    continue
                new_path = move_to_batch_folder(file_path, upc_code)
                if new_path:
                    files_to_upload.append((new_path, upc_code))
                    if ext == 'jpg':
                        image_filename = os.path.basename(new_path)
            else:
                with open(LOG_FILE, 'a') as log:
                    log.write(f"Missing file: {row['track_titles']}.{ext}\n")

        xml_file = create_ddex_xml(row, image_filename)

        if validate_ddex_xml(xml_file, SCHEMA_FILE):
            files_to_upload.append((xml_file, upc_code))
        else:
            with open(LOG_FILE, 'a') as log:
                log.write(f"Invalid XML: {os.path.basename(xml_file)}\n")

    print("📝 Files ready for upload:")
    for file, _ in files_to_upload:
        print(file)

    confirm = input("❓ Proceed with upload? (y/n): ")
    if confirm.lower() == 'y':
        for file, upc_code in files_to_upload:
            upload_to_ftp(file, upc_code)
"""



def process_and_upload(project_name, progress_callback=None):
    def log_msg(message):
        print(message)
        if progress_callback:
            progress_callback(message)

    try:
        log_msg("🚀 Starting process...")

        # Define paths dynamically
        user_home = os.path.expanduser("~")
        base_ddex_path = os.path.join(user_home, "DDEX")
        log_dir = os.path.join(base_ddex_path, "logs")
        os.makedirs(log_dir, exist_ok=True)  # Ensure log folder exists
        log_file_path = os.path.join(log_dir, "processing_done.txt")
        if not os.path.exists(log_file_path):
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write("📁 Log initialized.\n")

        # Read track data from Excel
        df = read_excel(EXCEL_FILE)
        files_to_upload = []
        processed_tracks = []

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
            log_msg(f"📝 Processing track: {row['track_titles']} (ISRC: {row['isrc_code']}, UPC: {upc_code})")

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

                    log_msg(f"🔍 Searching {ext.upper()} in {search_folder} → Found: {matching_files}")

                    if matching_files:
                        file_path = os.path.join(search_folder, matching_files[0])

                        # Skip invalid images
                        if ext == 'jpg' and not validate_image_size(file_path):
                            log_msg(f"⚠️ Skipping invalid image: {file_path}")
                            continue  

                        # Move file to UPC folder
                        new_path = move_to_batch_folder(file_path, upc_folder)  
                        if new_path:
                            log_msg(f"✅ Moved {file_path} to {new_path}")
                            files_to_upload.append((new_path, upc_code))
                            if ext == 'jpg':
                                image_filename = os.path.basename(new_path)
                    else:
                        log_msg(f"❌ No matching {ext.upper()} file found for {track_title}")
                        with open(log_file_path, 'a', encoding="utf-8") as log_file:
                            log_file.write(f"⚠️ Missing file: {track_title}.{ext}\n")

            # Generate and move DDEX XML
            xml_file = create_ddex_xml(row, image_filename or "default_cover.jpg")
            xml_dest = os.path.join(upc_folder, os.path.basename(xml_file))
            shutil.move(xml_file, xml_dest)
            files_to_upload.append((xml_dest, upc_code))
            processed_tracks.append({
                "title": row['track_titles'],
                "upc": row['upc_code']
            })

        # Print all files ready for upload
        log_msg("📝 Files ready for upload:")
        for file, _ in files_to_upload:
            log_msg(file)

        # Auto-confirm and upload
        for file, upc_code in files_to_upload:
            upload_to_ftp(file, upc_code)

        # ✅ Log success
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("✅ Processing completed successfully!\n✅ Files are ready for upload.")

        log_msg("✅ Processing completed successfully!")
        return True, processed_tracks

    except Exception as e:
        error_message = f"❌ Error: {str(e)}"
        log_msg(error_message)

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(error_message)

        return False, []

if __name__ == '__main__':
    print("🚀 Starting process...")
    process_and_upload()
    print("✅ All done!")
    

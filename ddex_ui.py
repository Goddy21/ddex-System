from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.filechooser import FileChooserListView 
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
import threading
import subprocess
import os
import datetime
from kivy.graphics import Color, Line, RoundedRectangle
import shutil
import time

# Import processing function from ddex.py
from ddex import process_and_upload  # Ensure this function supports project names
CONFIG_FILE = "config.txt"  # Store the last used directory here
class DDEXUploaderApp(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=20, spacing=15, **kwargs)

        def load_last_directory():
            """Load the last used directory from a file, or return default path."""
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    directory = f.read().strip()
                    if os.path.exists(directory):  # Ensure it still exists
                        return directory
            return os.path.expanduser("~")  # Default to user home directory


        # Define Colors (Dark Theme)
        self.primary_color = get_color_from_hex("#003153") 
        self.secondary_color = get_color_from_hex("#0A1F44")  
        self.bg_color = get_color_from_hex("#2980B9") 
        self.text_color = get_color_from_hex("#ECF0F1")  

                # Background Styling
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=self.update_rect, size=self.update_rect)

        # Title Label
        self.add_widget(Label(
            text="📂 [b]DDEX File Uploader[/b]",
            markup=True,
            font_size=36,
            bold=True,
            color=self.text_color,
            size_hint_y=0.1,
            halign="center",
            valign="middle",
            font_name="C:/Windows/Fonts/seguiemj.ttf" 
        ))

        # Project Name Input
        self.project_name_input = TextInput(
            hint_text="Enter Project Name",
            multiline=False,
            size_hint_y=None,
            height=35,
            font_size=18,
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1)
        )
        self.add_widget(self.project_name_input)

        # File Chooser
        self.file_chooser = FileChooserIconView(
            path=load_last_directory(),
            filters=["*.xlsx", "*.csv", "*.xml", "*.mp3", "*.wav", "*.jpg", "*.png"],
            show_hidden=False,
            size_hint_y=0.35
        )
        self.add_widget(self.file_chooser)

        # Log Display
        self.log_scroll = ScrollView(size_hint=(1, 0.25), do_scroll_x=False)

        self.log_output = TextInput(
            multiline=True,
            readonly=True,
            size_hint_y=None,  
            height=150,
            background_color=(0, 0, 0, 0.7),
            foreground_color=(1, 1, 1, 1),
            font_size=14,
            padding=[10, 10],
            font_name="C:/Windows/Fonts/seguiemj.ttf" 
        )

        # Add border dynamically
        with self.log_output.canvas.before:
            Color(1, 1, 1, 1) 
            #self.border = Line(width=2)  
            self.border = Line(rectangle=(0, 0, self.log_output.width, self.log_output.height), width=2)

        self.log_output.bind(size=self.on_size)

        def update_border(instance, value):
            """Update the border rectangle dynamically when size or position changes."""
            self.border.rectangle = (instance.x, instance.y, instance.width, instance.height)

        # Bind size and position updates
        self.log_output.bind(pos=update_border, size=update_border)
        self.log_output.bind(minimum_height=self.log_output.setter('height'))  # Ensure proper height handling

        self.log_scroll.add_widget(self.log_output)
        self.add_widget(self.log_scroll)


        # Buttons Layout
        button_layout = BoxLayout(size_hint_y=0.1, spacing=15)

        self.process_button = Button(
            text="⚙️ Process and Upload to FTP server",
            font_name="C:/Windows/Fonts/seguiemj.ttf",
            background_color=self.primary_color,
            size_hint_x=0.5,
            font_size=18,
            bold=True,
            background_normal='',
            background_down='',
            color=self.text_color
        )
        self.process_button.bind(on_press=self.start_processing)
        button_layout.add_widget(self.process_button)

        self.add_widget(button_layout)

        # Progress Bar
        self.progress_bar = ProgressBar(max=100, size_hint_y=0.05)
        self.add_widget(self.progress_bar)

    def on_size(self, *args):
        self.border.rectangle = (0, 0, self.log_output.width, self.log_output.height)
    def save_last_directory(self, directory):
        """Save the last used directory to a file."""
        with open(CONFIG_FILE, "w") as f:
            f.write(directory)
    def start_processing(self, instance):
        project_name = self.project_name_input.text.strip()
        selected_file = self.file_chooser.selection

        if not project_name:
            self.update_log("\n❌ Project name is required!")
            return

        if not selected_file:
            self.update_log("\n❌ No file selected!")
            return
        
        selected_directory = os.path.dirname(selected_file[0])
        self.save_last_directory(selected_directory)

        self.update_log(f"\n⏳ Processing started for project: {project_name}...")
        threading.Thread(target=self.run_processing, args=(selected_file[0], project_name), daemon=True).start()

    def run_processing(self, file_path, project_name):
        """Run processing script with proper folder structure."""
        try:
            today = datetime.datetime.now().strftime('%Y%m%d')
            home_dir = os.path.expanduser("~")  
            
            batch_folder = os.path.join(home_dir, "DDEX", project_name, f"BATCH_{today}")
            os.makedirs(batch_folder, exist_ok=True)

            def process_task():
                Clock.schedule_once(lambda dt: self.update_log("🚀 Starting processing...\n"), 0)

                success, processed_tracks = process_and_upload(project_name) 
                time.sleep(1) 
                
                if success:
                    Clock.schedule_once(lambda dt: self.update_log("\n✅ Processing completed successfully!"), 0)

                    for track in processed_tracks:
                        upc = track["upc"]  # Extract UPC
                        track_name = track["title"].replace(" ", "_").lower()  # Normalize filename

                        upc_folder = os.path.join(batch_folder, upc)
                        os.makedirs(upc_folder, exist_ok=True)  # Ensure UPC folder exists

                        # Move related files
                        for ext in [".mp3", ".wav", ".jpg", ".xml"]:
                            source_file = os.path.join(os.path.dirname(file_path), f"{track_name}{ext}")
                            if os.path.exists(source_file):
                                shutil.move(source_file, os.path.join(upc_folder, os.path.basename(source_file)))
                    
                    Clock.schedule_once(lambda dt: self.show_results(batch_folder), 0)

                else:
                    Clock.schedule_once(lambda dt: self.update_log("\n❌ Processing failed!"), 0)

                Clock.schedule_once(lambda dt: self.update_log("\n✅ Upload completed!"), 0)
                self.animate_progress(100)

            threading.Thread(target=process_task, daemon=True).start()

        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_log(f"\n❌ Error: {str(e)}"), 0)

    def show_results(self, project_folder):
        """Display results of processing and refresh folder explorer."""
        from datetime import datetime
        from kivy.clock import Clock

        # Use a dynamic directory based on user's home folder
        user_home = os.path.expanduser("~")
        today = datetime.today().strftime("%Y%m%d")

        # Load project name dynamically (assuming you store it somewhere)
        project_name = self.project_name_input.text.strip() or "DefaultProject"


        # Construct batch folder path dynamically
        batch_folder = os.path.join(user_home, "DDEX", f"BATCH_{today}")

        # Ensure the batch folder exists
        if hasattr(self, "file_chooser") and os.path.exists(batch_folder):
            self.file_chooser.path = batch_folder  

            Clock.schedule_once(lambda dt: self.update_log(f"\n📁 Folder Explorer Updated: {batch_folder}"), 0)

    def update_log(self, message):
        """Append message to log with scrolling."""
        print(f"Updating log: {message}")
        Clock.schedule_once(lambda dt: self._append_log(message), 0)

    def _append_log(self, message):
        """Update UI log output safely."""
        print(f"Appending message: {message}")
        if hasattr(self, 'log_output') and self.log_output:
            self.log_output.text += f"\n{message}"
            self.log_scroll.scroll_to(self.log_output, padding=10)

    def animate_progress(self, target_value):
        """Smoothly animate progress bar."""
        def update_progress(dt):
            if self.progress_bar.value < target_value:
                self.progress_bar.value += 2
                Clock.schedule_once(update_progress, 0.02)

        Clock.schedule_once(update_progress, 0.02)

    def update_rect(self, instance, value):
            self.rect.pos = instance.pos
            self.rect.size = instance.size
class DDEXApp(App):
    def build(self):
        self.icon = r"C:\Goddie\DDEX user interface\icon.png"
        return DDEXUploaderApp()

if __name__ == "__main__":
    DDEXApp().run()

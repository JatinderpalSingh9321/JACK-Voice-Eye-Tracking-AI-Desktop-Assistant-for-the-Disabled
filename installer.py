import os
import sys
import zipfile
import urllib.request
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import win32com.client

# Download URLs for Kokoro models
KOKORO_ONNX_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

class InstallerWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NavTools Setup")
        self.geometry("500x380")
        self.resizable(False, False)
        
        # Configure styles
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Helvetica", 16, "bold"))
        style.configure("Header.TFrame", background="#ffffff")
        
        self.pages = []
        self.current_page = 0
        
        # Variables
        default_dir = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "NavTools")
        self.install_dir = tk.StringVar(value=default_dir)
        self.dl_kokoro = tk.BooleanVar(value=False)
        self.create_desktop_shortcut = tk.BooleanVar(value=True)
        self.create_start_shortcut = tk.BooleanVar(value=True)
        
        # UI Container
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        
        # Bottom navigation
        self.nav_frame = ttk.Frame(self)
        self.nav_frame.pack(fill="x", side="bottom", pady=10, padx=10)
        
        self.btn_back = ttk.Button(self.nav_frame, text="< Back", command=self.go_back, state="disabled")
        self.btn_back.pack(side="left", padx=5)
        
        self.btn_next = ttk.Button(self.nav_frame, text="Next >", command=self.go_next)
        self.btn_next.pack(side="right", padx=5)
        
        self.btn_cancel = ttk.Button(self.nav_frame, text="Cancel", command=self.destroy)
        self.btn_cancel.pack(side="right", padx=10)
        
        # Initialize pages
        self.setup_welcome_page()
        self.setup_options_page()
        self.setup_progress_page()
        self.setup_finish_page()
        
        self.show_page(0)

    def setup_welcome_page(self):
        page = ttk.Frame(self.container)
        
        header = ttk.Frame(page, style="Header.TFrame")
        header.pack(fill="x", ipady=10)
        ttk.Label(header, text="Welcome to NavTools Setup", style="Title.TLabel", background="#ffffff").pack(padx=20, pady=10, anchor="w")
        
        content = ttk.Frame(page)
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(content, text="This wizard will guide you through the installation of NavTools,\n"
                                "the assistive gaze tracking and voice control suite.", justify="left").pack(anchor="w", pady=10)
        ttk.Label(content, text="Click Next to continue.", justify="left").pack(anchor="w", pady=20)
        
        self.pages.append(page)

    def setup_options_page(self):
        page = ttk.Frame(self.container)
        
        header = ttk.Frame(page, style="Header.TFrame")
        header.pack(fill="x", ipady=10)
        ttk.Label(header, text="Installation Options", style="Title.TLabel", background="#ffffff").pack(padx=20, pady=10, anchor="w")
        
        content = ttk.Frame(page)
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(content, text="Destination Folder:").pack(anchor="w")
        
        dir_frame = ttk.Frame(content)
        dir_frame.pack(fill="x", pady=5)
        ttk.Entry(dir_frame, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse...", command=self.browse_dir).pack(side="right", padx=(5, 0))
        
        ttk.Label(content, text="Shortcuts:").pack(anchor="w", pady=(15, 5))
        ttk.Checkbutton(content, text="Create Desktop Shortcut", variable=self.create_desktop_shortcut).pack(anchor="w")
        ttk.Checkbutton(content, text="Create Start Menu Shortcut", variable=self.create_start_shortcut).pack(anchor="w")
        
        ttk.Label(content, text="Voice Models:").pack(anchor="w", pady=(15, 5))
        ttk.Checkbutton(content, text="Download high-quality Kokoro ONNX voice pack (~340 MB)\n"
                                      "If unchecked, Jim will use the standard Windows voice.", variable=self.dl_kokoro).pack(anchor="w")
        
        self.pages.append(page)

    def browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.install_dir.get(), title="Select Installation Folder")
        if d:
            self.install_dir.set(os.path.join(d, "NavTools"))

    def setup_progress_page(self):
        page = ttk.Frame(self.container)
        
        header = ttk.Frame(page, style="Header.TFrame")
        header.pack(fill="x", ipady=10)
        ttk.Label(header, text="Installing...", style="Title.TLabel", background="#ffffff").pack(padx=20, pady=10, anchor="w")
        
        content = ttk.Frame(page)
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.lbl_status = ttk.Label(content, text="Preparing to install...")
        self.lbl_status.pack(anchor="w", pady=(30, 5))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(content, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x")
        
        self.lbl_detail = ttk.Label(content, text="", foreground="gray")
        self.lbl_detail.pack(anchor="w", pady=5)
        
        self.pages.append(page)

    def setup_finish_page(self):
        page = ttk.Frame(self.container)
        
        header = ttk.Frame(page, style="Header.TFrame")
        header.pack(fill="x", ipady=10)
        ttk.Label(header, text="Installation Complete", style="Title.TLabel", background="#ffffff").pack(padx=20, pady=10, anchor="w")
        
        content = ttk.Frame(page)
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(content, text="NavTools has been successfully installed on your computer.").pack(anchor="w", pady=10)
        
        self.launch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(content, text="Launch NavTools now", variable=self.launch_var).pack(anchor="w", pady=20)
        
        self.pages.append(page)

    def show_page(self, index):
        for p in self.pages:
            p.pack_forget()
        self.pages[index].pack(fill="both", expand=True)
        self.current_page = index
        
        # Update navigation buttons
        self.btn_back.config(state="normal" if index > 0 and index != 2 else "disabled")
        
        if index == len(self.pages) - 1:
            self.btn_next.config(text="Finish")
            self.btn_cancel.config(state="disabled")
        elif index == 2:
            self.btn_next.config(state="disabled")
            self.btn_cancel.config(state="disabled")
            self.start_installation()
        else:
            self.btn_next.config(text="Next >", state="normal")

    def go_next(self):
        if self.current_page == len(self.pages) - 1:
            self.finish()
        else:
            self.show_page(self.current_page + 1)

    def go_back(self):
        self.show_page(self.current_page - 1)

    def update_status(self, main_text, detail_text="", progress=-1):
        self.lbl_status.config(text=main_text)
        self.lbl_detail.config(text=detail_text)
        if progress >= 0:
            self.progress_var.set(progress)
        self.update_idletasks()

    def start_installation(self):
        threading.Thread(target=self.install_process, daemon=True).start()

    def install_process(self):
        try:
            target_dir = self.install_dir.get()
            os.makedirs(target_dir, exist_ok=True)
            
            # Determine path to bundled payload
            if getattr(sys, 'frozen', False):
                payload_path = os.path.join(sys._MEIPASS, "payload.zip")
            else:
                payload_path = os.path.join(os.path.dirname(__file__), "payload.zip")
            
            # Extract payload
            self.update_status("Extracting files...", "Reading payload.zip", 5)
            
            with zipfile.ZipFile(payload_path, 'r') as zf:
                files = zf.namelist()
                total_files = len(files)
                for i, file in enumerate(files):
                    zf.extract(file, target_dir)
                    if i % 50 == 0:
                        prog = 5 + (i / total_files) * (40 if self.dl_kokoro.get() else 85)
                        # Extract directly into target_dir. Since we zipped the "NavTools" folder,
                        # the files will be inside "target_dir/NavTools". Wait, Compress-Archive of a folder
                        # places the folder itself in the zip. We should handle that.
                        self.update_status("Extracting files...", file, prog)
            
            # The structure is target_dir/NavTools/...
            # We want the contents of NavTools to be directly in target_dir.
            extracted_folder = os.path.join(target_dir, "NavTools")
            if os.path.exists(extracted_folder) and os.path.isdir(extracted_folder):
                import shutil
                self.update_status("Moving files...", "Organizing installation directory", 48)
                for item in os.listdir(extracted_folder):
                    src = os.path.join(extracted_folder, item)
                    dst = os.path.join(target_dir, item)
                    # if dst exists, remove it
                    if os.path.exists(dst):
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    shutil.move(src, dst)
                os.rmdir(extracted_folder)

            # Download Kokoro models
            if self.dl_kokoro.get():
                models_dir = os.path.join(target_dir, "_internal", "models", "kokoro")
                os.makedirs(models_dir, exist_ok=True)
                
                def report_progress(block_num, block_size, total_size):
                    dl_bytes = block_num * block_size
                    if total_size > 0:
                        percent = dl_bytes / total_size
                        # mapped between 50% and 70% for onnx, 70% and 90% for bin
                        mapped_prog = 50 + (percent * 20)
                        if "onnx" not in current_dl:
                            mapped_prog = 70 + (percent * 20)
                        
                        dl_mb = dl_bytes / (1024*1024)
                        tot_mb = total_size / (1024*1024)
                        self.update_status(f"Downloading {current_dl}...", 
                                           f"{dl_mb:.1f} MB / {tot_mb:.1f} MB", min(mapped_prog, 90))

                current_dl = "kokoro-v1.0.onnx"
                urllib.request.urlretrieve(KOKORO_ONNX_URL, os.path.join(models_dir, "kokoro-v1.0.onnx"), report_progress)
                
                current_dl = "voices-v1.0.bin"
                urllib.request.urlretrieve(KOKORO_VOICES_URL, os.path.join(models_dir, "voices-v1.0.bin"), report_progress)
            
            # Create shortcuts
            self.update_status("Creating shortcuts...", "Configuring Windows integrations", 95)
            exe_path = os.path.join(target_dir, "NavTools.exe")
            ico_path = os.path.join(target_dir, "_internal", "navtools.ico") # wait, is it in _internal? We'll use exe itself.
            
            shell = win32com.client.Dispatch("WScript.Shell")
            
            if self.create_desktop_shortcut.get():
                desktop = shell.SpecialFolders("Desktop")
                shortcut = shell.CreateShortCut(os.path.join(desktop, "NavTools.lnk"))
                shortcut.Targetpath = exe_path
                shortcut.WorkingDirectory = target_dir
                shortcut.IconLocation = f"{exe_path},0"
                shortcut.save()
                
            if self.create_start_shortcut.get():
                programs = shell.SpecialFolders("Programs")
                start_dir = os.path.join(programs, "NavTools")
                os.makedirs(start_dir, exist_ok=True)
                shortcut = shell.CreateShortCut(os.path.join(start_dir, "NavTools.lnk"))
                shortcut.Targetpath = exe_path
                shortcut.WorkingDirectory = target_dir
                shortcut.IconLocation = f"{exe_path},0"
                shortcut.save()
            
            self.update_status("Installation complete", "All tasks finished successfully.", 100)
            self.after(500, self.go_next)
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Installation Error", str(e)))
            self.after(0, self.destroy)

    def finish(self):
        if self.launch_var.get():
            target_dir = self.install_dir.get()
            exe_path = os.path.join(target_dir, "NavTools.exe")
            if os.path.exists(exe_path):
                os.startfile(exe_path)
        self.destroy()

if __name__ == "__main__":
    app = InstallerWizard()
    app.mainloop()

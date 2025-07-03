import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
import subprocess
import threading
import time
import os
import struct
from PIL import Image, ImageTk
import json
import numpy as np

class Y1HelperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Y1 Helper - Innioasis Y1 Developer Tool")
        self.geometry("420x629")
        self.resizable(False, False)
        
        # Device configuration
        self.device_width = 480
        self.device_height = 360
        self.framebuffer_size = self.device_width * self.device_height * 4  # RGBA8888
        
        # Display scaling (75% of original size)
        self.display_scale = 0.75
        self.display_width = int(self.device_width * self.display_scale)  # 360
        self.display_height = int(self.device_height * self.display_scale)  # 270
        
        # State variables
        self.is_capturing = True  # Always capturing
        self.capture_thread = None
        self.current_app = None
        self.control_launcher = False
        self.last_screen_image = None
        self.device_connected = False
        self.prepare_device_visible = False  # Track if Prepare Device menu item is visible
        self.device_prepared = None  # Track if device has stock launcher installed
        self.prepare_prompt_refused = False  # Track if user refused the initial prepare prompt
        self.prepare_prompt_shown = False  # Track if prepare prompt has been shown for current connection
        
        # Essential UI variables
        self.status_var = tk.StringVar(value="Ready")
        self.launcher_var = tk.BooleanVar()
        self.rgb_profile_var = tk.StringVar(value="BGRA8888")
        
        # Add input pacing: minimum delay between input events (in seconds)
        self.input_pacing_interval = 0.1  # 100ms
        self.last_input_time = 0
        
        # Initialize UI
        self.setup_ui()
        self.setup_menu()
        self.setup_bindings()
        
        # Check ADB connection
        self.check_adb_connection()
        
        # Show placeholder if no device connected
        if not hasattr(self, 'device_connected') or not self.device_connected:
            self.show_disconnected_placeholder()
        
        # Detect current app and set launcher control (and start periodic check)
        self.detect_current_app()
        
        # Start screen capture immediately
        self.start_screen_capture()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Screen viewer frame
        screen_frame = ttk.LabelFrame(main_frame, text="Mouse Input Panel (480x360)", padding=5)
        screen_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Create canvas for screen display (scaled down to 75%)
        self.screen_canvas = tk.Canvas(screen_frame, width=self.display_width, height=self.display_height, 
                                     bg='black', cursor='crosshair', highlightthickness=0, bd=0)
        self.screen_canvas.pack()
        self.screen_canvas.config(width=self.display_width, height=self.display_height)
        
        # Remove old playback_frame, nav_frame, mid_frame
        # Add a concise explanation of keyboard and mouse mappings below the screen viewer
        mappings_text = (
            "Controls:\n"
            "Touch/Select: Left Click\n"
            "Back: Right Click, Q, /\n"
            "D-pad Up: W, Up Arrow, Scroll Wheel Up\n"
            "D-pad Down: S, Down Arrow, Scroll Wheel Down\n"
            "D-pad Left: A, Left Arrow\n"
            "D-pad Right: D, Right Arrow\n"
            "Center/Enter: Wheel Click, Enter, E, Right Shift\n"
            "Play/Pause: Space\n"
            "Next Track: Page Up\n"
            "Previous Track: Page Down\n"
            "Toggle Launcher Mode: Alt\n"
            "\nFix Launcher Mode: Scroll Wheel = Left/Right, Left Click = Enter"
        )
        mappings_label = ttk.Label(screen_frame, text=mappings_text, justify=tk.LEFT, font=("Segoe UI", 9))
        mappings_label.pack(pady=(10, 0), anchor="w")
        
        # Status bar at bottom (prominent display)
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                relief=tk.SUNKEN, borderwidth=1, padding=(5, 2))
        status_label.pack(fill=tk.X, side=tk.LEFT, expand=True)
        
        # Force focus to canvas after window is ready
        self.after(100, lambda: self.screen_canvas.focus_set())
        
        # Mouse click bindings
        self.screen_canvas.bind("<Button-1>", self.on_screen_click)       # Left click
        self.screen_canvas.bind("<Button-3>", self.on_screen_right_click) # Right click
        self.screen_canvas.bind("<Button-2>", self.on_mouse_wheel_click)  # Middle click (wheel click)
        self.screen_canvas.bind("<ButtonRelease-1>", self.on_nav_bar_click)
        
        # Mouse wheel bindings
        self.screen_canvas.bind("<MouseWheel>", self.on_mouse_wheel)      # Windows/macOS
        self.screen_canvas.bind("<Button-4>", self.on_mouse_wheel)        # Linux scroll up
        self.screen_canvas.bind("<Button-5>", self.on_mouse_wheel)        # Linux scroll down
        
        # Add Fix Launcher Scrolling toggle button (hidden by default)
        self.launcher_toggle_btn = ttk.Checkbutton(
            screen_frame,
            text="Simulate Y1 Scroll wheel Input",
            variable=self.launcher_var,
            command=self.toggle_launcher_control
        )
        self.launcher_toggle_btn.pack(pady=(8, 0), anchor="w")
        self.launcher_toggle_btn.pack_forget()  # Hide by default
        # Add tooltip to the button
        self. _add_tooltip(self.launcher_toggle_btn, (
            "When enabled, WASD, arrow keys, and the scroll wheel are remapped to match the Y1's unique scroll wheel: "
            "Up/Down become Left/Right, just like scrolling through a classic iPod menu. Perfect for Y1-optimised apps!"
        ))
        
        self.nav_bar_height = 30  # px, fixed height for nav bar
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="Go Home", command=self.go_home)
        self.context_menu.add_command(label="Open Settings", command=self.launch_settings)
        self.context_menu.add_command(label="Recent Apps", command=self.show_recent_apps)
    
    def setup_menu(self):
        menubar = Menu(self)
        self.config(menu=menubar)
        device_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Device", menu=device_menu)
        self.prepare_device_menu_item = device_menu.add_command(label="Prepare Device", command=self.prepare_device)
        device_menu.add_command(label="Launch Settings", command=self.launch_settings)
        device_menu.add_command(label="Go Home", command=self.go_home)
        self.device_menu = device_menu
        self.apps_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Apps", menu=self.apps_menu)
        self.apps_menu.add_command(label="Install APK...", command=self.install_apk)
        self.apps_menu.add_separator()
        self.refresh_apps()  # Populate on startup
        self.update_device_menu()
    
    def update_device_menu(self):
        """Update dynamic items in the Device menu (Nova Launcher, KeyCodeDisp, other launchers)"""
        # Remove all items after the static ones (up to and including Go Home)
        static_count = 3  # Prepare Device, Launch Settings, Go Home
        total_items = self.device_menu.index('end')
        if total_items is not None and total_items > static_count:
            for i in range(total_items, static_count, -1):
                self.device_menu.delete(i)
        # Only add dynamic items if device is connected
        if not getattr(self, 'device_connected', False):
            return
        # Get installed packages
        success, stdout, stderr = self.run_adb_command("shell pm list packages -3 -f")
        nova_installed = False
        keycode_installed = False
        extra_launchers = []
        launcher_pkgs = [
            ("com.teslacoilsw.launcher", "Open Nova Launcher"),
            ("com.android.launcher", "Open Android Launcher"),
            ("com.lge.launcher2", "Open LG Launcher"),
            ("com.sec.android.app.launcher", "Open Samsung Launcher"),
            ("com.miui.home", "Open MIUI Launcher")
        ]
        keycode_pkg = "jp.ne.neko.freewing.KeyCodeDisp"
        if success:
            for line in stdout.strip().split('\n'):
                if line.startswith('package:'):
                    if '=' in line:
                        package_name = line.split('=')[1]
                    else:
                        package_name = line[len('package:'):]
                    if package_name == "com.teslacoilsw.launcher":
                        nova_installed = True
                    if package_name == keycode_pkg:
                        keycode_installed = True
                    for pkg, label in launcher_pkgs:
                        if package_name == pkg and pkg != "com.teslacoilsw.launcher":
                            extra_launchers.append((pkg, label))
        self.device_menu.add_separator()
        if nova_installed:
            self.device_menu.add_command(label="Open Nova Launcher", command=self.open_nova_launcher)
        if keycode_installed:
            self.device_menu.add_command(label="View Input Keycodes", command=self.open_keycode_disp)
        for pkg, label in extra_launchers:
            self.device_menu.add_command(label=label, command=lambda p=pkg: self.open_launcher(p))
        self.device_menu.add_separator()
        self.device_menu.add_command(label="ADB Shell", command=self.open_adb_shell)
        self.device_menu.add_command(label="Device Info", command=self.show_device_info)
        self.device_menu.add_command(label="Change Device Language", command=self.change_device_language)
        self.device_menu.add_separator()
        self.device_menu.add_command(label="Exit", command=self.quit)
    
    def refresh_apps(self):
        """Refresh list of installed apps (Apps menu only)"""
        self.apps_menu.delete(0, tk.END)
        self.apps_menu.add_command(label="Install APK...", command=self.install_apk)
        self.apps_menu.add_separator()
        success, stdout, stderr = self.run_adb_command(
            "shell pm list packages -3 -f")
        apps = []
        launcher_pkgs = [
            "com.teslacoilsw.launcher",
            "com.android.launcher",
            "com.lge.launcher2",
            "com.sec.android.app.launcher",
            "com.miui.home",
            "com.innioasis.y1",
            "com.ayst.factorytest",
            "jp.ne.neko.freewing.KeyCodeDisp"
        ]
        if success:
            for line in stdout.strip().split('\n'):
                if line.startswith('package:'):
                    if '=' in line:
                        package_name = line.split('=')[1]
                    else:
                        package_name = line[len('package:'):]
                    if package_name in launcher_pkgs:
                        continue
                    apps.append(package_name)
        apps = [a for a in apps if a and a.strip()]
        if not apps:
            self.apps_menu.add_command(label="No user apps installed", state="disabled")
        else:
            for app in sorted(apps):
                app_menu = Menu(self.apps_menu, tearoff=0)
                app_menu.add_command(label="Launch", command=lambda a=app: self.launch_app(a))
                app_menu.add_command(label="Uninstall", command=lambda a=app: self.uninstall_app(a))
                self.apps_menu.add_cascade(label=app, menu=app_menu)
    
    def check_adb_connection(self):
        """Check if ADB is available and device is connected"""
        try:
            import os
            import platform
            
            # Use platform-appropriate ADB executable
            if platform.system() == "Windows":
                adb_path = os.path.join("platform-tools", "adb.exe")
            else:
                adb_path = os.path.join("platform-tools", "adb")
            
            result = subprocess.run([adb_path, "devices"], 
                                  capture_output=True, text=True, timeout=5)
            if "device" in result.stdout and "List of devices" in result.stdout:
                self.status_var.set("ADB Connected")
                self.device_connected = True
                self.refresh_apps()
            else:
                self.status_var.set("No ADB device found")
                self.device_connected = False
                # Don't call show_disconnected_placeholder here - let the capture loop handle it
        except Exception as e:
            self.status_var.set(f"ADB Error: {str(e)}")
            self.device_connected = False
            # Don't call show_disconnected_placeholder here - let the capture loop handle it
    
    def check_device_connection_status(self):
        """Check if device is still connected (lightweight check)"""
        try:
            import os
            import platform
            # Use platform-appropriate ADB executable
            if platform.system() == "Windows":
                adb_path = os.path.join("platform-tools", "adb.exe")
            else:
                adb_path = os.path.join("platform-tools", "adb")
            result = subprocess.run([adb_path, "devices"], 
                                  capture_output=True, text=True, timeout=3)
            if "device" in result.stdout and "List of devices" in result.stdout:
                if not self.device_connected:
                    # Device just reconnected
                    self.device_connected = True
                    self.status_var.set("Device connected")
                    self.refresh_apps()
                    # Check if device is prepared (has stock launcher)
                    if self.check_device_prepared() is False and not self.prepare_prompt_shown and self.device_prepared is not None:
                        # Only show prompt if we are certain device is connected and not prepared
                        self.prepare_prompt_shown = True
                        self.after(1000, self.show_unprepared_device_prompt)  # Delay to let UI settle
                else:
                    # Device was already connected, but app list may have changed externally
                    self.refresh_apps()
            else:
                if self.device_connected:
                    # Device just disconnected
                    self.device_connected = False
                    self.status_var.set("Device disconnected - Please reconnect")
                    self.hide_prepare_device_menu()
                    self.prepare_prompt_refused = False
                    self.prepare_prompt_shown = False
        except Exception as e:
            if self.device_connected:
                self.device_connected = False
                self.status_var.set("Device disconnected - Please reconnect")
                self.hide_prepare_device_menu()
                self.prepare_prompt_refused = False
                self.prepare_prompt_shown = False
    
    def detect_current_app(self):
        """Detect currently running app and set launcher control accordingly"""
        try:
            # Get the currently focused activity
            success, stdout, stderr = self.run_adb_command("shell dumpsys activity activities | grep mResumedActivity")
            detected_package = None
            if success and stdout:
                for line in stdout.strip().split('\n'):
                    if 'mResumedActivity' in line:
                        # Extract package name (regex for package/activity)
                        import re
                        match = re.search(r' ([a-zA-Z0-9_.]+)/(\S+)', line)
                        if match:
                            detected_package = match.group(1)
                        break
            if not detected_package:
                # Fallback: try alternative method
                success, stdout, stderr = self.run_adb_command("shell dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'")
                if success and stdout:
                    for line in stdout.strip().split('\n'):
                        import re
                        match = re.search(r' ([a-zA-Z0-9_.]+)/(\S+)', line)
                        if match:
                            detected_package = match.group(1)
                        break
            # Update current_app and launcher control logic
            if detected_package:
                self.current_app = detected_package
                if self._should_show_launcher_toggle(detected_package):
                    self.control_launcher = True
                    self.launcher_var.set(True)
                    self.launcher_toggle_btn.pack(pady=(8, 0), anchor="w")
                    self.status_var.set("Simulate Y1 Scroll wheel Input is available for this app")
                else:
                    self.control_launcher = False
                    self.launcher_var.set(False)
                    self.launcher_toggle_btn.pack_forget()
                if self._should_show_launcher_toggle(detected_package):
                    self.hide_prepare_device_menu()
            else:
                self.current_app = "unknown"
                self.control_launcher = False
                self.launcher_var.set(False)
                self.launcher_toggle_btn.pack_forget()
                self.status_var.set("App detection failed - Y1 scroll simulation disabled")
        except Exception as e:
            print(f"Error detecting current app: {e}")
            self.current_app = "unknown"
            self.control_launcher = False
            self.launcher_var.set(False)
            self.launcher_toggle_btn.pack_forget()
        # Schedule next check in 5 seconds if app is still running
        if hasattr(self, 'is_capturing') and self.is_capturing:
            self.after(5000, self.detect_current_app)
    
    def hide_prepare_device_menu(self):
        """Hide the Prepare Device menu item"""
        if hasattr(self, 'device_menu') and self.prepare_device_visible:
            self.device_menu.entryconfig("Prepare Device", state="disabled")
            self.prepare_device_visible = False
    
    def show_prepare_device_menu(self):
        """Show the Prepare Device menu item"""
        if hasattr(self, 'device_menu') and not self.prepare_device_visible and self.device_connected and self.prepare_prompt_refused:
            self.device_menu.entryconfig("Prepare Device", state="normal")
            self.prepare_device_visible = True
    
    def check_device_prepared(self):
        """Check if device has stock launcher installed (installed only, not running)"""
        success, stdout, stderr = self.run_adb_command("shell pm list packages com.innioasis.y1")
        if not success:
            self.device_prepared = None  # Unknown, don't prompt
            return None
        if "com.innioasis.y1" in stdout:
            self.device_prepared = True
            return True
        else:
            self.device_prepared = False
            return False
    
    def show_unprepared_device_prompt(self):
        """Show prompt for unprepared device"""
        result = messagebox.askyesno("Unprepared Device Detected", 
                                   "This Y1 device does not have the stock launcher installed.\n\n"
                                   "The device appears to be running a factory testing OS image.\n\n"
                                   "Would you like to prepare the device by installing the stock Y1 launcher?\n\n"
                                   "This will allow you to:\n"
                                   "• Start developing Y1 apps targeting Android API Level 16\n"
                                   "• Test apps on real hardware with the correct display and input setup\n"
                                   "• Use the full Y1 Helper functionality")
        if result:
            self.prepare_device()
        else:
            # User refused the prompt - show Prepare Device menu option
            self.prepare_prompt_refused = True
            self.show_prepare_device_menu()
    
    def run_adb_command(self, command, timeout=10):
        """Run ADB command and return result"""
        try:
            import os
            import platform
            
            # Use proper path for ADB executable
            if platform.system() == "Windows":
                adb_path = os.path.join("platform-tools", "adb.exe")
            else:
                adb_path = os.path.join("platform-tools", "adb")
            
            # Handle commands with quoted paths properly
            if '"' in command:
                # For commands with quoted paths, use shell=True on Windows
                if platform.system() == "Windows":
                    full_command = f'"{adb_path}" {command}'
                    result = subprocess.run(full_command, shell=True, capture_output=True, text=True, timeout=timeout)
                else:
                    # On Unix systems, split carefully
                    import shlex
                    full_command = [adb_path] + shlex.split(command)
                    result = subprocess.run(full_command, capture_output=True, text=True, timeout=timeout)
            else:
                # Simple command splitting for non-path commands
                full_command = [adb_path] + command.split()
                result = subprocess.run(full_command, capture_output=True, text=True, timeout=timeout)
            
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)
    
    def start_screen_capture(self):
        if not self.capture_thread or not self.capture_thread.is_alive():
            self.is_capturing = True
            self.capture_thread = threading.Thread(target=self.capture_screen_loop, daemon=True)
            self.capture_thread.start()
            self.status_var.set("Screen capture started")
    
    def capture_screen_loop(self):
        """Single-threaded screen capture loop: pull, decode, display, repeat"""
        import tempfile
        import os
        import platform
        
        temp_dir = tempfile.gettempdir()
        # Use platform-appropriate path separator
        fb_temp_path = os.path.join(temp_dir, "y1_fb0.tmp")
        placeholder_shown = False
        last_connection_check = 0
        connection_check_interval = 5  # Check connection every 5 seconds
        
        while self.is_capturing:
            try:
                current_time = time.time()
                
                # Periodically check device connection status
                if current_time - last_connection_check > connection_check_interval:
                    self.check_device_connection_status()
                    last_connection_check = current_time
                
                # Check if device is connected
                if not self.device_connected:
                    if not placeholder_shown:
                        self.show_disconnected_placeholder()
                        placeholder_shown = True
                        self.status_var.set("Device disconnected - Please reconnect")
                    time.sleep(1)  # Check less frequently when disconnected
                    continue
                
                # Reset placeholder flag when device is connected
                if placeholder_shown:
                    placeholder_shown = False
                    self.status_var.set("Device connected")
                
                # Pull framebuffer from device to temp file
                success, stdout, stderr = self.run_adb_command(f"pull /dev/graphics/fb0 \"{fb_temp_path}\"")
                if success and os.path.exists(fb_temp_path):
                    self.process_framebuffer(fb_temp_path)
                else:
                    # If framebuffer pull fails, device might be disconnected
                    if not placeholder_shown:
                        self.device_connected = False
                        self.show_disconnected_placeholder()
                        placeholder_shown = True
                        self.status_var.set("Device disconnected - Please reconnect")
                    time.sleep(0.5)
                # Removed small sleep to maximize update speed
            except Exception as e:
                print(f"Capture error: {e}")
                if not placeholder_shown:
                    self.device_connected = False
                    self.show_disconnected_placeholder()
                    placeholder_shown = True
                    self.status_var.set("Device disconnected - Please reconnect")
                time.sleep(0.5)
    
    def process_framebuffer(self, fb_path):
        """Process framebuffer data and display on canvas (single-threaded, numpy for BGRA/BGR)"""
        try:
            from PIL import Image
            if not os.path.exists(fb_path):
                return
            file_size = os.path.getsize(fb_path)
            if file_size < 100:
                return
            with open(fb_path, 'rb') as f:
                data = f.read(file_size)
            if len(data) < 100:
                return
            img_rgb = None
            expected_rgba = self.device_width * self.device_height * 4
            expected_rgb = self.device_width * self.device_height * 3
            expected_rgb565 = self.device_width * self.device_height * 2
            selected_profile = self.rgb_profile_var.get()
            formats_to_try = []
            if selected_profile == "Auto":
                if file_size >= expected_rgba:
                    formats_to_try = [
                        ("RGBA8888", "RGBA", expected_rgba, False),
                        ("BGRA8888", "RGBA", expected_rgba, True)
                    ]
                elif file_size >= expected_rgb:
                    formats_to_try = [
                        ("RGB888", "RGB", expected_rgb, False),
                        ("BGR888", "RGB", expected_rgb, True)
                    ]
                elif file_size >= expected_rgb565:
                    formats_to_try = [("RGB565", "RGB565", expected_rgb565, False)]
            else:
                if selected_profile == "RGBA8888":
                    formats_to_try = [("RGBA8888", "RGBA", expected_rgba, False)]
                elif selected_profile == "BGRA8888":
                    formats_to_try = [("BGRA8888", "RGBA", expected_rgba, True)]
                elif selected_profile == "RGB888":
                    formats_to_try = [("RGB888", "RGB", expected_rgb, False)]
                elif selected_profile == "BGR888":
                    formats_to_try = [("BGR888", "RGB", expected_rgb, True)]
                elif selected_profile == "RGB565":
                    formats_to_try = [("RGB565", "RGB565", expected_rgb565, False)]
            for format_name, pil_format, expected_size, swap_rb in formats_to_try:
                try:
                    if pil_format == "RGB565":
                        rgb_data = bytearray(expected_rgb)
                        for i in range(0, expected_rgb565, 2):
                            if i + 1 < len(data):
                                pixel = (data[i + 1] << 8) | data[i]
                                r = ((pixel >> 11) & 0x1F) << 3
                                g = ((pixel >> 5) & 0x3F) << 2
                                b = (pixel & 0x1F) << 3
                                rgb_idx = (i // 2) * 3
                                if rgb_idx + 2 < len(rgb_data):
                                    rgb_data[rgb_idx] = r
                                    rgb_data[rgb_idx + 1] = g
                                    rgb_data[rgb_idx + 2] = b
                        img = Image.frombytes('RGB', (self.device_width, self.device_height), bytes(rgb_data))
                        img_rgb = img
                    elif swap_rb:
                        arr = np.frombuffer(data[:expected_size], dtype=np.uint8)
                        arr = arr.reshape((self.device_height, self.device_width, int(expected_size // (self.device_width * self.device_height))))
                        arr = arr[..., [2, 1, 0, 3]] if arr.shape[2] == 4 else arr[..., [2, 1, 0]]
                        img = Image.fromarray(arr)
                        img_rgb = img.convert('RGB')
                    else:
                        img = Image.frombytes(pil_format, (self.device_width, self.device_height), data[:expected_size])
                        img_rgb = img.convert('RGB') if pil_format == 'RGBA' else img
                    break
                except Exception as e:
                    print(f"Failed to decode with {format_name}: {e}")
                    continue
            if img_rgb is None:
                print(f"Failed to decode framebuffer with auto-detection")
                img_rgb = Image.new('RGB', (self.device_width, self.device_height), (255, 0, 0))
            crop_top = 0
            if img_rgb is not None and img_rgb.height > 50:
                def has_black_status_bar(img):
                    import numpy as np
                    arr = np.array(img)
                    if arr.shape[0] < 50:
                        return False
                    top = arr[:25, :, :3]
                    return (top.mean() < 16)
                if has_black_status_bar(img_rgb):
                    crop_top = 25
                    img_rgb = img_rgb.crop((0, crop_top, img_rgb.width, img_rgb.height))
            src_height = self.device_height - crop_top
            display_height = int(src_height * self.display_scale)
            resized_img = img_rgb.resize((self.display_width, display_height), Image.Resampling.LANCZOS)
            # Always pad to full display height, centering the image vertically
            from PIL import Image
            padded = Image.new('RGB', (self.display_width, self.display_height), (0,0,0))
            y_offset = (self.display_height - display_height) // 2
            padded.paste(resized_img, (0, y_offset))
            photo = ImageTk.PhotoImage(padded)
            self.after_idle(lambda: self.update_screen_display(photo, self.display_height))
            # Save the last screen image for input mapping
            self.last_screen_image = img_rgb
        except Exception as e:
            print(f"Framebuffer processing error: {e}")
            try:
                from PIL import Image
                error_img = Image.new('RGB', (self.device_width, self.device_height), (255, 0, 0))
                resized_error_img = error_img.resize((self.display_width, self.display_height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(resized_error_img)
                self.after_idle(self.update_screen_display, photo)
            except:
                pass
    
    def force_framebuffer_refresh(self):
        """Force an immediate framebuffer refresh"""
        try:
            import tempfile
            import os
            import platform
            
            temp_dir = tempfile.gettempdir()
            # Use platform-appropriate path separator
            fb_temp_path = os.path.join(temp_dir, "y1_fb0.tmp")
            
            # Pull framebuffer and process immediately
            success, stdout, stderr = self.run_adb_command(f"pull /dev/graphics/fb0 \"{fb_temp_path}\"")
            if success and os.path.exists(fb_temp_path):
                self.process_framebuffer(fb_temp_path)
        except Exception as e:
            print(f"Force refresh error: {e}")
    
    def update_screen_display(self, photo, display_height=None):
        """Update screen display on main thread, with dynamic canvas height if needed"""
        try:
            if hasattr(self, 'current_photo'):
                del self.current_photo
            self.screen_canvas.config(height=self.display_height)
            from PIL import Image, ImageDraw
            pil_img = None
            try:
                pil_img = Image.frombytes('RGB', (self.display_width, self.display_height), photo._PhotoImage__photo.convert('RGB').tobytes())
            except Exception:
                pil_img = None
            if pil_img is not None:
                draw = ImageDraw.Draw(pil_img, 'RGBA')
                nav_height = self.nav_bar_height
                nav_y = self.display_height - nav_height
                draw.rectangle([0, nav_y, self.display_width, self.display_height], fill=(0,0,0,255))
                btn_radius = nav_height // 2 - 2
                spacing = self.display_width // 4
                # Home button (right): left-pointing triangle
                hx = self.display_width - spacing
                hy = nav_y + nav_height // 2
                draw.polygon([
                    (hx+btn_radius, hy),
                    (hx-btn_radius, hy-btn_radius),
                    (hx-btn_radius, hy+btn_radius)
                ], fill=(255,255,255,220))
                # Back button (left): circle
                bx = spacing
                by = nav_y + nav_height // 2
                draw.ellipse([
                    (bx-btn_radius, by-btn_radius),
                    (bx+btn_radius, by+btn_radius)
                ], outline=(255,255,255,220), width=3)
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(pil_img)
            self.current_photo = photo
            self.screen_canvas.delete("all")
            self.screen_canvas.create_image(0, 0, anchor=tk.NW, image=self.current_photo)
        except Exception as e:
            print(f"Display update error: {e}")
    
    def show_disconnected_placeholder(self):
        """Show placeholder when device is not connected"""
        try:
            # Create a placeholder image similar to iPod recovery screen
            img = Image.new('RGB', (self.display_width, self.display_height), (40, 40, 40))  # Dark gray background
            
            # Create a simple icon (USB cable symbol)
            icon_size = int(60 * self.display_scale)  # Scale icon size
            icon_x = (self.display_width - icon_size) // 2
            icon_y = (self.display_height - icon_size) // 2 - int(30 * self.display_scale)
            
            # Draw a simple USB icon (white rectangle with lines)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            
            # USB connector outline
            draw.rectangle([icon_x, icon_y, icon_x + icon_size, icon_y + icon_size], 
                         outline=(200, 200, 200), width=3)
            
            # USB pins (horizontal lines)
            pin_y1 = icon_y + 15
            pin_y2 = icon_y + 30
            pin_y3 = icon_y + 45
            draw.line([icon_x + 10, pin_y1, icon_x + icon_size - 10, pin_y1], 
                     fill=(200, 200, 200), width=2)
            draw.line([icon_x + 10, pin_y2, icon_x + icon_size - 10, pin_y2], 
                     fill=(200, 200, 200), width=2)
            draw.line([icon_x + 10, pin_y3, icon_x + icon_size - 10, pin_y3], 
                     fill=(200, 200, 200), width=2)
            
            # Add text with proper font
            try:
                from PIL import ImageFont
                # Try to use a system font
                font_size = 16
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    try:
                        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
                    except:
                        font = ImageFont.load_default()
                
                text = "Please Connect Your Y1"
                # Get text size for centering
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                text_x = (self.display_width - text_width) // 2
                text_y = icon_y + icon_size + int(20 * self.display_scale)
                
                # Draw text
                draw.text((text_x, text_y), text, fill=(200, 200, 200), font=font)
            except Exception as e:
                # Fallback to simple text rendering
                text = "Please Connect Your Y1"
                text_x = (self.display_width - len(text) * 8) // 2
                text_y = icon_y + icon_size + int(20 * self.display_scale)
                
                # Draw text as simple rectangles
                for i, char in enumerate(text):
                    char_x = text_x + i * 8
                    if char != ' ':
                        draw.rectangle([char_x, text_y, char_x + 6, text_y + 10], 
                                     fill=(200, 200, 200))
            
            # Convert to PhotoImage and display
            photo = ImageTk.PhotoImage(img)
            self.screen_canvas.delete("all")
            self.screen_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            
            # Store reference
            if hasattr(self, 'current_photo'):
                del self.current_photo
            self.current_photo = photo
            
        except Exception as e:
            print(f"Placeholder display error: {e}")
    
    def launch_settings(self):
        """Launch Android Settings app"""
        success, stdout, stderr = self.run_adb_command(
            "shell am start -n com.android.settings/.Settings")
        if success:
            self.status_var.set("Settings launched")
            self.current_app = "com.android.settings"
            self.control_launcher = False  # Disable launcher control
            self.launcher_var.set(False)  # Update UI checkbox
        else:
            self.status_var.set(f"Failed to launch settings: {stderr}")
    
    def go_home(self):
        """Restart the built-in home app (com.innioasis.y1)"""
        self.status_var.set("Restarting Home App...")
        # Force-stop the home app
        self.run_adb_command("shell am force-stop com.innioasis.y1")
        # Launch the home app
        success, stdout, stderr = self.run_adb_command("shell monkey -p com.innioasis.y1 -c android.intent.category.LAUNCHER 1")
        if success:
            self.status_var.set("Home app restarted (com.innioasis.y1)")
            self.current_app = "com.innioasis.y1"
            self.control_launcher = True  # Enable launcher control
            self.launcher_var.set(True)  # Update UI checkbox
        else:
            self.status_var.set("Failed to restart home app: " + (stderr or stdout))
            messagebox.showerror("Restart Home App", "Failed to restart the home app.\n\nPlease ensure:\n- Device is unlocked\n- Y1 launcher is installed\n- Device is responsive")
    
    def install_apk(self):
        """Install APK file"""
        file_path = filedialog.askopenfilename(
            title="Select APK file",
            filetypes=[("APK files", "*.apk"), ("All files", "*.*")]
        )
        if file_path:
            self.status_var.set("Installing APK...")
            
            # Convert to absolute path using platform-appropriate methods
            import os
            import platform
            file_path = os.path.abspath(file_path)
            
            # Use the full path in the ADB command
            success, stdout, stderr = self.run_adb_command(f"install -r \"{file_path}\"")
            
            if success:
                self.status_var.set("APK installed successfully")
                self.refresh_apps()
            else:
                # Provide more detailed error information
                error_msg = stderr.strip() if stderr else stdout.strip()
                if "device not found" in error_msg.lower():
                    self.status_var.set("APK installation failed: Device not connected")
                elif "permission denied" in error_msg.lower():
                    self.status_var.set("APK installation failed: Permission denied - check USB debugging")
                elif "failed to install" in error_msg.lower():
                    self.status_var.set("APK installation failed: Incompatible APK or insufficient storage")
                else:
                    self.status_var.set(f"APK installation failed: {error_msg}")
                
                # Show detailed error in console for debugging
                print(f"APK Installation Error:")
                print(f"  File: {file_path}")
                print(f"  Error: {error_msg}")
        else:
            self.status_var.set("APK installation cancelled")
    
    def prepare_device(self):
        """Install stock Y1 launcher from 2.1.9 update for development, plus Nova Launcher and KeyCodeDisp if available"""
        import os
        from tkinter import messagebox
        # Show friendly preparation dialog
        prep_msg = (
            "Preparing your Y1 device for development!\n\n"
            "Here's what will happen:\n"
            "• The device will be set to Android 4.2.2, matching your PC's language and region.\n"
            "• KeyCodeDisp will be installed to help you understand all available input events.\n"
            "• Nova Launcher will be installed so you can launch it from the utility if needed.\n"
            "• The Y1 launcher (com.innioasis.y1) will be set as the default home app.\n\n"
            "This ensures your device is ready for Y1 app development and testing!"
        )
        messagebox.showinfo("Preparing Device", prep_msg)
        # Check if the APKs exist
        stock_launcher_path = "com.innioasis.y1_2.1.9.apk"
        nova_launcher_path = "novalauncher.apk"
        keycodedisp_path = "keycodedisp.apk"
        missing = []
        if not os.path.exists(stock_launcher_path):
            missing.append(stock_launcher_path)
        if not os.path.exists(nova_launcher_path):
            missing.append(nova_launcher_path)
        if not os.path.exists(keycodedisp_path):
            missing.append(keycodedisp_path)
        if missing:
            self.status_var.set(f"Missing APK(s): {', '.join(missing)}")
            messagebox.showerror("Missing APK(s)", f"The following APK(s) are required for preparation but not found:\n\n{chr(10).join(missing)}\n\nPlease add them to the workspace directory.")
            return
        self.status_var.set("Preparing device - Installing stock launcher, Nova Launcher, and KeyCodeDisp...")
        # Install stock launcher
        abs_path = os.path.abspath(stock_launcher_path)
        success, stdout, stderr = self.run_adb_command(f"install -r \"{abs_path}\"", timeout=60)
        if not success:
            self.status_var.set(f"Failed to install stock launcher: {stderr}")
            messagebox.showerror("Install Error", f"Failed to install stock launcher:\n\n{stderr}")
            return
        # Install Nova Launcher
        abs_nova = os.path.abspath(nova_launcher_path)
        success, stdout, stderr = self.run_adb_command(f"install -r \"{abs_nova}\"", timeout=60)
        if not success:
            self.status_var.set(f"Failed to install Nova Launcher: {stderr}")
            messagebox.showerror("Install Error", f"Failed to install Nova Launcher:\n\n{stderr}")
            return
        # Install KeyCodeDisp
        abs_keycode = os.path.abspath(keycodedisp_path)
        success, stdout, stderr = self.run_adb_command(f"install -r \"{abs_keycode}\"", timeout=60)
        if not success:
            self.status_var.set(f"Failed to install KeyCodeDisp: {stderr}")
            messagebox.showerror("Install Error", f"Failed to install KeyCodeDisp:\n\n{stderr}")
            return
        self.status_var.set("All launchers and KeyCodeDisp installed. Launching stock launcher...")
        # Disable factory test package if present
        self.run_adb_command("shell pm disable-user --user 0 com.ayst.factorytest")
        # Launch the stock launcher
        launch_success, launch_stdout, launch_stderr = self.run_adb_command(
            "shell monkey -p com.innioasis.y1 -c android.intent.category.LAUNCHER 1")
        # Set Y1 launcher as default home app
        self.run_adb_command("shell cmd package set-home-activity com.innioasis.y1/.ui.LauncherActivity")
        if not launch_success:
            self.status_var.set("Launcher installed, but failed to launch.")
            print(f"Warning: Failed to launch stock launcher: {launch_stderr}")
        else:
            self.status_var.set("Launcher launched - Opening language settings...")
            self.after(2000, self.change_device_language)
        messagebox.showinfo("Device Prepared", "✓ Stock Y1 launcher (2.1.9), Nova Launcher, and KeyCodeDisp installed\n✓ Stock launcher set as default home\n✓ Language settings opened\n\nDevice is ready for Y1 development!")
    
    def open_nova_launcher(self):
        self.run_adb_command("shell monkey -p com.teslacoilsw.launcher -c android.intent.category.LAUNCHER 1")
        self.status_var.set("Nova Launcher opened")

    def open_keycode_disp(self):
        self.run_adb_command("shell monkey -p jp.ne.neko.freewing.KeyCodeDisp -c android.intent.category.LAUNCHER 1")
        self.status_var.set("KeyCode Display app opened")

    def open_launcher(self, pkg):
        self.run_adb_command(f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        self.status_var.set(f"Launcher {pkg} opened")
    
    def launch_app(self, package_name):
        """Launch specified app"""
        success, stdout, stderr = self.run_adb_command(
            f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        if success:
            self.status_var.set(f"Launched {package_name}")
            self.current_app = package_name
            self.control_launcher = False  # Disable launcher control
            self.launcher_var.set(False)  # Update UI checkbox
            self.refresh_apps()  # Ensure app list is up to date after launch
        else:
            self.status_var.set(f"Failed to launch {package_name}: {stderr}")
    
    def uninstall_app(self, package_name):
        confirm = messagebox.askyesno("Uninstall App", f"Are you sure you want to uninstall {package_name}?")
        if not confirm:
            return
        self.status_var.set(f"Uninstalling {package_name}...")
        success, stdout, stderr = self.run_adb_command(f"uninstall {package_name}")
        if success:
            self.status_var.set(f"{package_name} uninstalled successfully")
            self.refresh_apps()
        else:
            self.status_var.set(f"Failed to uninstall {package_name}: {stderr}")
    
    def toggle_launcher_control(self, event=None):
        """Toggle launcher control mode"""
        self.control_launcher = not self.control_launcher
        self.launcher_var.set(self.control_launcher)
        status = "enabled" if self.control_launcher else "disabled"
        self.status_var.set(f"Launcher control {status}")
    
    def on_screen_click(self, event):
        """Handle left click on screen (touch input or enter in launcher mode)"""
        if not self._input_paced():
            return
        # Calculate vertical offset if image is centered
        y_offset = 0
        if hasattr(self, 'display_height') and hasattr(self, 'device_height'):
            crop_top = 0
            # Heuristic: if the top 25px are black, we cropped them
            if hasattr(self, 'last_screen_image') and self.last_screen_image is not None:
                import numpy as np
                arr = np.array(self.last_screen_image)
                if arr.shape[0] >= 50 and (arr[:25, :, :3].mean() < 16):
                    crop_top = 25
            src_height = self.device_height - crop_top
            display_img_height = int(src_height * self.display_scale)
            y_offset = (self.display_height - display_img_height) // 2
        # Adjust for vertical offset
        adj_y = event.y - y_offset
        if adj_y < 0 or adj_y >= display_img_height:
            return  # Click outside the image area
        x = int(event.x / self.display_scale)
        y = int(adj_y / self.display_scale) + (crop_top if 'crop_top' in locals() else 0)
        if self.control_launcher:
            success, stdout, stderr = self.run_adb_command("shell input keyevent 66")  # KEYCODE_ENTER
            if success:
                self.status_var.set("Enter key sent")
            else:
                self.status_var.set(f"Enter key failed: {stderr}")
        else:
            success, stdout, stderr = self.run_adb_command(
                f"shell input tap {x} {y}")
            if success:
                self.status_var.set(f"Touch input sent to ({x}, {y})")
            else:
                self.status_var.set(f"Touch input failed: {stderr}")
    
    def on_screen_right_click(self, event):
        """Handle right click on screen (back button)"""
        if not self._input_paced():
            return
            
        success, stdout, stderr = self.run_adb_command("shell input keyevent 4")  # KEYCODE_BACK
        if success:
            self.status_var.set("Back button pressed")
        else:
            self.status_var.set(f"Back button failed: {stderr}")
    
    def on_mouse_wheel(self, event):
        if not self._input_paced():
            return
        direction = 0
        if hasattr(event, 'delta') and event.delta != 0:
            if event.delta > 0:
                direction = 1
            else:
                direction = -1
        elif hasattr(event, 'num'):
            if event.num == 4:
                direction = 1
            elif event.num == 5:
                direction = -1
            else:
                return
        else:
            return
        # Y1 scroll wheel mapping: counterclockwise = Dpad Left (up), clockwise = Dpad Right (down)
        if self.control_launcher:
            if direction > 0:
                keycode = 21  # KEYCODE_DPAD_LEFT
                dir_str = "left"
            else:
                keycode = 22  # KEYCODE_DPAD_RIGHT
                dir_str = "right"
        else:
            if direction > 0:
                keycode = 19  # KEYCODE_DPAD_UP
                dir_str = "up"
            else:
                keycode = 20  # KEYCODE_DPAD_DOWN
                dir_str = "down"
        success, stdout, stderr = self.run_adb_command(f"shell input keyevent {keycode}")
        if success:
            self.status_var.set(f"D-pad {dir_str} pressed")
        else:
            self.status_var.set(f"D-pad {dir_str} failed: {stderr}")
    
    def on_mouse_wheel_click(self, event):
        if not self._input_paced():
            return
        # Y1 scroll wheel center = ENTER, back/menu = BACK
        if self.control_launcher:
            keycode = 66  # KEYCODE_ENTER
            action = "enter"
        else:
            keycode = 23  # KEYCODE_DPAD_CENTER
            action = "d-pad center"
        success, stdout, stderr = self.run_adb_command(f"shell input keyevent {keycode}")
        if success:
            self.status_var.set(f"Mouse wheel click: {action} pressed")
        else:
            self.status_var.set(f"Mouse wheel click failed: {stderr}")
    
    def on_key_press(self, event):
        if not self._input_paced():
            return
        key = event.keysym.lower()
        dpad_map = {
            'w': 19, 'up': 19,
            's': 20, 'down': 20,
            'a': 21, 'left': 21,
            'd': 22, 'right': 22
        }
        direction_map = {
            19: 'up', 20: 'down', 21: 'left', 22: 'right'
        }
        if key in dpad_map:
            keycode = dpad_map[key]
            direction = direction_map[keycode]
            if self.control_launcher:
                if keycode == 19:
                    keycode = 21
                    direction = 'left'
                elif keycode == 20:
                    keycode = 22
                    direction = 'right'
        elif key in ['return', 'e', 'shift_r']:
            if self.control_launcher:
                keycode = 66
                direction = "enter"
            else:
                keycode = 23
                direction = "center"
        elif key in ['q', 'slash', 'Escape']:
            keycode = 4
            direction = "back"
        elif key == 'space':
            keycode = 85
            direction = "play/pause"
        elif key == 'prior':
            keycode = 87
            direction = "next"
        elif key == 'next':
            keycode = 88
            direction = "previous"
        else:
            return
        self.force_framebuffer_refresh()
        success, stdout, stderr = self.run_adb_command(f"shell input keyevent {keycode}")
        if success:
            self.status_var.set(f"Key {direction} pressed")
            self.after(100, self.force_framebuffer_refresh)
            self.after(1500, lambda: self.status_var.set("Ready"))
        else:
            self.status_var.set(f"Key {direction} failed: {stderr}")
    
    def toggle_play_pause(self):
        """Toggle play/pause on device"""
        self.force_framebuffer_refresh()
        self.run_adb_command("shell input keyevent 85")  # KEYCODE_MEDIA_PLAY_PAUSE
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def previous_track(self):
        """Send previous track key event"""
        self.force_framebuffer_refresh()
        self.run_adb_command("shell input keyevent 88")  # KEYCODE_MEDIA_PREVIOUS
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def next_track(self):
        """Send next track key event"""
        self.force_framebuffer_refresh()
        self.run_adb_command("shell input keyevent 87")  # KEYCODE_MEDIA_NEXT
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def nav_up(self):
        """Navigate up (inverted for launcher)"""
        self.force_framebuffer_refresh()
        if self.control_launcher:
            self.run_adb_command("shell input keyevent 20")  # KEYCODE_DPAD_DOWN
        else:
            self.run_adb_command("shell input keyevent 19")  # KEYCODE_DPAD_UP
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def nav_down(self):
        """Navigate down (inverted for launcher)"""
        self.force_framebuffer_refresh()
        if self.control_launcher:
            self.run_adb_command("shell input keyevent 19")  # KEYCODE_DPAD_UP
        else:
            self.run_adb_command("shell input keyevent 20")  # KEYCODE_DPAD_DOWN
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def nav_left(self):
        """Navigate left (inverted for launcher)"""
        self.force_framebuffer_refresh()
        if self.control_launcher:
            self.run_adb_command("shell input keyevent 22")  # KEYCODE_DPAD_RIGHT
        else:
            self.run_adb_command("shell input keyevent 21")  # KEYCODE_DPAD_LEFT
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def nav_right(self):
        """Navigate right (inverted for launcher)"""
        self.force_framebuffer_refresh()
        if self.control_launcher:
            self.run_adb_command("shell input keyevent 21")  # KEYCODE_DPAD_LEFT
        else:
            self.run_adb_command("shell input keyevent 22")  # KEYCODE_DPAD_RIGHT
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def nav_center(self):
        """Send center/select key event"""
        self.force_framebuffer_refresh()
        if self.control_launcher:
            self.run_adb_command("shell input keyevent 66")  # KEYCODE_ENTER
        else:
            self.run_adb_command("shell input keyevent 23")  # KEYCODE_DPAD_CENTER
        self.after(100, self.force_framebuffer_refresh)
        self.after(1500, lambda: self.status_var.set("Ready"))

    def open_adb_shell(self):
        """Open ADB shell in new window"""
        try:
            import os
            import platform
            if platform.system() == "Windows":
                adb_path = os.path.join("platform-tools", "adb.exe")
            else:
                adb_path = os.path.join("platform-tools", "adb")
            
            subprocess.Popen([adb_path, "shell"], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open ADB shell: {e}")
    
    def show_device_info(self):
        """Show device information"""
        info = []
        
        # Get device model
        success, stdout, stderr = self.run_adb_command("shell getprop ro.product.model")
        if success:
            info.append(f"Model: {stdout.strip()}")
        
        # Get Android version
        success, stdout, stderr = self.run_adb_command("shell getprop ro.build.version.release")
        if success:
            info.append(f"Android: {stdout.strip()}")
        
        # Get screen resolution
        success, stdout, stderr = self.run_adb_command("shell wm size")
        if success:
            info.append(f"Screen: {stdout.strip()}")
        
        # Get framebuffer info
        success, stdout, stderr = self.run_adb_command("shell cat /sys/class/graphics/fb0/bits_per_pixel")
        if success:
            info.append(f"Framebuffer bits per pixel: {stdout.strip()}")
        
        success, stdout, stderr = self.run_adb_command("shell cat /sys/class/graphics/fb0/stride")
        if success:
            info.append(f"Framebuffer stride: {stdout.strip()}")
        
        info_text = "\n".join(info) if info else "Unable to get device info"
        messagebox.showinfo("Device Information", info_text)
    
    def change_device_language(self):
        """Open Android language settings"""
        if not self.device_connected:
            messagebox.showerror("Error", "Device not connected!\n\nPlease ensure:\n- Device is connected via USB\n- USB debugging is enabled\n- Device is authorized for ADB")
            return
        
        self.status_var.set("Opening language settings...")
        success, stdout, stderr = self.run_adb_command("shell am start -a android.settings.LOCALE_SETTINGS")
        
        if success:
            self.status_var.set("Language settings opened")
            messagebox.showinfo("Language Settings", 
                              "Language settings have been opened on your device.\n\n"
                              "You can now:\n"
                              "• Select your preferred language\n"
                              "• Choose regional settings\n"
                              "• Configure input methods")
        else:
            error_msg = stderr.strip() if stderr else stdout.strip()
            self.status_var.set(f"Failed to open language settings: {error_msg}")
            messagebox.showerror("Error", 
                               f"Failed to open language settings:\n\n{error_msg}\n\n"
                               "Please ensure:\n"
                               "- Device is unlocked\n"
                               "- Settings app is available\n"
                               "- Device is responsive")
    
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            # Stop capture
            self.is_capturing = False
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    def on_closing(self):
        """Handle window closing"""
        self.cleanup()
        self.quit()

    def _input_paced(self):
        import time
        now = time.time()
        if now - self.last_input_time < self.input_pacing_interval:
            return False
        self.last_input_time = now
        return True

    def _add_tooltip(self, widget, text):
        # Simple tooltip for Tkinter widgets
        tooltip = tk.Toplevel(widget)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        label = tk.Label(tooltip, text=text, background="#fff", relief=tk.SOLID, borderwidth=1, font=("Segoe UI", 9), wraplength=320, justify=tk.LEFT)
        label.pack(ipadx=4, ipady=2)
        def enter(event):
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 20
            tooltip.geometry(f"+{x}+{y}")
            tooltip.deiconify()
        def leave(event):
            tooltip.withdraw()
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)
    
    def _should_show_launcher_toggle(self, package_name):
        # Show toggle if .y1 or .y1app in package name
        return package_name and (".y1" in package_name or ".y1app" in package_name)

    def on_nav_bar_click(self, event):
        """Handle clicks on the virtual nav bar: left=back, right=home"""
        canvas_height = int(self.screen_canvas.cget('height'))
        nav_y = canvas_height - self.nav_bar_height
        if event.y >= nav_y:
            if event.x < self.display_width // 2:
                # Left half: Back (circle)
                self.run_adb_command('shell input keyevent 4')  # KEYCODE_BACK
                self.status_var.set('Back button (virtual nav bar) pressed')
            else:
                # Right half: Home (triangle)
                self.run_adb_command('shell input keyevent 3')  # KEYCODE_HOME
                self.status_var.set('Home button (virtual nav bar) pressed')

    def show_context_menu(self, x, y):
        self.context_menu.tk_popup(x, y)

    def show_recent_apps(self):
        self.run_adb_command("shell input keyevent 187")  # KEYCODE_APP_SWITCH
        self.status_var.set("Recent Apps opened")

    def setup_bindings(self):
        # Global key bindings
        self.bind("<Alt_L>", self.toggle_launcher_control)
        self.bind("<Alt_R>", self.toggle_launcher_control)
        # Global key handling for all key presses
        self.bind_all("<Key>", self.on_key_press)

if __name__ == "__main__":
    app = Y1HelperApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop() 
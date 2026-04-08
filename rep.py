
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
import os
import sys
import json
import csv
import shutil
import urllib.request
import io

# --- OFFICIAL BRANDING COLORS ---
BRAND_BLUE = "#0C2340"     # PMS 289 C
BRAND_GOLD = "#FFBA00"
BRAND_WHITE = "#FFFFFF"
BRAND_OFFWHITE = "#F8F8F8"

# Semantic aliases
G_NAVY = BRAND_BLUE
G_GOLD = BRAND_GOLD
G_WHITE = BRAND_WHITE
G_OFFWHITE = BRAND_OFFWHITE

APP_NAME = "GoldenGriffinCadetDB"

# -------------------------
# PATH / RESOURCE HELPERS
# -------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_base_folder():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_app_data_dir():
    path = os.path.join(get_base_folder(), "app_data")
    os.makedirs(path, exist_ok=True)
    return path

APP_DATA_DIR = get_app_data_dir()
CADETS_JSON_PATH = os.path.join(APP_DATA_DIR, "CADETS.json")
PHOTOS_DIR = os.path.join(APP_DATA_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

# -------------------------
# DEFAULT / STORAGE
# -------------------------
DEFAULT_CADETS = [
    {
        "first": "John",
        "last": "Doe",
        "email": "j.doe@canisius.edu",
        "phone": "555-0123",
        "station1": "Fort Liberty",
        "station2": "Fort Moore",
        "branch": "Infantry",
        "status": "Commissioned",
        "year": "2024",
        "image_path": None
    }
]

def load_cadets():
    if os.path.exists(CADETS_JSON_PATH):
        try:
            with open(CADETS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as e:
            messagebox.showwarning("Load Warning", f"Could not load saved cadet data.\n\n{e}")
    return DEFAULT_CADETS.copy()

def save_cadets():
    try:
        with open(CADETS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(cadets, f, indent=2)
    except Exception as e:
        messagebox.showerror("Save Error", f"Could not save records.\n\n{e}")

def safe_copy_photo_to_app(fp, first, last):
    if not fp or not os.path.exists(fp):
        return None

    ext = os.path.splitext(fp)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        messagebox.showwarning("Invalid Image", "Only .jpg, .jpeg, and .png files are supported.")
        return None

    clean_first = first.strip().replace(" ", "_") or "Unknown"
    clean_last = last.strip().replace(" ", "_") or "Cadet"
    base_name = f"{clean_first}_{clean_last}"
    dest_name = base_name + ext
    dest_path = os.path.join(PHOTOS_DIR, dest_name)

    counter = 1
    while os.path.exists(dest_path):
        dest_name = f"{base_name}_{counter}{ext}"
        dest_path = os.path.join(PHOTOS_DIR, dest_name)
        counter += 1

    try:
        shutil.copy2(fp, dest_path)
        return dest_path
    except Exception as e:
        messagebox.showwarning("Photo Copy Warning", f"Photo could not be copied.\n\n{e}")
        return None

def delete_local_photo_if_managed(photo_path):
    try:
        if photo_path and os.path.exists(photo_path) and os.path.dirname(photo_path) == PHOTOS_DIR:
            os.remove(photo_path)
    except Exception:
        pass

def export_json_backup():
    if not cadets:
        messagebox.showinfo("Export", "No cadet data to export.")
        return

    fp = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json")],
        title="Export Cadet Data to JSON"
    )
    if not fp:
        return

    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(cadets, f, indent=2)
        messagebox.showinfo("Export Success", f"JSON backup saved to:\n\n{fp}")
    except Exception as e:
        messagebox.showerror("Export Error", f"Could not export JSON backup.\n\n{e}")

def export_csv():
    if not cadets:
        messagebox.showinfo("Export", "No cadet data to export.")
        return

    fp = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        title="Export Cadet Data to CSV"
    )
    if not fp:
        return

    fieldnames = ["first", "last", "year", "branch", "status", "email", "phone", "station1", "station2", "image_path"]

    try:
        with open(fp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for cadet in cadets:
                row = {field: cadet.get(field, "") for field in fieldnames}
                writer.writerow(row)
        messagebox.showinfo("Export Success", f"CSV saved to:\n\n{fp}")
    except Exception as e:
        messagebox.showerror("Export Error", f"Could not export CSV.\n\n{e}")

def import_json_backup():
    global cadets

    fp = filedialog.askopenfilename(
        filetypes=[("JSON files", "*.json")],
        title="Import Cadet Data from JSON"
    )
    if not fp:
        return

    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            messagebox.showerror("Import Error", "Selected JSON file is not a valid cadet list.")
            return

        cadets = data
        save_cadets()
        show_all()
        messagebox.showinfo("Import Success", f"Cadet data imported from:\n\n{fp}")
    except Exception as e:
        messagebox.showerror("Import Error", f"Could not import JSON backup.\n\n{e}")

# -------------------------
# DATA
# -------------------------
cadets = load_cadets()

# -------------------------
# UI FUNCTIONS
# -------------------------
def open_full_profile(cadet):
    profile_win = tk.Toplevel(root)
    profile_win.title(f"Official Record: {cadet.get('first','')} {cadet.get('last','')}")
    profile_win.geometry("480x750")
    profile_win.configure(bg=G_NAVY, padx=30, pady=30)

    img_frame = tk.Frame(
        profile_win,
        width=220,
        height=220,
        bg=G_GOLD,
        highlightthickness=2,
        highlightbackground=G_WHITE
    )
    img_frame.pack(pady=10)
    img_frame.pack_propagate(False)

    img_label = tk.Label(
        img_frame,
        text="NO PHOTO",
        bg=G_NAVY,
        fg=G_WHITE,
        font=("Arial", 10, "bold")
    )
    img_label.pack(expand=True, fill="both", padx=5, pady=5)

    img_path = cadet.get("image_path")
    if img_path and os.path.exists(img_path):
        try:
            img = Image.open(img_path)
            img.thumbnail((210, 210))
            photo = ImageTk.PhotoImage(img)
            img_label.config(image=photo, text="")
            img_label.image = photo
        except Exception:
            img_label.config(text="IMAGE ERROR")

    tk.Label(
        profile_win,
        text=f"{str(cadet.get('first','')).upper()} {str(cadet.get('last','')).upper()}",
        font=("Times New Roman", 20, "bold"),
        bg=G_NAVY,
        fg=G_GOLD
    ).pack(pady=(15, 0))

    tk.Label(
        profile_win,
        text=f"Golden Griffin Battalion • Class of {cadet.get('year','N/A')}",
        font=("Arial", 11, "italic"),
        bg=G_NAVY,
        fg=G_WHITE
    ).pack(pady=(0, 20))

    details_frame = tk.Frame(profile_win, bg=G_NAVY)
    details_frame.pack(fill="x")

    info = [
        ("BRANCH", cadet.get("branch")),
        ("STATUS", cadet.get("status")),
        ("EMAIL", cadet.get("email")),
        ("PHONE", cadet.get("phone")),
        ("1ST STATION", cadet.get("station1")),
        ("2ND STATION", cadet.get("station2"))
    ]

    for label, value in info:
        row = tk.Frame(details_frame, bg=G_NAVY)
        row.pack(fill="x", pady=3)

        tk.Label(
            row,
            text=f"{label}:",
            font=("Arial", 9, "bold"),
            bg=G_NAVY,
            fg=G_GOLD,
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)

        tk.Label(
            row,
            text=str(value) if value is not None else "",
            font=("Arial", 10),
            bg=G_NAVY,
            fg=G_WHITE,
            anchor="w"
        ).pack(side=tk.LEFT)

    tk.Button(
        profile_win,
        text="CLOSE RECORD",
        command=profile_win.destroy,
        bg=G_GOLD,
        fg=G_NAVY,
        font=("Arial", 10, "bold"),
        relief="flat"
    ).pack(pady=30)

def add_cadet():
    add_win = tk.Toplevel(root)
    add_win.title("Battalion Record Entry")
    add_win.geometry("500x680")
    add_win.configure(bg=G_OFFWHITE)

    header = tk.Frame(add_win, bg=G_NAVY, height=60)
    header.pack(fill="x")
    tk.Label(
        header,
        text="NEW CADET REGISTRATION",
        font=("Arial", 14, "bold"),
        bg=G_NAVY,
        fg=G_GOLD
    ).pack(pady=15)

    form_container = tk.Frame(add_win, bg=G_OFFWHITE, padx=40, pady=20)
    form_container.pack(fill="both", expand=True)

    fields = [
        ("First Name", "first"),
        ("Last Name", "last"),
        ("Comm. Year", "year"),
        ("Branch", "branch"),
        ("Email", "email"),
        ("Phone Number", "phone"),
        ("1st Duty Station", "station1"),
        ("2nd Duty Station", "station2"),
        ("Commission Status", "status")
    ]

    entries = {}
    current_image_path = [None]

    for i, (label_text, key) in enumerate(fields):
        tk.Label(
            form_container,
            text=label_text,
            bg=G_OFFWHITE,
            fg=G_NAVY,
            font=("Arial", 10, "bold")
        ).grid(row=i, column=0, sticky="e", pady=5)

        entry = tk.Entry(form_container, width=30, relief="solid")
        entry.grid(row=i, column=1, padx=15, pady=5)
        entries[key] = entry

    path_label = tk.Label(
        form_container,
        text="No Image Uploaded",
        fg="red",
        bg=G_OFFWHITE,
        font=("Arial", 8)
    )
    path_label.grid(row=len(fields), column=1, sticky="w")

    def select_image():
        fp = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if fp:
            current_image_path[0] = fp
            path_label.config(text=os.path.basename(fp), fg="green")

    tk.Button(
        form_container,
        text="📷 UPLOAD PHOTO",
        command=select_image,
        bg=G_NAVY,
        fg=G_WHITE,
        relief="flat"
    ).grid(row=len(fields), column=0, pady=10)

    def save_new_cadet():
        first = entries["first"].get().strip()
        last = entries["last"].get().strip()

        if not first or not last:
            messagebox.showerror("Error", "Required fields: First Name and Last Name")
            return

        new_data = {key: entry.get().strip() for key, entry in entries.items()}
        new_data["image_path"] = safe_copy_photo_to_app(current_image_path[0], first, last)

        cadets.append(new_data)
        save_cadets()
        add_win.destroy()
        show_all()
        messagebox.showinfo("Saved", f"{first} {last} was added successfully.")

    tk.Button(
        add_win,
        text="SAVE TO BATTALION ARCHIVE",
        command=save_new_cadet,
        bg="#28a745",
        fg="white",
        font=("Arial", 11, "bold"),
        pady=10,
        relief="flat"
    ).pack(fill="x", side="bottom")

def open_edit_window(cadet_index):
    cadet = cadets[cadet_index]

    edit_win = tk.Toplevel(root)
    edit_win.title(f"Edit Record: {cadet.get('first','')} {cadet.get('last','')}")
    edit_win.geometry("540x760")
    edit_win.configure(bg=G_OFFWHITE)

    header = tk.Frame(edit_win, bg=G_NAVY, height=60)
    header.pack(fill="x")
    tk.Label(
        header,
        text="EDIT CADET RECORD",
        font=("Arial", 14, "bold"),
        bg=G_NAVY,
        fg=G_GOLD
    ).pack(pady=15)

    form_container = tk.Frame(edit_win, bg=G_OFFWHITE, padx=40, pady=20)
    form_container.pack(fill="both", expand=True)

    fields = [
        ("First Name", "first"),
        ("Last Name", "last"),
        ("Comm. Year", "year"),
        ("Branch", "branch"),
        ("Email", "email"),
        ("Phone Number", "phone"),
        ("1st Duty Station", "station1"),
        ("2nd Duty Station", "station2"),
        ("Commission Status", "status")
    ]

    entries = {}
    photo_action = {"mode": "keep", "new_path": None}

    for i, (label_text, key) in enumerate(fields):
        tk.Label(
            form_container,
            text=label_text,
            bg=G_OFFWHITE,
            fg=G_NAVY,
            font=("Arial", 10, "bold")
        ).grid(row=i, column=0, sticky="e", pady=5)

        entry = tk.Entry(form_container, width=32, relief="solid")
        entry.grid(row=i, column=1, padx=15, pady=5)
        entry.insert(0, cadet.get(key, ""))
        entries[key] = entry

    current_photo = cadet.get("image_path")
    current_photo_name = os.path.basename(current_photo) if current_photo else "No Photo Assigned"

    path_label = tk.Label(
        form_container,
        text=current_photo_name,
        fg="green" if current_photo else "red",
        bg=G_OFFWHITE,
        font=("Arial", 8)
    )
    path_label.grid(row=len(fields), column=1, sticky="w", pady=(0, 8))

    def change_photo():
        fp = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if fp:
            photo_action["mode"] = "replace"
            photo_action["new_path"] = fp
            path_label.config(text=f"New: {os.path.basename(fp)}", fg="green")

    def remove_photo():
        photo_action["mode"] = "remove"
        photo_action["new_path"] = None
        path_label.config(text="Photo will be removed", fg="red")

    photo_btn_frame = tk.Frame(form_container, bg=G_OFFWHITE)
    photo_btn_frame.grid(row=len(fields) + 1, column=0, columnspan=2, pady=10)

    tk.Button(
        photo_btn_frame,
        text="🖼 CHANGE PHOTO",
        command=change_photo,
        bg=G_NAVY,
        fg=G_WHITE,
        relief="flat",
        padx=10
    ).pack(side=tk.LEFT, padx=5)

    tk.Button(
        photo_btn_frame,
        text="❌ REMOVE PHOTO",
        command=remove_photo,
        bg="#d9534f",
        fg="white",
        relief="flat",
        padx=10
    ).pack(side=tk.LEFT, padx=5)

    def save_changes():
        first = entries["first"].get().strip()
        last = entries["last"].get().strip()

        if not first or not last:
            messagebox.showerror("Error", "Required fields: First Name and Last Name")
            return

        old_photo = cadet.get("image_path")

        updated_data = {key: entry.get().strip() for key, entry in entries.items()}

        if photo_action["mode"] == "replace":
            new_photo = safe_copy_photo_to_app(photo_action["new_path"], first, last)
            updated_data["image_path"] = new_photo
            if new_photo and old_photo != new_photo:
                delete_local_photo_if_managed(old_photo)

        elif photo_action["mode"] == "remove":
            updated_data["image_path"] = None
            delete_local_photo_if_managed(old_photo)

        else:
            updated_data["image_path"] = old_photo

        cadets[cadet_index] = updated_data
        save_cadets()
        edit_win.destroy()
        show_all()
        messagebox.showinfo("Updated", f"{first} {last} was updated successfully.")

    tk.Button(
        edit_win,
        text="SAVE CHANGES",
        command=save_changes,
        bg="#28a745",
        fg="white",
        font=("Arial", 11, "bold"),
        pady=10,
        relief="flat"
    ).pack(fill="x", side="bottom")

def edit_cadet():
    if not cadets:
        messagebox.showinfo("Edit", "No cadets to edit.")
        return

    edit_select_win = tk.Toplevel(root)
    edit_select_win.title("Edit Cadet Record")
    edit_select_win.geometry("560x430")
    edit_select_win.configure(bg=G_OFFWHITE, padx=20, pady=20)

    tk.Label(
        edit_select_win,
        text="SELECT A CADET TO EDIT",
        font=("Arial", 12, "bold"),
        bg=G_OFFWHITE,
        fg=G_NAVY
    ).pack(pady=(0, 10))

    listbox = tk.Listbox(
        edit_select_win,
        width=65,
        height=15,
        font=("Arial", 10),
        bg=G_WHITE,
        fg=G_NAVY,
        selectbackground=G_NAVY,
        selectforeground=G_WHITE
    )
    listbox.pack(pady=10)

    indexed = list(enumerate(cadets))
    indexed.sort(key=lambda t: (str(t[1].get("last", "")).lower(), str(t[1].get("first", "")).lower()))

    for original_index, c in indexed:
        display = f"{c.get('last','')}, {c.get('first','')} | {c.get('branch','Unassigned')} | Class {c.get('year','N/A')}"
        listbox.insert(tk.END, display)

    def open_selected():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("Edit", "Select a cadet first.")
            return
        chosen_row = sel[0]
        original_index, _ = indexed[chosen_row]
        edit_select_win.destroy()
        open_edit_window(original_index)

    tk.Button(
        edit_select_win,
        text="EDIT SELECTED",
        command=open_selected,
        bg=G_GOLD,
        fg=G_NAVY,
        font=("Arial", 10, "bold"),
        relief="flat",
        padx=10,
        pady=8
    ).pack(pady=8)

    tk.Button(
        edit_select_win,
        text="CANCEL",
        command=edit_select_win.destroy,
        bg=G_NAVY,
        fg=G_WHITE,
        font=("Arial", 10, "bold"),
        relief="flat",
        padx=10,
        pady=8
    ).pack(pady=4)

def delete_cadet():
    if not cadets:
        messagebox.showinfo("Delete", "No cadets to delete.")
        return

    del_win = tk.Toplevel(root)
    del_win.title("Delete Cadet Record")
    del_win.geometry("520x420")
    del_win.configure(bg=G_OFFWHITE, padx=20, pady=20)

    tk.Label(
        del_win,
        text="SELECT A CADET TO DELETE",
        font=("Arial", 12, "bold"),
        bg=G_OFFWHITE,
        fg=G_NAVY
    ).pack(pady=(0, 10))

    listbox = tk.Listbox(
        del_win,
        width=60,
        height=14,
        font=("Arial", 10),
        bg=G_WHITE,
        fg=G_NAVY,
        selectbackground=G_NAVY,
        selectforeground=G_WHITE
    )
    listbox.pack(pady=10)

    indexed = list(enumerate(cadets))
    indexed.sort(key=lambda t: (str(t[1].get("last", "")).lower(), str(t[1].get("first", "")).lower()))

    for original_index, c in indexed:
        display = f"{c.get('last','')}, {c.get('first','')} | {c.get('branch','Unassigned')} | Class {c.get('year','N/A')}"
        listbox.insert(tk.END, display)

    def confirm_delete():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("Delete", "Select a cadet first.")
            return

        chosen_row = sel[0]
        original_index, c = indexed[chosen_row]
        name = f"{c.get('first','')} {c.get('last','')}".strip()

        if not messagebox.askyesno("Confirm Delete", f"Delete record for:\n\n{name}\n\nThis cannot be undone."):
            return

        img_path = c.get("image_path")
        delete_local_photo_if_managed(img_path)

        del cadets[original_index]
        save_cadets()
        del_win.destroy()
        show_all()

    tk.Button(
        del_win,
        text="DELETE SELECTED",
        command=confirm_delete,
        bg="#d9534f",
        fg="white",
        font=("Arial", 10, "bold"),
        relief="flat",
        padx=10,
        pady=8
    ).pack(pady=8)

    tk.Button(
        del_win,
        text="CANCEL",
        command=del_win.destroy,
        bg=G_NAVY,
        fg=G_WHITE,
        font=("Arial", 10, "bold"),
        relief="flat",
        padx=10,
        pady=8
    ).pack(pady=4)

# -------------------------
# DISPLAY LOGIC
# -------------------------
def display_entry(c, stable_idx):
    tag_name = f"cadet_{stable_idx}"

    display_box.insert(tk.END, "  ▶ ", "bullet")
    display_box.insert(tk.END, f"{c.get('first','').upper()} {c.get('last','').upper()} ", tag_name)
    display_box.insert(tk.END, f"[Class of {c.get('year', 'N/A')}]\n", "year_tag")

    display_box.tag_configure(tag_name, foreground=G_NAVY, font=("Arial", 11, "bold"), underline=True)
    display_box.tag_configure("bullet", foreground=G_GOLD, font=("Arial", 11, "bold"))
    display_box.tag_configure("year_tag", foreground="#666666", font=("Arial", 10))

    display_box.tag_bind(tag_name, "<Button-1>", lambda e, curr_c=c: open_full_profile(curr_c))
    display_box.tag_bind(tag_name, "<Enter>", lambda e: display_box.config(cursor="hand2"))
    display_box.tag_bind(tag_name, "<Leave>", lambda e: display_box.config(cursor=""))

    display_box.insert(
        tk.END,
        f"      Duty Station: {c.get('station1', 'TBD')} | Status: {c.get('status', '')}\n\n"
    )

def show_all():
    display_box.config(state="normal")
    display_box.delete(1.0, tk.END)

    if not cadets:
        display_box.insert(tk.END, "No cadet records found.\n")
        display_box.config(state="disabled")
        return

    indexed = list(enumerate(cadets))
    indexed.sort(key=lambda t: str(t[1].get("branch", "Unassigned")).lower())

    current_branch = None
    for stable_idx, c in indexed:
        branch = str(c.get("branch", "Unassigned")).upper()
        if branch != current_branch:
            current_branch = branch
            display_box.insert(tk.END, f" {current_branch} \n", "header")
            display_box.tag_configure(
                "header",
                font=("Arial", 12, "bold"),
                foreground=G_WHITE,
                background=G_NAVY
            )
            display_box.insert(tk.END, "\n")
        display_entry(c, stable_idx)

    display_box.config(state="disabled")

def search_cadet():
    query = ent_search.get().strip().lower()
    display_box.config(state="normal")
    display_box.delete(1.0, tk.END)

    if not query:
        show_all()
        return

    found_any = False
    for idx, c in enumerate(cadets):
        if any(query in str(val).lower() for val in c.values()):
            display_entry(c, idx)
            found_any = True

    if not found_any:
        display_box.insert(tk.END, "No matching cadets found.\n")

    display_box.config(state="disabled")

# -------------------------
# MAIN UI SETUP
# -------------------------
root = tk.Tk()
root.title("Golden Griffin Battalion | Cadet Repertoire Database")
root.geometry("1180x880")
root.configure(bg=G_OFFWHITE)

top_bar = tk.Frame(root, bg=G_NAVY, height=140)
top_bar.pack(fill="x")

branding_container = tk.Frame(top_bar, bg=G_NAVY)
branding_container.pack(expand=True, pady=10)

local_logo_path = resource_path(os.path.join("assets", "griffin_logo.png"))
logo_url = "https://logos-world.net/wp-content/uploads/2020/06/Canisius-Golden-Griffins-Logo.png"

loaded_logo = False

if os.path.exists(local_logo_path):
    try:
        img_data = Image.open(local_logo_path)
        img_data.thumbnail((120, 120))
        b_logo = ImageTk.PhotoImage(img_data)

        logo_label = tk.Label(branding_container, image=b_logo, bg=G_NAVY)
        logo_label.image = b_logo
        logo_label.pack(side=tk.LEFT, padx=20)
        loaded_logo = True
    except Exception:
        loaded_logo = False

if not loaded_logo:
    try:
        req = urllib.request.Request(logo_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as url:
            raw_data = url.read()

        img_data = Image.open(io.BytesIO(raw_data))
        img_data.thumbnail((120, 120))
        b_logo = ImageTk.PhotoImage(img_data)

        logo_label = tk.Label(branding_container, image=b_logo, bg=G_NAVY)
        logo_label.image = b_logo
        logo_label.pack(side=tk.LEFT, padx=20)
        loaded_logo = True
    except Exception:
        tk.Label(
            branding_container,
            text="[GRIFFIN EMBLEM]",
            font=("Arial", 10, "bold"),
            fg=G_GOLD,
            bg=G_NAVY,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=10
        ).pack(side=tk.LEFT, padx=20)

text_inner = tk.Frame(branding_container, bg=G_NAVY)
text_inner.pack(side=tk.LEFT)

tk.Label(
    text_inner,
    text="GOLDEN GRIFFIN BATTALION",
    font=("Times New Roman", 28, "bold"),
    bg=G_NAVY,
    fg=G_GOLD
).pack(anchor="w")

tk.Label(
    text_inner,
    text="CANISIUS UNIVERSITY ARMY ROTC DATABASE",
    font=("Arial", 11, "bold"),
    bg=G_NAVY,
    fg=G_WHITE
).pack(anchor="w")

# Search row
s_frame = tk.Frame(root, bg=G_OFFWHITE, pady=20)
s_frame.pack()

tk.Label(
    s_frame,
    text="FIND CADET:",
    font=("Arial", 10, "bold"),
    bg=G_OFFWHITE,
    fg=G_NAVY
).pack(side=tk.LEFT, padx=5)

ent_search = tk.Entry(s_frame, width=40, font=("Arial", 11), relief="solid")
ent_search.pack(side=tk.LEFT, padx=5)

tk.Button(
    s_frame,
    text="SEARCH ARCHIVE",
    command=search_cadet,
    bg=G_NAVY,
    fg=G_WHITE,
    relief="flat",
    padx=15
).pack(side=tk.LEFT, padx=5)

tk.Button(
    s_frame,
    text="CLEAR",
    command=lambda: (ent_search.delete(0, tk.END), show_all()),
    bg=G_GOLD,
    fg=G_NAVY,
    relief="flat",
    padx=12
).pack(side=tk.LEFT, padx=5)

# Main buttons
b_frame = tk.Frame(root, bg=G_OFFWHITE)
b_frame.pack(pady=10)

btn_style = {
    "font": ("Arial", 9, "bold"),
    "relief": "flat",
    "width": 15,
    "cursor": "hand2",
    "pady": 5
}

tk.Button(
    b_frame,
    text="➕ ADD RECORD",
    command=add_cadet,
    bg="#28a745",
    fg="white",
    **btn_style
).pack(side=tk.LEFT, padx=5)

tk.Button(
    b_frame,
    text="✏ EDIT RECORD",
    command=edit_cadet,
    bg=G_GOLD,
    fg=G_NAVY,
    **btn_style
).pack(side=tk.LEFT, padx=5)

tk.Button(
    b_frame,
    text="📋 VIEW ALL",
    command=show_all,
    bg=G_GOLD,
    fg=G_NAVY,
    **btn_style
).pack(side=tk.LEFT, padx=5)

tk.Button(
    b_frame,
    text="🗑 DELETE",
    command=delete_cadet,
    bg="#d9534f",
    fg="white",
    **btn_style
).pack(side=tk.LEFT, padx=5)

tk.Button(
    b_frame,
    text="💾 EXPORT JSON",
    command=export_json_backup,
    bg=G_NAVY,
    fg=G_WHITE,
    **btn_style
).pack(side=tk.LEFT, padx=5)

tk.Button(
    b_frame,
    text="📄 EXPORT CSV",
    command=export_csv,
    bg=G_NAVY,
    fg=G_WHITE,
    **btn_style
).pack(side=tk.LEFT, padx=5)

tk.Button(
    b_frame,
    text="📥 IMPORT JSON",
    command=import_json_backup,
    bg=G_GOLD,
    fg=G_NAVY,
    **btn_style
).pack(side=tk.LEFT, padx=5)

info_frame = tk.Frame(root, bg=G_OFFWHITE)
info_frame.pack(pady=(5, 10))

tk.Label(
    info_frame,
    text=f"Data folder: {APP_DATA_DIR}",
    font=("Arial", 9, "italic"),
    bg=G_OFFWHITE,
    fg="#555555"
).pack()

display_box = tk.Text(
    root,
    height=27,
    width=130,
    bg=G_WHITE,
    fg=G_NAVY,
    relief="solid",
    font=("Arial", 10),
    padx=20,
    pady=20
)
display_box.pack(pady=10)

show_all()
root.mainloop()
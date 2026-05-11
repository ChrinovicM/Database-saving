"""
GoldenGriffinCadetDB  v2.0
Canisius University Army ROTC — Battalion Cadet Database
---------------------------------------------------------
Changes from v1:
  • Proper login window with Admin / User roles
  • Multi-user accounts table (username + hashed password + role)
  • ttk.Treeview directory replaces raw tk.Text box
  • Live search-as-you-type + dropdown filters (branch / year / status)
  • Tabbed layout  → Directory | Statistics | Admin Panel
  • Audit log table (who changed what and when)
  • save_cadets() replaced with proper INSERT/UPDATE/DELETE per record
  • Removed unused imports (FileViewer, formattable2, duplicate os/sys)
  • Session lock after 10 minutes of inactivity
  • Added component field: Active Duty / Reserve / National Guard
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
import os, sys, json, csv, shutil, io, base64, secrets, hashlib, datetime, traceback
import sqlite3
import urllib.request
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ──────────────────────────────────────────
#  BRANDING
# ──────────────────────────────────────────
BRAND_BLUE    = "#0C2340"
BRAND_GOLD    = "#FFBA00"
BRAND_WHITE   = "#FFFFFF"
BRAND_OFFWHITE= "#F8F8F8"
G_NAVY   = BRAND_BLUE
G_GOLD   = BRAND_GOLD
G_WHITE  = BRAND_WHITE
G_OFFWHITE = BRAND_OFFWHITE
APP_NAME = "GoldenGriffinCadetDB"
SESSION_TIMEOUT_MS = 10 * 60 * 1000   # 10 minutes

# ──────────────────────────────────────────
#  PATH HELPERS
# ──────────────────────────────────────────
def resource_path(rel):
    try:    base = sys._MEIPASS
    except: base = os.path.abspath(".")
    return os.path.join(base, rel)

def get_base_folder():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_app_data_dir():
    p = os.path.join(get_base_folder(), "app_data")
    os.makedirs(p, exist_ok=True)
    return p

APP_DATA_DIR = get_app_data_dir()
PHOTOS_DIR   = os.path.join(APP_DATA_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

DB_PATH = os.path.join(APP_DATA_DIR, "cadets.db")

# ──────────────────────────────────────────
#  DATABASE SETUP
# ──────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Cadets table
    c.execute("""CREATE TABLE IF NOT EXISTS cadets (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        first      TEXT NOT NULL,
        last       TEXT NOT NULL,
        email      TEXT,
        station1   TEXT,
        station2   TEXT,
        branch     TEXT,
        status     TEXT,
        year       TEXT,
        component  TEXT,
        notes      TEXT,
        image_path TEXT
    )""")

    # Users / roles table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        username   TEXT UNIQUE NOT NULL,
        salt       TEXT NOT NULL,
        hash       TEXT NOT NULL,
        role       TEXT NOT NULL DEFAULT 'user',
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # Audit log
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        username   TEXT,
        action     TEXT,
        detail     TEXT,
        timestamp  TEXT DEFAULT (datetime('now'))
    )""")

    conn.commit()

    # Migrate existing databases — add component column if missing
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(cadets)").fetchall()]
    if "component" not in existing_cols:
        c.execute("ALTER TABLE cadets ADD COLUMN component TEXT DEFAULT ''")
        conn.commit()
        print("[DB] Migrated: added 'component' column to cadets table.")
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        _create_user(conn, "admin", "admin123", "admin")
        print("[DB] Default admin created  →  username: admin  password: admin123")
        print("[DB] PLEASE change this password immediately via Admin Panel → User Management.")

    # Seed a sample cadet if table empty
    c.execute("SELECT COUNT(*) FROM cadets")
    if c.fetchone()[0] == 0:
        c.execute("""INSERT INTO cadets
            (first,last,email,station1,station2,branch,status,year,component,notes,image_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("John","Doe","j.doe@canisius.edu","Fort Liberty","Fort Moore",
             "Infantry","Commissioned","2024","Active Duty","Sample cadet record.",None))
        conn.commit()

    conn.close()

def _create_user(conn, username, password, role):
    salt = secrets.token_hex(16)
    h    = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()
    conn.cursor().execute(
        "INSERT OR IGNORE INTO users (username,salt,hash,role) VALUES (?,?,?,?)",
        (username, salt, h, role))
    conn.commit()

def verify_user(username, password):
    """Returns role string or None."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT salt, hash, role FROM users WHERE username=?", (username,))
    row  = c.fetchone()
    conn.close()
    if not row:
        return None
    salt, stored_hash, role = row
    attempt = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()
    return role if attempt == stored_hash else None

# ──────────────────────────────────────────
#  AUDIT LOG
# ──────────────────────────────────────────
def log_action(username, action, detail=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute(
            "INSERT INTO audit_log (username,action,detail) VALUES (?,?,?)",
            (username, action, detail))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ──────────────────────────────────────────
#  PHOTO HELPERS
# ──────────────────────────────────────────
def safe_copy_photo(fp, first, last):
    if not fp or not os.path.exists(fp):
        return None
    ext = os.path.splitext(fp)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        messagebox.showwarning("Invalid Image", "Only .jpg .jpeg .png are supported.")
        return None
    base = f"{first.strip().replace(' ','_') or 'Unknown'}_{last.strip().replace(' ','_') or 'Cadet'}"
    dest = os.path.join(PHOTOS_DIR, base + ext)
    i = 1
    while os.path.exists(dest):
        dest = os.path.join(PHOTOS_DIR, f"{base}_{i}{ext}"); i += 1
    try:
        shutil.copy2(fp, dest); return dest
    except Exception as e:
        messagebox.showwarning("Photo Warning", str(e)); return None

def delete_managed_photo(path):
    try:
        if path and os.path.exists(path) and os.path.dirname(os.path.abspath(path)) == os.path.abspath(PHOTOS_DIR):
            os.remove(path)
    except Exception:
        pass

# ──────────────────────────────────────────
#  CADET DATA ACCESS
# ──────────────────────────────────────────
CADET_FIELDS = ("id","first","last","email","station1","station2",
                "branch","status","year","component","notes","image_path")

def row_to_dict(row):
    return dict(zip(CADET_FIELDS, row))

def load_all_cadets():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.cursor().execute(
        "SELECT id,first,last,email,station1,station2,branch,status,year,component,notes,image_path "
        "FROM cadets ORDER BY last,first").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def db_insert_cadet(data):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""INSERT INTO cadets
        (first,last,email,station1,station2,branch,status,year,component,notes,image_path)
        VALUES (:first,:last,:email,:station1,:station2,:branch,:status,:year,:component,:notes,:image_path)""", data)
    new_id = cur.lastrowid
    conn.commit(); conn.close()
    return new_id

def db_update_cadet(data):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("""UPDATE cadets SET
        first=:first, last=:last, email=:email,
        station1=:station1, station2=:station2,
        branch=:branch, status=:status, year=:year,
        component=:component, notes=:notes, image_path=:image_path
        WHERE id=:id""", data)
    conn.commit(); conn.close()

def db_delete_cadet(cadet_id):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("DELETE FROM cadets WHERE id=?", (cadet_id,))
    conn.commit(); conn.close()

# ──────────────────────────────────────────
#  LOGIN WINDOW
# ──────────────────────────────────────────
class LoginWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Golden Griffin Battalion — Sign In")
        self.geometry("440x380")
        self.resizable(False, False)
        self.configure(bg=G_NAVY)
        self.result = None          # (username, role) on success
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()

    def _build(self):
        # Header
        tk.Label(self, text="GOLDEN GRIFFIN BATTALION",
                 font=("Times New Roman", 18, "bold"),
                 bg=G_NAVY, fg=G_GOLD).pack(pady=(30, 0))
        tk.Label(self, text="Cadet Repertoire Database",
                 font=("Arial", 10), bg=G_NAVY, fg=G_WHITE).pack(pady=(0, 25))

        form = tk.Frame(self, bg=G_NAVY)
        form.pack(padx=50, fill="x")

        tk.Label(form, text="Username", bg=G_NAVY, fg=G_WHITE,
                 font=("Arial", 10, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self.ent_user = tk.Entry(form, width=28, font=("Arial", 11), relief="solid")
        self.ent_user.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        tk.Label(form, text="Password", bg=G_NAVY, fg=G_WHITE,
                 font=("Arial", 10, "bold"), anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        self.ent_pass = tk.Entry(form, width=28, font=("Arial", 11), relief="solid", show="●")
        self.ent_pass.grid(row=3, column=0, sticky="ew", pady=(0, 20))

        self.lbl_err = tk.Label(form, text="", bg=G_NAVY, fg="#FF6B6B",
                                font=("Arial", 9))
        self.lbl_err.grid(row=4, column=0)

        tk.Button(self, text="SIGN IN", command=self._attempt,
                  bg=G_GOLD, fg=G_NAVY, font=("Arial", 11, "bold"),
                  relief="flat", padx=20, pady=8, cursor="hand2").pack(pady=10)

        tk.Label(self, text="Default admin: admin / admin123",
                 font=("Arial", 8, "italic"), bg=G_NAVY, fg="#888888").pack(pady=(0, 10))

        self.ent_user.focus()
        self.bind("<Return>", lambda e: self._attempt())

    def _attempt(self):
        username = self.ent_user.get().strip()
        password = self.ent_pass.get()
        if not username or not password:
            self.lbl_err.config(text="Please enter username and password.")
            return
        role = verify_user(username, password)
        if role is None:
            self.lbl_err.config(text="Invalid username or password.")
            self.ent_pass.delete(0, tk.END)
            return
        self.result = (username, role)
        self.destroy()

    def _cancel(self):
        self.destroy()

# ──────────────────────────────────────────
#  CADET FORM  (shared by Add + Edit)
# ──────────────────────────────────────────
# Branches grouped under Logistics Corps per current Army structure
LOGISTICS_BRANCHES = {
    "Quartermaster", "Transportation", "Ordnance"
}

BRANCH_OPTIONS = [
    "",
    # Combat Arms
    "Air Defense Artillery",
    "Armor",
    "Aviation",
    "Field Artillery",
    "Infantry",
    "Special Forces",
    # Combat Support
    "Chemical",
    "Corps of Engineers",
    "Cyber",
    "Military Intelligence",
    "Military Police",
    "Signal",
    # Logistics (Quartermaster, Transportation, Ordnance consolidated)
    "Logistics — Ordnance",
    "Logistics — Quartermaster",
    "Logistics — Transportation",
    # Combat Service Support / Other
    "Adjutant General",
    "Finance",
    "Judge Advocate",
    "Medical Service",
    "Intelligence",
]
STATUS_OPTIONS    = ["","Contracted","MS1","MS2","MS3","MS4","Commissioned","Separated","Alumni"]
COMPONENT_OPTIONS = ["","Active Duty","Reserve","National Guard"]

class CadetFormWindow(tk.Toplevel):
    """
    Reusable cadet form.  Pass cadet dict to pre-populate (edit mode).
    on_save(data_dict) is called with the final data.
    """
    def __init__(self, parent, title, on_save, cadet=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("540x840")
        self.resizable(False, False)
        self.configure(bg=G_OFFWHITE)
        self.on_save = on_save
        self.cadet   = cadet or {}
        self._photo_action = {"mode": "keep", "new_path": None}
        self.grab_set()
        self._build()

    def _build(self):
        # Header bar
        hdr = tk.Frame(self, bg=G_NAVY, height=56)
        hdr.pack(fill="x")
        tk.Label(hdr, text=self.title(), font=("Arial", 13, "bold"),
                 bg=G_NAVY, fg=G_GOLD).pack(pady=14)

        body = tk.Frame(self, bg=G_OFFWHITE, padx=40, pady=16)
        body.pack(fill="both", expand=True)

        fields = [
            ("First Name *",      "first",     "entry"),
            ("Last Name *",       "last",      "entry"),
            ("Comm. Year",        "year",      "entry"),
            ("Branch",            "branch",    "combo"),
            ("Commission Status", "status",    "combo"),
            ("Component",         "component", "combo"),
            ("Email",             "email",     "entry"),
            ("1st Duty Station",  "station1",  "entry"),
            ("2nd Duty Station",  "station2",  "entry"),
        ]

        self.vars = {}
        for i, (label, key, kind) in enumerate(fields):
            tk.Label(body, text=label, bg=G_OFFWHITE, fg=G_NAVY,
                     font=("Arial", 10, "bold"), anchor="w").grid(
                         row=i*2, column=0, columnspan=2, sticky="w", pady=(8, 0))
            if kind == "combo":
                if key == "branch":
                    opts = BRANCH_OPTIONS
                elif key == "component":
                    opts = COMPONENT_OPTIONS
                else:
                    opts = STATUS_OPTIONS
                var  = tk.StringVar(value=self.cadet.get(key, ""))
                cb   = ttk.Combobox(body, textvariable=var, values=opts,
                                    state="readonly", width=38)
                cb.grid(row=i*2+1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
                self.vars[key] = var
            else:
                var = tk.StringVar(value=self.cadet.get(key, ""))
                tk.Entry(body, textvariable=var, width=40,
                         font=("Arial", 10), relief="solid").grid(
                             row=i*2+1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
                self.vars[key] = var

        # Notes
        row_base = len(fields) * 2
        tk.Label(body, text="Notes / Remarks", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold"), anchor="w").grid(
                     row=row_base, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.txt_notes = tk.Text(body, width=40, height=3,
                                  font=("Arial", 10), relief="solid")
        self.txt_notes.insert("1.0", self.cadet.get("notes", "") or "")
        self.txt_notes.grid(row=row_base+1, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        # Photo row
        photo_row = row_base + 2
        tk.Label(body, text="Photo", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold"), anchor="w").grid(
                     row=photo_row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        btn_frame = tk.Frame(body, bg=G_OFFWHITE)
        btn_frame.grid(row=photo_row+1, column=0, columnspan=2, sticky="w")

        current = self.cadet.get("image_path")
        self.lbl_photo = tk.Label(btn_frame,
                                  text=os.path.basename(current) if current else "No photo",
                                  fg="green" if current else "gray",
                                  bg=G_OFFWHITE, font=("Arial", 9))
        self.lbl_photo.pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(btn_frame, text="📷 Change", command=self._choose_photo,
                  bg=G_NAVY, fg=G_WHITE, relief="flat", font=("Arial", 9),
                  padx=8, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="✕ Remove", command=self._remove_photo,
                  bg="#d9534f", fg=G_WHITE, relief="flat", font=("Arial", 9),
                  padx=8, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=2)

        # Save button
        tk.Button(self, text="💾  SAVE RECORD", command=self._save,
                  bg="#28a745", fg=G_WHITE, font=("Arial", 11, "bold"),
                  relief="flat", pady=10, cursor="hand2").pack(
                      fill="x", side="bottom")

    def _choose_photo(self):
        fp = filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg *.jpeg *.png")], parent=self)
        if fp:
            self._photo_action = {"mode": "replace", "new_path": fp}
            self.lbl_photo.config(text=f"New: {os.path.basename(fp)}", fg="green")

    def _remove_photo(self):
        self._photo_action = {"mode": "remove", "new_path": None}
        self.lbl_photo.config(text="Will be removed", fg="red")

    def _save(self):
        first = self.vars["first"].get().strip()
        last  = self.vars["last"].get().strip()
        if not first or not last:
            messagebox.showerror("Validation", "First Name and Last Name are required.", parent=self)
            return

        data = {k: v.get().strip() for k, v in self.vars.items()}
        data["notes"]      = self.txt_notes.get("1.0", "end-1c").strip()
        data["id"]         = self.cadet.get("id")

        old_photo = self.cadet.get("image_path")
        mode      = self._photo_action["mode"]
        if mode == "replace":
            new_photo = safe_copy_photo(self._photo_action["new_path"], first, last)
            data["image_path"] = new_photo
            if new_photo and old_photo != new_photo:
                delete_managed_photo(old_photo)
        elif mode == "remove":
            data["image_path"] = None
            delete_managed_photo(old_photo)
        else:
            data["image_path"] = old_photo

        self.on_save(data)
        self.destroy()

# ──────────────────────────────────────────
#  FULL PROFILE POPUP
# ──────────────────────────────────────────
class ProfileWindow(tk.Toplevel):
    def __init__(self, parent, cadet):
        super().__init__(parent)
        self.title(f"Record — {cadet.get('first','')} {cadet.get('last','')}")
        self.geometry("460x720")
        self.configure(bg=G_NAVY, padx=30, pady=20)
        self._build(cadet)

    def _build(self, c):
        # Photo
        img_frame = tk.Frame(self, width=210, height=210, bg=G_GOLD,
                              highlightthickness=2, highlightbackground=G_WHITE)
        img_frame.pack(pady=10)
        img_frame.pack_propagate(False)
        img_lbl = tk.Label(img_frame, text="NO PHOTO", bg=G_NAVY, fg=G_WHITE,
                           font=("Arial", 10, "bold"))
        img_lbl.pack(expand=True, fill="both", padx=5, pady=5)
        path = c.get("image_path")
        if path and os.path.exists(path):
            try:
                img = Image.open(path); img.thumbnail((200, 200))
                ph  = ImageTk.PhotoImage(img)
                img_lbl.config(image=ph, text=""); img_lbl.image = ph
            except Exception:
                img_lbl.config(text="IMAGE ERROR")

        tk.Label(self,
                 text=f"{c.get('first','').upper()} {c.get('last','').upper()}",
                 font=("Times New Roman", 20, "bold"), bg=G_NAVY, fg=G_GOLD
                 ).pack(pady=(12, 0))
        tk.Label(self,
                 text=f"Golden Griffin Battalion  •  Class of {c.get('year','N/A')}",
                 font=("Arial", 10, "italic"), bg=G_NAVY, fg=G_WHITE
                 ).pack(pady=(0, 16))

        info = [
            ("BRANCH",      c.get("branch")),
            ("STATUS",      c.get("status")),
            ("COMPONENT",   c.get("component")),
            ("EMAIL",       c.get("email")),
            ("1ST STATION", c.get("station1")),
            ("2ND STATION", c.get("station2")),
            ("NOTES",       c.get("notes")),
        ]
        for label, val in info:
            row = tk.Frame(self, bg=G_NAVY); row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{label}:", font=("Arial", 9, "bold"),
                     bg=G_NAVY, fg=G_GOLD, width=13, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=val or "—", font=("Arial", 10),
                     bg=G_NAVY, fg=G_WHITE, anchor="w", wraplength=280,
                     justify="left").pack(side=tk.LEFT)

        tk.Button(self, text="CLOSE", command=self.destroy,
                  bg=G_GOLD, fg=G_NAVY, font=("Arial", 10, "bold"),
                  relief="flat", pady=6, cursor="hand2").pack(pady=20)

# ──────────────────────────────────────────
#  MAIN APPLICATION WINDOW
# ──────────────────────────────────────────
class App(tk.Tk):
    def __init__(self, username, role):
        super().__init__()
        self.username   = username
        self.role       = role              # "admin" or "user"
        self.is_admin   = (role == "admin")
        self._timeout_id = None

        self.title("Golden Griffin Battalion | Cadet Repertoire Database")
        self.geometry("1200x900")
        self.configure(bg=G_OFFWHITE)
        self.minsize(900, 680)

        self._build_ui()
        self._reload_cadets()
        self._reset_timeout()

    # ── UI CONSTRUCTION ─────────────────────
    def _build_ui(self):
        self._build_header()
        self._build_notebook()

    def _build_header(self):
        bar = tk.Frame(self, bg=G_NAVY, height=110)
        bar.pack(fill="x")

        inner = tk.Frame(bar, bg=G_NAVY)
        inner.pack(expand=True, pady=10)

        # Logo
        local_logo = resource_path(os.path.join("assets", "griffin_logo.png"))
        logo_url   = "https://logos-world.net/wp-content/uploads/2020/06/Canisius-Golden-Griffins-Logo.png"
        loaded = False
        for src in [local_logo]:
            if os.path.exists(src):
                try:
                    img = Image.open(src); img.thumbnail((90, 90))
                    ph  = ImageTk.PhotoImage(img)
                    lbl = tk.Label(inner, image=ph, bg=G_NAVY); lbl.image = ph
                    lbl.pack(side=tk.LEFT, padx=16)
                    loaded = True; break
                except Exception:
                    pass
        if not loaded:
            try:
                req = urllib.request.Request(logo_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=4) as u:
                    raw = u.read()
                img = Image.open(io.BytesIO(raw)); img.thumbnail((90, 90))
                ph  = ImageTk.PhotoImage(img)
                lbl = tk.Label(inner, image=ph, bg=G_NAVY); lbl.image = ph
                lbl.pack(side=tk.LEFT, padx=16); loaded = True
            except Exception:
                pass
        if not loaded:
            tk.Label(inner, text="[EMBLEM]", font=("Arial", 9, "bold"),
                     fg=G_GOLD, bg=G_NAVY, relief="solid", padx=8, pady=8
                     ).pack(side=tk.LEFT, padx=16)

        txt = tk.Frame(inner, bg=G_NAVY)
        txt.pack(side=tk.LEFT)
        tk.Label(txt, text="GOLDEN GRIFFIN BATTALION",
                 font=("Times New Roman", 26, "bold"), bg=G_NAVY, fg=G_GOLD
                 ).pack(anchor="w")
        tk.Label(txt, text="CANISIUS UNIVERSITY  |  ARMY ROTC CADET DATABASE",
                 font=("Arial", 10, "bold"), bg=G_NAVY, fg=G_WHITE).pack(anchor="w")
        tk.Label(txt, text=f"Signed in as  {self.username}  ({self.role.upper()})",
                 font=("Arial", 9, "italic"), bg=G_NAVY, fg=G_GOLD).pack(anchor="w")

        # Sign-out button
        tk.Button(bar, text="Sign Out", command=self._sign_out,
                  bg=G_GOLD, fg=G_NAVY, font=("Arial", 9, "bold"),
                  relief="flat", padx=10, pady=4, cursor="hand2"
                  ).place(relx=1.0, rely=0.5, anchor="e", x=-20)

    def _build_notebook(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",        background=G_OFFWHITE, borderwidth=0)
        style.configure("TNotebook.Tab",    background="#DDDDDD", foreground=G_NAVY,
                         font=("Arial", 10, "bold"), padding=(16, 6))
        style.map("TNotebook.Tab",
                  background=[("selected", G_NAVY)],
                  foreground=[("selected", G_GOLD)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=8)

        # Tab 1 — Directory
        dir_frame = tk.Frame(nb, bg=G_OFFWHITE)
        nb.add(dir_frame, text="  📋  Directory  ")
        self._build_directory_tab(dir_frame)

        # Tab 2 — Statistics
        stats_frame = tk.Frame(nb, bg=G_OFFWHITE)
        nb.add(stats_frame, text="  📊  Statistics  ")
        self._build_stats_tab(stats_frame)

        # Tab 3 — Admin Panel (admin only)
        if self.is_admin:
            admin_frame = tk.Frame(nb, bg=G_OFFWHITE)
            nb.add(admin_frame, text="  🔒  Admin Panel  ")
            self._build_admin_tab(admin_frame)

        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

    # ── DIRECTORY TAB ────────────────────────
    def _build_directory_tab(self, parent):
        # ── Toolbar
        toolbar = tk.Frame(parent, bg=G_OFFWHITE, pady=8)
        toolbar.pack(fill="x", padx=10)

        btn_cfg = dict(font=("Arial", 9, "bold"), relief="flat",
                       padx=12, pady=5, cursor="hand2")

        if self.is_admin:
            tk.Button(toolbar, text="➕ Add", command=self._add_cadet,
                      bg="#28a745", fg=G_WHITE, **btn_cfg).pack(side=tk.LEFT, padx=3)
            tk.Button(toolbar, text="✏ Edit", command=self._edit_cadet,
                      bg=G_GOLD, fg=G_NAVY, **btn_cfg).pack(side=tk.LEFT, padx=3)
            tk.Button(toolbar, text="🗑 Delete", command=self._delete_cadet,
                      bg="#d9534f", fg=G_WHITE, **btn_cfg).pack(side=tk.LEFT, padx=3)
            tk.Frame(toolbar, width=2, bg="#CCCCCC").pack(side=tk.LEFT, padx=6, fill="y", pady=2)
            tk.Button(toolbar, text="💾 Export JSON", command=self._export_json,
                      bg=G_NAVY, fg=G_WHITE, **btn_cfg).pack(side=tk.LEFT, padx=3)
            tk.Button(toolbar, text="📄 Export CSV", command=self._export_csv,
                      bg=G_NAVY, fg=G_WHITE, **btn_cfg).pack(side=tk.LEFT, padx=3)
            tk.Button(toolbar, text="📥 Import JSON", command=self._import_json,
                      bg=G_NAVY, fg=G_WHITE, **btn_cfg).pack(side=tk.LEFT, padx=3)

        tk.Button(toolbar, text="👁 View Profile", command=self._view_profile,
                  bg=G_GOLD, fg=G_NAVY, **btn_cfg).pack(side=tk.LEFT, padx=3)

        # ── Search & Filter bar
        sf = tk.Frame(parent, bg=G_OFFWHITE, pady=6)
        sf.pack(fill="x", padx=10)

        tk.Label(sf, text="Search:", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._apply_filters())
        tk.Entry(sf, textvariable=self.var_search, width=28,
                 font=("Arial", 10), relief="solid").pack(side=tk.LEFT, padx=4)

        tk.Label(sf, text="Branch:", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(12, 4))
        self.var_branch = tk.StringVar(value="All")
        self.cb_branch  = ttk.Combobox(sf, textvariable=self.var_branch,
                                        state="readonly", width=18)
        self.cb_branch.pack(side=tk.LEFT, padx=4)
        self.cb_branch.bind("<<ComboboxSelected>>", lambda _: self._apply_filters())

        tk.Label(sf, text="Year:", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(8, 4))
        self.var_year = tk.StringVar(value="All")
        self.cb_year  = ttk.Combobox(sf, textvariable=self.var_year,
                                      state="readonly", width=8)
        self.cb_year.pack(side=tk.LEFT, padx=4)
        self.cb_year.bind("<<ComboboxSelected>>", lambda _: self._apply_filters())

        tk.Label(sf, text="Status:", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(8, 4))
        self.var_status = tk.StringVar(value="All")
        self.cb_status  = ttk.Combobox(sf, textvariable=self.var_status,
                                        state="readonly", width=14)
        self.cb_status.pack(side=tk.LEFT, padx=4)
        self.cb_status.bind("<<ComboboxSelected>>", lambda _: self._apply_filters())

        tk.Label(sf, text="Component:", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(8, 4))
        self.var_component = tk.StringVar(value="All")
        self.cb_component  = ttk.Combobox(sf, textvariable=self.var_component,
                                           values=["All"] + COMPONENT_OPTIONS[1:],
                                           state="readonly", width=14)
        self.cb_component.pack(side=tk.LEFT, padx=4)
        self.cb_component.bind("<<ComboboxSelected>>", lambda _: self._apply_filters())

        tk.Button(sf, text="✕ Clear", command=self._clear_filters,
                  bg=G_GOLD, fg=G_NAVY, font=("Arial", 9, "bold"),
                  relief="flat", padx=10, pady=4, cursor="hand2"
                  ).pack(side=tk.LEFT, padx=8)

        self.lbl_count = tk.Label(sf, text="", bg=G_OFFWHITE, fg="#555555",
                                  font=("Arial", 9, "italic"))
        self.lbl_count.pack(side=tk.RIGHT, padx=8)

        # ── Treeview
        tv_frame = tk.Frame(parent)
        tv_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        cols = ("last", "first", "year", "branch", "status", "component", "station1", "email")
        self.tree = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                  selectmode="browse")

        headers = {
            "last":      ("Last Name",   150),
            "first":     ("First Name",  120),
            "year":      ("Class Year",   80),
            "branch":    ("Branch",      155),
            "status":    ("Status",      110),
            "component": ("Component",   120),
            "station1":  ("1st Station", 140),
            "email":     ("Email",       185),
        }
        for col, (heading, width) in headers.items():
            self.tree.heading(col, text=heading,
                              command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=width, minwidth=60)

        # Alternating row colors
        self.tree.tag_configure("odd",  background=G_WHITE)
        self.tree.tag_configure("even", background="#EEF2F7")

        vsb = ttk.Scrollbar(tv_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal",  command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _: self._view_profile())
        self._sort_col   = None
        self._sort_rev   = False

    # ── STATS TAB ────────────────────────────
    def _build_stats_tab(self, parent):
        self.stats_frame = parent
        lbl = tk.Label(parent, text="Statistics will load when you switch to this tab.",
                       font=("Arial", 11), bg=G_OFFWHITE, fg=G_NAVY)
        lbl.pack(pady=40)

    def _refresh_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()

        cadets = self.all_cadets

        tk.Label(self.stats_frame, text="Battalion Statistics",
                 font=("Times New Roman", 18, "bold"), bg=G_OFFWHITE, fg=G_NAVY
                 ).pack(pady=(24, 4))
        tk.Label(self.stats_frame,
                 text=f"As of {datetime.datetime.now().strftime('%B %d, %Y')}",
                 font=("Arial", 10, "italic"), bg=G_OFFWHITE, fg="#666666"
                 ).pack(pady=(0, 20))

        # Summary cards
        cards_row = tk.Frame(self.stats_frame, bg=G_OFFWHITE)
        cards_row.pack(pady=8)

        commissioned = sum(1 for c in cadets if c.get("status","").lower() == "commissioned")
        branches     = set(c.get("branch","") for c in cadets if c.get("branch"))
        years        = set(c.get("year","")   for c in cadets if c.get("year"))

        for label, val in [
            ("Total Cadets",     len(cadets)),
            ("Commissioned",     commissioned),
            ("Branches",         len(branches)),
            ("Class Years",      len(years)),
        ]:
            card = tk.Frame(cards_row, bg=G_NAVY, padx=24, pady=16,
                            relief="flat", bd=0)
            card.pack(side=tk.LEFT, padx=12)
            tk.Label(card, text=str(val), font=("Arial", 28, "bold"),
                     bg=G_NAVY, fg=G_GOLD).pack()
            tk.Label(card, text=label, font=("Arial", 9),
                     bg=G_NAVY, fg=G_WHITE).pack()

        # Branch breakdown
        tk.Label(self.stats_frame, text="Cadets by Branch",
                 font=("Arial", 13, "bold"), bg=G_OFFWHITE, fg=G_NAVY
                 ).pack(pady=(24, 6))

        from collections import Counter
        branch_counts = Counter(c.get("branch","Unassigned") or "Unassigned" for c in cadets)
        max_count     = max(branch_counts.values(), default=1)

        # Separate Logistics branches so they render as a sub-group
        logistics_keys = [b for b in branch_counts if b.startswith("Logistics")]
        other_keys     = [b for b in branch_counts if not b.startswith("Logistics")]
        logistics_total = sum(branch_counts[b] for b in logistics_keys)

        bar_frame = tk.Frame(self.stats_frame, bg=G_OFFWHITE)
        bar_frame.pack(fill="x", padx=60)

        def _bar_row(parent, label, count, indent=False, bold=False):
            row = tk.Frame(parent, bg=G_OFFWHITE)
            row.pack(fill="x", pady=1)
            lbl_text  = ("  " if indent else "") + label
            lbl_font  = ("Arial", 10, "bold") if bold else ("Arial", 10)
            bar_color = G_NAVY if bold else G_GOLD
            tk.Label(row, text=lbl_text, font=lbl_font, bg=G_OFFWHITE,
                     fg=G_NAVY, width=30, anchor="e").pack(side=tk.LEFT)
            bar_w = max(4, int(260 * count / max_count))
            bar   = tk.Frame(row, bg=bar_color, height=16, width=bar_w)
            bar.pack(side=tk.LEFT, padx=6)
            bar.pack_propagate(False)
            tk.Label(row, text=str(count), font=("Arial", 9, "bold"),
                     bg=G_OFFWHITE, fg=G_NAVY).pack(side=tk.LEFT)

        # Non-logistics branches sorted by count
        for branch in sorted(other_keys, key=lambda b: -branch_counts[b]):
            _bar_row(bar_frame, branch, branch_counts[branch])

        # Logistics group header + sub-rows
        if logistics_keys:
            tk.Frame(bar_frame, bg="#CCCCCC", height=1).pack(fill="x", pady=4)
            _bar_row(bar_frame, "Logistics Corps (total)", logistics_total, bold=True)
            for branch in sorted(logistics_keys, key=lambda b: -branch_counts[b]):
                label = branch.replace("Logistics — ", "")
                _bar_row(bar_frame, label, branch_counts[branch], indent=True)

        # Status breakdown
        tk.Label(self.stats_frame, text="Cadets by Status",
                 font=("Arial", 13, "bold"), bg=G_OFFWHITE, fg=G_NAVY
                 ).pack(pady=(20, 6))

        status_counts = Counter(c.get("status","Unknown") or "Unknown" for c in cadets)
        tbl = tk.Frame(self.stats_frame, bg=G_OFFWHITE)
        tbl.pack()
        for i, (status, count) in enumerate(sorted(status_counts.items(), key=lambda x: -x[1])):
            bg = G_WHITE if i % 2 == 0 else "#EEF2F7"
            row = tk.Frame(tbl, bg=bg, padx=16, pady=4)
            row.pack(fill="x")
            tk.Label(row, text=status, font=("Arial", 10), bg=bg,
                     fg=G_NAVY, width=20, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=str(count), font=("Arial", 10, "bold"),
                     bg=bg, fg=G_NAVY).pack(side=tk.LEFT)

        # Component breakdown
        tk.Label(self.stats_frame, text="Cadets by Component",
                 font=("Arial", 13, "bold"), bg=G_OFFWHITE, fg=G_NAVY
                 ).pack(pady=(20, 6))

        component_counts = Counter(c.get("component","Unknown") or "Unknown" for c in cadets)
        comp_colors = {
            "Active Duty":    "#0C2340",
            "Reserve":        "#1a6b3a",
            "National Guard": "#8B4513",
            "Unknown":        "#888888",
        }
        comp_row = tk.Frame(self.stats_frame, bg=G_OFFWHITE)
        comp_row.pack(pady=4)
        for comp in ["Active Duty", "Reserve", "National Guard"]:
            count  = component_counts.get(comp, 0)
            color  = comp_colors.get(comp, G_NAVY)
            card   = tk.Frame(comp_row, bg=color, padx=20, pady=12, relief="flat")
            card.pack(side=tk.LEFT, padx=10)
            tk.Label(card, text=str(count), font=("Arial", 22, "bold"),
                     bg=color, fg=G_GOLD).pack()
            tk.Label(card, text=comp, font=("Arial", 9),
                     bg=color, fg=G_WHITE).pack()

    # ── ADMIN TAB ────────────────────────────
    def _build_admin_tab(self, parent):
        tk.Label(parent, text="Admin Panel",
                 font=("Times New Roman", 18, "bold"),
                 bg=G_OFFWHITE, fg=G_NAVY).pack(pady=(24, 4))

        btn_cfg = dict(font=("Arial", 10, "bold"), relief="flat",
                       padx=20, pady=8, cursor="hand2", width=22)

        sec = tk.Frame(parent, bg=G_OFFWHITE)
        sec.pack(pady=16)

        tk.Label(sec, text="USER MANAGEMENT", font=("Arial", 10, "bold"),
                 bg=G_OFFWHITE, fg="#888888").grid(row=0, column=0, columnspan=2,
                                                    pady=(0, 8), sticky="w")
        tk.Button(sec, text="➕ Add User Account",
                  command=self._admin_add_user,
                  bg="#28a745", fg=G_WHITE, **btn_cfg).grid(row=1, column=0, padx=8, pady=4)
        tk.Button(sec, text="🗑 Remove User Account",
                  command=self._admin_remove_user,
                  bg="#d9534f", fg=G_WHITE, **btn_cfg).grid(row=1, column=1, padx=8, pady=4)
        tk.Button(sec, text="🔑 Change My Password",
                  command=self._admin_change_password,
                  bg=G_NAVY, fg=G_WHITE, **btn_cfg).grid(row=2, column=0, padx=8, pady=4)
        tk.Button(sec, text="👥 View All Users",
                  command=self._admin_view_users,
                  bg=G_NAVY, fg=G_WHITE, **btn_cfg).grid(row=2, column=1, padx=8, pady=4)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=40, pady=16)

        sec2 = tk.Frame(parent, bg=G_OFFWHITE)
        sec2.pack(pady=4)
        tk.Label(sec2, text="AUDIT LOG", font=("Arial", 10, "bold"),
                 bg=G_OFFWHITE, fg="#888888").pack(pady=(0, 8))
        tk.Button(sec2, text="📜 View Audit Log",
                  command=self._admin_view_audit,
                  bg=G_NAVY, fg=G_WHITE, **btn_cfg).pack()

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=40, pady=16)

        sec3 = tk.Frame(parent, bg=G_OFFWHITE)
        sec3.pack()
        tk.Label(sec3, text="DATA MANAGEMENT", font=("Arial", 10, "bold"),
                 bg=G_OFFWHITE, fg="#888888").pack(pady=(0, 8))
        tk.Label(sec3,
                 text=f"Database: {DB_PATH}\nPhotos:   {PHOTOS_DIR}",
                 font=("Arial", 9, "italic"), bg=G_OFFWHITE, fg="#666666",
                 justify="left").pack(pady=4)

    # ── DATA HELPERS ────────────────────────
    def _reload_cadets(self):
        self.all_cadets = load_all_cadets()
        self._refresh_filter_dropdowns()
        self._apply_filters()

    def _refresh_filter_dropdowns(self):
        branches = sorted(set(c.get("branch","") for c in self.all_cadets if c.get("branch")))
        years    = sorted(set(c.get("year","")   for c in self.all_cadets if c.get("year")), reverse=True)
        statuses = sorted(set(c.get("status","") for c in self.all_cadets if c.get("status")))
        self.cb_branch["values"]    = ["All"] + branches
        self.cb_year["values"]      = ["All"] + years
        self.cb_status["values"]    = ["All"] + statuses
        # Component options are fixed; no need to derive from data

    def _apply_filters(self):
        query     = self.var_search.get().strip().lower()
        branch    = self.var_branch.get()
        year      = self.var_year.get()
        status    = self.var_status.get()
        component = self.var_component.get()

        filtered = self.all_cadets
        if query:
            filtered = [c for c in filtered
                        if any(query in str(v).lower() for v in c.values())]
        if branch != "All":
            filtered = [c for c in filtered if c.get("branch") == branch]
        if year != "All":
            filtered = [c for c in filtered if c.get("year") == year]
        if status != "All":
            filtered = [c for c in filtered if c.get("status") == status]
        if component != "All":
            filtered = [c for c in filtered if c.get("component") == component]

        self._populate_tree(filtered)
        self.lbl_count.config(
            text=f"{len(filtered)} of {len(self.all_cadets)} cadets")

    def _populate_tree(self, cadets):
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(cadets):
            tag  = "odd" if i % 2 == 0 else "even"
            vals = (c.get("last",""), c.get("first",""), c.get("year",""),
                    c.get("branch",""), c.get("status",""), c.get("component",""),
                    c.get("station1",""), c.get("email",""))
            self.tree.insert("", tk.END, iid=str(c["id"]), values=vals, tags=(tag,))

    def _sort_tree(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col; self._sort_rev = False
        self.all_cadets.sort(
            key=lambda c: str(c.get(col, "")).lower(),
            reverse=self._sort_rev)
        self._apply_filters()

    def _clear_filters(self):
        self.var_search.set("")
        self.var_branch.set("All")
        self.var_year.set("All")
        self.var_status.set("All")
        self.var_component.set("All")
        self._apply_filters()

    def _selected_cadet(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a cadet first.")
            return None
        cid = int(sel[0])
        return next((c for c in self.all_cadets if c["id"] == cid), None)

    # ── CADET ACTIONS ───────────────────────
    def _view_profile(self):
        c = self._selected_cadet()
        if c:
            ProfileWindow(self, c)

    def _add_cadet(self):
        def on_save(data):
            data.pop("id", None)
            new_id = db_insert_cadet(data)
            log_action(self.username, "ADD_CADET",
                       f"{data.get('first')} {data.get('last')} (id={new_id})")
            self._reload_cadets()
            messagebox.showinfo("Saved",
                f"{data.get('first')} {data.get('last')} added successfully.")
        CadetFormWindow(self, "NEW CADET REGISTRATION", on_save)

    def _edit_cadet(self):
        c = self._selected_cadet()
        if not c:
            return
        def on_save(data):
            db_update_cadet(data)
            log_action(self.username, "EDIT_CADET",
                       f"{data.get('first')} {data.get('last')} (id={data.get('id')})")
            self._reload_cadets()
            messagebox.showinfo("Updated",
                f"{data.get('first')} {data.get('last')} updated successfully.")
        CadetFormWindow(self, "EDIT CADET RECORD", on_save, cadet=c)

    def _delete_cadet(self):
        c = self._selected_cadet()
        if not c:
            return
        name = f"{c.get('first','')} {c.get('last','')}".strip()
        if not messagebox.askyesno("Confirm Delete",
            f"Permanently delete record for:\n\n{name}\n\nThis cannot be undone."):
            return
        delete_managed_photo(c.get("image_path"))
        db_delete_cadet(c["id"])
        log_action(self.username, "DELETE_CADET",
                   f"{name} (id={c['id']})")
        self._reload_cadets()

    # ── IMPORT / EXPORT ─────────────────────
    def _export_json(self):
        if not self.all_cadets:
            messagebox.showinfo("Export", "No cadet data to export."); return
        fp = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON files","*.json")], title="Export to JSON")
        if not fp: return
        try:
            with open(fp,"w",encoding="utf-8") as f:
                json.dump(self.all_cadets, f, indent=2)
            log_action(self.username, "EXPORT_JSON", fp)
            messagebox.showinfo("Export Success", f"Saved to:\n{fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_csv(self):
        if not self.all_cadets:
            messagebox.showinfo("Export", "No cadet data to export."); return
        fp = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV files","*.csv")], title="Export to CSV")
        if not fp: return
        fields = ["first","last","year","branch","status","component","email",
                  "station1","station2","notes","image_path"]
        try:
            with open(fp,"w",newline="",encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for c in self.all_cadets:
                    w.writerow({k: c.get(k,"") for k in fields})
            log_action(self.username, "EXPORT_CSV", fp)
            messagebox.showinfo("Export Success", f"Saved to:\n{fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _import_json(self):
        fp = filedialog.askopenfilename(filetypes=[("JSON files","*.json")],
                                         title="Import from JSON")
        if not fp: return
        try:
            with open(fp,"r",encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                messagebox.showerror("Import Error","File is not a valid cadet list."); return
            if not messagebox.askyesno("Confirm Import",
                f"Import {len(data)} records?\n\nExisting records are kept; duplicates will be added."):
                return
            for record in data:
                record.pop("id", None)
                record.setdefault("notes", "")
                db_insert_cadet(record)
            log_action(self.username, "IMPORT_JSON", f"{len(data)} records from {fp}")
            self._reload_cadets()
            messagebox.showinfo("Import Success", f"Imported {len(data)} records.")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    # ── ADMIN ACTIONS ───────────────────────
    def _admin_add_user(self):
        win = tk.Toplevel(self)
        win.title("Add User Account")
        win.geometry("380x300")
        win.configure(bg=G_OFFWHITE, padx=30, pady=20)
        win.grab_set()

        fields = {}
        for label, key, show in [
            ("Username", "user", ""),
            ("Password", "pass", "●"),
            ("Confirm Password", "pass2", "●"),
        ]:
            tk.Label(win, text=label, bg=G_OFFWHITE, fg=G_NAVY,
                     font=("Arial", 10, "bold")).pack(anchor="w", pady=(8,0))
            e = tk.Entry(win, width=34, font=("Arial", 10),
                         relief="solid", show=show)
            e.pack(fill="x")
            fields[key] = e

        tk.Label(win, text="Role:", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 10, "bold")).pack(anchor="w", pady=(8,0))
        role_var = tk.StringVar(value="user")
        ttk.Combobox(win, textvariable=role_var, values=["user","admin"],
                     state="readonly", width=12).pack(anchor="w")

        def do_add():
            uname = fields["user"].get().strip()
            pw    = fields["pass"].get()
            pw2   = fields["pass2"].get()
            if not uname or not pw:
                messagebox.showerror("Error","Username and password required.", parent=win); return
            if pw != pw2:
                messagebox.showerror("Error","Passwords do not match.", parent=win); return
            conn = sqlite3.connect(DB_PATH)
            _create_user(conn, uname, pw, role_var.get())
            conn.close()
            log_action(self.username, "ADD_USER", f"{uname} ({role_var.get()})")
            messagebox.showinfo("Success", f"User '{uname}' created.", parent=win)
            win.destroy()

        tk.Button(win, text="Create User", command=do_add,
                  bg="#28a745", fg=G_WHITE, font=("Arial", 10,"bold"),
                  relief="flat", pady=6, cursor="hand2").pack(pady=16, fill="x")

    def _admin_remove_user(self):
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute(
            "SELECT username, role FROM users ORDER BY username").fetchall()
        conn.close()
        if not rows:
            messagebox.showinfo("Users","No users found."); return
        win = tk.Toplevel(self)
        win.title("Remove User")
        win.geometry("360x340")
        win.configure(bg=G_OFFWHITE, padx=20, pady=20)
        win.grab_set()
        tk.Label(win, text="Select user to remove:",
                 bg=G_OFFWHITE, fg=G_NAVY, font=("Arial", 11,"bold")).pack(pady=(0,8))
        lb = tk.Listbox(win, font=("Arial", 10), height=10,
                        bg=G_WHITE, fg=G_NAVY,
                        selectbackground=G_NAVY, selectforeground=G_WHITE)
        lb.pack(fill="both", expand=True)
        for uname, role in rows:
            lb.insert(tk.END, f"{uname}  [{role}]")

        def do_remove():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("Select","Pick a user first.", parent=win); return
            uname = rows[sel[0]][0]
            if uname == self.username:
                messagebox.showerror("Error","Cannot remove your own account.", parent=win); return
            if not messagebox.askyesno("Confirm", f"Remove user '{uname}'?", parent=win): return
            conn2 = sqlite3.connect(DB_PATH)
            conn2.cursor().execute("DELETE FROM users WHERE username=?", (uname,))
            conn2.commit(); conn2.close()
            log_action(self.username,"REMOVE_USER", uname)
            messagebox.showinfo("Done", f"User '{uname}' removed.", parent=win)
            win.destroy()

        tk.Button(win, text="Remove Selected", command=do_remove,
                  bg="#d9534f", fg=G_WHITE, font=("Arial", 10,"bold"),
                  relief="flat", pady=6, cursor="hand2").pack(pady=10, fill="x")

    def _admin_view_users(self):
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute(
            "SELECT username, role, created_at FROM users ORDER BY username").fetchall()
        conn.close()
        win = tk.Toplevel(self)
        win.title("All User Accounts")
        win.geometry("500x360")
        win.configure(bg=G_OFFWHITE, padx=20, pady=20)
        win.grab_set()
        tk.Label(win, text="User Accounts", bg=G_OFFWHITE, fg=G_NAVY,
                 font=("Arial", 13,"bold")).pack(pady=(0,10))
        cols = ("username","role","created_at")
        tv   = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for col, hdr, w in [("username","Username",180),
                              ("role","Role",100),("created_at","Created",180)]:
            tv.heading(col, text=hdr); tv.column(col, width=w)
        for row in rows:
            tv.insert("", tk.END, values=row)
        tv.pack(fill="both", expand=True)

    def _admin_change_password(self):
        old  = simpledialog.askstring("Current Password","Enter your current password:", show="●", parent=self)
        if not old: return
        role = verify_user(self.username, old)
        if role is None:
            messagebox.showerror("Error","Incorrect current password."); return
        new  = simpledialog.askstring("New Password","Enter new password:", show="●", parent=self)
        if not new: return
        new2 = simpledialog.askstring("Confirm","Confirm new password:", show="●", parent=self)
        if new != new2:
            messagebox.showerror("Error","Passwords do not match."); return
        salt = secrets.token_hex(16)
        h    = hashlib.pbkdf2_hmac('sha256', new.encode(), salt.encode(), 200_000).hex()
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute("UPDATE users SET salt=?,hash=? WHERE username=?",
                              (salt, h, self.username))
        conn.commit(); conn.close()
        log_action(self.username,"CHANGE_PASSWORD","")
        messagebox.showinfo("Success","Password changed successfully.")

    def _admin_view_audit(self):
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute(
            "SELECT timestamp,username,action,detail FROM audit_log "
            "ORDER BY id DESC LIMIT 200").fetchall()
        conn.close()
        win = tk.Toplevel(self)
        win.title("Audit Log")
        win.geometry("760x480")
        win.configure(bg=G_OFFWHITE, padx=10, pady=10)
        win.grab_set()
        tk.Label(win, text="Audit Log  (last 200 entries)",
                 bg=G_OFFWHITE, fg=G_NAVY, font=("Arial", 13,"bold")).pack(pady=(0,8))
        cols = ("timestamp","username","action","detail")
        tv   = ttk.Treeview(win, columns=cols, show="headings", height=20)
        for col, hdr, w in [("timestamp","Timestamp",160),("username","User",100),
                              ("action","Action",140),("detail","Detail",320)]:
            tv.heading(col, text=hdr); tv.column(col, width=w)
        for row in rows:
            tv.insert("", tk.END, values=row)
        vsb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vsb.set)
        tv.pack(side=tk.LEFT, fill="both", expand=True)
        vsb.pack(side=tk.RIGHT, fill="y")

    # ── TAB CHANGE ──────────────────────────
    def _on_tab_change(self, event):
        tab_text = self.nb.tab(self.nb.select(), "text")
        if "Statistics" in tab_text:
            self._refresh_stats()

    # ── SESSION MANAGEMENT ──────────────────
    def _reset_timeout(self):
        if self._timeout_id:
            self.after_cancel(self._timeout_id)
        self._timeout_id = self.after(SESSION_TIMEOUT_MS, self._lock_session)
        self.bind_all("<Motion>",    lambda e: self._reset_timeout())
        self.bind_all("<KeyPress>",  lambda e: self._reset_timeout())

    def _lock_session(self):
        self.withdraw()
        result = ask_login(self)
        if result is None:
            self.destroy(); return
        username, role = result
        if username != self.username:
            messagebox.showwarning("Session","Please log in with the same account.")
            self.destroy(); return
        self.deiconify()
        self._reset_timeout()

    def _sign_out(self):
        log_action(self.username,"SIGN_OUT","")
        self.destroy()

# ──────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────
def ask_login(parent=None):
    """Show login window, return (username, role) or None."""
    if parent is None:
        dummy = tk.Tk(); dummy.withdraw()
    else:
        dummy = parent
    win = LoginWindow(dummy)
    dummy.wait_window(win)
    if parent is None:
        dummy.destroy()
    return win.result

def main():
    init_db()

    # Need a root window to host the login dialog
    root = tk.Tk()
    root.withdraw()

    result = ask_login(root)
    if result is None:
        root.destroy(); return

    root.destroy()

    username, role = result
    log_action(username,"SIGN_IN","")
    app = App(username, role)
    app.mainloop()

if __name__ == "__main__":
    main()

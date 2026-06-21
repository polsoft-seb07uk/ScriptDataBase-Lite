#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScriptDataBase Lite v3.0.8 – PyQt6
Napisany od zera: czysty, bez bledow, pelna funkcjonalnosc.

Zmiany v3.0.2:
  - Cache skompilowanych regex (detect_language + SyntaxHighlighter)
  - Debounce 150 ms w polu wyszukiwania
  - Czcionka edytora z ustawien stosowana natychmiast
  - Skrot Ctrl+Enter: uruchom z edytora bez zapisywania
  - ScriptRunWorker: output strumieniowany, brak zbednego bufora
  - Staly katalog danych: C:/.polsoft/ScriptDataBase

Zmiany v3.0.3:
  - Eksport ZIP: skrypty jako osobne pliki w podkatalogach kategorii + metadata JSON
  - Wyszukiwanie pelnotekstowe w kodzie z podswietleniem trafien

Zmiany v3.0.4:
  - UUID4 zamiast timestamp jako ID skryptu – brak kolizji przy masowym tworzeniu
  - Walidacja importu JSON: sprawdzenie wymaganych pol (name, code), typow,
    naprawa nieznanych kategorii, raport bledow z mozliwoscia pominięcia

Zmiany v3.0.5:
  - Znajdz / Zamien w edytorze (Ctrl+H): wyszukiwanie z opcjami (wielkosc liter,
    cale slowa, wyrazenia regularne), zamiana pojedyncza i zbiorcza
  - Podglad diff przy edycji istniejacego skryptu: porownanie ostatnio zapisanej
    wersji z biezaca tresc edytora (kolorowane dodane/usuniete linie)
  - Eksport z edytora: zapis kodu bezposrednio z zakladki Nowy/Edytuj do pliku,
    niezaleznie od zapisu skryptu do bazy

Zmiany v3.0.6:
  - Ulubione skrypty (pin): przycisk/skrot Ctrl+P/menu kontekstowe, przypiete
    skrypty zawsze na gorze listy, filtr "Tylko ulubione", oznaczenie 📌
  - Statystyki uruchomien: licznik run_count i data last_run zliczane przy
    kazdym realnym uruchomieniu skryptu (RunDialog), widoczne w podgladzie
  - Nowy dialog 📊 Statystyki (Narzedzia / Ctrl+T): skrypty wg kategorii,
    najczesciej uruchamiane (top 10), lista przypietych
  - Migracja wstecznej kompatybilnosci: stare wpisy scripts.json bez pol
    pinned/run_count/last_run sa automatycznie uzupelniane przy starcie
  - Duplikowanie skryptu resetuje jego statystyki (nowy, niezalezny wpis);
    edycja istniejacego skryptu juz ich nie zeruje

Zmiany v3.0.7:
  - Nowa zakladka 🧩 Snippety: niezalezna mini-baza krotkich fragmentow
    kodu, osobny plik snippets.json, wlasna lista z wyszukiwaniem i filtrem
    kategorii, edytor z podswietlaniem skladni
  - "⏎ Wstaw do edytora": wstrzykuje kod snippetu w pozycji kursora
    w glownym edytorze (zakladka Nowy/Edytuj) i przelacza na nia
  - "🧩 Zapisz zaznaczenie jako snippet" (menu Edycja): przenosi zaznaczony
    fragment (lub caly kod) z edytora skryptow do nowego snippetu
  - Motyw i czcionka edytora snippetow synchronizowane z ustawieniami
    aplikacji (tak samo jak pozostale edytory)

Zmiany v3.0.8:
  - Mozliwosc zamiany kolejnosci zakladek glownego okna: QTabWidget.setMovable
    (przeciaganie myszka na pasku) + sekcja "Kolejnosc zakladek" w Ustawieniach
    (lista drag&drop + przyciski W gore/W dol), obie metody w pelni synchroniczne
  - Kolejnosc zapisywana w settings.json (klucz tab_order) i przywracana
    przy starcie aplikacji
  - Wszystkie dotychczasowe odwolania self.tabs.setCurrentIndex(N) zastapione
    nawigacja po referencji do widgetu (_goto_tab) – przelaczanie zakladek
    z menu/akcji dziala poprawnie niezaleznie od ich biezacej kolejnosci
"""

import sys
import os
import json
import subprocess
import shutil
import re
import uuid
import zipfile
import platform
import datetime
import threading
import tempfile
import shlex
import difflib
from pathlib import Path
from typing import Optional, TypedDict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLabel, QLineEdit, QTextEdit, QPlainTextEdit,
    QPushButton, QComboBox, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QFileDialog, QDialog, QDialogButtonBox,
    QGroupBox, QFormLayout, QCheckBox, QSpinBox, QMenu,
    QFrame, QAbstractItemView, QTextBrowser, QProgressBar
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize,
    QRegularExpression
)
from PyQt6.QtGui import (
    QFont, QColor, QSyntaxHighlighter, QTextCharFormat,
    QKeySequence, QAction, QTextCursor,
    QShortcut, QTextDocument, QIcon
)

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
BASE_DIR  = Path("C:/.polsoft/ScriptDataBase")
BASE_DIR.mkdir(parents=True, exist_ok=True)   # utwórz katalog jeśli nie istnieje
DATA_FILE = BASE_DIR / "scripts.json"
SETT_FILE = BASE_DIR / "settings.json"
SNIP_FILE = BASE_DIR / "snippets.json"

def resource_path(name: str) -> str:
    """Zwraca ścieżkę do zasobu (np. ikony) - działa zarówno przy uruchomieniu
    ze źródeł, jak i po spakowaniu do EXE przez PyInstaller (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

ICON_PATH = resource_path("sdb.ico")


# ─────────────────────────────────────────────
#  TYPY DANYCH
# ─────────────────────────────────────────────
class Script(TypedDict, total=False):
    """Słownik reprezentujący jeden skrypt w bazie.
    total=False – pola statystyk (pinned, run_count, last_run) mogą
    być nieobecne w starych wpisach przed migracją."""
    id:        str
    name:      str
    code:      str
    category:  str
    tags:      str
    desc:      str
    date:      str
    pinned:    bool
    run_count: int
    last_run:  str | None


class AppSettings(TypedDict, total=False):
    theme:           str
    language:        str
    font_size:       int
    font_family:     str
    confirm_delete:  bool
    seed_builtins:   bool
    tab_order:       list
    window_geometry: str


class Snippet(TypedDict, total=False):
    id:       str
    name:     str
    code:     str
    category: str
    tags:     str
    desc:     str
    date:     str


def new_id() -> str:
    """Generuje unikalny identyfikator skryptu jako UUID4 (string).
    Zastępuje poprzednie timestamp*1000 – eliminuje ryzyko kolizji
    przy szybkim tworzeniu wielu skryptów naraz."""
    return str(uuid.uuid4())

# ─────────────────────────────────────────────
#  JSON helpers
# ─────────────────────────────────────────────
def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        # Nie kasuj cicho danych przy uszkodzonym JSON – zrób kopię,
        # żeby było co odzyskać, i zgłoś problem w konsoli.
        try:
            backup = path.with_name(f"{path.stem}.corrupt-{datetime.datetime.now():%Y%m%d%H%M%S}{path.suffix}")
            shutil.copy2(path, backup)
            print(f"[ScriptDataBase] Uszkodzony plik {path.name} ({e}); kopia zapasowa: {backup.name}",
                  file=sys.stderr)
        except Exception as e:
            print(f"[ScriptDataBase] Nie można zapisać kopii zapasowej {path.name}: {e}",
                  file=sys.stderr)
        return default

def save_json(path: Path, data):
    """Zapis atomowy: dane trafiają najpierw do pliku tymczasowego,
    a dopiero potem podmieniają plik docelowy – awaria w trakcie
    zapisu (np. brak miejsca na dysku) nie zniszczy istniejących danych."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        print(f"[ScriptDataBase] Błąd zapisu {path.name}: {e}", file=sys.stderr)
        raise

# ─────────────────────────────────────────────
#  I18N / JĘZYK (PL bazowy, EN nakładka słownikowa)
# ─────────────────────────────────────────────
class LanguageManager:
    """Polski jest językiem bazowym (klucze słownika EN są oryginalnymi
    tekstami PL użytymi w kodzie). tr(text) zwraca tłumaczenie angielskie,
    jeśli aktywny jest język 'en', w przeciwnym razie zwraca tekst bez zmian."""

    current = "en"

    EN = {
        # ── Okno / zakładki ──
        "🗄️ ScriptDataBase Lite v3.0.8": "🗄️ ScriptDataBase Lite v3.0.8",
        "➕ Nowy / Edytuj": "➕ New / Edit",
        "📋 Moje skrypty": "📋 My Scripts",
        "⚙️ Ustawienia": "⚙️ Settings",
        "ScriptDataBase Lite v3.0.8 gotowy  |  Ctrl+N: nowy  |  Ctrl+S: zapisz  |  Ctrl+Enter: uruchom":
            "ScriptDataBase Lite v3.0.8 ready  |  Ctrl+N: new  |  Ctrl+S: save  |  Ctrl+Enter: run",

        # ── Pasek menu ──
        "Plik": "File",
        "➕ Nowy skrypt": "➕ New script",
        "📂 Otwórz plik do edytora": "📂 Open file into editor",
        "💾 Zapisz skrypt": "💾 Save script",
        "📥 Importuj skrypty (JSON)": "📥 Import scripts (JSON)",
        "📤 Eksportuj wszystkie (JSON)": "📤 Export all (JSON)",
        "📁 Otwórz folder danych": "📁 Open data folder",
        "✖ Wyjdź": "✖ Exit",
        "Skrypty": "Scripts",
        "✏️ Edytuj wybrany": "✏️ Edit selected",
        "▶ Uruchom wybrany": "▶ Run selected",
        "📋 Kopiuj kod": "📋 Copy code",
        "🗑 Usuń wybrany": "🗑 Delete selected",
        "Widok": "View",
        "🌑 Motyw ciemny": "🌑 Dark theme",
        "☀️ Motyw jasny": "☀️ Light theme",
        "Narzędzia": "Tools",
        "🔄 Wykryj terminale": "🔄 Detect terminals",
        "🗑 Wyczyść edytor": "🗑 Clear editor",
        "🔡 Sortuj skrypty (A-Z)": "🔡 Sort scripts (A-Z)",
        "Pomoc": "Help",
        "ℹ️ O programie": "ℹ️ About",

        "▶ Uruchom z edytora": "▶ Run from editor",
        "📦 Eksportuj wszystkie (ZIP)": "📦 Export all (ZIP)",
        "Eksport ZIP": "ZIP Export",
        "Wyeksportowano do ZIP": "Exported to ZIP",
        "Brak skryptów do eksportu.": "No scripts to export.",
        "Błąd eksportu ZIP:": "ZIP export error:",
        "🔍 Szukaj (nazwa / tagi / opis / kod)...": "🔍 Search (name / tags / desc / code)...",
        "📄 Szukaj w kodzie": "📄 Search in code",
        "Przeszukuje również treść kodu skryptów": "Also searches script code content",
        "✅ w kodzie": "✅ in code",
        # ── Język / Switcher ──
        "🌐 Język": "🌐 Language",
        "Polski": "Polish",
        "Angielski": "English",
        "🇵🇱 Polski": "🇵🇱 Polish",
        "🇬🇧 Angielski": "🇬🇧 English",
        "Zmiana języka": "Language change",
        "Aby zastosować nowy język, aplikacja zostanie zrestartowana.\nKontynuować?":
            "The application needs to restart to apply the new language.\nContinue?",

        # ── Zakładka: Nowy / Edytuj ──
        "Nazwa skryptu...": "Script name...",
        "Nazwa:": "Name:",
        "Kategoria:": "Category:",
        "Tagi:": "Tags:",
        "tag1,tag2,tag3": "tag1,tag2,tag3",
        "Krótki opis skryptu...": "Short script description...",
        "Opis:": "Description:",
        "Język:": "Language:",
        "—": "—",
        "🔍 Auto-wykryj": "🔍 Auto-detect",
        "🗑 Wyczyść": "🗑 Clear",
        "# Wpisz lub wklej tutaj kod skryptu...": "# Type or paste your script code here...",
        "💾 Zapisz ustawienia": "💾 Save settings",
        "📋 Kopiuj": "📋 Copy",
        "Linie:": "Lines:",
        "Znaki:": "Characters:",
        "✅ Skopiowano do schowka!": "✅ Copied to clipboard!",
        "Błąd": "Error",
        "Podaj nazwę skryptu.": "Enter a script name.",
        "Kod skryptu jest pusty.": "Script code is empty.",

        # ── Zakładka: Moje skrypty ──
        "🔍 Szukaj (nazwa / tagi / opis)...": "🔍 Search (name / tags / description)...",
        "Wszystkie": "All",
        "✏️ Edytuj": "✏️ Edit",
        "▶ Uruchom": "▶ Run",
        "🗑 Usuń": "🗑 Delete",
        "📤 Eksportuj": "📤 Export",
        "Skryptów:": "Scripts:",
        "Usuń skrypt": "Delete script",
        "Usunąć": "Delete",
        "Eksportuj skrypt": "Export script",
        "Skrypt": "Script",
        "Eksport": "Export",
        "Zaznacz skrypt na liście.": "Select a script from the list.",
        "Wyeksportowano": "Exported",
        "skryptów.": "scripts.",

        # ── Dialog uruchamiania ──
        "Uruchom skrypt": "Run script",
        "Terminal:": "Terminal:",
        "(brak terminali)": "(no terminals)",
        "Argumenty:": "Arguments:",
        "opcjonalne argumenty...": "optional arguments...",
        "Zapisz do pliku tymczasowego i uruchom": "Save to temp file and run",
        "Wyjście skryptu pojawi się tutaj...": "Script output will appear here...",
        "Zamknij": "Close",
        "Brak terminali": "No terminals",
        "Nie wykryto żadnych terminali.": "No terminals were detected.",
        "Nieznany terminal.": "Unknown terminal.",
        "(brak wyjścia)": "(no output)",
        "Timeout (30s).": "Timeout (30s).",
        "Błąd:": "Error:",
        "Zapisano do:": "Saved to:",
        "Uruchamianie w terminalu...": "Launching in terminal...",

        # ── Ustawienia ──
        "Motyw": "Theme",
        "🌑 Ciemny (Dark)": "🌑 Dark",
        "☀️ Jasny (Light)": "☀️ Light",
        "Czcionka edytora": "Editor font",
        "Rozmiar:": "Size:",
        "Rodzina:": "Family:",
        "Ogólne": "General",
        "Potwierdzaj usuwanie skryptów": "Confirm script deletion",
        "↩ Przywróć domyślne": "↩ Restore defaults",
        "Ustawienia": "Settings",
        "Ustawienia zapisane.": "Settings saved.",

        # ── O programie ──
        "O programie – ScriptDataBase Lite v3.0.8": "About – ScriptDataBase Lite v3.0.8",
        "🗄️ ScriptDataBase Lite": "🗄️ ScriptDataBase Lite",
        "wersja 3.0.8  •  PyQt6": "version 3.0.8  •  PyQt6",
        "Autor": "Author",
        "<b>Imię i nazwisko:</b>": "<b>Name:</b>",
        "<b>Organizacja:</b>": "<b>Organization:</b>",
        "<b>GitHub:</b>": "<b>GitHub:</b>",
        "<b>E-mail:</b>": "<b>E-mail:</b>",
        "<b>Licencja:</b>": "<b>License:</b>",
        "Freeware – wolne oprogramowanie": "Freeware – free software",
        "Środowisko": "Environment",
        "<b>Python:</b>": "<b>Python:</b>",
        "<b>Platforma:</b>": "<b>Platform:</b>",
        "<b>Katalog:</b>": "<b>Directory:</b>",
        "OK": "OK",
        "© 2025 Sebastian Januchowski / polsoft.ITS™ Group\n"
        "Program jest darmowy (Freeware). Dozwolone jest używanie\n"
        "i dystrybuowanie bez modyfikacji, z zachowaniem informacji o autorze.":
            "© 2025 Sebastian Januchowski / polsoft.ITS™ Group\n"
            "This program is freeware. You may use and distribute it\n"
            "without modification, provided author credit is retained.",

        "Błędy walidacji": "Validation errors",
        "nie jest obiektem JSON.": "is not a JSON object.",
        "brak wymaganych pól:": "missing required fields:",
        "i jeszcze": "and",
        "błędów": "more errors",
        "Znaleziono błędy w": "Found errors in",
        "rekordach": "records",
        "Zaimportować tylko poprawne rekordy?": "Import only valid records?",
        "Pominiętych (błędy walidacji):": "Skipped (validation errors):",

        # ── Pliki / import / export ──
        "Otwórz plik": "Open file",
        "Importuj skrypty": "Import scripts",
        "Eksportuj wszystkie": "Export all",
        "Oczekiwano listy skryptów.": "A list of scripts was expected.",
        "Błąd importu": "Import error",
        "Nie można otworzyć pliku:": "Could not open file:",
        "Import": "Import",
        "Zaimportowano": "Imported",
        "nowych skryptów.": "new scripts.",

        # ── Pasek stanu ──
        "Posortowano skrypty A-Z.": "Scripts sorted A-Z.",
        "Terminale:": "Terminals:",
        "(brak)": "(none)",
        "✅ Zaktualizowano:": "✅ Updated:",
        "✅ Zapisano:": "✅ Saved:",
        "🗑 Usunięto:": "🗑 Deleted:",
        "📑 Zduplikowano:": "📑 Duplicated:",
        "📑 Duplikuj": "📑 Duplicate",
        "kopia": "copy",

        # ── Uruchamianie skryptów (async) ──
        "Usuń plik tymczasowy po zakończeniu": "Delete temp file when finished",
        "⏹ Zatrzymaj": "⏹ Stop",
        "Uruchamianie...": "Running...",
        "Przerwano przez użytkownika.": "Stopped by user.",
        "Timeout": "Timeout",

        # ── Niezapisane zmiany ──
        "Niezapisane zmiany": "Unsaved changes",
        "Masz niezapisany skrypt w edytorze. Czy na pewno chcesz wyjść?":
            "You have an unsaved script in the editor. Are you sure you want to exit?",
        "Masz niezapisane zmiany w edytorze. Czy na pewno chcesz je wyczyścić?":
            "You have unsaved changes in the editor. Are you sure you want to clear them?",
        "Nazwa już istnieje": "Name already exists",
        "Skrypt o nazwie": "A script named",
        "już istnieje. Zapisać mimo to jako osobny wpis?":
            "already exists. Save it anyway as a separate entry?",

        # ── Znajdź / Zamień (Ctrl+H) ──
        "🔍 Znajdź / Zamień": "🔍 Find / Replace",
        "Tekst do znalezienia...": "Text to find...",
        "Znajdź:": "Find:",
        "Tekst zastępczy...": "Replacement text...",
        "Zamień na:": "Replace with:",
        "Uwzględnij wielkość liter": "Match case",
        "Całe słowa": "Whole words",
        "Wyrażenie regularne": "Regular expression",
        "Znajdź dalej": "Find next",
        "Zamień": "Replace",
        "Zamień wszystko": "Replace all",
        "Nie znaleziono.": "Not found.",
        "Nieprawidłowe wyrażenie regularne.": "Invalid regular expression.",
        "Zamieniono:": "Replaced:",
        "Edycja": "Edit",
        "🔍 Znajdź / Zamień w edytorze (Ctrl+H)": "🔍 Find / Replace in editor (Ctrl+H)",

        # ── Podgląd zmian (diff) ──
        "📊 Podgląd zmian": "📊 Show changes",
        "📊 Podgląd różnic": "📊 Diff preview",
        "📊 Podgląd zmian (diff)": "📊 Show changes (diff)",
        "Brak różnic – kod jest identyczny.": "No differences – code is identical.",
        "Dodane linie:": "Added lines:",
        "Usunięte linie:": "Removed lines:",
        "Ta funkcja jest dostępna tylko podczas edycji istniejącego skryptu.":
            "This feature is only available while editing an existing script.",

        # ── Eksport z edytora ──
        "✅ Wyeksportowano do:": "✅ Exported to:",
        "Porównaj z ostatnio zapisaną wersją (dostępne przy edycji istniejącego skryptu)":
            "Compare with the last saved version (available while editing an existing script)",
        "Zapisz aktualny kod z edytora bezpośrednio do pliku":
            "Save the current editor code directly to a file",

        # ── Ulubione (pin) i statystyki uruchomień ──
        "📌 Tylko ulubione": "📌 Favorites only",
        "Pokaż tylko przypięte skrypty": "Show only pinned scripts",
        "📌 Przypnij": "📌 Pin",
        "📌 Odepnij": "📌 Unpin",
        "📌 Przypnij / odepnij wybrany": "📌 Pin / unpin selected",
        "📌 Przypięto:": "📌 Pinned:",
        "📌 Odpięto:": "📌 Unpinned:",
        "Uruchomień:": "Runs:",
        "Ostatnio:": "Last run:",
        "📊 Statystyki": "📊 Statistics",
        "Przypiętych:": "Pinned:",
        "Łącznie uruchomień:": "Total runs:",
        "Skrypty wg kategorii": "Scripts by category",
        "Kategoria": "Category",
        "Liczba": "Count",
        "Najczęściej uruchamiane": "Most run",
        "Uruchomień": "Runs",
        "(brak danych)": "(no data)",
        "Przypięte skrypty": "Pinned scripts",

        # ── Zakładka: Snippety ──
        "🧩 Snippety": "🧩 Snippets",
        "🔍 Szukaj snippetów (nazwa / kod)...": "🔍 Search snippets (name / code)...",
        "Nazwa snippetu...": "Snippet name...",
        "# Wpisz lub wklej tutaj fragment kodu...": "# Type or paste your code snippet here...",
        "➕ Nowy snippet": "➕ New snippet",
        "💾 Zapisz snippet": "💾 Save snippet",
        "⏎ Wstaw do edytora": "⏎ Insert into editor",
        "⏎ Wstawiono do edytora.": "⏎ Inserted into editor.",
        "Snippetów:": "Snippets:",
        "Podaj nazwę snippetu.": "Enter a snippet name.",
        "Kod snippetu jest pusty.": "Snippet code is empty.",
        "Usuń snippet": "Delete snippet",
        "🧩 Zapisz zaznaczenie jako snippet": "🧩 Save selection as snippet",

        # ── Kolejność zakładek (Ustawienia) ──
        "Kolejność zakładek": "Tab order",
        "Przeciągnij pozycje, aby zmienić kolejność zakładek głównego okna.":
            "Drag items to change the order of the main window's tabs.",
        "⬆ W górę": "⬆ Move up",
        "⬇ W dół": "⬇ Move down",
    }

    @classmethod
    def tr(cls, text: str) -> str:
        if cls.current == "en":
            return cls.EN.get(text, text)
        return text

    @classmethod
    def set_language(cls, lang: str):
        cls.current = lang if lang in ("pl", "en") else "pl"


def tr(text: str) -> str:
    return LanguageManager.tr(text)

# ─────────────────────────────────────────────
#  THEME
# ─────────────────────────────────────────────
DARK = {
    "bg":       "#1e1e2e",
    "bg2":      "#181825",
    "surface":  "#313244",
    "fg":       "#cdd6f4",
    "comment":  "#6c7086",
    "accent":   "#89b4fa",
    "green":    "#a6e3a1",
    "red":      "#f38ba8",
    "yellow":   "#f9e2af",
    "mauve":    "#cba6f7",
    "teal":     "#94e2d5",
}

LIGHT = {
    "bg":       "#eff1f5",
    "bg2":      "#e6e9ef",
    "surface":  "#ccd0da",
    "fg":       "#4c4f69",
    "comment":  "#9ca0b0",
    "accent":   "#1e66f5",
    "green":    "#40a02b",
    "red":      "#d20f39",
    "yellow":   "#df8e1d",
    "mauve":    "#8839ef",
    "teal":     "#179299",
}

def make_stylesheet(c: dict[str, str]) -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {c['bg']};
    color: {c['fg']};
    font-family: Consolas, 'Courier New', monospace;
    font-size: 10pt;
}}
QTabWidget::pane {{
    border: 1px solid {c['surface']};
    background: {c['bg']};
}}
QTabBar::tab {{
    background: {c['surface']};
    color: {c['fg']};
    padding: 6px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {c['accent']};
    color: {c['bg']};
    border-bottom: 2px solid {c['accent']};
}}
QTabBar::tab:hover:!selected {{
    background: {c['bg2']};
}}
QPushButton {{
    background: {c['surface']};
    color: {c['fg']};
    border: none;
    padding: 5px 12px;
    border-radius: 4px;
}}
QPushButton:hover {{
    background: {c['accent']};
    color: {c['bg']};
}}
QPushButton:pressed {{
    background: {c['teal']};
    color: {c['bg']};
}}
QPushButton#btn_save {{
    background: {c['accent']};
    color: {c['bg']};
    font-weight: bold;
}}
QPushButton#btn_run {{
    background: {c['green']};
    color: {c['bg']};
    font-weight: bold;
}}
QPushButton#btn_delete {{
    background: {c['red']};
    color: white;
}}
QLineEdit, QComboBox, QSpinBox {{
    background: {c['bg2']};
    color: {c['fg']};
    border: 1px solid {c['surface']};
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: {c['accent']};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {c['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {c['bg2']};
    color: {c['fg']};
    selection-background-color: {c['accent']};
    selection-color: {c['bg']};
}}
QTextEdit, QPlainTextEdit {{
    background: {c['bg2']};
    color: {c['fg']};
    border: 1px solid {c['surface']};
    border-radius: 3px;
    selection-background-color: {c['accent']};
}}
QListWidget {{
    background: {c['bg2']};
    color: {c['fg']};
    border: 1px solid {c['surface']};
    border-radius: 3px;
    outline: none;
}}
QListWidget::item:selected {{
    background: {c['accent']};
    color: {c['bg']};
    border-radius: 2px;
}}
QListWidget::item:hover:!selected {{
    background: {c['surface']};
}}
QTreeWidget {{
    background: {c['bg2']};
    color: {c['fg']};
    border: 1px solid {c['surface']};
    border-radius: 3px;
    outline: none;
}}
QTreeWidget::item:selected {{
    background: {c['accent']};
    color: {c['bg']};
}}
QTreeWidget::item:hover:!selected {{
    background: {c['surface']};
}}
QHeaderView::section {{
    background: {c['surface']};
    color: {c['accent']};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {c['bg']};
    font-weight: bold;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {c['bg2']};
    width: 10px;
    height: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {c['surface']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:hover {{
    background: {c['accent']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{ background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QGroupBox {{
    border: 1px solid {c['surface']};
    border-radius: 5px;
    margin-top: 8px;
    padding-top: 4px;
    color: {c['accent']};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}
QMenuBar {{
    background: {c['bg2']};
    color: {c['fg']};
    border-bottom: 1px solid {c['surface']};
}}
QMenuBar::item:selected {{
    background: {c['accent']};
    color: {c['bg']};
}}
QMenu {{
    background: {c['bg2']};
    color: {c['fg']};
    border: 1px solid {c['surface']};
}}
QMenu::item:selected {{
    background: {c['accent']};
    color: {c['bg']};
}}
QMenu::separator {{
    height: 1px;
    background: {c['surface']};
    margin: 3px 6px;
}}
QSplitter::handle {{
    background: {c['surface']};
}}
QStatusBar {{
    background: {c['bg2']};
    color: {c['comment']};
    border-top: 1px solid {c['surface']};
}}
QCheckBox {{
    color: {c['fg']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {c['surface']};
    border-radius: 3px;
    background: {c['bg2']};
}}
QCheckBox::indicator:checked {{
    background: {c['accent']};
    border-color: {c['accent']};
}}
QLabel#tag_label {{
    background: {c['surface']};
    color: {c['accent']};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8pt;
}}
QFrame#separator {{
    color: {c['surface']};
}}
QProgressBar {{
    background: {c['bg2']};
    border: 1px solid {c['surface']};
    border-radius: 3px;
    text-align: center;
    color: {c['fg']};
}}
QProgressBar::chunk {{
    background: {c['accent']};
    border-radius: 2px;
}}
"""

# ─────────────────────────────────────────────
#  SYNTAX HIGHLIGHTER
# ─────────────────────────────────────────────
SYNTAX_RULES = {
    "Python": [
        ("keyword",  r"\b(False|None|True|and|as|assert|async|await|break|class|continue|"
                     r"def|del|elif|else|except|finally|for|from|global|if|import|in|is|"
                     r"lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b"),
        ("builtin",  r"\b(print|len|range|int|str|float|list|dict|set|tuple|bool|type|"
                     r"open|input|super|self|cls|__init__|__name__|__main__)\b"),
        ("string",   r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\''),
        ("comment",  r"#[^\n]*"),
        ("number",   r"\b\d+(\.\d+)?\b"),
        ("decorator",r"@\w+"),
    ],
    "Bash": [
        ("keyword",  r"\b(if|then|else|elif|fi|for|while|do|done|case|esac|in|"
                     r"function|return|export|local|source|echo|exit|shift|break|continue)\b"),
        ("string",   r'"(?:[^"\\]|\\.)*"|\'[^\']*\''),
        ("comment",  r"#[^\n]*"),
        ("variable", r"\$\{?\w+\}?"),
        ("number",   r"\b\d+\b"),
    ],
    "PowerShell": [
        ("keyword",  r"\b(if|else|elseif|foreach|for|while|do|switch|function|return|"
                     r"param|begin|process|end|try|catch|finally|throw|break|continue|exit)\b"),
        ("cmdlet",   r"\b\w+-\w+\b"),
        ("string",   r'"(?:[^"\\]|\\.)*"|\'[^\']*\''),
        ("comment",  r"#[^\n]*|<#[\s\S]*?#>"),
        ("variable", r"\$\w+"),
        ("number",   r"\b\d+(\.\d+)?\b"),
    ],
    "Batch": [
        ("keyword",  r"(?i)\b(echo|set|if|else|goto|call|exit|for|do|in|rem|pause|"
                     r"cd|md|rd|del|copy|move|ren|dir|cls|type|find|sort|more)\b"),
        ("label",    r"^:\w+"),
        ("variable", r"%\w+%|%~?\d"),
        ("comment",  r"(?i)^rem[^\n]*"),
        ("string",   r'"[^"]*"'),
    ],
    "JavaScript": [
        ("keyword",  r"\b(var|let|const|function|return|if|else|for|while|do|switch|case|"
                     r"break|continue|new|delete|typeof|instanceof|class|extends|"
                     r"import|export|default|async|await|try|catch|finally|throw|yield)\b"),
        ("builtin",  r"\b(console|document|window|Array|Object|String|Number|Boolean|"
                     r"Promise|Math|JSON|Date|RegExp|Error|Map|Set)\b"),
        ("string",   r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`'),
        ("comment",  r"//[^\n]*|/\*[\s\S]*?\*/"),
        ("number",   r"\b\d+(\.\d+)?\b"),
    ],
    "SQL": [
        ("keyword",  r"(?i)\b(SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|"
                     r"CREATE|TABLE|DROP|ALTER|ADD|INDEX|VIEW|JOIN|LEFT|RIGHT|INNER|"
                     r"ON|AND|OR|NOT|NULL|AS|DISTINCT|ORDER|BY|GROUP|HAVING|LIMIT)\b"),
        ("function", r"(?i)\b(COUNT|SUM|AVG|MIN|MAX|COALESCE|CAST|NOW|UPPER|LOWER|TRIM|LENGTH)\b"),
        ("string",   r"'[^']*'"),
        ("comment",  r"--[^\n]*|/\*[\s\S]*?\*/"),
        ("number",   r"\b\d+(\.\d+)?\b"),
    ],
    "VBScript": [
        ("keyword",  r"(?i)\b(Dim|Set|If|Then|Else|ElseIf|End|For|Each|Next|While|Wend|"
                     r"Do|Loop|Until|Function|Sub|Call|Exit|ReDim|Class|Public|Private|"
                     r"Const|New|Nothing|True|False|And|Or|Not|Is|Mod|On|Error|Resume)\b"),
        ("builtin",  r"(?i)\b(MsgBox|InputBox|WScript|CreateObject|Response|Request|"
                     r"Server|Session|Application|Err|CStr|CInt|CDbl|IsNull|IsEmpty)\b"),
        ("string",   r'"(?:[^"]|"")*"'),
        ("comment",  r"'[^\n]*|(?i)^\s*REM\b[^\n]*"),
        ("number",   r"\b\d+(\.\d+)?\b"),
    ],
    "Ruby": [
        ("keyword",  r"\b(def|end|if|elsif|else|unless|case|when|while|until|for|in|do|"
                     r"begin|rescue|ensure|raise|class|module|return|yield|break|next|"
                     r"redo|retry|nil|true|false|and|or|not|self|super|require|require_relative|attr_accessor)\b"),
        ("builtin",  r"\b(puts|print|p|gets|loop|lambda|proc|each|map|select|reject|"
                     r"reduce|inject|Integer|String|Array|Hash|Symbol|Float)\b"),
        ("string",   r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''),
        ("comment",  r"#[^\n]*|^=begin[\s\S]*?^=end"),
        ("variable", r"@{1,2}\w+|\$\w+"),
        ("number",   r"\b\d+(\.\d+)?\b"),
        ("symbol",   r":\w+"),
    ],
    "Lua": [
        ("keyword",  r"\b(and|break|do|else|elseif|end|false|for|function|goto|if|in|"
                     r"local|nil|not|or|repeat|return|then|true|until|while)\b"),
        ("builtin",  r"\b(print|pairs|ipairs|tostring|tonumber|type|pcall|require|"
                     r"setmetatable|getmetatable|table|string|math|os|io)\b"),
        ("string",   r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\[\[[\s\S]*?\]\]'),
        ("comment",  r"--\[\[[\s\S]*?\]\]|--[^\n]*"),
        ("number",   r"\b0x[0-9a-fA-F]+\b|\b\d+(\.\d+)?\b"),
    ],
    "Other": [],
}

TOKEN_COLORS_DARK = {
    "keyword":   "#cba6f7",
    "builtin":   "#89dceb",
    "string":    "#a6e3a1",
    "comment":   "#6c7086",
    "number":    "#fab387",
    "decorator": "#f9e2af",
    "variable":  "#89b4fa",
    "cmdlet":    "#89dceb",
    "function":  "#89dceb",
    "label":     "#f9e2af",
    "operator":  "#f38ba8",
    "symbol":    "#f5c2e7",
}
TOKEN_COLORS_LIGHT = {
    "keyword":   "#8839ef",
    "builtin":   "#179299",
    "string":    "#40a02b",
    "comment":   "#9ca0b0",
    "number":    "#fe640b",
    "decorator": "#df8e1d",
    "variable":  "#1e66f5",
    "cmdlet":    "#179299",
    "function":  "#179299",
    "label":     "#df8e1d",
    "operator":  "#d20f39",
    "symbol":    "#ea76cb",
}

class SyntaxHighlighterQt(QSyntaxHighlighter):
    def __init__(self, document, language="Python", dark=True):
        super().__init__(document)
        self.language = language
        self.dark = dark
        self._build_rules()

    def set_language(self, language: str):
        self.language = language
        self._build_rules()
        self.rehighlight()

    def set_dark(self, dark: bool):
        self.dark = dark
        self._build_rules()
        self.rehighlight()

    def _build_rules(self):
        colors = TOKEN_COLORS_DARK if self.dark else TOKEN_COLORS_LIGHT
        cache_key = (self.language, self.dark)
        if hasattr(self, "_cache_key") and self._cache_key == cache_key:
            return
        self._cache_key = cache_key
        self._rules = []
        for token, pattern in SYNTAX_RULES.get(self.language, []):
            fmt = QTextCharFormat()
            color = colors.get(token, "#cdd6f4")
            fmt.setForeground(QColor(color))
            if token == "keyword":
                fmt.setFontWeight(700)
            flags = QRegularExpression.PatternOption.MultilineOption
            self._rules.append((QRegularExpression(pattern, flags), fmt))

    def highlightBlock(self, text: str):
        for regex, fmt in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

# ─────────────────────────────────────────────
#  LANGUAGE DETECTION
# ─────────────────────────────────────────────
LANG_PATTERNS = [
    # Wzorce bardziej charakterystyczne (shebang, unikalne słowa kluczowe)
    # muszą iść przed ogólnymi, inaczej np. "def foo(x)" w Ruby trafi
    # w regułę Pythona zanim dojdzie do reguły Ruby.
    ("Ruby",       r"^#!.*\bruby\b|\bdef\s+\w+[^\n:]*\n(?:.*\n)*?\s*end\b|\brequire(_relative)?\s+[\'\"]|\bputs\s+[\'\"f]"),
    ("Lua",        r"(?i)^#!.*\blua\b|\blocal\s+function\b|\blocal\s+\w+\s*=|--\[\[|\bfunction\s+\w+\s*\([^\n)]*\)\s*$"),
    ("VBScript",   r"(?i)^\s*(Dim |Set |WScript\.|MsgBox|Sub |End Sub|Function .+\(.*\)\s*$)"),
    ("PowerShell", r"(?i)(param\s*\(|\$\w+\s*=|Write-Host|Get-|Set-|New-|Remove-)"),
    ("Batch",      r"(?i)^(@echo|rem |::\s|if errorlevel|goto )"),
    ("Python",     r"^\s*(import |from .+ import|def \w+\([^\n]*\)\s*:|class |print\(|if __name__)"),
    ("JavaScript", r"(function\s*\(|const |let |var |=>|console\.log)"),
    ("SQL",        r"(?i)^\s*(SELECT |INSERT |UPDATE |DELETE |CREATE TABLE)"),
    ("Bash",       r"(^#!.*sh|^\s*(export|source)\s+)"),
]

_LANG_PATTERNS_COMPILED = [
    (lang, re.compile(pat, re.MULTILINE)) for lang, pat in LANG_PATTERNS
]

def detect_language(code: str) -> str:
    for lang, rx in _LANG_PATTERNS_COMPILED:
        if rx.search(code):
            return lang
    return "Other"

CATEGORIES = [
    "Python", "Bash", "PowerShell", "Batch", "JavaScript",
    "SQL", "VBScript", "Ruby", "Lua", "Other"
]

EXT_MAP = {
    "Python": ".py", "Bash": ".sh", "PowerShell": ".ps1",
    "Batch": ".bat", "JavaScript": ".js", "SQL": ".sql",
    "VBScript": ".vbs", "Ruby": ".rb", "Lua": ".lua", "Other": ".txt",
}

# ─────────────────────────────────────────────
#  TERMINAL DETECTION
# ─────────────────────────────────────────────
TERMINAL_DEFS = [
    ("cmd",        "CMD",          ["cmd", "/c", "echo ok"],  ["cmd", "/k"]),
    ("powershell", "PowerShell",   ["powershell", "-Command", "echo ok"], ["powershell", "-NoExit", "-Command"]),
    ("pwsh",       "PS Core",      ["pwsh", "-Command", "echo ok"], ["pwsh", "-NoExit", "-Command"]),
    ("bash",       "Bash",         ["bash", "--version"],     ["bash", "-c"]),
    ("sh",         "sh",           ["sh", "--version"],       ["sh", "-c"]),
    ("zsh",        "Zsh",          ["zsh", "--version"],      ["zsh", "-c"]),
    ("wsl",        "WSL",          ["wsl", "echo", "ok"],     ["wsl"]),
]

def detect_terminals():
    def _check(entry):
        tid, label, test, _ = entry
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            r = subprocess.run(test, capture_output=True, timeout=2, creationflags=flags)
            if r.returncode is not None:
                return (tid, label)
        except Exception:
            pass  # terminal nieobecny lub niedostępny – oczekiwany przypadek
        return None

    found = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(TERMINAL_DEFS)) as pool:
        for result in pool.map(_check, TERMINAL_DEFS):
            if result:
                found.append(result)
    # Stabilna kolejność zgodna z TERMINAL_DEFS, niezależna od czasu odpowiedzi
    order = {tid: i for i, (tid, *_rest) in enumerate(TERMINAL_DEFS)}
    found.sort(key=lambda t: order.get(t[0], 99))
    return found


# ─────────────────────────────────────────────
#  EDITOR WIDGET (z numerami linii)
# ─────────────────────────────────────────────
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor._line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor._paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, dark=True, parent=None):
        super().__init__(parent)
        self.dark = dark
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()
        self.setTabStopDistance(32)
        font = QFont("Consolas", 10)
        font.setFixedPitch(True)
        self.setFont(font)
        self._highlighter = None

    def set_language(self, lang: str):
        if self._highlighter:
            self._highlighter.set_language(lang)
        else:
            self._highlighter = SyntaxHighlighterQt(self.document(), lang, self.dark)

    def apply_font_settings(self, family: str, size: int):
        font = QFont(family, size)
        font.setFixedPitch(True)
        self.setFont(font)
        self._update_line_area_width()

    def set_dark(self, dark: bool):
        self.dark = dark
        if self._highlighter:
            self._highlighter.set_dark(dark)

    def _line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self):
        self.setViewportMargins(self._line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(cr.left(), cr.top(),
                                    self._line_number_area_width(), cr.height())

    def _paint_line_numbers(self, event):
        from PyQt6.QtGui import QPainter
        painter = QPainter(self._line_area)
        bg = QColor("#181825" if self.dark else "#e6e9ef")
        fg = QColor("#6c7086" if self.dark else "#9ca0b0")
        painter.fillRect(event.rect(), bg)
        painter.setPen(fg)
        font = self.font()
        font.setPointSize(font.pointSize() - 1)
        painter.setFont(font)

        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        w = self._line_area.width() - 4

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, w, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(block_num + 1))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_num += 1

# ─────────────────────────────────────────────
#  ZNAJDŹ / ZAMIEŃ (Ctrl+H w edytorze)
# ─────────────────────────────────────────────
class FindReplaceDialog(QDialog):
    """Bezmodalne okno Znajdź / Zamień działające bezpośrednio na przekazanym
    edytorze kodu (CodeEditor / QPlainTextEdit). Wspiera dopasowanie wielkości
    liter, całych słów oraz wyrażenia regularne (QRegularExpression)."""

    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle(tr("🔍 Znajdź / Zamień"))
        self.setMinimumWidth(380)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        form = QFormLayout()
        self.entry_find = QLineEdit()
        self.entry_find.setPlaceholderText(tr("Tekst do znalezienia..."))
        self.entry_find.returnPressed.connect(self._find_next)
        form.addRow(tr("Znajdź:"), self.entry_find)

        self.entry_replace = QLineEdit()
        self.entry_replace.setPlaceholderText(tr("Tekst zastępczy..."))
        self.entry_replace.returnPressed.connect(self._replace_one)
        form.addRow(tr("Zamień na:"), self.entry_replace)
        layout.addLayout(form)

        opts_row = QHBoxLayout()
        self.chk_case = QCheckBox(tr("Uwzględnij wielkość liter"))
        opts_row.addWidget(self.chk_case)
        self.chk_whole = QCheckBox(tr("Całe słowa"))
        opts_row.addWidget(self.chk_whole)
        self.chk_regex = QCheckBox(tr("Wyrażenie regularne"))
        opts_row.addWidget(self.chk_regex)
        layout.addLayout(opts_row)

        btn_row = QHBoxLayout()
        self.btn_find_next = QPushButton(tr("Znajdź dalej"))
        self.btn_find_next.clicked.connect(self._find_next)
        btn_row.addWidget(self.btn_find_next)

        self.btn_replace = QPushButton(tr("Zamień"))
        self.btn_replace.clicked.connect(self._replace_one)
        btn_row.addWidget(self.btn_replace)

        self.btn_replace_all = QPushButton(tr("Zamień wszystko"))
        self.btn_replace_all.clicked.connect(self._replace_all)
        btn_row.addWidget(self.btn_replace_all)
        layout.addLayout(btn_row)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #6c7086; font-size: 8pt;")
        layout.addWidget(self.status_lbl)

        btn_close = QPushButton(tr("Zamknij"))
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _flags(self) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.chk_whole.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags

    def _compile_regex(self):
        opts = QRegularExpression.PatternOption.NoPatternOption
        if not self.chk_case.isChecked():
            opts |= QRegularExpression.PatternOption.CaseInsensitiveOption
        rx = QRegularExpression(self.entry_find.text(), opts)
        if not rx.isValid():
            self.status_lbl.setText(tr("Nieprawidłowe wyrażenie regularne."))
            return None
        return rx

    def _find_from(self, cursor: QTextCursor):
        pattern = self.entry_find.text()
        flags = self._flags()
        if self.chk_regex.isChecked():
            rx = self._compile_regex()
            if rx is None:
                return None
            return self.editor.document().find(rx, cursor, flags)
        return self.editor.document().find(pattern, cursor, flags)

    def _find_next(self):
        if not self.entry_find.text():
            return
        found = self._find_from(self.editor.textCursor())
        if found is None:
            return
        if found.isNull():
            # zawiń wyszukiwanie do początku dokumentu
            start = QTextCursor(self.editor.document())
            start.movePosition(QTextCursor.MoveOperation.Start)
            found = self._find_from(start)
            if found is None:
                return
        if found.isNull():
            self.status_lbl.setText(tr("Nie znaleziono."))
        else:
            self.editor.setTextCursor(found)
            self.status_lbl.setText("")

    def _current_selection_matches(self, cursor: QTextCursor) -> bool:
        if not cursor.hasSelection():
            return False
        selected = cursor.selectedText()
        pattern = self.entry_find.text()
        if not pattern:
            return False
        if self.chk_regex.isChecked():
            rx = self._compile_regex()
            if rx is None:
                return False
            m = rx.match(selected)
            return m.hasMatch() and m.capturedStart() == 0 and m.capturedLength() == len(selected)
        if self.chk_case.isChecked():
            return selected == pattern
        return selected.lower() == pattern.lower()

    def _replace_one(self):
        if not self.entry_find.text():
            return
        cursor = self.editor.textCursor()
        if self._current_selection_matches(cursor):
            cursor.insertText(self.entry_replace.text())
            self.editor.setTextCursor(cursor)
        self._find_next()

    def _replace_all(self):
        pattern = self.entry_find.text()
        if not pattern:
            return
        replacement = self.entry_replace.text()
        flags = self._flags()
        rx = None
        if self.chk_regex.isChecked():
            rx = self._compile_regex()
            if rx is None:
                return

        edit_cursor = self.editor.textCursor()
        edit_cursor.beginEditBlock()
        doc_cursor = QTextCursor(self.editor.document())
        doc_cursor.movePosition(QTextCursor.MoveOperation.Start)
        count = 0
        while True:
            found = (self.editor.document().find(rx, doc_cursor, flags) if rx is not None
                     else self.editor.document().find(pattern, doc_cursor, flags))
            if found.isNull():
                break
            found.insertText(replacement)
            doc_cursor = found
            count += 1
        edit_cursor.endEditBlock()
        self.status_lbl.setText(f"{tr('Zamieniono:')} {count}")


# ─────────────────────────────────────────────
#  PODGLĄD RÓŻNIC (DIFF) PRZY EDYCJI SKRYPTU
# ─────────────────────────────────────────────
class DiffDialog(QDialog):
    """Pokazuje uproszczony 'unified diff' między oryginalną (zapisaną)
    wersją kodu skryptu a aktualną zawartością edytora – dodane linie
    na zielono, usunięte na czerwono, nagłówki bloków na niebiesko."""

    def __init__(self, original: str, current: str, dark: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("📊 Podgląd różnic"))
        self.resize(720, 560)
        layout = QVBoxLayout(self)

        self.view = QTextBrowser()
        mono = QFont("Consolas", 10)
        mono.setFixedPitch(True)
        self.view.setFont(mono)
        layout.addWidget(self.view, 1)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #6c7086; font-size: 8pt;")
        layout.addWidget(self.lbl_summary)

        btn_close = QPushButton(tr("Zamknij"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        self._render(original, current, dark)

    def _render(self, original: str, current: str, dark: bool):
        orig_lines = original.splitlines()
        curr_lines = current.splitlines()
        diff = list(difflib.unified_diff(orig_lines, curr_lines, lineterm=""))

        add_c  = "#a6e3a1" if dark else "#40a02b"
        del_c  = "#f38ba8" if dark else "#d20f39"
        hunk_c = "#89b4fa" if dark else "#1e66f5"
        ctx_c  = "#cdd6f4" if dark else "#4c4f69"
        bg     = "#1e1e2e" if dark else "#eff1f5"

        added = removed = 0
        html_lines = []
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                continue
            esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            esc = esc.replace(" ", "&nbsp;") if esc.startswith(("+", "-", "@")) else esc
            if line.startswith("@@"):
                html_lines.append(f'<span style="color:{hunk_c};">{esc}</span>')
            elif line.startswith("+"):
                added += 1
                html_lines.append(f'<span style="color:{add_c};">{esc}</span>')
            elif line.startswith("-"):
                removed += 1
                html_lines.append(f'<span style="color:{del_c};">{esc}</span>')
            else:
                html_lines.append(f'<span style="color:{ctx_c};">{esc}</span>')

        if not html_lines:
            html_lines = [f'<span style="color:{ctx_c};">{tr("Brak różnic – kod jest identyczny.")}</span>']

        html = f'<pre style="background-color:{bg}; margin:0;">' + "<br>".join(html_lines) + "</pre>"
        self.view.setHtml(html)
        self.lbl_summary.setText(f"{tr('Dodane linie:')} {added}   {tr('Usunięte linie:')} {removed}")


# ─────────────────────────────────────────────
#  ADD/EDIT SCRIPT TAB
# ─────────────────────────────────────────────
class AddEditTab(QWidget):
    script_saved = pyqtSignal(dict)

    def __init__(self, dark=True, parent=None):
        super().__init__(parent)
        self.dark = dark
        self.editing_id: Optional[int] = None
        self._dirty = False
        self._known_names: set = set()
        self._original_code: Optional[str] = None
        self._find_dialog: Optional["FindReplaceDialog"] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Top form
        form = QFormLayout()
        form.setSpacing(6)

        self.entry_name = QLineEdit()
        self.entry_name.setPlaceholderText(tr("Nazwa skryptu..."))
        form.addRow(tr("Nazwa:"), self.entry_name)

        row2 = QHBoxLayout()
        self.combo_cat = QComboBox()
        self.combo_cat.addItems(CATEGORIES)
        self.combo_cat.setFixedWidth(180)
        self.combo_cat.currentTextChanged.connect(self._on_category_changed)
        row2.addWidget(QLabel(tr("Kategoria:")))
        row2.addWidget(self.combo_cat)
        row2.addSpacing(16)
        row2.addWidget(QLabel(tr("Tagi:")))
        self.entry_tags = QLineEdit()
        self.entry_tags.setPlaceholderText(tr("tag1,tag2,tag3"))
        row2.addWidget(self.entry_tags)
        layout.addLayout(form)

        self.entry_name.textChanged.connect(self._mark_dirty)
        self.entry_tags.textChanged.connect(self._mark_dirty)
        layout.addLayout(row2)

        self.entry_desc = QLineEdit()
        self.entry_desc.setPlaceholderText(tr("Krótki opis skryptu..."))
        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel(tr("Opis:")))
        desc_row.addWidget(self.entry_desc)
        layout.addLayout(desc_row)
        self.entry_desc.textChanged.connect(self._mark_dirty)

        # Language / detect bar
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(tr("Język:")))
        self.lbl_lang = QLabel(tr("—"))
        self.lbl_lang.setObjectName("tag_label")
        lang_row.addWidget(self.lbl_lang)
        lang_row.addStretch()

        btn_detect = QPushButton(tr("🔍 Auto-wykryj"))
        btn_detect.clicked.connect(self._auto_detect)
        lang_row.addWidget(btn_detect)

        btn_clear = QPushButton(tr("🗑 Wyczyść"))
        btn_clear.clicked.connect(self.clear)
        lang_row.addWidget(btn_clear)

        btn_find = QPushButton(tr("🔍 Znajdź / Zamień"))
        btn_find.setToolTip("Ctrl+H")
        btn_find.clicked.connect(self._open_find_replace)
        lang_row.addWidget(btn_find)
        layout.addLayout(lang_row)

        # Code editor
        self.editor = CodeEditor(self.dark)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.setPlaceholderText(tr("# Wpisz lub wklej tutaj kod skryptu..."))
        layout.addWidget(self.editor, 1)

        # Highlighter
        self._hl = SyntaxHighlighterQt(self.editor.document(), "Python", self.dark)
        self.editor._highlighter = self._hl

        # Skrót Ctrl+H – Znajdź / Zamień, aktywny gdy fokus jest w edytorze
        self._find_shortcut = QShortcut(QKeySequence("Ctrl+H"), self.editor)
        self._find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._find_shortcut.activated.connect(self._open_find_replace)

        # Śledzenie niezapisanych zmian: modificationChanged reaguje tylko
        # na faktyczne edycje treści, w przeciwieństwie do textChanged, które
        # odpala się też przy samym przekolorowaniu składni (rehighlight()).
        self.editor.document().modificationChanged.connect(self._on_modification_changed)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_save = QPushButton(tr("💾 Zapisz skrypt"))
        self.btn_save.setObjectName("btn_save")
        self.btn_save.clicked.connect(self._save)
        btn_row.addWidget(self.btn_save)

        btn_copy = QPushButton(tr("📋 Kopiuj kod"))
        btn_copy.clicked.connect(self._copy_code)
        btn_row.addWidget(btn_copy)

        self.btn_diff = QPushButton(tr("📊 Podgląd zmian"))
        self.btn_diff.setEnabled(False)
        self.btn_diff.setToolTip(tr("Porównaj z ostatnio zapisaną wersją (dostępne przy edycji istniejącego skryptu)"))
        self.btn_diff.clicked.connect(self._show_diff)
        btn_row.addWidget(self.btn_diff)

        btn_export = QPushButton(tr("📤 Eksportuj"))
        btn_export.setToolTip(tr("Zapisz aktualny kod z edytora bezpośrednio do pliku"))
        btn_export.clicked.connect(self._export_from_editor)
        btn_row.addWidget(btn_export)
        layout.addLayout(btn_row)

        # Status
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #6c7086; font-size: 8pt;")
        layout.addWidget(self.status_lbl)

    def _on_text_changed(self):
        code = self.editor.toPlainText()
        lines = code.count("\n") + 1 if code else 0
        chars = len(code)
        self.status_lbl.setText(f"{tr('Linie:')} {lines} | {tr('Znaki:')} {chars}")

    def _on_category_changed(self, category: str):
        # combo_cat.addItems() w _build_ui emituje currentTextChanged zanim
        # self._hl i self.lbl_lang zdążą powstać – ignorujemy taki wczesny sygnał.
        if not hasattr(self, "_hl"):
            return
        self.lbl_lang.setText(category)
        self._hl.set_language(category)
        self._mark_dirty()

    def _on_modification_changed(self, modified: bool):
        if modified:
            self._dirty = True

    def _mark_dirty(self):
        self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty

    def set_known_names(self, names):
        """Wywoływane przez MainWindow po każdej zmianie listy skryptów,
        żeby _save() mogło ostrzec przed cichym utworzeniem duplikatu nazwy."""
        self._known_names = set(names)

    def _existing_names(self) -> set:
        return self._known_names

    def _auto_detect(self):
        code = self.editor.toPlainText()
        lang = detect_language(code)
        idx = self.combo_cat.findText(lang)
        if idx >= 0:
            self.combo_cat.setCurrentIndex(idx)  # wyzwala _on_category_changed
        else:
            # Język spoza listy CATEGORIES (teoretycznie nie powinno się zdarzyć,
            # bo detect_language zwraca tylko wartości z CATEGORIES lub "Other") –
            # i tak aktualizujemy etykietę/highlighter na wszelki wypadek.
            self.lbl_lang.setText(lang)
            self._hl.set_language(lang)

    def _save(self):
        name = self.entry_name.text().strip()
        code = self.editor.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, tr("Błąd"), tr("Podaj nazwę skryptu."))
            return
        if not code:
            QMessageBox.warning(self, tr("Błąd"), tr("Kod skryptu jest pusty."))
            return
        if self.editing_id is None and name in self._existing_names():
            reply = QMessageBox.question(
                self, tr("Nazwa już istnieje"),
                f"{tr('Skrypt o nazwie')} „{name}” {tr('już istnieje. Zapisać mimo to jako osobny wpis?')}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        script = {
            "id": self.editing_id if self.editing_id is not None else new_id(),
            "name": name,
            "category": self.combo_cat.currentText(),
            "tags": self.entry_tags.text().strip(),
            "desc": self.entry_desc.text().strip(),
            "code": code,
            "date": datetime.date.today().isoformat(),
        }
        self.script_saved.emit(script)
        self._dirty = False
        self.editor.document().setModified(False)
        if self.editing_id is not None:
            self._original_code = code
        self._update_diff_button_state()

    def _open_find_replace(self):
        if self._find_dialog is None:
            self._find_dialog = FindReplaceDialog(self.editor, self)
        sel = self.editor.textCursor().selectedText()
        if sel:
            self._find_dialog.entry_find.setText(sel)
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog.activateWindow()
        self._find_dialog.entry_find.setFocus()
        self._find_dialog.entry_find.selectAll()

    def _update_diff_button_state(self):
        self.btn_diff.setEnabled(self._original_code is not None)

    def _show_diff(self):
        if self._original_code is None:
            return
        current = self.editor.toPlainText()
        dlg = DiffDialog(self._original_code, current, self.dark, self)
        dlg.exec()

    def _export_from_editor(self):
        """Eksportuje aktualny kod z edytora bezpośrednio do pliku –
        niezależnie od zapisu skryptu do bazy (przycisk 💾 Zapisz skrypt)."""
        code = self.editor.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, tr("Błąd"), tr("Kod skryptu jest pusty."))
            return
        ext = EXT_MAP.get(self.combo_cat.currentText(), ".txt")
        default_name = (self.entry_name.text().strip() or "script") + ext
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Eksportuj skrypt"), default_name,
            f"{tr('Skrypt')} (*{ext});;TXT (*.txt);;{tr('Wszystkie')} (*)")
        if path:
            Path(path).write_text(code, encoding="utf-8")
            self.status_lbl.setText(f"{tr('✅ Wyeksportowano do:')} {path}")

    def _copy_code(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        self.status_lbl.setText(tr("✅ Skopiowano do schowka!"))

    def load_script(self, script: Script):
        self.editing_id = script["id"]
        self.entry_name.setText(script.get("name", ""))
        lang = script.get("category", "Other")
        idx = self.combo_cat.findText(lang)
        if idx >= 0:
            self.combo_cat.setCurrentIndex(idx)  # wyzwala _on_category_changed
        else:
            self.lbl_lang.setText(lang)
            self._hl.set_language(lang)
        self.entry_tags.setText(script.get("tags", ""))
        self.entry_desc.setText(script.get("desc", ""))
        self.editor.setPlainText(script.get("code", ""))
        self._dirty = False
        self.editor.document().setModified(False)
        self._original_code = script.get("code", "")
        self._update_diff_button_state()

    def clear(self, confirm: bool = True):
        if confirm and self._dirty:
            reply = QMessageBox.question(
                self, tr("Niezapisane zmiany"),
                tr("Masz niezapisane zmiany w edytorze. Czy na pewno chcesz je wyczyścić?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.editing_id = None
        self.entry_name.clear()
        self.combo_cat.setCurrentIndex(0)
        self.entry_tags.clear()
        self.entry_desc.clear()
        self.editor.clear()
        self.lbl_lang.setText("—")
        self.status_lbl.clear()
        self._dirty = False
        self.editor.document().setModified(False)
        self._original_code = None
        self._update_diff_button_state()

    def set_dark(self, dark: bool):
        self.dark = dark
        self.editor.set_dark(dark)
        self._hl.set_dark(dark)

# ─────────────────────────────────────────────
#  SCRIPT LIST TAB
# ─────────────────────────────────────────────
class ScriptListTab(QWidget):
    edit_requested      = pyqtSignal(dict)
    run_requested       = pyqtSignal(dict)
    delete_requested    = pyqtSignal(dict)
    duplicate_requested = pyqtSignal(dict)
    pin_toggled         = pyqtSignal(dict)

    def __init__(self, terminals: list[tuple], parent=None):
        super().__init__(parent)
        self.terminals = terminals
        self.confirm_delete = True
        self._scripts: list[Script] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Filter bar
        bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("🔍 Szukaj (nazwa / tagi / opis / kod)..."))
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(150)
        self._filter_timer.timeout.connect(self._filter)
        self.search_edit.textChanged.connect(self._filter_timer.start)
        bar.addWidget(self.search_edit)

        self.chk_search_code = QCheckBox(tr("📄 Szukaj w kodzie"))
        self.chk_search_code.setToolTip(tr("Przeszukuje również treść kodu skryptów"))
        self.chk_search_code.stateChanged.connect(self._filter_timer.start)
        bar.addWidget(self.chk_search_code)

        self.chk_pinned_only = QCheckBox(tr("📌 Tylko ulubione"))
        self.chk_pinned_only.setToolTip(tr("Pokaż tylko przypięte skrypty"))
        self.chk_pinned_only.stateChanged.connect(self._filter)
        bar.addWidget(self.chk_pinned_only)

        self.filter_cat = QComboBox()
        self.filter_cat.addItem(tr("Wszystkie"))
        self.filter_cat.addItems(CATEGORIES)
        self.filter_cat.currentTextChanged.connect(self._filter)
        self.filter_cat.setFixedWidth(140)
        bar.addWidget(self.filter_cat)
        layout.addLayout(bar)

        # Split: list + preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: list
        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._ctx_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self.list_widget.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self.list_widget)

        # Right: preview
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        self.preview_name = QLabel("")
        self.preview_name.setStyleSheet("font-size: 13pt; font-weight: bold; color: #89b4fa;")
        self.preview_name.setWordWrap(True)
        rl.addWidget(self.preview_name)

        meta_row = QHBoxLayout()
        self.preview_cat = QLabel("")
        self.preview_cat.setObjectName("tag_label")
        meta_row.addWidget(self.preview_cat)
        self.preview_tags = QLabel("")
        self.preview_tags.setStyleSheet("color: #6c7086; font-size: 8pt;")
        meta_row.addWidget(self.preview_tags)
        meta_row.addStretch()
        self.preview_date = QLabel("")
        self.preview_date.setStyleSheet("color: #6c7086; font-size: 8pt;")
        meta_row.addWidget(self.preview_date)
        rl.addLayout(meta_row)

        self.preview_desc = QLabel("")
        self.preview_desc.setWordWrap(True)
        self.preview_desc.setStyleSheet("color: #a6adc8;")
        rl.addWidget(self.preview_desc)

        self.preview_stats = QLabel("")
        self.preview_stats.setStyleSheet("color: #6c7086; font-size: 8pt;")
        rl.addWidget(self.preview_stats)

        self.preview_editor = CodeEditor()
        self.preview_editor.setReadOnly(True)
        self.preview_editor.setMaximumHeight(999)
        self._preview_hl = SyntaxHighlighterQt(self.preview_editor.document(), "Python")
        rl.addWidget(self.preview_editor, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        self.btn_edit = QPushButton(tr("✏️ Edytuj"))
        self.btn_edit.clicked.connect(self._do_edit)
        btn_row.addWidget(self.btn_edit)

        self.btn_run = QPushButton(tr("▶ Uruchom"))
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._do_run)
        btn_row.addWidget(self.btn_run)

        self.btn_pin = QPushButton(tr("📌 Przypnij"))
        self.btn_pin.clicked.connect(self._do_toggle_pin)
        btn_row.addWidget(self.btn_pin)

        self.btn_copy = QPushButton(tr("📋 Kopiuj"))
        self.btn_copy.clicked.connect(self._do_copy)
        btn_row.addWidget(self.btn_copy)

        self.btn_delete = QPushButton(tr("🗑 Usuń"))
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.clicked.connect(self._do_delete)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        self.btn_export = QPushButton(tr("📤 Eksportuj"))
        self.btn_export.clicked.connect(self._do_export)
        btn_row.addWidget(self.btn_export)
        rl.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 600])
        layout.addWidget(splitter, 1)

        # Count label
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: #6c7086; font-size: 8pt;")
        layout.addWidget(self.count_lbl)

    def load_scripts(self, scripts: list[Script]):
        self._scripts = scripts
        self._filter()

    def _filter(self):
        q = self.search_edit.text().lower()
        cat = self.filter_cat.currentText()
        search_code = self.chk_search_code.isChecked()
        only_pinned = self.chk_pinned_only.isChecked()

        current = self.list_widget.currentItem()
        selected_id = current.data(Qt.ItemDataRole.UserRole).get("id") if current else None

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        count = 0
        restore_item = None

        matched = []
        for s in self._scripts:
            if cat != tr("Wszystkie") and s.get("category") != cat:
                continue
            if only_pinned and not s.get("pinned", False):
                continue
            haystack = " ".join([s.get("name",""), s.get("tags",""), s.get("desc","")]).lower()
            in_meta = q and q in haystack
            in_code = search_code and q and q in s.get("code","").lower()
            if q and not in_meta and not in_code:
                continue
            matched.append((s, in_code and not in_meta))

        # Przypięte skrypty zawsze na górze listy, reszta zachowuje
        # dotychczasową kolejność (zwykle alfabetyczną po sortowaniu).
        matched.sort(key=lambda pair: not pair[0].get("pinned", False))

        for s, only_in_code in matched:
            pin_prefix = "📌 " if s.get("pinned", False) else ""
            label = f"{pin_prefix}[{s.get('category','?')}]  {s.get('name','')}"
            if only_in_code:
                label += f"  {tr('✅ w kodzie')}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s)
            # Podświetl wyniki znalezione tylko w kodzie
            if only_in_code:
                item.setForeground(QColor("#f9e2af"))
            self.list_widget.addItem(item)
            if selected_id is not None and s.get("id") == selected_id:
                restore_item = item
            count += 1
        self.count_lbl.setText(f"{tr('Skryptów:')} {count}")
        self.list_widget.blockSignals(False)

        if restore_item is not None:
            self.list_widget.setCurrentItem(restore_item)
        else:
            self.list_widget.setCurrentItem(None)
            self._clear_preview()

    def _format_stats(self, s: Script) -> str:
        run_count = s.get("run_count", 0)
        last_run = s.get("last_run")
        parts = [f"▶ {tr('Uruchomień:')} {run_count}"]
        if last_run:
            try:
                dt = datetime.datetime.fromisoformat(last_run)
                parts.append(f"{tr('Ostatnio:')} {dt.strftime('%Y-%m-%d %H:%M')}")
            except ValueError:
                parts.append(f"{tr('Ostatnio:')} {last_run}")
        return "   ".join(parts)

    def _clear_preview(self):
        self.preview_name.clear()
        self.preview_cat.clear()
        self.preview_tags.clear()
        self.preview_date.clear()
        self.preview_desc.clear()
        self.preview_stats.clear()
        self.preview_editor.clear()
        self.btn_pin.setText(tr("📌 Przypnij"))

    def _on_selection(self, current, _prev):
        if not current:
            self._clear_preview()
            return
        s = current.data(Qt.ItemDataRole.UserRole)
        self._show_preview(s)
        self.btn_pin.setText(tr("📌 Odepnij") if s.get("pinned", False) else tr("📌 Przypnij"))

    def _show_preview(self, s: Script):
        pin_prefix = "📌 " if s.get("pinned", False) else ""
        self.preview_name.setText(pin_prefix + s.get("name",""))
        self.preview_cat.setText(s.get("category",""))
        tags = s.get("tags","")
        self.preview_tags.setText(f"🏷 {tags}" if tags else "")
        self.preview_date.setText(s.get("date",""))
        self.preview_desc.setText(s.get("desc",""))
        self.preview_stats.setText(self._format_stats(s))
        code = s.get("code","")
        self.preview_editor.setPlainText(code)
        lang = s.get("category", "Other")
        self._preview_hl.set_language(lang)

        # Podświetl trafienia wyszukiwania w podglądzie kodu
        q = self.search_edit.text()
        if q and self.chk_search_code.isChecked() and q.lower() in code.lower():
            self._highlight_code_matches(q)

    def _highlight_code_matches(self, query: str):
        """Zaznacza wszystkie wystąpienia frazy w podglądzie kodu (case-insensitive)."""
        doc = self.preview_editor.document()
        cursor = QTextCursor(doc)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#f9e2af"))
        fmt.setForeground(QColor("#1e1e2e"))

        rx = QRegularExpression(
            re.escape(query),
            QRegularExpression.PatternOption.CaseInsensitiveOption
        )
        it = rx.globalMatch(doc.toPlainText())
        while it.hasNext():
            m = it.next()
            cursor.setPosition(m.capturedStart())
            cursor.setPosition(m.capturedEnd(), QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def _current_script(self) -> Optional[dict]:
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_double_click(self, item):
        s = item.data(Qt.ItemDataRole.UserRole)
        self.edit_requested.emit(s)

    def _do_edit(self):
        s = self._current_script()
        if s:
            self.edit_requested.emit(s)

    def _do_run(self):
        s = self._current_script()
        if s:
            self.run_requested.emit(s)

    def _do_copy(self):
        s = self._current_script()
        if s:
            QApplication.clipboard().setText(s.get("code",""))

    def _do_delete(self):
        s = self._current_script()
        if not s:
            return
        if self.confirm_delete:
            if QMessageBox.question(self, tr("Usuń skrypt"),
                f"{tr('Usunąć')} '{s.get('name')}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
        self._clear_preview()
        self.delete_requested.emit(s)

    def _do_duplicate(self):
        s = self._current_script()
        if s:
            self.duplicate_requested.emit(s)

    def _do_toggle_pin(self):
        s = self._current_script()
        if s:
            self.pin_toggled.emit(s)

    def _do_export(self):
        s = self._current_script()
        if not s:
            QMessageBox.information(self, tr("Eksport"), tr("Zaznacz skrypt na liście."))
            return
        ext = EXT_MAP.get(s.get("category","Other"), ".txt")
        path, _ = QFileDialog.getSaveFileName(self, tr("Eksportuj skrypt"),
                                              s.get("name","script") + ext,
                                              f"{tr('Skrypt')} (*{ext});;TXT (*.txt);;{tr('Wszystkie')} (*)")
        if path:
            Path(path).write_text(s.get("code",""), encoding="utf-8")

    def _ctx_menu(self, pos):
        s = self._current_script()
        if not s:
            return
        pin_label = tr("📌 Odepnij") if s.get("pinned", False) else tr("📌 Przypnij")
        menu = QMenu(self)
        menu.addAction(tr("✏️ Edytuj"), self._do_edit)
        menu.addAction(tr("▶ Uruchom"), self._do_run)
        menu.addAction(tr("📋 Kopiuj kod"), self._do_copy)
        menu.addSeparator()
        menu.addAction(pin_label, self._do_toggle_pin)
        menu.addSeparator()
        menu.addAction(tr("📤 Eksportuj"), self._do_export)
        menu.addSeparator()
        menu.addAction(tr("📑 Duplikuj"), self._do_duplicate)
        menu.addSeparator()
        menu.addAction(tr("🗑 Usuń"), self._do_delete)
        menu.exec(self.list_widget.mapToGlobal(pos))

# ─────────────────────────────────────────────
#  RUN DIALOG
# ─────────────────────────────────────────────
class ScriptRunWorker(QThread):
    """Uruchamia skrypt Python w osobnym wątku, żeby okno aplikacji
    pozostawało responsywne podczas oczekiwania na wynik.

    Output jest strumieniowany na bieżąco (linia po linii) przez sygnał
    output_line, zamiast czekać na zakończenie procesu i pokazać wszystko
    naraz – dzięki temu długo działające skrypty (np. z print() w pętli)
    są widoczne w czasie rzeczywistym."""
    output_line = pyqtSignal(str)
    finished_run = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, cmd: list[str], env: dict[str, str], timeout_s: int = 30, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.env = env
        self.timeout_s = timeout_s
        self._process: Optional[subprocess.Popen] = None
        self._stop_requested = False
        self._timed_out = False
        self._watchdog: Optional[threading.Timer] = None

    def run(self):
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=self.env,
                creationflags=flags, bufsize=1,
            )
        except Exception as e:
            self.failed.emit(str(e))
            return

        # Strażnik timeoutu działa równolegle, bo proc.stdout.readline()
        # jest blokujące i nie ma wbudowanego parametru timeout.
        if self.timeout_s:
            self._watchdog = threading.Timer(self.timeout_s, self._on_timeout)
            self._watchdog.daemon = True
            self._watchdog.start()

        collected = []
        try:
            for line in self._process.stdout:
                collected.append(line)
                self.output_line.emit(line.rstrip("\n"))
        except Exception as e:
            print(f"[ScriptDataBase] Błąd odczytu stdout: {e}", file=sys.stderr)
        finally:
            if self._watchdog:
                self._watchdog.cancel()

        self._process.wait()

        if self._timed_out:
            self.finished_run.emit(f"{tr('Timeout')} ({self.timeout_s}s).")
        elif self._stop_requested:
            self.finished_run.emit(tr("Przerwano przez użytkownika."))
        else:
            if not collected:
                self.finished_run.emit(tr("(brak wyjścia)"))
            else:
                self.finished_run.emit("")  # output już przesłany przez output_line

    def _on_timeout(self):
        self._timed_out = True
        self._kill_process()

    def _kill_process(self):
        if self._process and self._process.poll() is None:
            try:
                self._process.kill()
            except Exception as e:
                print(f"[ScriptDataBase] Nie można zabić procesu: {e}", file=sys.stderr)

    def stop(self):
        self._stop_requested = True
        if self._watchdog:
            self._watchdog.cancel()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception as e:
                print(f"[ScriptDataBase] Nie można zatrzymać procesu: {e}", file=sys.stderr)


class TerminalDetectWorker(QThread):
    """Wykrywa dostępne terminale w tle. W przeciwieństwie do zwykłego
    threading.Thread, QThread + pyqtSignal to jedyny niezawodny sposób
    bezpiecznego przekazania wyniku z powrotem do wątku GUI w Qt –
    QTimer.singleShot wywołany z wątku spoza Qt nie jest gwarantowany
    do działania (callback może nigdy się nie wykonać)."""
    detected = pyqtSignal(list)

    def run(self):
        terminals = detect_terminals()
        self.detected.emit(terminals)


class RunDialog(QDialog):
    def __init__(self, script: Script, terminals: list[tuple], parent=None):
        super().__init__(parent)
        self.script = script
        self.terminals = terminals
        self._worker: Optional[ScriptRunWorker] = None
        self._tmp_path: Optional[str] = None
        self.setWindowTitle(tr("Uruchom skrypt"))
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Skrypt: <b>{self.script.get('name')}</b>"))

        form = QFormLayout()
        self.combo_term = QComboBox()
        for tid, label in self.terminals:
            self.combo_term.addItem(label, tid)
        if not self.terminals:
            self.combo_term.addItem(tr("(brak terminali)"), None)
        form.addRow(tr("Terminal:"), self.combo_term)

        self.entry_args = QLineEdit()
        self.entry_args.setPlaceholderText(tr("opcjonalne argumenty..."))
        form.addRow(tr("Argumenty:"), self.entry_args)

        self.chk_tmpfile = QCheckBox(tr("Usuń plik tymczasowy po zakończeniu"))
        self.chk_tmpfile.setChecked(True)
        form.addRow("", self.chk_tmpfile)
        layout.addLayout(form)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # tryb nieokreślony (pulsujący)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText(tr("Wyjście skryptu pojawi się tutaj..."))
        self.output.setMaximumHeight(200)
        layout.addWidget(self.output)

        btns = QDialogButtonBox()
        self.run_btn = btns.addButton(tr("▶ Uruchom"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.stop_btn = btns.addButton(tr("⏹ Zatrzymaj"), QDialogButtonBox.ButtonRole.ActionRole)
        self.stop_btn.setEnabled(False)
        btns.addButton(tr("Zamknij"), QDialogButtonBox.ButtonRole.RejectRole)
        self.run_btn.clicked.connect(self._run)
        self.stop_btn.clicked.connect(self._stop)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _run(self):
        cat = self.script.get("category", "Other")
        if not self.terminals and cat != "Python":
            QMessageBox.warning(self, tr("Brak terminali"), tr("Nie wykryto żadnych terminali."))
            return
        if self._worker is not None and self._worker.isRunning():
            return  # już trwa

        tid = self.combo_term.currentData()
        args = self.entry_args.text().strip()
        code = self.script.get("code", "")
        ext = EXT_MAP.get(cat, ".txt")

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False,
                                             encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name
        except Exception as e:
            self.output.setText(f"{tr('Błąd:')} {e}")
            return
        self._tmp_path = tmp_path

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        if cat == "Python":
            cmd = [sys.executable, tmp_path] + (shlex.split(args) if args else [])
            self.output.clear()
            self._set_running(True)
            self._worker = ScriptRunWorker(cmd, env, timeout_s=30, parent=self)
            self._worker.output_line.connect(self._on_output_line)
            self._worker.finished_run.connect(self._on_finished)
            self._worker.failed.connect(self._on_failed)
            self._worker.finished.connect(lambda: self._set_running(False))
            self._worker.start()
        else:
            term_map = {t[0]: t for t in TERMINAL_DEFS}
            if tid not in term_map:
                self.output.append(tr("Nieznany terminal."))
                self._cleanup_tmp()
                return
            _, _, _, launch = term_map[tid]

            # Na Unixie plik tymczasowy nie ma domyślnie praw wykonywalnych,
            # więc "bash -c /tmp/plik.sh" próbowałby wykonać samą ścieżkę
            # jako komendę i kończyłby się "Permission denied". Zamiast na
            # to liczyć, budujemy komendę tak, by interpreter dostał plik
            # jako jawny argument źródłowy.
            if tid in ("bash", "sh", "zsh"):
                shell_bin = launch[0]
                cmd = [shell_bin, tmp_path] + (shlex.split(args) if args else [])
            elif tid in ("powershell", "pwsh"):
                cmd = launch[:-1] + [f"& '{tmp_path}'" + (f" {args}" if args else "")]
            else:
                cmd = launch + [tmp_path] + (shlex.split(args) if args else [])

            self.output.setText(f"{tr('Zapisano do:')} {tmp_path}\n{tr('Uruchamianie w terminalu...')}")
            try:
                proc = subprocess.Popen(cmd, env=env)
            except Exception as e:
                self.output.setText(f"{tr('Błąd:')} {e}")
                self._cleanup_tmp()
                return
            if self.chk_tmpfile.isChecked():
                self._watch_external_process(proc)

    def _watch_external_process(self, proc: subprocess.Popen):
        """Czeka w tle aż zewnętrzny terminal zakończy proces i wtedy
        usuwa plik tymczasowy (jeśli zaznaczono odpowiednią opcję).
        _cleanup_tmp() jest wywoływane przez QTimer.singleShot, żeby
        zawsze trafić do GUI thread – bezpośrednie wywołanie z wątku
        daemon naruszałoby thread-safety PyQt6."""
        def _wait():
            try:
                proc.wait()
            except Exception as e:
                print(f"[ScriptDataBase] Błąd oczekiwania na proces terminala: {e}",
                      file=sys.stderr)
            QTimer.singleShot(0, self._cleanup_tmp)
        threading.Thread(target=_wait, daemon=True).start()

    def _on_output_line(self, line: str):
        self.output.append(line)
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, status: str):
        if status:
            self.output.append(f"\n{status}")
        if self.chk_tmpfile.isChecked():
            self._cleanup_tmp()

    def _on_failed(self, message: str):
        self.output.setText(f"{tr('Błąd:')} {message}")
        self._cleanup_tmp()

    def _cleanup_tmp(self):
        if self._tmp_path:
            try:
                os.unlink(self._tmp_path)
            except Exception as e:
                print(f"[ScriptDataBase] Nie można usunąć pliku tymczasowego: {e}",
                      file=sys.stderr)
            self._tmp_path = None

    def _stop(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)

    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.progress.setVisible(running)

    def closeEvent(self, event):
        self._stop()
        event.accept()

    def reject(self):
        self._stop()
        super().reject()


# ─────────────────────────────────────────────
#  SETTINGS TAB
# ─────────────────────────────────────────────
class SettingsTab(QWidget):
    settings_changed  = pyqtSignal(dict)
    tab_order_changed = pyqtSignal(list)   # lista kluczy zakładek w nowej kolejności

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._tab_keys: list = []   # klucze odpowiadające pozycjom w tab_list_widget
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        hdr = QLabel(tr("⚙️ Ustawienia"))
        hdr.setStyleSheet("font-size: 14pt; font-weight: bold; color: #89b4fa;")
        layout.addWidget(hdr)

        # Theme
        grp_theme = QGroupBox(tr("Motyw"))
        gl = QHBoxLayout(grp_theme)
        self.radio_dark = QPushButton(tr("🌑 Ciemny (Dark)"))
        self.radio_dark.clicked.connect(lambda: self._set_theme("dark"))
        self.radio_light = QPushButton(tr("☀️ Jasny (Light)"))
        self.radio_light.clicked.connect(lambda: self._set_theme("light"))
        gl.addWidget(self.radio_dark)
        gl.addWidget(self.radio_light)
        gl.addStretch()
        layout.addWidget(grp_theme)

        # Language
        grp_lang = QGroupBox(tr("🌐 Język"))
        ll = QHBoxLayout(grp_lang)
        self.btn_lang_pl = QPushButton(tr("🇵🇱 Polski"))
        self.btn_lang_pl.clicked.connect(lambda: self._set_language("pl"))
        self.btn_lang_en = QPushButton(tr("🇬🇧 Angielski"))
        self.btn_lang_en.clicked.connect(lambda: self._set_language("en"))
        ll.addWidget(self.btn_lang_pl)
        ll.addWidget(self.btn_lang_en)
        ll.addStretch()
        layout.addWidget(grp_lang)

        # Font
        grp_font = QGroupBox(tr("Czcionka edytora"))
        fl = QFormLayout(grp_font)
        self.spin_font = QSpinBox()
        self.spin_font.setRange(7, 24)
        self.spin_font.setValue(10)
        fl.addRow(tr("Rozmiar:"), self.spin_font)
        self.combo_font = QComboBox()
        self.combo_font.addItems(["Consolas", "Courier New", "Fira Code",
                                   "JetBrains Mono", "Cascadia Code", "Monospace"])
        fl.addRow(tr("Rodzina:"), self.combo_font)
        layout.addWidget(grp_font)

        # General
        grp_gen = QGroupBox(tr("Ogólne"))
        genl = QVBoxLayout(grp_gen)
        self.chk_confirm_del = QCheckBox(tr("Potwierdzaj usuwanie skryptów"))
        self.chk_confirm_del.setChecked(True)
        genl.addWidget(self.chk_confirm_del)
        layout.addWidget(grp_gen)

        # Kolejność zakładek – przeciąganie (drag & drop) lub przyciski ↑/↓.
        # Lista jest jedynym źródłem prawdy o kolejności w tym widgecie;
        # MainWindow synchronizuje ją w obie strony (patrz set_available_tabs
        # oraz sygnał tab_order_changed).
        grp_tabs = QGroupBox(tr("Kolejność zakładek"))
        tl = QVBoxLayout(grp_tabs)
        tl.addWidget(QLabel(tr("Przeciągnij pozycje, aby zmienić kolejność zakładek głównego okna.")))
        tab_row = QHBoxLayout()
        self.tab_list_widget = QListWidget()
        self.tab_list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tab_list_widget.setMaximumHeight(140)
        self.tab_list_widget.model().rowsMoved.connect(self._on_tab_list_reordered)
        tab_row.addWidget(self.tab_list_widget, 1)

        tab_btns = QVBoxLayout()
        self.btn_tab_up = QPushButton(tr("⬆ W górę"))
        self.btn_tab_up.clicked.connect(self._move_tab_up)
        tab_btns.addWidget(self.btn_tab_up)
        self.btn_tab_down = QPushButton(tr("⬇ W dół"))
        self.btn_tab_down.clicked.connect(self._move_tab_down)
        tab_btns.addWidget(self.btn_tab_down)
        tab_btns.addStretch()
        tab_row.addLayout(tab_btns)
        tl.addLayout(tab_row)
        layout.addWidget(grp_tabs)

        # Buttons
        btn_row = QHBoxLayout()
        btn_save = QPushButton(tr("💾 Zapisz ustawienia"))
        btn_save.setObjectName("btn_save")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_reset = QPushButton(tr("↩ Przywróć domyślne"))
        btn_reset.clicked.connect(self._reset)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    def _load_values(self):
        self.spin_font.setValue(self.settings.get("font_size", 10))
        fam = self.settings.get("font_family", "Consolas")
        idx = self.combo_font.findText(fam)
        if idx >= 0:
            self.combo_font.setCurrentIndex(idx)
        self.chk_confirm_del.setChecked(self.settings.get("confirm_delete", True))

    # ─── Kolejność zakładek ───────────────────
    def set_available_tabs(self, pairs: list[tuple[str, str]]):
        """Wypełnia listę zakładkami w podanej kolejności. pairs to lista
        (klucz, etykieta) – wywoływane przez MainWindow przy starcie i po
        każdej zmianie kolejności (np. przeciągnięciem na pasku zakładek),
        żeby ta lista zawsze odzwierciedlała stan faktyczny."""
        self.tab_list_widget.blockSignals(True)
        self.tab_list_widget.clear()
        self._tab_keys = []
        for key, label in pairs:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.tab_list_widget.addItem(item)
            self._tab_keys.append(key)
        self.tab_list_widget.blockSignals(False)

    def _sync_keys_from_widget(self):
        self._tab_keys = [
            self.tab_list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.tab_list_widget.count())
        ]

    def _on_tab_list_reordered(self, *_args):
        self._sync_keys_from_widget()
        self.tab_order_changed.emit(self._tab_keys)

    def _move_tab_up(self):
        row = self.tab_list_widget.currentRow()
        if row <= 0:
            return
        item = self.tab_list_widget.takeItem(row)
        self.tab_list_widget.insertItem(row - 1, item)
        self.tab_list_widget.setCurrentRow(row - 1)
        self._sync_keys_from_widget()
        self.tab_order_changed.emit(self._tab_keys)

    def _move_tab_down(self):
        row = self.tab_list_widget.currentRow()
        if row < 0 or row >= self.tab_list_widget.count() - 1:
            return
        item = self.tab_list_widget.takeItem(row)
        self.tab_list_widget.insertItem(row + 1, item)
        self.tab_list_widget.setCurrentRow(row + 1)
        self._sync_keys_from_widget()
        self.tab_order_changed.emit(self._tab_keys)

    def _set_theme(self, theme: str):
        self.settings["theme"] = theme
        self.settings_changed.emit(self.settings)

    def _set_language(self, lang: str):
        if lang == self.settings.get("language", "pl"):
            return
        self.settings["language"] = lang
        self.settings_changed.emit(self.settings)

    def _save(self):
        self.settings["font_size"] = self.spin_font.value()
        self.settings["font_family"] = self.combo_font.currentText()
        self.settings["confirm_delete"] = self.chk_confirm_del.isChecked()
        self.settings_changed.emit(self.settings)
        try:
            save_json(SETT_FILE, self.settings)
        except OSError as e:
            QMessageBox.critical(self, tr("Błąd zapisu"),
                f"{tr('Nie można zapisać ustawień:')}\n{e}")
            return
        QMessageBox.information(self, tr("Ustawienia"), tr("Ustawienia zapisane."))

    def _reset(self):
        self.settings = {"theme": "dark", "font_size": 10, "font_family": "Consolas", "confirm_delete": True}
        self._load_values()
        self.settings_changed.emit(self.settings)
        default_order = ["edit", "list", "settings", "snippets", "stats"]
        self.tab_order_changed.emit(default_order)

# ─────────────────────────────────────────────
#  STATS DIALOG
# ─────────────────────────────────────────────
class StatsDialog(QDialog):
    """Podsumowanie bazy skryptów: liczba skryptów per kategoria,
    najczęściej i ostatnio uruchamiane skrypty oraz przypięte ulubione."""

    def __init__(self, scripts: list[Script], parent=None):
        super().__init__(parent)
        self.scripts = scripts
        self.setWindowTitle(tr("📊 Statystyki"))
        self.setMinimumSize(560, 480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        total = len(self.scripts)
        pinned = sum(1 for s in self.scripts if s.get("pinned", False))
        total_runs = sum(s.get("run_count", 0) for s in self.scripts)

        summary = QLabel(
            f"{tr('Skryptów:')} <b>{total}</b>   •   "
            f"📌 {tr('Przypiętych:')} <b>{pinned}</b>   •   "
            f"▶ {tr('Łącznie uruchomień:')} <b>{total_runs}</b>"
        )
        summary.setStyleSheet("font-size: 10pt;")
        layout.addWidget(summary)

        # ── Skrypty per kategoria ──
        grp_cat = QGroupBox(tr("Skrypty wg kategorii"))
        cat_layout = QVBoxLayout(grp_cat)
        self.tree_cat = QTreeWidget()
        self.tree_cat.setHeaderLabels([tr("Kategoria"), tr("Liczba")])
        self.tree_cat.setRootIsDecorated(False)
        self.tree_cat.setMaximumHeight(150)
        counts: dict = {}
        for s in self.scripts:
            cat = s.get("category", "Other")
            counts[cat] = counts.get(cat, 0) + 1
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            QTreeWidgetItem(self.tree_cat, [cat, str(n)])
        cat_layout.addWidget(self.tree_cat)
        layout.addWidget(grp_cat)

        # ── Najczęściej uruchamiane ──
        grp_top = QGroupBox(tr("Najczęściej uruchamiane"))
        top_layout = QVBoxLayout(grp_top)
        self.tree_top = QTreeWidget()
        self.tree_top.setHeaderLabels([tr("Skrypt"), tr("Uruchomień")])
        self.tree_top.setRootIsDecorated(False)
        self.tree_top.setMaximumHeight(150)
        most_run = sorted(
            (s for s in self.scripts if s.get("run_count", 0) > 0),
            key=lambda s: -s.get("run_count", 0)
        )[:10]
        if most_run:
            for s in most_run:
                QTreeWidgetItem(self.tree_top, [s.get("name",""), str(s.get("run_count", 0))])
        else:
            empty = QTreeWidgetItem(self.tree_top, [tr("(brak danych)"), ""])
            empty.setDisabled(True)
        top_layout.addWidget(self.tree_top)
        layout.addWidget(grp_top)

        # ── Przypięte skrypty ──
        grp_pinned = QGroupBox(tr("Przypięte skrypty"))
        pinned_layout = QVBoxLayout(grp_pinned)
        self.tree_pinned = QTreeWidget()
        self.tree_pinned.setHeaderLabels([tr("Skrypt"), tr("Kategoria")])
        self.tree_pinned.setRootIsDecorated(False)
        self.tree_pinned.setMaximumHeight(120)
        pinned_scripts = [s for s in self.scripts if s.get("pinned", False)]
        if pinned_scripts:
            for s in pinned_scripts:
                QTreeWidgetItem(self.tree_pinned, [s.get("name",""), s.get("category","")])
        else:
            empty = QTreeWidgetItem(self.tree_pinned, [tr("(brak danych)"), ""])
            empty.setDisabled(True)
        pinned_layout.addWidget(self.tree_pinned)
        layout.addWidget(grp_pinned)

        btns = QDialogButtonBox()
        btns.addButton(tr("Zamknij"), QDialogButtonBox.ButtonRole.RejectRole)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

# ─────────────────────────────────────────────
#  STATS TAB (stały tab w głównym pasku zakładek)
# ─────────────────────────────────────────────
class StatsTab(QWidget):
    """Wersja StatsDialog jako stały tab głównego okna – te same dane
    (skrypty per kategoria, najczęściej uruchamiane, przypięte), ale
    odświeżane na żądanie przez refresh() zamiast budowane raz przy
    otwarciu modalnego okna."""

    def __init__(self, scripts: list[Script], parent=None):
        super().__init__(parent)
        self.scripts = scripts
        self._build_ui()
        self.refresh(scripts)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        hdr = QLabel(tr("📊 Statystyki"))
        hdr.setStyleSheet("font-size: 14pt; font-weight: bold; color: #89b4fa;")
        layout.addWidget(hdr)

        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet("font-size: 10pt;")
        layout.addWidget(self.lbl_summary)

        # ── Skrypty per kategoria ──
        grp_cat = QGroupBox(tr("Skrypty wg kategorii"))
        cat_layout = QVBoxLayout(grp_cat)
        self.tree_cat = QTreeWidget()
        self.tree_cat.setHeaderLabels([tr("Kategoria"), tr("Liczba")])
        self.tree_cat.setRootIsDecorated(False)
        self.tree_cat.setMaximumHeight(150)
        cat_layout.addWidget(self.tree_cat)
        layout.addWidget(grp_cat)

        # ── Najczęściej uruchamiane ──
        grp_top = QGroupBox(tr("Najczęściej uruchamiane"))
        top_layout = QVBoxLayout(grp_top)
        self.tree_top = QTreeWidget()
        self.tree_top.setHeaderLabels([tr("Skrypt"), tr("Uruchomień")])
        self.tree_top.setRootIsDecorated(False)
        self.tree_top.setMaximumHeight(150)
        top_layout.addWidget(self.tree_top)
        layout.addWidget(grp_top)

        # ── Przypięte skrypty ──
        grp_pinned = QGroupBox(tr("Przypięte skrypty"))
        pinned_layout = QVBoxLayout(grp_pinned)
        self.tree_pinned = QTreeWidget()
        self.tree_pinned.setHeaderLabels([tr("Skrypt"), tr("Kategoria")])
        self.tree_pinned.setRootIsDecorated(False)
        self.tree_pinned.setMaximumHeight(120)
        pinned_layout.addWidget(self.tree_pinned)
        layout.addWidget(grp_pinned)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton(tr("🔄 Odśwież"))
        btn_refresh.clicked.connect(lambda: self.refresh(self.scripts))
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    def refresh(self, scripts: list[Script]):
        """Przebudowuje wszystkie listy na podstawie aktualnej kolekcji
        skryptów – wywoływane przez MainWindow po każdej zmianie danych
        (zapis/usunięcie/duplikacja skryptu, przełączenie pin, itd.)."""
        self.scripts = scripts

        total = len(self.scripts)
        pinned = sum(1 for s in self.scripts if s.get("pinned", False))
        total_runs = sum(s.get("run_count", 0) for s in self.scripts)
        self.lbl_summary.setText(
            f"{tr('Skryptów:')} <b>{total}</b>   •   "
            f"📌 {tr('Przypiętych:')} <b>{pinned}</b>   •   "
            f"▶ {tr('Łącznie uruchomień:')} <b>{total_runs}</b>"
        )

        self.tree_cat.clear()
        counts: dict = {}
        for s in self.scripts:
            cat = s.get("category", "Other")
            counts[cat] = counts.get(cat, 0) + 1
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            QTreeWidgetItem(self.tree_cat, [cat, str(n)])

        self.tree_top.clear()
        most_run = sorted(
            (s for s in self.scripts if s.get("run_count", 0) > 0),
            key=lambda s: -s.get("run_count", 0)
        )[:10]
        if most_run:
            for s in most_run:
                QTreeWidgetItem(self.tree_top, [s.get("name",""), str(s.get("run_count", 0))])
        else:
            empty = QTreeWidgetItem(self.tree_top, [tr("(brak danych)"), ""])
            empty.setDisabled(True)

        self.tree_pinned.clear()
        pinned_scripts = [s for s in self.scripts if s.get("pinned", False)]
        if pinned_scripts:
            for s in pinned_scripts:
                QTreeWidgetItem(self.tree_pinned, [s.get("name",""), s.get("category","")])
        else:
            empty = QTreeWidgetItem(self.tree_pinned, [tr("(brak danych)"), ""])
            empty.setDisabled(True)

# ─────────────────────────────────────────────
#  ABOUT DIALOG
# ─────────────────────────────────────────────
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("O programie – ScriptDataBase Lite v3.0.8"))
        self.setMinimumWidth(480)
        self.setMaximumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel(tr("🗄️ ScriptDataBase Lite"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #89b4fa;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(tr("wersja 3.0.8  •  PyQt6"))
        ver.setStyleSheet("font-size: 10pt; color: #6c7086;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #313244;")
        layout.addWidget(line)

        # Author block
        grp_author = QGroupBox(tr("Autor"))
        al = QFormLayout(grp_author)
        al.setSpacing(6)
        al.setContentsMargins(12, 10, 12, 10)

        def _row(label: str, value: str, link: str = "") -> QLabel:
            lbl = QLabel()
            if link:
                lbl.setText(f'<a href="{link}" style="color:#89b4fa;">{value}</a>')
                lbl.setOpenExternalLinks(True)
            else:
                lbl.setText(value)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                        Qt.TextInteractionFlag.LinksAccessibleByMouse)
            return lbl

        al.addRow(QLabel(tr("<b>Imię i nazwisko:</b>")), _row("", "Sebastian Januchowski"))
        al.addRow(QLabel(tr("<b>Organizacja:</b>")),     _row("", "polsoft.ITS™ Group"))
        al.addRow(QLabel(tr("<b>GitHub:</b>")),
                  _row("", "github.com/polsoft-seb07uk", "https://github.com/polsoft-seb07uk"))
        al.addRow(QLabel(tr("<b>E-mail:</b>")),
                  _row("", "polsoft.its@fastservice.com",
                       "mailto:polsoft.its@fastservice.com"))
        al.addRow(QLabel(tr("<b>Licencja:</b>")),        _row("", "Freeware – wolne oprogramowanie"))
        layout.addWidget(grp_author)

        # System info block
        grp_sys = QGroupBox(tr("Środowisko"))
        sl = QFormLayout(grp_sys)
        sl.setSpacing(6)
        sl.setContentsMargins(12, 10, 12, 10)

        def _info(v: str) -> QLabel:
            lbl = QLabel(v)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setStyleSheet("color: #a6adc8;")
            return lbl

        sl.addRow(QLabel(tr("<b>Python:</b>")),    _info(sys.version.split()[0]))
        sl.addRow(QLabel(tr("<b>Platforma:</b>")), _info(f"{platform.system()} {platform.release()}"))
        sl.addRow(QLabel(tr("<b>Katalog:</b>")),   _info(str(BASE_DIR)))
        layout.addWidget(grp_sys)

        # Copyright notice
        copy_lbl = QLabel(
            "© 2025 Sebastian Januchowski / polsoft.ITS™ Group\n"
            "Program jest darmowy (Freeware). Dozwolone jest używanie\n"
            "i dystrybuowanie bez modyfikacji, z zachowaniem informacji o autorze."
        )
        copy_lbl.setStyleSheet("font-size: 8pt; color: #6c7086;")
        copy_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy_lbl.setWordWrap(True)
        layout.addWidget(copy_lbl)

        btn = QPushButton(tr("OK"))
        btn.setFixedWidth(100)
        btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

# ─────────────────────────────────────────────
#  SNIPPETS TAB
# ─────────────────────────────────────────────
class SnippetsTab(QWidget):
    """Niezależna mini-baza krótkich fragmentów kodu (boilerplate,
    jednolinijkowce, idiomy) – osobny plik snippets.json, osobne
    od głównej bazy skryptów. Pozwala szybko wstawić zapisany
    fragment do edytora w zakładce Nowy/Edytuj."""

    insert_requested = pyqtSignal(str)   # kod snippetu do wstawienia w edytorze

    def __init__(self, dark=True, parent=None):
        super().__init__(parent)
        self.dark = dark
        self._snippets: list[Snippet] = []
        self._editing_id: Optional[str] = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Lewa strona: lista + filtr ──
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)

        bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("🔍 Szukaj snippetów (nazwa / kod)..."))
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(150)
        self._filter_timer.timeout.connect(self._filter)
        self.search_edit.textChanged.connect(self._filter_timer.start)
        bar.addWidget(self.search_edit)
        ll.addLayout(bar)

        self.filter_cat = QComboBox()
        self.filter_cat.addItem(tr("Wszystkie"))
        self.filter_cat.addItems(CATEGORIES)
        self.filter_cat.currentTextChanged.connect(self._filter)
        ll.addWidget(self.filter_cat)

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._ctx_menu)
        self.list_widget.currentItemChanged.connect(self._on_selection)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._do_insert())
        ll.addWidget(self.list_widget, 1)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: #6c7086; font-size: 8pt;")
        ll.addWidget(self.count_lbl)

        splitter.addWidget(left)

        # ── Prawa strona: edytor snippetu ──
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        form = QHBoxLayout()
        self.entry_name = QLineEdit()
        self.entry_name.setPlaceholderText(tr("Nazwa snippetu..."))
        form.addWidget(QLabel(tr("Nazwa:")))
        form.addWidget(self.entry_name, 1)
        form.addWidget(QLabel(tr("Kategoria:")))
        self.combo_cat = QComboBox()
        self.combo_cat.addItems(CATEGORIES)
        self.combo_cat.currentTextChanged.connect(self._on_category_changed)
        form.addWidget(self.combo_cat)
        rl.addLayout(form)

        self.editor = CodeEditor(self.dark)
        self.editor.setPlaceholderText(tr("# Wpisz lub wklej tutaj fragment kodu..."))
        self._hl = SyntaxHighlighterQt(self.editor.document(), "Python", self.dark)
        self.editor._highlighter = self._hl
        rl.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton(tr("➕ Nowy snippet"))
        self.btn_new.clicked.connect(self._do_new)
        btn_row.addWidget(self.btn_new)

        self.btn_save = QPushButton(tr("💾 Zapisz snippet"))
        self.btn_save.setObjectName("btn_save")
        self.btn_save.clicked.connect(self._do_save)
        btn_row.addWidget(self.btn_save)

        self.btn_insert = QPushButton(tr("⏎ Wstaw do edytora"))
        self.btn_insert.setObjectName("btn_run")
        self.btn_insert.clicked.connect(self._do_insert)
        btn_row.addWidget(self.btn_insert)

        self.btn_copy = QPushButton(tr("📋 Kopiuj"))
        self.btn_copy.clicked.connect(self._do_copy)
        btn_row.addWidget(self.btn_copy)

        btn_row.addStretch()
        self.btn_delete = QPushButton(tr("🗑 Usuń"))
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.clicked.connect(self._do_delete)
        btn_row.addWidget(self.btn_delete)
        rl.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([260, 620])
        layout.addWidget(splitter, 1)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #6c7086; font-size: 8pt;")
        layout.addWidget(self.status_lbl)

    # ─── Dane ─────────────────────────────────
    def _load(self):
        self._snippets = load_json(SNIP_FILE, [])
        changed = False
        for sn in self._snippets:
            if "id" not in sn or not str(sn["id"]).strip():
                sn["id"] = new_id()
                changed = True
        if changed:
            self._save_all()
        self._filter()

    def _save_all(self):
        try:
            save_json(SNIP_FILE, self._snippets)
        except OSError as e:
            QMessageBox.critical(self, tr("Błąd zapisu"),
                f"{tr('Nie można zapisać snippets.json:')}\n{e}")

    # ─── Filtr / lista ────────────────────────
    def _filter(self):
        q = self.search_edit.text().lower()
        cat = self.filter_cat.currentText()

        current = self.list_widget.currentItem()
        selected_id = current.data(Qt.ItemDataRole.UserRole).get("id") if current else None

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        count = 0
        restore_item = None
        for sn in self._snippets:
            if cat != tr("Wszystkie") and sn.get("category") != cat:
                continue
            haystack = (sn.get("name","") + " " + sn.get("code","")).lower()
            if q and q not in haystack:
                continue
            label = f"[{sn.get('category','?')}]  {sn.get('name','')}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, sn)
            self.list_widget.addItem(item)
            if selected_id is not None and sn.get("id") == selected_id:
                restore_item = item
            count += 1
        self.count_lbl.setText(f"{tr('Snippetów:')} {count}")
        self.list_widget.blockSignals(False)

        if restore_item is not None:
            self.list_widget.setCurrentItem(restore_item)

    def _current_snippet(self) -> Optional[Snippet]:
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_selection(self, current, _prev):
        if not current:
            return
        sn = current.data(Qt.ItemDataRole.UserRole)
        self._editing_id = sn.get("id")
        self.entry_name.setText(sn.get("name",""))
        idx = self.combo_cat.findText(sn.get("category","Other"))
        if idx >= 0:
            self.combo_cat.setCurrentIndex(idx)
        self.editor.setPlainText(sn.get("code",""))
        self._hl.set_language(sn.get("category","Other"))

    def _on_category_changed(self, category: str):
        self._hl.set_language(category)

    # ─── Akcje ────────────────────────────────
    def _do_new(self):
        self._editing_id = None
        self.entry_name.clear()
        self.editor.clear()
        self.combo_cat.setCurrentIndex(0)
        self.list_widget.setCurrentItem(None)
        self.entry_name.setFocus()

    def _do_save(self):
        name = self.entry_name.text().strip()
        code = self.editor.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, tr("Błąd"), tr("Podaj nazwę snippetu."))
            return
        if not code:
            QMessageBox.warning(self, tr("Błąd"), tr("Kod snippetu jest pusty."))
            return
        if self._editing_id is not None:
            for sn in self._snippets:
                if sn.get("id") == self._editing_id:
                    sn["name"] = name
                    sn["category"] = self.combo_cat.currentText()
                    sn["code"] = code
                    sn["date"] = datetime.date.today().isoformat()
                    break
            self.status_lbl.setText(f"{tr('✅ Zaktualizowano:')} {name}")
        else:
            sn = {
                "id": new_id(),
                "name": name,
                "category": self.combo_cat.currentText(),
                "code": code,
                "date": datetime.date.today().isoformat(),
            }
            self._snippets.append(sn)
            self._editing_id = sn["id"]
            self.status_lbl.setText(f"{tr('✅ Zapisano:')} {name}")
        self._save_all()
        self._filter()

    def _do_delete(self):
        sn = self._current_snippet()
        if not sn:
            return
        if QMessageBox.question(
            self, tr("Usuń snippet"),
            f"{tr('Usunąć')} '{sn.get('name')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._snippets = [x for x in self._snippets if x.get("id") != sn.get("id")]
        self._save_all()
        self._do_new()
        self._filter()
        self.status_lbl.setText(f"{tr('🗑 Usunięto:')} {sn.get('name','')}")

    def _do_copy(self):
        code = self.editor.toPlainText()
        if code:
            QApplication.clipboard().setText(code)
            self.status_lbl.setText(tr("✅ Skopiowano do schowka!"))

    def _do_insert(self):
        """Wysyła kod bieżącego snippetu do zakładki Nowy/Edytuj, wstawiając
        go w aktualnej pozycji kursora edytora głównego (zamiast zaznaczenia,
        jeśli takie istnieje)."""
        code = self.editor.toPlainText()
        if not code.strip():
            sn = self._current_snippet()
            code = sn.get("code","") if sn else ""
        if not code:
            return
        self.insert_requested.emit(code)
        self.status_lbl.setText(tr("⏎ Wstawiono do edytora."))

    def _ctx_menu(self, pos):
        sn = self._current_snippet()
        if not sn:
            return
        menu = QMenu(self)
        menu.addAction(tr("⏎ Wstaw do edytora"), self._do_insert)
        menu.addAction(tr("📋 Kopiuj"), self._do_copy)
        menu.addSeparator()
        menu.addAction(tr("🗑 Usuń"), self._do_delete)
        menu.exec(self.list_widget.mapToGlobal(pos))

    # ─── Motyw / czcionka (wywoływane z MainWindow) ──
    def set_dark(self, dark: bool):
        self.dark = dark
        self.editor.set_dark(dark)
        self._hl.set_dark(dark)

    def apply_font_settings(self, family: str, size: int):
        self.editor.apply_font_settings(family, size)

# ─────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._scripts: list[Script] = load_json(DATA_FILE, [])
        self._migrate_script_stats()
        self._settings: AppSettings = {
            "theme": "light",
            "language": "en",
            "font_size": 10,
            "font_family": "Consolas",
            "confirm_delete": True,
            "seed_builtins": True,
            **load_json(SETT_FILE, {})
        }
        self._dark = (self._settings.get("theme", "light") == "dark")
        LanguageManager.set_language(self._settings.get("language", "en"))
        self._terminals: list[tuple] = []

        self.setWindowTitle(tr("🗄️ ScriptDataBase Lite v3.0.8"))
        self.setMinimumSize(1000, 660)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self._restore_geometry()
        self._apply_theme()
        self._build_ui()
        self._build_menubar()
        # Zastosuj zapisaną czcionkę edytora
        fam  = self._settings.get("font_family", "Consolas")
        fsz  = self._settings.get("font_size", 10)
        self.tab_edit.editor.apply_font_settings(fam, fsz)
        self.tab_list.preview_editor.apply_font_settings(fam, fsz)
        self.tab_snippets.apply_font_settings(fam, fsz)
        self._refresh_list()

        # Detect terminals in background
        QTimer.singleShot(500, self._detect_terminals_bg)

        self.statusBar().showMessage(tr("ScriptDataBase Lite v3.0.8 gotowy  |  Ctrl+N: nowy  |  Ctrl+S: zapisz  |  Ctrl+Enter: uruchom"))

    def _migrate_script_stats(self):
        """Uzupełnia brakujące pola statystyk (pinned/run_count/last_run)
        w skryptach zapisanych przed wprowadzeniem tej funkcji – zapewnia
        wsteczną kompatybilność ze starszymi plikami scripts.json."""
        changed = False
        for s in self._scripts:
            if "pinned" not in s:
                s["pinned"] = False
                changed = True
            if "run_count" not in s:
                s["run_count"] = 0
                changed = True
            if "last_run" not in s:
                s["last_run"] = None
                changed = True
        if changed:
            try:
                save_json(DATA_FILE, self._scripts)
            except OSError as e:
                print(f"[ScriptDataBase] Błąd zapisu migracji: {e}", file=sys.stderr)

    def _restore_geometry(self):
        geo = self._settings.get("window_geometry", "")
        if geo:
            try:
                w, h = map(int, geo.split("x"))
                self.resize(w, h)
                # Center
                screen = QApplication.primaryScreen().availableGeometry()
                self.move((screen.width()-w)//2, (screen.height()-h)//2)
                return
            except Exception as e:
                print(f"[ScriptDataBase] Nieprawidłowa geometria okna: {e}", file=sys.stderr)
        self.resize(1150, 740)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width()-1150)//2, (screen.height()-740)//2)

    def _apply_theme(self):
        c = DARK if self._dark else LIGHT
        self._colors = c
        self.setStyleSheet(make_stylesheet(c))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        # Przeciąganie zakładek myszką – pozwala zamienić ich kolejność
        # bez konieczności otwierania ustawień.
        self.tabs.setMovable(True)
        self.tabs.tabBar().tabMoved.connect(self._on_tab_moved)

        # Tab 0: Add/Edit
        self.tab_edit = AddEditTab(self._dark)
        self.tab_edit.script_saved.connect(self._on_script_saved)
        self.tabs.addTab(self.tab_edit, tr("➕ Nowy / Edytuj"))

        # Tab 1: List
        self.tab_list = ScriptListTab(self._terminals)
        self.tab_list.confirm_delete = self._settings.get("confirm_delete", True)
        self.tab_list.edit_requested.connect(self._load_for_edit)
        self.tab_list.run_requested.connect(self._run_script)
        self.tab_list.delete_requested.connect(self._delete_script)
        self.tab_list.duplicate_requested.connect(self._duplicate_script)
        self.tab_list.pin_toggled.connect(self._toggle_pin)
        self.tabs.addTab(self.tab_list, tr("📋 Moje skrypty"))

        # Tab 2: Settings
        self.tab_settings = SettingsTab(self._settings)
        self.tab_settings.settings_changed.connect(self._on_settings_changed)
        self.tab_settings.tab_order_changed.connect(self._apply_tab_order)
        self.tabs.addTab(self.tab_settings, tr("⚙️ Ustawienia"))

        # Tab 3: Snippets
        self.tab_snippets = SnippetsTab(self._dark)
        self.tab_snippets.insert_requested.connect(self._insert_snippet)
        self.tabs.addTab(self.tab_snippets, tr("🧩 Snippety"))

        # Tab 4: Stats
        self.tab_stats = StatsTab(self._scripts)
        self.tabs.addTab(self.tab_stats, tr("📊 Statystyki"))

        # Stałe klucze zakładek (niezależne od tłumaczonych etykiet i od
        # bieżącej pozycji na pasku) – używane do zapisu/odczytu kolejności
        # w ustawieniach (tab_order) oraz do nawigacji po widgecie (_goto_tab).
        self._tab_keys = ["edit", "list", "settings", "snippets", "stats"]
        self.tab_settings.set_available_tabs(self._tab_labels())
        self._restore_tab_order()

        main_layout.addWidget(self.tabs)

    def _build_menubar(self):
        mb = self.menuBar()

        # ── Plik ──
        m_file = mb.addMenu(tr("Plik"))

        a_new = QAction(tr("➕ Nowy skrypt"), self)
        a_new.setShortcut(QKeySequence("Ctrl+N"))
        a_new.triggered.connect(self._new_script)
        m_file.addAction(a_new)

        a_open = QAction(tr("📂 Otwórz plik do edytora"), self)
        a_open.setShortcut(QKeySequence("Ctrl+O"))
        a_open.triggered.connect(self._open_file)
        m_file.addAction(a_open)

        m_file.addSeparator()

        a_save = QAction(tr("💾 Zapisz skrypt"), self)
        a_save.setShortcut(QKeySequence("Ctrl+S"))
        a_save.triggered.connect(self.tab_edit._save)
        m_file.addAction(a_save)

        m_file.addSeparator()

        a_run_editor = QAction(tr("▶ Uruchom z edytora"), self)
        a_run_editor.setShortcut(QKeySequence("Ctrl+Return"))
        a_run_editor.triggered.connect(self._run_from_editor)
        m_file.addAction(a_run_editor)

        m_file.addSeparator()

        a_import = QAction(tr("📥 Importuj skrypty (JSON)"), self)
        a_import.triggered.connect(self._import_scripts)
        m_file.addAction(a_import)

        a_export_json = QAction(tr("📤 Eksportuj wszystkie (JSON)"), self)
        a_export_json.triggered.connect(self._export_all_json)
        m_file.addAction(a_export_json)

        a_export_zip = QAction(tr("📦 Eksportuj wszystkie (ZIP)"), self)
        a_export_zip.triggered.connect(self._export_all_zip)
        m_file.addAction(a_export_zip)

        m_file.addSeparator()

        a_open_dir = QAction(tr("📁 Otwórz folder danych"), self)
        a_open_dir.triggered.connect(lambda: self._open_path(BASE_DIR))
        m_file.addAction(a_open_dir)

        m_file.addSeparator()

        a_quit = QAction(tr("✖ Wyjdź"), self)
        a_quit.setShortcut(QKeySequence("Alt+F4"))
        a_quit.triggered.connect(self.close)
        m_file.addAction(a_quit)

        # ── Skrypty ──
        m_scripts = mb.addMenu(tr("Skrypty"))

        a_edit = QAction(tr("✏️ Edytuj wybrany"), self)
        a_edit.setShortcut(QKeySequence("Ctrl+E"))
        a_edit.triggered.connect(lambda: self.tab_list._do_edit())
        m_scripts.addAction(a_edit)

        a_run = QAction(tr("▶ Uruchom wybrany"), self)
        a_run.setShortcut(QKeySequence("Ctrl+R"))
        a_run.triggered.connect(lambda: self.tab_list._do_run())
        m_scripts.addAction(a_run)

        a_copy = QAction(tr("📋 Kopiuj kod"), self)
        a_copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        a_copy.triggered.connect(lambda: self.tab_list._do_copy())
        m_scripts.addAction(a_copy)

        a_pin = QAction(tr("📌 Przypnij / odepnij wybrany"), self)
        a_pin.setShortcut(QKeySequence("Ctrl+P"))
        a_pin.triggered.connect(lambda: self.tab_list._do_toggle_pin())
        m_scripts.addAction(a_pin)

        m_scripts.addSeparator()

        a_del = QAction(tr("🗑 Usuń wybrany"), self)
        a_del.setShortcut(QKeySequence("Delete"))
        a_del.triggered.connect(lambda: self.tab_list._do_delete())
        m_scripts.addAction(a_del)

        # ── Edycja ──
        m_edit = mb.addMenu(tr("Edycja"))

        a_find = QAction(tr("🔍 Znajdź / Zamień w edytorze (Ctrl+H)"), self)
        a_find.triggered.connect(self._open_find_replace_global)
        m_edit.addAction(a_find)

        a_diff = QAction(tr("📊 Podgląd zmian (diff)"), self)
        a_diff.triggered.connect(self._show_diff_global)
        m_edit.addAction(a_diff)

        m_edit.addSeparator()

        a_to_snippet = QAction(tr("🧩 Zapisz zaznaczenie jako snippet"), self)
        a_to_snippet.triggered.connect(self._save_selection_as_snippet)
        m_edit.addAction(a_to_snippet)

        # ── Widok ──
        m_view = mb.addMenu(tr("Widok"))

        for label, key in [("➕ Nowy/Edytuj", "edit"), ("📋 Moje skrypty", "list"),
                            ("⚙️ Ustawienia", "settings"), ("🧩 Snippety", "snippets")]:
            a = QAction(tr(label), self)
            a.triggered.connect(lambda checked, k=key: self._goto_tab(self._widget_for_key(k)))
            m_view.addAction(a)

        m_view.addSeparator()

        a_dark = QAction(tr("🌑 Motyw ciemny"), self)
        a_dark.triggered.connect(lambda: self._switch_theme("dark"))
        m_view.addAction(a_dark)

        a_light = QAction(tr("☀️ Motyw jasny"), self)
        a_light.triggered.connect(lambda: self._switch_theme("light"))
        m_view.addAction(a_light)

        # ── Język ──
        m_lang = mb.addMenu(tr("🌐 Język"))

        a_lang_pl = QAction(tr("🇵🇱 Polski"), self)
        a_lang_pl.triggered.connect(lambda: self._change_language("pl"))
        m_lang.addAction(a_lang_pl)

        a_lang_en = QAction(tr("🇬🇧 Angielski"), self)
        a_lang_en.triggered.connect(lambda: self._change_language("en"))
        m_lang.addAction(a_lang_en)

        # ── Narzędzia ──
        m_tools = mb.addMenu(tr("Narzędzia"))

        a_detect = QAction(tr("🔄 Wykryj terminale"), self)
        a_detect.triggered.connect(self._detect_terminals_bg)
        m_tools.addAction(a_detect)

        m_tools.addSeparator()

        a_clear = QAction(tr("🗑 Wyczyść edytor"), self)
        a_clear.triggered.connect(self.tab_edit.clear)
        m_tools.addAction(a_clear)

        a_sort = QAction(tr("🔡 Sortuj skrypty (A-Z)"), self)
        a_sort.triggered.connect(self._sort_scripts)
        m_tools.addAction(a_sort)

        m_tools.addSeparator()

        a_stats = QAction(tr("📊 Statystyki"), self)
        a_stats.setShortcut(QKeySequence("Ctrl+T"))
        a_stats.triggered.connect(self._show_stats)
        m_tools.addAction(a_stats)

        # ── Pomoc ──
        m_help = mb.addMenu(tr("Pomoc"))

        a_about = QAction(tr("ℹ️ O programie"), self)
        a_about.triggered.connect(lambda: AboutDialog(self).exec())
        m_help.addAction(a_about)

    # ─── Script management ───────────────────
    def _on_script_saved(self, script: Script):
        # Update or insert
        existing_ids = [s.get("id") for s in self._scripts]
        if script.get("id") in existing_ids:
            idx = existing_ids.index(script.get("id"))
            # Edycja istniejącego skryptu nie powinna zerować jego statystyk
            # (przypięcie, licznik uruchomień, data ostatniego uruchomienia).
            old = self._scripts[idx]
            script["pinned"]    = old.get("pinned", False)
            script["run_count"] = old.get("run_count", 0)
            script["last_run"]  = old.get("last_run")
            self._scripts[idx] = script
            msg = f"{tr('✅ Zaktualizowano:')} {script['name']}"
        else:
            script.setdefault("pinned", False)
            script.setdefault("run_count", 0)
            script.setdefault("last_run", None)
            self._scripts.append(script)
            msg = f"{tr('✅ Zapisano:')} {script['name']}"
        self._save_scripts()
        self._refresh_list()
        self.statusBar().showMessage(msg, 4000)
        self._goto_tab(self.tab_list)

    def _save_scripts(self):
        try:
            save_json(DATA_FILE, self._scripts)
        except OSError as e:
            QMessageBox.critical(self, tr("Błąd zapisu"),
                f"{tr('Nie można zapisać scripts.json:')}\n{e}")

    def _save_settings(self):
        try:
            save_json(SETT_FILE, self._settings)
        except OSError as e:
            QMessageBox.critical(self, tr("Błąd zapisu"),
                f"{tr('Nie można zapisać settings.json:')}\n{e}")

    def _refresh_list(self):
        self.tab_list.load_scripts(self._scripts)
        self.tab_edit.set_known_names(s.get("name", "") for s in self._scripts)
        self.tab_stats.refresh(self._scripts)

    def _load_for_edit(self, script: Script):
        self.tab_edit.load_script(script)
        self._goto_tab(self.tab_edit)

    def _goto_tab(self, widget: QWidget):
        """Przełącza na zakładkę po referencji do widgetu zamiast po
        sztywnym indeksie – indeksy zmieniają się, gdy użytkownik
        przeciągnie zakładki w inną kolejność."""
        idx = self.tabs.indexOf(widget)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    # ─── Kolejność zakładek ───────────────────
    def _tab_labels(self) -> list:
        """Zwraca pary (klucz, etykieta) dla wszystkich zakładek w ICH
        AKTUALNEJ kolejności na pasku – używane do wypełnienia listy
        w Ustawieniach."""
        key_for_widget = {v: k for k, v in self._tab_key_map().items()}
        pairs = []
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            key = key_for_widget.get(w)
            if key:
                pairs.append((key, self.tabs.tabText(i)))
        return pairs

    def _tab_key_map(self) -> dict:
        """Jedyne źródło prawdy o tym, jaki stały klucz odpowiada któremu
        widgetowi zakładki – używane przez _tab_labels/_widget_for_key/
        _current_tab_order, żeby nie powielać tego mapowania w kilku miejscach."""
        return {
            "edit": self.tab_edit, "list": self.tab_list,
            "settings": self.tab_settings, "snippets": self.tab_snippets,
            "stats": self.tab_stats,
        }

    def _widget_for_key(self, key: str) -> Optional[QWidget]:
        return self._tab_key_map().get(key)

    def _current_tab_order(self) -> list:
        """Odczytuje bieżącą kolejność zakładek z paska jako listę kluczy."""
        key_for_widget = {v: k for k, v in self._tab_key_map().items()}
        order = []
        for i in range(self.tabs.count()):
            key = key_for_widget.get(self.tabs.widget(i))
            if key:
                order.append(key)
        return order

    def _on_tab_moved(self, *_args):
        """Użytkownik przeciągnął zakładkę myszką – zapisz nową kolejność
        i odśwież listę w Ustawieniach, żeby pozostała z nią spójna."""
        self._settings["tab_order"] = self._current_tab_order()
        self._save_settings()
        self.tab_settings.set_available_tabs(self._tab_labels())

    def _restore_tab_order(self):
        """Ustawia kolejność zakładek wg ostatnio zapisanej w ustawieniach
        (klucz 'tab_order'). Brakujące/nieznane klucze są pomijane,
        a zakładki spoza listy dopinane na koniec – tak plik ustawień
        sprzed tej funkcji (lub uszkodzony) nie gubi żadnej zakładki."""
        order = self._settings.get("tab_order")
        if not order:
            return
        bar = self.tabs.tabBar()
        for target_pos, key in enumerate(order):
            widget = self._widget_for_key(key)
            if widget is None:
                continue
            current_pos = self.tabs.indexOf(widget)
            if current_pos != -1 and current_pos != target_pos:
                bar.moveTab(current_pos, target_pos)
        self.tab_settings.set_available_tabs(self._tab_labels())

    def _apply_tab_order(self, order: list[str]):
        """Wywoływane z Ustawień (lista z przyciskami ↑/↓ lub drag&drop) –
        stosuje nową kolejność na pasku zakładek i zapisuje ją. Lista w
        Ustawieniach jest już aktualna (to ona jest źródłem zdarzenia),
        ale jawnie ją odświeżamy też tutaj – obejmuje to przypadek resetu
        do wartości domyślnych, gdzie kolejność na pasku mogła się nie
        zmienić mimo zmiany w samej liście."""
        bar = self.tabs.tabBar()
        for target_pos, key in enumerate(order):
            widget = self._widget_for_key(key)
            if widget is None:
                continue
            current_pos = self.tabs.indexOf(widget)
            if current_pos != -1 and current_pos != target_pos:
                bar.moveTab(current_pos, target_pos)
        self._settings["tab_order"] = self._current_tab_order()
        self._save_settings()
        self.tab_settings.set_available_tabs(self._tab_labels())

    def _insert_snippet(self, code: str):
        """Wstawia kod snippetu w pozycji kursora edytora głównego
        (zakładka Nowy/Edytuj), zastępując zaznaczenie jeśli istnieje,
        i przełącza na tę zakładkę."""
        cursor = self.tab_edit.editor.textCursor()
        cursor.insertText(code)
        self._goto_tab(self.tab_edit)
        self.tab_edit.editor.setFocus()

    def _save_selection_as_snippet(self):
        """Przenosi zaznaczony fragment (lub cały kod, jeśli nic nie
        zaznaczono) z edytora skryptów do zakładki Snippety, gotowy
        do zapisania pod nową nazwą."""
        cursor = self.tab_edit.editor.textCursor()
        code = cursor.selectedText().replace("\u2029", "\n") if cursor.hasSelection() \
            else self.tab_edit.editor.toPlainText()
        if not code.strip():
            return
        self.tab_snippets._do_new()
        self.tab_snippets.editor.setPlainText(code)
        cat = self.tab_edit.combo_cat.currentText()
        idx = self.tab_snippets.combo_cat.findText(cat)
        if idx >= 0:
            self.tab_snippets.combo_cat.setCurrentIndex(idx)
        self._goto_tab(self.tab_snippets)
        self.tab_snippets.entry_name.setFocus()

    def _open_find_replace_global(self):
        self._goto_tab(self.tab_edit)
        self.tab_edit._open_find_replace()

    def _show_diff_global(self):
        self._goto_tab(self.tab_edit)
        if self.tab_edit._original_code is None:
            QMessageBox.information(
                self, tr("📊 Podgląd różnic"),
                tr("Ta funkcja jest dostępna tylko podczas edycji istniejącego skryptu.")
            )
            return
        self.tab_edit._show_diff()


    def _run_from_editor(self):
        """Uruchamia kod aktualnie otwarty w edytorze bez konieczności
        wcześniejszego zapisania – tworzy skrypt tymczasowy tylko do uruchomienia."""
        code = self.tab_edit.editor.toPlainText().strip()
        if not code:
            return
        script = {
            "id": -1,
            "name": self.tab_edit.entry_name.text().strip() or "editor",
            "category": self.tab_edit.combo_cat.currentText(),
            "code": code,
        }
        dlg = RunDialog(script, self._terminals, self)
        dlg.exec()

    def _run_script(self, script: Script):
        self._record_run(script)
        dlg = RunDialog(script, self._terminals, self)
        dlg.exec()

    def _record_run(self, script: Script):
        """Zwiększa licznik uruchomień i zapisuje datę ostatniego uruchomienia
        dla skryptu z bazy (pomija skrypty tymczasowe z edytora, id=-1)."""
        if script.get("id") == -1:
            return
        for s in self._scripts:
            if s.get("id") == script.get("id"):
                s["run_count"] = s.get("run_count", 0) + 1
                s["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
                # Synchronizuj te same pola w słowniku, który trzyma dialog
                # uruchamiania / podgląd, żeby UI od razu pokazał nową wartość.
                script["run_count"] = s["run_count"]
                script["last_run"] = s["last_run"]
                break
        self._save_scripts()
        self._refresh_list()

    def _delete_script(self, script: Script):
        self._scripts = [x for x in self._scripts if x.get("id") != script.get("id")]
        self._save_scripts()
        self._refresh_list()
        self.statusBar().showMessage(f"{tr('🗑 Usunięto:')} {script.get('name','')}", 4000)

    def _duplicate_script(self, script: Script):
        s = dict(script)
        s["id"] = new_id()
        s["name"] = f"{script.get('name','')} ({tr('kopia')})"
        s["date"] = datetime.date.today().isoformat()
        # Duplikat to nowy, niezależny wpis – statystyki uruchomień
        # i przypięcie oryginału mu nie przysługują.
        s["pinned"] = False
        s["run_count"] = 0
        s["last_run"] = None
        self._scripts.append(s)
        self._save_scripts()
        self._refresh_list()
        self.statusBar().showMessage(f"{tr('📑 Zduplikowano:')} {s['name']}", 4000)

    def _toggle_pin(self, script: Script):
        for s in self._scripts:
            if s.get("id") == script.get("id"):
                s["pinned"] = not s.get("pinned", False)
                msg = tr("📌 Przypięto:") if s["pinned"] else tr("📌 Odpięto:")
                self.statusBar().showMessage(f"{msg} {s.get('name','')}", 3000)
                break
        self._save_scripts()
        self._refresh_list()

    def _new_script(self):
        self.tab_edit.clear()
        self._goto_tab(self.tab_edit)


    def _sort_scripts(self):
        self._scripts.sort(key=lambda s: s.get("name","").lower())
        self._save_scripts()
        self._refresh_list()
        self.statusBar().showMessage(tr("Posortowano skrypty A-Z."), 3000)

    def _show_stats(self):
        dlg = StatsDialog(self._scripts, self)
        dlg.exec()

    # ─── File operations ─────────────────────
    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Otwórz plik"),
                   "", f"{tr('Skrypty')} (*.py *.sh *.ps1 *.bat *.js *.sql *.rb *.lua *.vbs *.txt);;{tr('Wszystkie')} (*)")
        if not path:
            return
        try:
            code = Path(path).read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, tr("Błąd"), f"{tr('Nie można otworzyć pliku:')}\n{e}")
            return
        name = Path(path).stem
        lang = detect_language(code)
        self.tab_edit.clear()
        self.tab_edit.entry_name.setText(name)
        idx = self.tab_edit.combo_cat.findText(lang)
        if idx >= 0:
            self.tab_edit.combo_cat.setCurrentIndex(idx)
        self.tab_edit.editor.setPlainText(code)
        self.tab_edit.lbl_lang.setText(lang)
        self.tab_edit._hl.set_language(lang)
        self._goto_tab(self.tab_edit)

    def _import_scripts(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Importuj skrypty"), "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError(tr("Oczekiwano listy skryptów."))
        except Exception as e:
            QMessageBox.critical(self, tr("Błąd importu"), str(e))
            return

        # ── Walidacja każdego rekordu ──────────────────────────────────
        REQUIRED = ("name", "code")
        VALID_CATS = set(CATEGORIES)
        errors   = []
        valid    = []
        for i, s in enumerate(data, start=1):
            if not isinstance(s, dict):
                errors.append(f"#{i}: {tr('nie jest obiektem JSON.')}")
                continue
            missing = [f for f in REQUIRED if not str(s.get(f, "")).strip()]
            if missing:
                label = s.get("name") or f"#{i}"
                errors.append(f"{label}: {tr('brak wymaganych pól:')} {', '.join(missing)}")
                continue
            # Napraw kategorię – jeśli nieznana, ustaw "Other"
            if s.get("category") not in VALID_CATS:
                s["category"] = "Other"
            valid.append(s)

        if errors:
            limit   = 10
            summary = "\n".join(errors[:limit])
            if len(errors) > limit:
                summary += f"\n… ({tr('i jeszcze')} {len(errors)-limit} {tr('błędów')})"
            skip = QMessageBox.question(
                self, tr("Błędy walidacji"),
                f"{tr('Znaleziono błędy w')} {len(errors)} {tr('rekordach')}:\n\n"
                f"{summary}\n\n{tr('Zaimportować tylko poprawne rekordy?')}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if skip != QMessageBox.StandardButton.Yes:
                return
        # ── Dodaj tylko nowe (nie duplikaty) ──────────────────────────
        existing_ids = {s["id"] for s in self._scripts}
        added = 0
        for s in valid:
            if s.get("id") in existing_ids:
                continue
            if "id" not in s or not str(s["id"]).strip():
                s["id"] = new_id()
            self._scripts.append(s)
            existing_ids.add(s["id"])
            added += 1

        self._save_scripts()
        self._refresh_list()
        skipped = len(data) - len(valid)
        msg = f"{tr('Zaimportowano')} {added} {tr('nowych skryptów.')}"
        if skipped:
            msg += f"\n{tr('Pominiętych (błędy walidacji):')} {skipped}"
        QMessageBox.information(self, tr("Import"), msg)

    def _export_all_json(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Eksportuj wszystkie"),
                                              "scripts_export.json", "JSON (*.json)")
        if path:
            try:
                save_json(Path(path), self._scripts)
            except OSError as e:
                QMessageBox.critical(self, tr("Błąd eksportu"), str(e))
                return
            QMessageBox.information(self, tr("Eksport"), f"{tr('Wyeksportowano')} {len(self._scripts)} {tr('skryptów.')}")

    def _export_all_zip(self):
        """Eksportuje wszystkie skrypty jako osobne pliki w archiwum ZIP.
        Każdy skrypt trafia do podkatalogu swojej kategorii, np.:
            Python/hello_world.py
            Bash/backup.sh
        Dodatkowo dołączany jest scripts.json z pełnymi metadanymi."""
        if not self._scripts:
            QMessageBox.information(self, tr("Eksport ZIP"), tr("Brak skryptów do eksportu."))
            return

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"scripts_export_{ts}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Eksportuj wszystkie (ZIP)"),
            default_name, "ZIP (*.zip)"
        )
        if not path:
            return

        try:
            # Śledź duplikaty nazw plików w obrębie tej samej kategorii
            name_counters: dict = {}
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for s in self._scripts:
                    cat  = s.get("category", "Other")
                    name = s.get("name", "skrypt")
                    ext  = EXT_MAP.get(cat, ".txt")
                    # Sanitizacja nazwy pliku – usuń znaki niedozwolone w FS
                    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
                    arc_path  = f"{cat}/{safe_name}{ext}"
                    # Obsługa duplikatów w tej samej kategorii
                    key = arc_path.lower()
                    if key in name_counters:
                        name_counters[key] += 1
                        arc_path = f"{cat}/{safe_name}_{name_counters[key]}{ext}"
                    else:
                        name_counters[key] = 0
                    zf.writestr(arc_path, s.get("code", ""))

                # Dołącz pełne metadane jako JSON
                meta = json.dumps(self._scripts, indent=2, ensure_ascii=False)
                zf.writestr("_metadata/scripts.json", meta)

            size_kb = Path(path).stat().st_size // 1024
            QMessageBox.information(
                self, tr("Eksport ZIP"),
                f"{tr('Wyeksportowano do ZIP')} {len(self._scripts)} {tr('skryptów.')}\n"
                f"{Path(path).name}  ({size_kb} KB)"
            )
        except Exception as e:
            QMessageBox.critical(self, tr("Błąd"), f"{tr('Błąd eksportu ZIP:')}\n{e}")

    def _open_path(self, path: Path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            QMessageBox.warning(self, tr("Błąd"), str(e))

    # ─── Theme ──────────────────────────────
    def _switch_theme(self, theme: str):
        self._dark = (theme == "dark")
        self._settings["theme"] = theme
        self._apply_theme()
        self.tab_edit.set_dark(self._dark)
        self.tab_list.preview_editor.set_dark(self._dark)
        self.tab_list._preview_hl.set_dark(self._dark)
        self.tab_snippets.set_dark(self._dark)
        self._save_settings()

    def _on_settings_changed(self, settings: AppSettings):
        old_lang = self._settings.get("language", "pl")
        new_lang = settings.get("language", "pl")
        self._settings = settings
        self.tab_list.confirm_delete = settings.get("confirm_delete", True)
        # Zastosuj czcionkę edytora natychmiast
        family = settings.get("font_family", "Consolas")
        size   = settings.get("font_size", 10)
        self.tab_edit.editor.apply_font_settings(family, size)
        self.tab_list.preview_editor.apply_font_settings(family, size)
        self.tab_snippets.apply_font_settings(family, size)
        if settings.get("theme","dark") == "dark":
            self._switch_theme("dark")
        else:
            self._switch_theme("light")
        if new_lang != old_lang:
            self._change_language(new_lang)

    # ─── Język ──────────────────────────────
    def _change_language(self, lang: str):
        if lang == LanguageManager.current:
            return
        reply = QMessageBox.question(
            self, tr("Zmiana języka"),
            tr("Aby zastosować nowy język, aplikacja zostanie zrestartowana.\nKontynuować?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            # revert any pending change so it isn't silently persisted
            self._settings["language"] = LanguageManager.current
            self._save_settings()
            return
        self._settings["language"] = lang
        self._settings["window_geometry"] = f"{self.width()}x{self.height()}"
        self._save_settings()
        self._restart_app()

    def _restart_app(self):
        python = sys.executable
        script = os.path.abspath(__file__)
        os.execv(python, [python, script] + sys.argv[1:])

    # ─── Terminal detection ──────────────────
    def _detect_terminals_bg(self):
        # Referencja w self._term_worker jest konieczna – inaczej Python
        # mógłby zebrać obiekt QThread, zanim zdąży zakończyć pracę.
        self._term_worker = TerminalDetectWorker(self)
        self._term_worker.detected.connect(self._on_terminals_detected)
        self._term_worker.start()

    def _on_terminals_detected(self, terminals: list[tuple]):
        self._terminals = terminals
        self.tab_list.terminals = terminals
        names = ", ".join(l for _, l in terminals) if terminals else tr("(brak)")
        self.statusBar().showMessage(f"{tr('Terminale:')} {names}", 5000)

    # ─── Closevent ──────────────────────────
    def closeEvent(self, event):
        if self.tab_edit.is_dirty():
            reply = QMessageBox.question(
                self, tr("Niezapisane zmiany"),
                tr("Masz niezapisany skrypt w edytorze. Czy na pewno chcesz wyjść?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._settings["window_geometry"] = f"{self.width()}x{self.height()}"
        self._settings["tab_order"] = self._current_tab_order()
        self._save_settings()
        event.accept()

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def main():
    # High DPI – ustawienie polityki musi nastąpić PRZED utworzeniem
    # instancji QApplication, inaczej Qt zgłasza ostrzeżenie i je ignoruje.
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception as e:
        print(f"[ScriptDataBase] HighDPI policy niedostępna: {e}", file=sys.stderr)

    app = QApplication(sys.argv)
    app.setApplicationName("ScriptDataBase Lite")
    app.setApplicationVersion("3.0.8")
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

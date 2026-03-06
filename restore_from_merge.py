import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# --- KONFIGURATION ---
# Passe diesen Pfad an den Ort an, an dem deine Merge-Dateien liegen.
MERGE_FILES_DIRECTORY = r"C:\Users\Anwender\Documents\GitHub\File-Merger-for-ChatGPT-and-other-AI\outputFolder"
# --- ENDE DER KONFIGURATION ---


def parse_merge_datei(dateipfad):
    """
    Liest eine Merge-Datei und extrahiert die Dateipfade und deren Inhalte.
    Gibt eine Liste von Dictionaries zurück, jedes mit 'pfad' und 'inhalt'.
    """
    try:
        with open(dateipfad, 'r', encoding='utf-8') as f:
            gesamter_inhalt = f.read()
    except Exception as e:
        messagebox.showerror("Fehler beim Lesen", f"Konnte die Datei nicht lesen: {dateipfad}\n\nFehler: {e}")
        return None

    wiederherzustellende_dateien = []
    
    # Wir suchen den Start des "File Contents"-Abschnitts
    inhalt_start_marker = "File Contents"
    start_index = gesamter_inhalt.find(inhalt_start_marker)
    if start_index == -1:
        messagebox.showerror("Formatfehler", "Der Abschnitt 'File Contents' wurde in der Merge-Datei nicht gefunden.")
        return None
        
    # Der relevante Inhalt beginnt nach dem "File Contents"-Header
    relevanter_inhalt = gesamter_inhalt[start_index:]

    # Wir splitten den Inhalt anhand der Trennlinie, um einzelne Dateiblöcke zu erhalten
    # re.split behält die Trennzeichen, was hier nützlich sein kann, aber wir nutzen einen Lookahead
    # um die Trennlinie nicht mit zu splitten, sondern als Trenner zu nutzen.
    # Der Ausdruck sucht nach der Trennlinie, die von einer neuen Zeile gefolgt wird.
    trennlinie = r"\n================================================================================\n📄 File: "
    dateibloecke = re.split(trennlinie, relevanter_inhalt)

    # Der erste Block ist nur der Header, wir überspringen ihn
    for block in dateibloecke[1:]:
        try:
            # Der Dateiname ist jetzt am Anfang des Blocks, aber der Pfad ist zuverlässiger
            # Wir fügen den Trenner wieder hinzu, um den Pfad korrekt zu parsen
            voller_block = "📄 File: " + block
            
            # Extrahiere den relativen Pfad
            pfad_match = re.search(r"📁 Path: (.*?)\n", voller_block)
            if not pfad_match:
                continue # Block ohne Pfadangabe überspringen
            
            relativer_pfad = pfad_match.group(1).strip()

            # Extrahiere den Inhalt der Datei
            # Der Inhalt beginnt nach der ersten `====...====` Linie im Block
            inhalt_start_index = voller_block.find("================================================================================\n\n")
            if inhalt_start_index != -1:
                # + Länge der Trennlinie und der zwei Newlines
                start_pos = inhalt_start_index + len("================================================================================\n\n")
                dateinhalt = voller_block[start_pos:]
                
                # Entferne eventuelle abschließende Trennlinien vom Inhalt
                end_trennlinie = "\n\n================================================================================"
                if dateinhalt.endswith(end_trennlinie):
                    dateinhalt = dateinhalt[:-len(end_trennlinie)]
                
                wiederherzustellende_dateien.append({
                    'pfad': relativer_pfad,
                    'inhalt': dateinhalt
                })

        except Exception as e:
            print(f"Fehler beim Parsen eines Blocks: {e}")
            continue

    if not wiederherzustellende_dateien:
        messagebox.showwarning("Keine Dateien gefunden", "Es konnten keine wiederherstellbaren Dateiinhalte in der Merge-Datei gefunden werden.")
        return None

    return wiederherzustellende_dateien


def stelle_projekt_wieder_her(dateien_info, ziel_ordner):
    """
    Erstellt die Ordnerstruktur und die Dateien im Zielordner.
    """
    if not dateien_info:
        return

    try:
        # Erstelle den Basis-Zielordner, falls er nicht existiert
        os.makedirs(ziel_ordner, exist_ok=True)

        for datei_info in dateien_info:
            relativer_pfad = datei_info['pfad']
            inhalt = datei_info['inhalt']
            
            # Erstelle den vollständigen Zielpfad für die Datei
            # os.path.normpath bereinigt den Pfad (z.B. C:/Users/../Desktop -> C:/Desktop)
            voller_zielpfad = os.path.normpath(os.path.join(ziel_ordner, relativer_pfad))
            
            # Erstelle das Verzeichnis für die Datei, falls es nicht existiert
            datei_verzeichnis = os.path.dirname(voller_zielpfad)
            os.makedirs(datei_verzeichnis, exist_ok=True)
            
            # Schreibe den Inhalt in die Datei
            with open(voller_zielpfad, 'w', encoding='utf-8') as f:
                f.write(inhalt)
        
        messagebox.showinfo("Erfolg", f"Projekt erfolgreich wiederhergestellt in:\n{ziel_ordner}")

    except Exception as e:
        messagebox.showerror("Fehler bei der Wiederherstellung", f"Ein Fehler ist aufgetreten:\n\n{e}")


class RestoreApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File Merger - Restore Tool")
        self.root.geometry("800x600")

        # --- Datenhaltung ---
        self.alle_dateien = self.lade_merge_dateien()
        
        # --- GUI Elemente ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Filter / Suche
        filter_frame = ttk.Frame(main_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *args: self.update_liste())
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var)
        filter_entry.pack(fill=tk.X, expand=True)

        # Dateiliste
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        
        self.listbox.bind("<<ListboxSelect>>", self.on_list_select)

        # Zielpfad und Aktionen
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(action_frame, text="Zielordner:").pack(side=tk.LEFT, padx=(0, 5))
        self.output_path_var = tk.StringVar()
        output_entry = ttk.Entry(action_frame, textvariable=self.output_path_var)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        browse_button = ttk.Button(action_frame, text="Durchsuchen...", command=self.browse_output_path)
        browse_button.pack(side=tk.LEFT, padx=5)
        
        restore_button = ttk.Button(main_frame, text="Ausgewählte Datei wiederherstellen", command=self.starte_wiederherstellung)
        restore_button.pack(fill=tk.X, pady=10)

        # Initiales Befüllen der Liste
        self.update_liste()

    def lade_merge_dateien(self):
        """Lädt alle .txt Dateien aus dem konfigurierten Verzeichnis und sortiert sie nach Änderungsdatum."""
        if not os.path.isdir(MERGE_FILES_DIRECTORY):
            messagebox.showerror("Fehler", f"Das konfigurierte Verzeichnis existiert nicht:\n{MERGE_FILES_DIRECTORY}")
            return []
            
        dateien = []
        for dateiname in os.listdir(MERGE_FILES_DIRECTORY):
            if dateiname.lower().endswith(".txt"):
                voller_pfad = os.path.join(MERGE_FILES_DIRECTORY, dateiname)
                try:
                    mod_time = os.path.getmtime(voller_pfad)
                    dateien.append({'name': dateiname, 'path': voller_pfad, 'mod_time': mod_time})
                except OSError:
                    continue
        
        # Sortiere nach Änderungsdatum, neueste zuerst
        dateien.sort(key=lambda x: x['mod_time'], reverse=True)
        return dateien

    def update_liste(self):
        """Aktualisiert die Listbox basierend auf dem Filtertext."""
        self.listbox.delete(0, tk.END)
        filter_text = self.filter_var.get().lower()
        
        for datei in self.alle_dateien:
            if filter_text in datei['name'].lower():
                # Formatierung für die Anzeige: Name + Änderungsdatum
                mod_time_str = datetime.fromtimestamp(datei['mod_time']).strftime('%Y-%m-%d %H:%M:%S')
                display_text = f"{datei['name']}  ({mod_time_str})"
                self.listbox.insert(tk.END, display_text)

    def on_list_select(self, event):
        """Wird aufgerufen, wenn ein Element in der Liste ausgewählt wird. Setzt den Standard-Zielpfad."""
        selection_indices = self.listbox.curselection()
        if not selection_indices:
            return
            
        # Finde die ausgewählte Datei in unserer Original-Datenliste
        selected_display_text = self.listbox.get(selection_indices[0])
        selected_filename = selected_display_text.split("  (")[0]
        
        selected_file_info = next((f for f in self.alle_dateien if f['name'] == selected_filename), None)
        
        if selected_file_info:
            # Erstelle einen sinnvollen Standard-Namen für den wiederhergestellten Ordner
            base_name = os.path.splitext(selected_file_info['name'])[0]
            restored_folder_name = f"{base_name}_restored"
            
            # Standardpfad ist im gleichen Verzeichnis wie die Merge-Dateien
            default_path = os.path.join(MERGE_FILES_DIRECTORY, restored_folder_name)
            self.output_path_var.set(default_path)

    def browse_output_path(self):
        """Öffnet einen Dialog zur Auswahl eines Ordners."""
        directory = filedialog.askdirectory(title="Wähle einen Zielordner")
        if directory:
            self.output_path_var.set(directory)

    def starte_wiederherstellung(self):
        """Startet den gesamten Prozess: Parsen und Wiederherstellen."""
        selection_indices = self.listbox.curselection()
        if not selection_indices:
            messagebox.showwarning("Keine Auswahl", "Bitte wähle zuerst eine Merge-Datei aus der Liste aus.")
            return
            
        ziel_ordner = self.output_path_var.get()
        if not ziel_ordner:
            messagebox.showwarning("Kein Zielpfad", "Bitte gib einen Zielordner an.")
            return

        # Finde die ausgewählte Datei in unserer Original-Datenliste
        selected_display_text = self.listbox.get(selection_indices[0])
        selected_filename = selected_display_text.split("  (")[0]
        selected_file_info = next((f for f in self.alle_dateien if f['name'] == selected_filename), None)

        if not selected_file_info:
            messagebox.showerror("Fehler", "Konnte die ausgewählte Datei nicht finden. Bitte die Liste neu laden.")
            return

        dateipfad = selected_file_info['path']
        
        # Schritt 1: Datei parsen
        print(f"Parse Datei: {dateipfad}")
        dateien_info = parse_merge_datei(dateipfad)
        
        # Schritt 2: Projekt wiederherstellen
        if dateien_info:
            print(f"Stelle {len(dateien_info)} Dateien im Ordner '{ziel_ordner}' wieder her.")
            stelle_projekt_wieder_her(dateien_info, ziel_ordner)


if __name__ == "__main__":
    # Überprüfe, ob der konfigurierte Pfad existiert, bevor die GUI startet
    if not os.path.isdir(MERGE_FILES_DIRECTORY):
        tk.Tk().withdraw() # Verstecke das Hauptfenster für die Fehlermeldung
        messagebox.showerror(
            "Konfigurationsfehler",
            f"Das angegebene Verzeichnis für die Merge-Dateien existiert nicht:\n\n"
            f"{MERGE_FILES_DIRECTORY}\n\n"
            f"Bitte passe die Variable 'MERGE_FILES_DIRECTORY' im Skript an."
        )
    else:
        app_root = tk.Tk()
        app = RestoreApp(app_root)
        app_root.mainloop()
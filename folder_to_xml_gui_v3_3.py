import sys
import json
import copy
import stat
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTreeWidget,
    QTreeWidgetItem, QPlainTextEdit, QMessageBox, QSplitter,
    QHeaderView, QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QInputDialog, QCompleter
)


class PrefixCatalogueDialog(QDialog):
    """Editable prefix catalogue; changes are persisted by the main window."""
    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage prefix catalogue")
        self.resize(900, 600)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Group name", "Prefix code", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.setColumnWidth(0, 330)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 420)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Edit existing entries or add your own project prefixes. "
            "The catalogue is stored in prefix_catalogue.json next to the Python program."
        ))
        layout.addWidget(self.table)
        buttons_row = QHBoxLayout()
        add_btn = QPushButton("Add prefix")
        add_btn.clicked.connect(self.add_row)
        delete_btn = QPushButton("Delete selected")
        delete_btn.clicked.connect(self.delete_rows)
        buttons_row.addWidget(add_btn)
        buttons_row.addWidget(delete_btn)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)
        self.dialog_buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.dialog_buttons.accepted.connect(self.accept)
        self.dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(self.dialog_buttons)
        for group_name, entries in groups:
            for code, description in entries:
                self.add_row(group_name, code, description)

    def add_row(self, group="Project / custom", code="", description=""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, value in enumerate((group, code, description)):
            self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.setCurrentCell(row, 1)

    def delete_rows(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def get_groups(self):
        grouped = {}
        for row in range(self.table.rowCount()):
            group_item = self.table.item(row, 0)
            code_item = self.table.item(row, 1)
            desc_item = self.table.item(row, 2)
            group = group_item.text().strip() if group_item else "Project / custom"
            code = code_item.text().strip() if code_item else ""
            desc = desc_item.text().strip() if desc_item else ""
            if not code:
                continue
            grouped.setdefault(group or "Project / custom", []).append((code, desc))
        return [(name, entries) for name, entries in grouped.items()]


class FolderXmlEditor(QMainWindow):
    PREFIX_COLUMN = 1
    GROUP_COLUMN = 2
    DESCRIPTION_COLUMN = 3
    EMPTY_PREFIX = "__QET_EXPLICIT_EMPTY_PREFIX__"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Folder Structure to XML - Standards / coding selector (v3.2)")
        self.resize(1600, 850)
        self.root_folder = None
        self.destination_file = None
        self.destination_tree = None
        self.catalogue_standards = []
        self.norm_profiles = []
        self.current_norm_id = "all"
        self.catalogue_note = ""
        self.standards_last_checked = ""
        self.prefix_groups = self.load_prefix_catalogue()
        self.build_ui()

    @property
    def catalogue_path(self):
        return Path(__file__).resolve().with_name("prefix_catalogue.json")

    def load_prefix_catalogue(self):
        if self.catalogue_path.exists():
            try:
                data = json.loads(self.catalogue_path.read_text(encoding="utf-8"))
                self.catalogue_standards = data.get("standards", [])
                self.norm_profiles = data.get("norm_profiles", [])
                self.catalogue_note = data.get("catalogue_note", "")
                self.standards_last_checked = data.get("standards_last_checked", "")
                groups = []
                for group in data.get("groups", []):
                    name = str(group.get("name", "Project / custom"))
                    entries = []
                    for entry in group.get("entries", []):
                        code = str(entry.get("code", "")).strip()
                        description = str(entry.get("description", "")).strip()
                        if code:
                            entries.append((code, description))
                    if entries:
                        groups.append((name, entries))
                return groups
            except (OSError, ValueError, TypeError) as exc:
                QMessageBox.warning(None, "Prefix catalogue", f"Could not read {self.catalogue_path}:\n{exc}\n\nThe application will start with an empty catalogue.")
        return []

    def save_prefix_catalogue(self):
        payload = {
            "version": 3,
            "groups": [
                {"name": name, "entries": [
                    {"code": code, "description": description} for code, description in entries
                ]} for name, entries in self.prefix_groups
            ],
            "catalogue_note": self.catalogue_note,
            "standards_last_checked": self.standards_last_checked,
            "standards": self.catalogue_standards,
            "norm_profiles": self.norm_profiles,
        }
        self.catalogue_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        norm_row = QHBoxLayout()
        norm_row.addWidget(QLabel("Norm / application:"))
        self.norm_selector = QComboBox()
        self.norm_selector.setMinimumWidth(420)
        self.norm_selector.addItem("All standards and coding groups", "all")
        for profile in self.norm_profiles:
            self.norm_selector.addItem(profile.get("name", profile.get("id", "")), profile.get("id", ""))
        self.norm_selector.currentIndexChanged.connect(self.norm_selection_changed)
        norm_row.addWidget(self.norm_selector, 1)
        self.norm_info_label = QLabel("Select a norm or application to filter the prefix lists.")
        self.norm_info_label.setWordWrap(True)
        norm_row.addWidget(self.norm_info_label, 2)
        layout.addLayout(norm_row)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source folder:"))
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        source_row.addWidget(self.folder_edit, 1)
        browse_btn = QPushButton("Browse source...")
        browse_btn.clicked.connect(self.choose_folder)
        source_row.addWidget(browse_btn)
        scan_btn = QPushButton("Scan folders")
        scan_btn.clicked.connect(self.scan_folders)
        source_row.addWidget(scan_btn)
        layout.addLayout(source_row)

        destination_row = QHBoxLayout()
        destination_row.addWidget(QLabel("Destination XML:"))
        self.destination_edit = QLineEdit()
        self.destination_edit.setReadOnly(True)
        destination_row.addWidget(self.destination_edit, 1)
        open_xml_btn = QPushButton("Open destination XML...")
        open_xml_btn.clicked.connect(self.open_destination_xml)
        destination_row.addWidget(open_xml_btn)
        layout.addLayout(destination_row)

        tools_row = QHBoxLayout()
        tools_row.addWidget(QLabel("Edit prefixes in either tree; '(inherit)' means no explicit prefix."))
        tools_row.addStretch()
        catalogue_btn = QPushButton("Manage prefixes...")
        catalogue_btn.clicked.connect(self.manage_prefixes)
        tools_row.addWidget(catalogue_btn)
        import_prefixes_btn = QPushButton("Import destination prefixes to catalogue")
        import_prefixes_btn.clicked.connect(self.import_destination_prefixes)
        import_prefixes_btn.setEnabled(False)
        self.import_prefixes_btn = import_prefixes_btn
        tools_row.addWidget(import_prefixes_btn)
        clear_btn = QPushButton("Set selected to inherit")
        clear_btn.clicked.connect(self.clear_selected_prefix)
        tools_row.addWidget(clear_btn)
        layout.addLayout(tools_row)

        main_splitter = QSplitter(Qt.Horizontal)

        # Source side mirrors the destination side: structure and XML are separate tabs.
        source_tabs = QTabWidget()
        source_structure_widget = QWidget()
        source_structure_layout = QVBoxLayout(source_structure_widget)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Source folder / category", "Prefix", "Group name", "Description"])
        self.configure_resizable_tree(self.tree)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        source_structure_layout.addWidget(self.tree)
        source_tabs.addTab(source_structure_widget, "Source structure / prefixes")

        source_preview_widget = QWidget()
        source_preview_layout = QVBoxLayout(source_preview_widget)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        source_preview_layout.addWidget(self.preview)
        source_tabs.addTab(source_preview_widget, "Generated XML")
        main_splitter.addWidget(source_tabs)

        destination_tabs = QTabWidget()
        destination_tree_widget = QWidget()
        destination_tree_layout = QVBoxLayout(destination_tree_widget)
        self.destination_structure = QTreeWidget()
        self.destination_structure.setColumnCount(4)
        self.destination_structure.setHeaderLabels(["Loaded XML category", "Prefix (editable)", "Group name", "Description"])
        self.configure_resizable_tree(self.destination_structure)
        destination_tree_layout.addWidget(self.destination_structure)
        destination_tabs.addTab(destination_tree_widget, "Destination structure")

        destination_preview_widget = QWidget()
        destination_preview_layout = QVBoxLayout(destination_preview_widget)
        self.destination_preview = QPlainTextEdit()
        self.destination_preview.setReadOnly(True)
        self.destination_preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        destination_preview_layout.addWidget(self.destination_preview)
        destination_tabs.addTab(destination_preview_widget, "Destination XML text")
        main_splitter.addWidget(destination_tabs)
        main_splitter.setSizes([440, 520, 640])
        layout.addWidget(main_splitter, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("Select a source folder and open a destination XML file.")
        bottom.addWidget(self.status_label, 1)
        refresh_btn = QPushButton("Refresh preview")
        refresh_btn.clicked.connect(self.update_preview)
        bottom.addWidget(refresh_btn)
        self.save_destination_btn = QPushButton("Save destination prefix edits")
        self.save_destination_btn.clicked.connect(self.save_destination_edits)
        self.save_destination_btn.setEnabled(False)
        bottom.addWidget(self.save_destination_btn)
        self.merge_btn = QPushButton("Merge source folders into destination XML")
        self.merge_btn.clicked.connect(self.merge_into_destination)
        self.merge_btn.setEnabled(False)
        bottom.addWidget(self.merge_btn)
        export_btn = QPushButton("Export source as new XML...")
        export_btn.clicked.connect(self.export_xml)
        bottom.addWidget(export_btn)
        layout.addLayout(bottom)

    @staticmethod
    def configure_resizable_tree(tree):
        header = tree.header()
        # Columns are initially sized to their contents, then remain manually resizable.
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(65)
        tree.setAlternatingRowColors(True)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    @staticmethod
    def autosize_tree_columns(tree):
        tree.resizeColumnToContents(0)
        tree.resizeColumnToContents(1)
        tree.resizeColumnToContents(2)
        tree.resizeColumnToContents(3)
        # Keep wide descriptions usable without letting them dominate the whole tree.
        limits = {0: 360, 1: 150, 2: 280, 3: 460}
        for column, maximum in limits.items():
            tree.setColumnWidth(column, min(tree.columnWidth(column), maximum))

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select root folder", str(Path.home()))
        if folder:
            self.root_folder = Path(folder)
            self.folder_edit.setText(str(self.root_folder))
            self.scan_folders()

    def norm_selection_changed(self, _index=None):
        # Preserve any unsaved prefix edits while the selector filters available codes.
        destination_states = {}
        def capture(item):
            combo = self.destination_structure.itemWidget(item, 1)
            destination_states[item.data(0, Qt.UserRole)] = self.combo_prefix_state(combo)
            for child_index in range(item.childCount()):
                capture(item.child(child_index))
        if self.destination_tree is not None:
            for top_index in range(self.destination_structure.topLevelItemCount()):
                capture(self.destination_structure.topLevelItem(top_index))

        self.current_norm_id = self.norm_selector.currentData() or "all"
        profile = next((p for p in self.norm_profiles if p.get("id") == self.current_norm_id), None)
        if profile:
            refs = ", ".join(profile.get("standards", []))
            note = profile.get("note", "")
            self.norm_info_label.setText((refs + " — " if refs else "") + note)
        else:
            self.norm_info_label.setText("All standards and project coding groups are available.")
        self.rebuild_all_prefix_selectors()
        if self.destination_tree is not None:
            self.populate_destination_structure()
            def restore(item):
                state = destination_states.get(item.data(0, Qt.UserRole))
                combo = self.destination_structure.itemWidget(item, 1)
                if state is not None and combo is not None:
                    has_prefix, code = state
                    if not has_prefix:
                        combo.setCurrentIndex(0)
                    elif not code:
                        combo.setCurrentIndex(1)
                    else:
                        match = next((i for i in range(combo.count()) if str(combo.itemData(i) or "") == code), -1)
                        if match < 0:
                            combo.addItem(code, code)
                            match = combo.count() - 1
                        combo.setCurrentIndex(match)
                    self.destination_prefix_changed(item)
                for child_index in range(item.childCount()):
                    restore(item.child(child_index))
            for top_index in range(self.destination_structure.topLevelItemCount()):
                restore(self.destination_structure.topLevelItem(top_index))

    def prefix_options(self):
        """Return unique prefix codes filtered by the selected norm/application profile."""
        allowed_groups = None
        if self.current_norm_id != "all":
            profile = next((p for p in self.norm_profiles if p.get("id") == self.current_norm_id), None)
            allowed_groups = set(profile.get("groups", [])) if profile else set()
        by_code = {}
        for group_name, entries in self.prefix_groups:
            if allowed_groups is not None and group_name not in allowed_groups:
                continue
            for code, description in entries:
                code = str(code).strip()
                if not code:
                    continue
                record = by_code.setdefault(code, {"groups": [], "descriptions": []})
                if group_name and group_name not in record["groups"]:
                    record["groups"].append(group_name)
                if description and description not in record["descriptions"]:
                    record["descriptions"].append(description)
        options = [("(inherit)", None, "No <prefix> element; inherit the parent prefix", "")]
        options.append(("(no letter)", self.EMPTY_PREFIX, "Explicit empty <prefix/>; this folder has no letter", "QET XML"))
        for code in sorted(by_code, key=str.casefold):
            record = by_code[code]
            options.append((code, code, " | ".join(record["descriptions"]), " / ".join(record["groups"])))
        return options

    def scan_folders(self):
        folder_text = self.folder_edit.text().strip()
        if not folder_text:
            QMessageBox.warning(self, "No folder", "Select a source folder first.")
            return
        root = Path(folder_text)
        if not root.is_dir():
            QMessageBox.critical(self, "Invalid folder", "The selected source folder does not exist.")
            return
        # A QET collection root contains qet_labels.xml. Scan a category folder
        # inside it (for example, .../elements-company/devices), not the collection root.
        if (root / "qet_labels.xml").is_file():
            QMessageBox.warning(
                self, "Select a folder inside the collection",
                "The selected folder appears to be the QET collection root because it contains qet_labels.xml.\n\n"
                "Select the category folder inside the collection instead (for example: devices), then scan and merge."
            )
            return
        self.root_folder = root
        self.tree.clear()
        root_item = self.make_item(root.name, "")
        self.tree.addTopLevelItem(root_item)
        self.add_prefix_selector(root_item, "")
        self.add_subfolders(root_item, root, root)
        root_item.setExpanded(True)
        self.autosize_tree_columns(self.tree)
        self.status_label.setText(f"Scanned source folder: {root}")
        self.update_preview()
        self.compare_structures()

    def make_item(self, name, prefix):
        item = QTreeWidgetItem([name, "", "", ""])
        item.setData(0, Qt.UserRole, name)
        item.setData(0, Qt.UserRole + 1, prefix)
        return item

    def add_prefix_selector(self, item, prefix=None, explicit_empty=False):
        combo = QComboBox()
        combo.setMinimumWidth(75)
        combo.setMaximumWidth(150)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMaxVisibleItems(20)
        combo.setToolTip(
            "Type to filter prefix codes. (inherit) omits the prefix element; "
            "(no letter) writes an explicit empty <prefix/> element."
        )
        selected_index = 0
        for display, code, description, group_name in self.prefix_options():
            combo.addItem(display, code)
            index = combo.count() - 1
            combo.setItemData(index, description, Qt.UserRole + 1)
            combo.setItemData(index, group_name, Qt.UserRole + 2)
            combo.setItemData(index, f"{group_name} — {description}" if group_name else description, Qt.ToolTipRole)
            if explicit_empty and code == self.EMPTY_PREFIX:
                selected_index = index
            elif not explicit_empty and prefix and code == prefix:
                selected_index = index
        if prefix and selected_index == 0 and not explicit_empty:
            combo.addItem(prefix, prefix)
            combo.setItemData(combo.count() - 1, "Custom / existing XML prefix", Qt.UserRole + 1)
            selected_index = combo.count() - 1
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)
        combo.setCurrentIndex(selected_index)
        self.tree.setItemWidget(item, self.PREFIX_COLUMN, combo)
        combo.currentIndexChanged.connect(lambda _=None, current=item: self.prefix_changed(current))
        combo.editTextChanged.connect(lambda _=None, current=item: self.prefix_changed(current))
        self.update_item_description(item)

    @staticmethod
    def _is_hidden_or_link(path):
        """Match QET's folder scan behavior: skip hidden folders and folder links."""
        if path.name.startswith(".") or path.is_symlink():
            return True
        try:
            is_junction = getattr(path, "is_junction", None)
            if callable(is_junction) and is_junction():
                return True
            attributes = getattr(path.stat(), "st_file_attributes", 0)
            hidden_flag = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)
            if attributes & hidden_flag:
                return True
        except OSError:
            return True
        return False

    def add_subfolders(self, parent_item, folder, base_dir):
        try:
            directories = sorted(
                (p for p in folder.iterdir() if p.is_dir() and not self._is_hidden_or_link(p)),
                key=lambda p: p.name.casefold()
            )
        except OSError as exc:
            QMessageBox.warning(self, "Folder access", f"Cannot read {folder}:\n{exc}")
            return
        for directory in directories:
            child = self.make_item(directory.name, "")
            parent_item.addChild(child)
            self.add_prefix_selector(child, "")
            self.add_subfolders(child, directory, base_dir)

    def combo_prefix_state(self, combo):
        """Return (has_prefix_element, value), preserving <prefix/> vs no element."""
        if combo is None:
            return False, ""
        text = combo.currentText().strip()
        index = combo.currentIndex()
        if index >= 0 and text == combo.itemText(index):
            value = combo.itemData(index)
            if value is None:
                return False, ""  # no element: inherit parent
            if value == self.EMPTY_PREFIX:
                return True, ""   # explicit empty element: no letter
            return True, str(value).strip()
        if text.casefold() in ("(inherit)", "inherit"):
            return False, ""
        if text.casefold() in ("(no letter)", "no letter"):
            return True, ""
        return (bool(text), text)

    def combo_code(self, combo):
        return self.combo_prefix_state(combo)[1]

    def prefix_changed(self, item):
        self.update_item_description(item)
        self.update_preview()
        self.compare_structures()

    def update_item_description(self, item):
        combo = self.tree.itemWidget(item, self.PREFIX_COLUMN)
        if combo is None:
            return
        has_prefix, code = self.combo_prefix_state(combo)
        index = combo.currentIndex()
        description = combo.itemData(index, Qt.UserRole + 1) if index >= 0 else ""
        if not has_prefix:
            description = "Inherited from parent"
        elif not code:
            description = "Explicit empty <prefix/> — no letter"
        elif not description or (index >= 0 and combo.currentText() != combo.itemText(index)):
            description = "Custom / project-specific code"
        group_name = combo.itemData(index, Qt.UserRole + 2) if index >= 0 else ""
        if code and (not group_name or (index >= 0 and combo.currentText() != combo.itemText(index))):
            group_name = "Custom / project"
        item.setText(self.GROUP_COLUMN, str(group_name or ""))
        item.setText(self.DESCRIPTION_COLUMN, str(description))
        item.setToolTip(self.GROUP_COLUMN, str(group_name or ""))
        item.setToolTip(self.DESCRIPTION_COLUMN, str(description))

    def clear_selected_prefix(self):
        for item in self.tree.selectedItems():
            combo = self.tree.itemWidget(item, self.PREFIX_COLUMN)
            if combo is not None:
                combo.setCurrentIndex(0)
                combo.setEditText("(inherit)")
        self.update_preview()

    def manage_prefixes(self):
        dialog = PrefixCatalogueDialog(self.prefix_groups, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        new_groups = dialog.get_groups()
        if not new_groups:
            QMessageBox.warning(self, "Prefix catalogue", "At least one prefix entry is required.")
            return
        self.prefix_groups = new_groups
        try:
            self.save_prefix_catalogue()
        except OSError as exc:
            QMessageBox.critical(self, "Save prefix catalogue", str(exc))
            return
        self.rebuild_all_prefix_selectors()
        if self.destination_tree is not None:
            self.populate_destination_structure()
        QMessageBox.information(self, "Prefix catalogue", f"Prefix catalogue saved:\n{self.catalogue_path}")

    def import_destination_prefixes(self):
        """Import explicit prefix values from the opened destination XML into JSON."""
        if self.destination_tree is None or self.destination_file is None:
            QMessageBox.warning(self, "No destination", "Open a destination XML file first.")
            return

        # Preserve any unsaved prefix edits currently shown in the destination tree.
        current_destination_codes = {}
        def capture_current(item):
            path = item.data(0, Qt.UserRole)
            combo = self.destination_structure.itemWidget(item, 1)
            current_destination_codes[path] = self.combo_prefix_state(combo) if combo else (False, "")
            for child_index in range(item.childCount()):
                capture_current(item.child(child_index))
        for top_index in range(self.destination_structure.topLevelItemCount()):
            capture_current(self.destination_structure.topLevelItem(top_index))

        existing_codes = {
            code.strip().casefold()
            for _group_name, entries in self.prefix_groups
            for code, _description in entries
            if code.strip()
        }
        imported = {}

        def walk(element, category_path=()):
            name = element.get("name", "")
            current_path = category_path + ((name,) if name else ())
            for child in list(element):
                if not isinstance(child.tag, str):
                    continue
                if child.tag == "prefix":
                    code = (child.text or "").strip()
                    if code and code.casefold() not in existing_codes:
                        imported.setdefault(code, set()).add(" / ".join(current_path))
                elif child.tag == "category":
                    walk(child, current_path)

        root = self.destination_tree.getroot()
        for child in list(root):
            if isinstance(child.tag, str) and child.tag == "category":
                walk(child)

        if not imported:
            QMessageBox.information(
                self, "Import destination prefixes",
                "No new prefixes found. All explicit destination prefixes are already present in the catalogue."
            )
            return

        group_name = "Imported from destination XML"
        group_index = next((i for i, (name, _entries) in enumerate(self.prefix_groups) if name == group_name), None)
        if group_index is None:
            self.prefix_groups.append((group_name, []))
            group_index = len(self.prefix_groups) - 1

        updated_groups = list(self.prefix_groups)
        updated_name, updated_entries = updated_groups[group_index]
        updated_entries = list(updated_entries)
        for code in sorted(imported, key=str.casefold):
            categories = ", ".join(sorted(filter(None, imported[code])))
            description = f"Imported from {self.destination_file.name}"
            if categories:
                description += f"; category: {categories}"
            updated_entries.append((code, description))
        updated_groups[group_index] = (updated_name, updated_entries)
        self.prefix_groups = updated_groups

        try:
            self.save_prefix_catalogue()
        except OSError as exc:
            QMessageBox.critical(self, "Save prefix catalogue", str(exc))
            return

        self.rebuild_all_prefix_selectors()
        self.populate_destination_structure()
        # Restore the live destination selections (including unsaved edits).
        def restore_current(item):
            path = item.data(0, Qt.UserRole)
            state = current_destination_codes.get(path)
            if state is not None:
                has_prefix, code = state
                combo = self.destination_structure.itemWidget(item, 1)
                if combo is not None:
                    if not has_prefix:
                        combo.setCurrentIndex(0)
                    elif not code:
                        combo.setCurrentIndex(1)
                    else:
                        match = next((i for i in range(combo.count()) if str(combo.itemData(i) or "") == code), -1)
                        if match >= 0:
                            combo.setCurrentIndex(match)
                        else:
                            combo.addItem(code, code)
                            combo.setCurrentIndex(combo.count() - 1)
                    self.destination_prefix_changed(item)
            for child_index in range(item.childCount()):
                restore_current(item.child(child_index))
        for top_index in range(self.destination_structure.topLevelItemCount()):
            restore_current(self.destination_structure.topLevelItem(top_index))

        self.compare_structures()
        QMessageBox.information(
            self, "Import complete",
            f"Added {len(imported)} new prefix(es) from the destination XML to:\n{self.catalogue_path}\n\n"
            "Existing catalogue entries were retained."
        )

    def rebuild_all_prefix_selectors(self):
        def visit(item):
            combo = self.tree.itemWidget(item, self.PREFIX_COLUMN)
            old_has_prefix, old_code = self.combo_prefix_state(combo)
            self.add_prefix_selector(item, old_code, explicit_empty=(old_has_prefix and not old_code))
            for i in range(item.childCount()):
                visit(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))
        self.update_preview()

    def open_destination_xml(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open destination XML", str(Path.home()), "XML files (*.xml);;All files (*.*)")
        if not filename:
            return
        try:
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
            self.destination_tree = ET.parse(filename, parser=parser)
            root = self.destination_tree.getroot()
            if root.tag != "labels":
                raise ValueError(f"Expected root element <labels>, found <{root.tag}>.")
            self.destination_file = Path(filename)
            self.destination_edit.setText(str(self.destination_file))
            self.show_destination_file()
            self.populate_destination_structure()
            self.compare_structures()
            self.merge_btn.setEnabled(self.tree.topLevelItemCount() > 0)
            self.import_prefixes_btn.setEnabled(True)
            self.status_label.setText(f"Destination XML opened: {self.destination_file}")
        except (OSError, ET.ParseError, ValueError) as exc:
            self.destination_tree = None
            self.destination_file = None
            self.destination_edit.clear()
            self.destination_preview.setPlainText("")
            self.destination_structure.clear()
            self.save_destination_btn.setEnabled(False)
            self.merge_btn.setEnabled(False)
            self.import_prefixes_btn.setEnabled(False)
            QMessageBox.critical(self, "Open XML failed", str(exc))

    def populate_destination_structure(self):
        self.destination_structure.clear()
        if self.destination_tree is None:
            self.save_destination_btn.setEnabled(False)
            return
        root = self.destination_tree.getroot()
        category_index = 0
        for element in list(root):
            if isinstance(element.tag, str) and element.tag == "category":
                item = self.add_destination_category(None, element, (category_index,))
                item.setExpanded(True)
                category_index += 1
        self.save_destination_btn.setEnabled(True)
        self.autosize_tree_columns(self.destination_structure)
        self.compare_structures()

    def add_destination_category(self, parent_item, element, element_path):
        item = QTreeWidgetItem([element.get("name", ""), "", "", ""])
        if parent_item is None:
            self.destination_structure.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        item.setData(0, Qt.UserRole, element_path)
        prefix_element = next((child for child in list(element) if child.tag == "prefix"), None)
        has_prefix_element = prefix_element is not None
        prefix = (prefix_element.text or "").strip() if has_prefix_element else ""
        combo = QComboBox()
        combo.setMinimumWidth(75)
        combo.setMaximumWidth(150)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMaxVisibleItems(20)
        combo.setToolTip("Type characters to search/filter prefix codes, or select a code. Group name and description are shown in separate columns.")
        for display, code, description, group_name in self.prefix_options():
            combo.addItem(display, code)
            combo.setItemData(combo.count() - 1, description, Qt.UserRole + 1)
            combo.setItemData(combo.count() - 1, group_name, Qt.UserRole + 2)
            combo.setItemData(combo.count() - 1, f"{group_name} — {description}" if group_name else description, Qt.ToolTipRole)
        if not has_prefix_element:
            match = 0
        elif not prefix:
            match = 1
        else:
            match = next((i for i in range(combo.count()) if combo.itemData(i) == prefix), -1)
            if match < 0:
                combo.addItem(prefix, prefix)
                combo.setItemData(combo.count() - 1, "Custom / existing destination prefix", Qt.UserRole + 1)
                match = combo.count() - 1
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)
        combo.setCurrentIndex(match)
        self.destination_structure.setItemWidget(item, 1, combo)
        description = ("Inherited from parent" if not has_prefix_element else
                       "Explicit empty <prefix/> — no letter" if not prefix else
                       (combo.itemData(match, Qt.UserRole + 1) or "Custom / project-specific code"))
        group_name = combo.itemData(match, Qt.UserRole + 2) if match >= 0 else ""
        if prefix and not group_name:
            group_name = "Custom / loaded XML"
        item.setText(2, str(group_name or ""))
        item.setText(3, str(description))
        item.setToolTip(2, str(group_name or ""))
        item.setToolTip(3, str(description))
        combo.currentIndexChanged.connect(lambda _=None, current=item: self.destination_prefix_changed(current))
        combo.editTextChanged.connect(lambda _=None, current=item: self.destination_prefix_changed(current))
        category_index = 0
        for child in list(element):
            if isinstance(child.tag, str) and child.tag == "category":
                self.add_destination_category(item, child, element_path + (category_index,))
                category_index += 1
        return item

    def destination_prefix_changed(self, item):
        combo = self.destination_structure.itemWidget(item, 1)
        has_prefix, code = self.combo_prefix_state(combo)
        index = combo.currentIndex() if combo else -1
        description = combo.itemData(index, Qt.UserRole + 1) if combo and index >= 0 else ""
        if not has_prefix:
            description = "Inherited from parent"
        elif not code:
            description = "Explicit empty <prefix/> — no letter"
        elif not description or (index >= 0 and combo.currentText() != combo.itemText(index)):
            description = "Custom / project-specific code"
        group_name = combo.itemData(index, Qt.UserRole + 2) if combo and index >= 0 else ""
        if code and not group_name:
            group_name = "Custom / loaded XML"
        item.setText(2, str(group_name or ""))
        item.setText(3, str(description))
        item.setToolTip(2, str(group_name or ""))
        item.setToolTip(3, str(description))
        self.compare_structures()

    @staticmethod
    def _tree_item_path(item):
        """Return the exact QET hierarchy key; folder names are case-sensitive."""
        names = []
        current = item
        while current is not None:
            names.append(current.text(0))
            current = current.parent()
        return tuple(reversed(names))

    def _collect_tree_items(self, tree, destination=False):
        result = {}
        prefix_column = 1

        def visit(item):
            path = self._tree_item_path(item)
            combo = tree.itemWidget(item, prefix_column)
            prefix = self.combo_code(combo) if combo is not None else ""
            result[path] = (item, prefix)
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(tree.topLevelItemCount()):
            visit(tree.topLevelItem(index))
        return result

    @staticmethod
    def _set_item_difference(item, is_different):
        color = QColor("#d00000") if is_different else QColor()
        brush = QBrush(color) if is_different else QBrush()
        for column in range(item.columnCount()):
            item.setForeground(column, brush)
        # The prefix is a cell widget, so color its editable text separately.
        tree = item.treeWidget()
        if tree is not None:
            combo = tree.itemWidget(item, 1)
            if combo is not None:
                combo.setStyleSheet("QComboBox, QComboBox QLineEdit { color: #d00000; }" if is_different else "")

    def compare_structures(self):
        """Highlight only folders/categories missing from the opposite tree.

        Prefix values are deliberately ignored: an empty or different prefix is not
        a folder-structure difference and must not turn the source row red.
        """
        if not hasattr(self, "tree") or not hasattr(self, "destination_structure"):
            return
        source_items = self._collect_tree_items(self.tree)
        destination_items = self._collect_tree_items(self.destination_structure, destination=True)

        # Clear previous comparison colors.
        for item, _prefix in source_items.values():
            self._set_item_difference(item, False)
        for item, _prefix in destination_items.values():
            self._set_item_difference(item, False)

        if self.destination_tree is None:
            return

        source_paths = set(source_items)
        destination_paths = set(destination_items)
        # Only a folder/category absent from the other hierarchy is highlighted.
        for path in source_paths - destination_paths:
            self._set_item_difference(source_items[path][0], True)
        for path in destination_paths - source_paths:
            self._set_item_difference(destination_items[path][0], True)

    def apply_destination_prefix_edits(self):
        if self.destination_tree is None:
            return
        root = self.destination_tree.getroot()
        def visit(item):
            path = item.data(0, Qt.UserRole)
            element = root
            for index in path:
                categories = [child for child in list(element) if isinstance(child.tag, str) and child.tag == "category"]
                element = categories[index]
            combo = self.destination_structure.itemWidget(item, 1)
            has_prefix, prefix = self.combo_prefix_state(combo)
            prefix_nodes = [child for child in list(element) if isinstance(child.tag, str) and child.tag == "prefix"]
            # Preserve the XML schema ordering: prefix follows all child categories.
            for node in prefix_nodes:
                element.remove(node)
            if has_prefix:
                ET.SubElement(element, "prefix").text = prefix or None
            for child_index in range(item.childCount()):
                visit(item.child(child_index))
        for index in range(self.destination_structure.topLevelItemCount()):
            visit(self.destination_structure.topLevelItem(index))

    def create_application_backup(self):
        """Create a backup with a name QET itself does not use."""
        base = self.destination_file.with_name(self.destination_file.name + ".folder_to_xml.bak")
        backup = base
        if backup.exists():
            backup = self.destination_file.with_name(
                self.destination_file.name + time.strftime(".%Y%m%d_%H%M%S.folder_to_xml.bak")
            )
        backup.write_bytes(self.destination_file.read_bytes())
        return backup

    def save_destination_edits(self):
        if self.destination_tree is None or self.destination_file is None:
            QMessageBox.warning(self, "No destination", "Open a destination XML file first.")
            return
        try:
            self.apply_destination_prefix_edits()
            backup_path = self.create_application_backup()
            temp_path = self.destination_file.with_suffix(self.destination_file.suffix + ".tmp")
            try:
                ET.indent(self.destination_tree, space="    ")
                self.destination_tree.write(temp_path, encoding="utf-8", xml_declaration=True)
                parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
                ET.parse(str(temp_path), parser=parser)
                temp_path.replace(self.destination_file)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            self.show_destination_file()
            self.status_label.setText("Destination XML prefix edits saved.")
            QMessageBox.information(self, "Saved", f"Prefix edits saved to:\n{self.destination_file}\nBackup: {backup_path.name}")
        except (OSError, ET.ParseError, ValueError, IndexError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def show_destination_file(self):
        if not self.destination_file:
            self.destination_preview.clear()
            return
        try:
            content = self.destination_file.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = self.destination_file.read_text(encoding="cp1252")
        self.destination_preview.setPlainText(content)

    def item_to_xml(self, item):
        category = ET.Element("category", {"name": item.text(0)})
        for index in range(item.childCount()):
            category.append(self.item_to_xml(item.child(index)))
        combo = self.tree.itemWidget(item, self.PREFIX_COLUMN)
        has_prefix, prefix = self.combo_prefix_state(combo)
        if has_prefix:
            ET.SubElement(category, "prefix").text = prefix or None
        return category

    def build_xml_tree(self):
        if self.tree.topLevelItemCount() == 0:
            raise ValueError("There are no source folders to export or merge.")
        labels = ET.Element("labels")
        labels.append(self.item_to_xml(self.tree.topLevelItem(0)))
        return ET.ElementTree(labels)

    def xml_text(self):
        tree = self.build_xml_tree()
        ET.indent(tree, space="    ")
        return ET.tostring(tree.getroot(), encoding="unicode")

    def update_preview(self, *args):
        if self.tree.topLevelItemCount() == 0:
            self.preview.clear()
            self.merge_btn.setEnabled(self.destination_tree is not None)
            return
        try:
            self.preview.setPlainText('<?xml version="1.0" encoding="utf-8"?>\n' + self.xml_text())
        except Exception as exc:
            self.preview.setPlainText(f"XML preview error:\n{exc}")
        self.merge_btn.setEnabled(self.destination_tree is not None)

    @staticmethod
    def find_category(parent, name):
        for child in list(parent):
            if isinstance(child.tag, str) and child.tag == "category" and child.get("name") == name:
                return child
        return None

    def merge_category(self, destination_parent, source_category):
        """Merge recursively; never alter an existing destination category or prefix."""
        name = source_category.get("name", "")
        existing = self.find_category(destination_parent, name)
        if existing is None:
            destination_parent.append(copy.deepcopy(source_category))
            return 1
        added = 0
        for source_child in list(source_category):
            if isinstance(source_child.tag, str) and source_child.tag == "category":
                added += self.merge_category(existing, source_child)
        return added

    def merge_into_destination(self):
        if self.destination_tree is None or self.destination_file is None:
            QMessageBox.warning(self, "No destination", "Open a destination XML file first.")
            return
        if self.tree.topLevelItemCount() == 0:
            QMessageBox.warning(self, "No source", "Select and scan a source folder first.")
            return
        try:
            self.apply_destination_prefix_edits()
            source_root = self.build_xml_tree().getroot()
            # Work on a copy so cancelling the backup prompt cannot alter the in-memory destination.
            merged_tree = ET.ElementTree(copy.deepcopy(self.destination_tree.getroot()))
            destination_root = merged_tree.getroot()
            if destination_root.tag != "labels":
                raise ValueError("Destination XML root must be <labels>.")
            added = 0
            for source_category in list(source_root):
                if isinstance(source_category.tag, str) and source_category.tag == "category":
                    added += self.merge_category(destination_root, source_category)

            backup_path = self.create_application_backup()
            ET.indent(merged_tree, space="    ")
            temp_path = self.destination_file.with_suffix(self.destination_file.suffix + ".tmp")
            try:
                merged_tree.write(temp_path, encoding="utf-8", xml_declaration=True)
                # Validate the temporary output before replacing the original destination.
                parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
                ET.parse(str(temp_path), parser=parser)
                temp_path.replace(self.destination_file)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
            self.destination_tree = ET.parse(str(self.destination_file), parser=parser)
            self.show_destination_file()
            self.populate_destination_structure()
            self.status_label.setText(f"Merge complete: {added} new categories added. Backup: {backup_path.name}")
            QMessageBox.information(
                self, "Merge complete",
                f"The source folder structure has been merged into:\n{self.destination_file}\n\n"
                f"New categories added: {added}\nExisting destination prefixes were preserved.\n"
                f"Backup created: {backup_path}"
            )
        except (OSError, ET.ParseError, ValueError) as exc:
            QMessageBox.critical(self, "Merge failed", str(exc))

    def export_xml(self):
        if self.tree.topLevelItemCount() == 0:
            QMessageBox.warning(self, "Nothing to export", "Scan a source folder first.")
            return
        default_name = f"{self.root_folder.name}_labels.xml" if self.root_folder else "labels.xml"
        filename, _ = QFileDialog.getSaveFileName(self, "Save XML file", default_name, "XML files (*.xml)")
        if not filename:
            return
        if not filename.lower().endswith(".xml"):
            filename += ".xml"
        try:
            tree = self.build_xml_tree()
            ET.indent(tree, space="    ")
            tree.write(filename, encoding="utf-8", xml_declaration=True)
            ET.parse(filename)
            self.status_label.setText(f"Source XML exported and validated: {filename}")
            QMessageBox.information(self, "Export complete", f"XML successfully exported and validated:\n{filename}")
        except (OSError, ET.ParseError, ValueError) as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


def main():
    app = QApplication(sys.argv)
    window = FolderXmlEditor()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

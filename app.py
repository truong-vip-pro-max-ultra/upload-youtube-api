"""YT Batch Uploader - GUI PySide6 cho yt_uploader.py

Quan ly NHIEU tai khoan (moi cookie = 1 account, giong upload-facebook-reels),
moi account co the co nhieu kenh. Upload hang loat, dinh tuyen tung video ->
(tai khoan, kenh) bat ky.

Chay: python app.py
Build exe: pyinstaller --onefile --windowed --collect-all curl_cffi app.py
"""

import json
import os
import queue
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QThread, Signal, QDateTime, QSize, QRect
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QFileDialog, QProgressBar, QHeaderView, QFrame,
    QAbstractItemView, QSplitter, QMessageBox, QCheckBox, QDateTimeEdit,
    QSpinBox, QDialog, QDialogButtonBox, QGridLayout, QTabWidget,
)

from yt_uploader import YouTubeUploader, UploadCancelled, CookieStore
import account_store as acct

VIDEO_EXTS = "Video (*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v)"

PRIVACY_OPTIONS = [
    ("Riêng tư", "PRIVATE"),
    ("Không công khai", "UNLISTED"),
    ("Công khai", "PUBLIC"),
]
MFK_OPTIONS = [
    ("Không dành cho trẻ em", False),
    ("Dành cho trẻ em", True),
]

# Role luu du lieu rieng tung dong (tren item cot FILE)
ROLE_TARGET = Qt.UserRole + 3      # key "accId|pageId" cua kenh
ROLE_VIDEOS = Qt.UserRole + 4      # list[{path,title,desc,privacy,mfk}] gan cho kenh

# Bang KENH (tab Upload): moi dong = 1 kenh, gan nhieu video vao (giong FB fanpage)
UCOL_CHECK, UCOL_ACCOUNT, UCOL_CHANNEL, UCOL_VIDEOS, UCOL_STATUS = range(5)
# Bang account
ACOL_CHECK, ACOL_NAME, ACOL_STATUS, ACOL_CHANNELS, ACOL_TIME = range(5)

# ---- Bang mau ----
C_BG        = "#0e1013"
C_SURFACE   = "#181b21"
C_SURFACE_2 = "#1f232b"
C_INPUT     = "#20242d"
C_BORDER    = "#2b303b"
C_TEXT      = "#e7e9ee"
C_MUTED     = "#828a99"
C_ACCENT    = "#f5333f"
C_ACCENT_HI = "#ff5b64"
C_OK        = "#46d17f"
C_WARN      = "#f5c451"
C_ERR       = "#ff6b6b"

QSS = f"""
* {{ font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
QMainWindow, QWidget {{ background: {C_BG}; color: {C_TEXT}; }}
QLabel {{ background: transparent; color: {C_TEXT}; }}

QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {C_MUTED};
    padding: 10px 20px; margin-right: 4px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {C_TEXT}; border-bottom: 2px solid {C_ACCENT}; }}
QTabBar::tab:hover {{ color: {C_TEXT}; }}

QFrame#card {{
    background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 14px;
}}
QLabel#cardTitle {{
    font-size: 11px; font-weight: 700; color: {C_MUTED};
    letter-spacing: 1.4px; text-transform: uppercase;
}}
QLabel#field {{ color: {C_MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#hint {{ color: {C_MUTED}; font-size: 12px; }}
QLabel#statusOk  {{ color: {C_OK}; font-weight: 600; }}
QLabel#statusErr {{ color: {C_ERR}; font-weight: 600; }}

QLineEdit, QPlainTextEdit, QComboBox, QDateTimeEdit, QSpinBox {{
    background: {C_INPUT}; border: 1px solid {C_BORDER}; border-radius: 9px;
    padding: 8px 11px; color: {C_TEXT};
    selection-background-color: {C_ACCENT}; selection-color: white;
}}
QLineEdit:hover, QComboBox:hover, QDateTimeEdit:hover, QSpinBox:hover,
QPlainTextEdit:hover {{ border-color: #3a4150; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QDateTimeEdit:focus, QSpinBox:focus {{ border-color: {C_ACCENT}; }}
QLineEdit::placeholder {{ color: #5f6675; }}

QCheckBox {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{
    width: 19px; height: 19px; border-radius: 6px;
    border: 1px solid #3c4351; background: {C_INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {C_ACCENT}; }}
QCheckBox::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}

QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-top: 6px solid {C_MUTED}; margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {C_SURFACE_2}; border: 1px solid {C_BORDER}; border-radius: 10px;
    selection-background-color: {C_ACCENT}; selection-color: white;
    outline: none; padding: 5px;
}}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 4px 8px; border-radius: 6px; }}

QDateTimeEdit::drop-down, QSpinBox::up-button, QSpinBox::down-button {{
    border: none; width: 18px; background: transparent;
}}
QSpinBox::up-arrow {{ image: none; width:0;height:0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 5px solid {C_MUTED}; }}
QSpinBox::down-arrow {{ image: none; width:0;height:0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {C_MUTED}; }}
QCalendarWidget QWidget {{ background: {C_SURFACE_2}; color: {C_TEXT}; }}
QCalendarWidget QAbstractItemView {{ selection-background-color: {C_ACCENT}; }}

QPushButton {{
    background: {C_SURFACE_2}; border: 1px solid {C_BORDER}; border-radius: 9px;
    padding: 9px 15px; font-weight: 600; color: {C_TEXT};
}}
QPushButton:hover {{ background: #262b34; border-color: #3a4150; }}
QPushButton:pressed {{ background: {C_INPUT}; }}
QPushButton:disabled {{ color: #565d6b; background: #171a20; border-color: #23272f; }}

QPushButton#primary {{
    background: {C_ACCENT}; border: none; color: white;
    font-size: 14px; font-weight: 700; padding: 12px 22px;
}}
QPushButton#primary:hover {{ background: {C_ACCENT_HI}; }}
QPushButton#primary:pressed {{ background: #cf2932; }}
QPushButton#primary:disabled {{ background: #4a2325; color: #b79597; }}

QPushButton#ghost {{ background: transparent; border: 1px solid {C_BORDER}; }}
QPushButton#ghost:hover {{ background: {C_SURFACE_2}; }}
QPushButton#danger {{ background: transparent; border: 1px solid #7a2b2b; color: {C_ERR}; }}
QPushButton#danger:hover {{ background: #2c1c1e; }}

QTableWidget {{
    background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 12px;
    gridline-color: transparent; alternate-background-color: #1c2027; outline: none;
}}
QTableWidget::item {{ padding: 9px 10px; border: none; color: {C_TEXT}; }}
QTableWidget::item:selected {{ background: #33222a; color: #ffffff; }}
QTableWidget::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #3c4351; background: {C_INPUT};
}}
QTableWidget::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}
QTableWidget::indicator:hover {{ border-color: {C_ACCENT}; }}
QHeaderView::section {{
    background: {C_SURFACE}; color: {C_MUTED};
    font-weight: 700; font-size: 11px; letter-spacing: 0.6px;
    border: none; border-bottom: 1px solid {C_BORDER}; padding: 10px;
}}
QTableCornerButton::section {{ background: {C_SURFACE}; border: none; }}

QProgressBar {{
    background: {C_INPUT}; border: none; border-radius: 8px; height: 16px;
    text-align: center; font-size: 11px; font-weight: 600; color: #ffffff;
}}
QProgressBar::chunk {{ background: {C_ACCENT}; border-radius: 8px; }}

QPlainTextEdit#log {{
    background: #0a0c0f; border: 1px solid {C_BORDER}; border-radius: 11px;
    font-family: 'Cascadia Code', Consolas, monospace; font-size: 12px; color: #96b8a6;
    padding: 8px;
}}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar::handle:vertical {{ background: #333a46; border-radius: 5px; min-height: 34px; }}
QScrollBar::handle:vertical:hover {{ background: #454e5e; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle:horizontal {{ background: #333a46; border-radius: 5px; min-width: 34px; }}

QSplitter::handle {{ background: transparent; height: 8px; }}
QDialog {{ background: {C_BG}; }}
QDialogButtonBox QPushButton {{ min-width: 92px; }}
"""


# ==========================================================================
# Bang co cot checkbox (mo hinh chon nhieu dong giong upload-facebook-reels)
# ==========================================================================
_CHECK_FLAGS = (Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)


def add_check_item(table, row):
    item = QTableWidgetItem()
    item.setFlags(_CHECK_FLAGS)
    item.setCheckState(Qt.Unchecked)
    item.setTextAlignment(Qt.AlignCenter)
    table.setItem(row, 0, item)
    return item


def row_checked(table, row):
    it = table.item(row, 0)
    return it is not None and it.checkState() == Qt.Checked


def checked_rows(table):
    return [r for r in range(table.rowCount()) if row_checked(table, r)]


def selected_rows(table):
    return sorted({idx.row() for idx in table.selectedIndexes()})


def target_rows(table):
    ticked = checked_rows(table)
    return ticked if ticked else selected_rows(table)


def set_rows_checked(table, rows, value):
    state = Qt.Checked if value else Qt.Unchecked
    for row in rows:
        it = table.item(row, 0)
        if it is not None:
            it.setCheckState(state)


class CheckableHeaderView(QHeaderView):
    toggled = Signal(bool)
    _BOX = 18

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._checked = False
        self.setSectionsClickable(True)

    def set_checked(self, value):
        if self._checked != value:
            self._checked = value
            self.updateSection(0)

    def _box_rect(self, rect):
        x = rect.x() + (rect.width() - self._BOX) // 2
        y = rect.y() + (rect.height() - self._BOX) // 2
        return QRect(x, y, self._BOX, self._BOX)

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0:
            return
        box = self._box_rect(rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._checked:
            painter.setBrush(QColor(C_ACCENT)); painter.setPen(QColor(C_ACCENT))
            painter.drawRoundedRect(box, 4, 4)
            pen = QPen(QColor("white")); pen.setWidth(2)
            pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            cy = box.center().y()
            painter.drawLine(box.left() + 4, cy + 1, box.center().x() - 1, box.bottom() - 4)
            painter.drawLine(box.center().x() - 1, box.bottom() - 4, box.right() - 3, box.top() + 4)
        else:
            pen = QPen(QColor("#3c4351")); pen.setWidth(2)
            painter.setPen(pen); painter.setBrush(QColor(C_INPUT))
            painter.drawRoundedRect(box, 4, 4)
        painter.restore()

    def mousePressEvent(self, event):
        if self.logicalIndexAt(int(event.position().x())) == 0:
            self._checked = not self._checked
            self.updateSection(0)
            self.toggled.emit(self._checked)
            return
        super().mousePressEvent(event)


def make_table(headers, check_col_width=40):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(40)
    table.setWordWrap(False)
    hdr = CheckableHeaderView(table)
    table.setHorizontalHeader(hdr)
    hdr.toggled.connect(lambda on: set_rows_checked(table, list(range(table.rowCount())), on))
    hdr.setSectionResizeMode(0, QHeaderView.Fixed)
    table.setColumnWidth(0, check_col_width)
    return table, hdr


# ==========================================================================
# Dialogs
# ==========================================================================
class CookiePasteDialog(QDialog):
    """Dan cookie JSON cua 1 tai khoan."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Dán cookie JSON")
        self.setMinimumSize(560, 440)
        self.cookies = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18); lay.setSpacing(12)
        intro = QLabel(
            "Dán cookie 1 tài khoản (JSON export từ Cookie-Editor, cookies.txt, "
            "hoặc chuỗi <code>tên=giá_trị; …</code>)."
        )
        intro.setObjectName("hint"); intro.setWordWrap(True)
        lay.addWidget(intro)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('[ { "name": "SAPISID", "value": "...", "domain": ".youtube.com" }, ... ]')
        f = self.editor.font(); f.setFamily("Consolas"); self.editor.setFont(f)
        lay.addWidget(self.editor, 1)
        self.msg = QLabel(""); self.msg.setObjectName("hint"); self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Thêm tài khoản")
        btns.button(QDialogButtonBox.Ok).setObjectName("primary")
        btns.button(QDialogButtonBox.Cancel).setText("Hủy")
        btns.accepted.connect(self._on_ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _err(self, text):
        self.msg.setText(text); self.msg.setObjectName("statusErr")
        self.msg.style().unpolish(self.msg); self.msg.style().polish(self.msg)

    def _on_ok(self):
        text = self.editor.toPlainText().strip()
        if not text:
            self._err("⚠ Chưa dán nội dung cookie."); return
        try:
            store = CookieStore(text)
        except Exception as e:
            self._err(f"✗ Cookie không hợp lệ: {e}"); return
        if not acct.has_login_cookie(store.cookies):
            self._err("✗ Thiếu cookie đăng nhập (SAPISID/SID). Export lại khi đang đăng nhập.")
            return
        self.cookies = store.cookies
        self.accept()


class DescriptionDialog(QDialog):
    """O nhap mo ta LON (nhieu dong) de gan hang loat."""

    def __init__(self, parent, *, subtitle="", initial=""):
        super().__init__(parent)
        self.setWindowTitle("Mô tả")
        self.setMinimumSize(600, 440)
        self.text = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18); lay.setSpacing(12)
        if subtitle:
            lb = QLabel(subtitle); lb.setObjectName("hint"); lb.setWordWrap(True)
            lay.addWidget(lb)
        self.editor = QPlainTextEdit(initial)
        self.editor.setPlaceholderText("Nhập mô tả cho video...")
        f = self.editor.font(); f.setPointSize(11); self.editor.setFont(f)
        lay.addWidget(self.editor, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Áp dụng")
        btns.button(QDialogButtonBox.Ok).setObjectName("primary")
        btns.button(QDialogButtonBox.Cancel).setText("Hủy")
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _ok(self):
        self.text = self.editor.toPlainText().strip()
        self.accept()


class TitlePatternDialog(QDialog):
    """Nhap mau tieu de hang loat: {n} = so thu tu, {name} = ten file."""

    def __init__(self, parent, *, subtitle=""):
        super().__init__(parent)
        self.setWindowTitle("Tiêu đề hàng loạt")
        self.setMinimumWidth(520)
        self.pattern = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18); lay.setSpacing(12)
        if subtitle:
            lb = QLabel(subtitle); lb.setObjectName("hint"); lb.setWordWrap(True)
            lay.addWidget(lb)
        tip = QLabel("Dùng <b>{n}</b> = số thứ tự (trong mỗi kênh), "
                     "<b>{name}</b> = tên file. VD: <i>Tập {n} - {name}</i>")
        tip.setObjectName("hint"); tip.setWordWrap(True)
        lay.addWidget(tip)
        self.edit = QLineEdit(); self.edit.setMinimumHeight(44)
        f = self.edit.font(); f.setPointSize(12); self.edit.setFont(f)
        self.edit.setPlaceholderText("VD: Video {n} - {name}")
        lay.addWidget(self.edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Áp dụng")
        btns.button(QDialogButtonBox.Ok).setObjectName("primary")
        btns.button(QDialogButtonBox.Cancel).setText("Hủy")
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _ok(self):
        self.pattern = self.edit.text().strip()
        if self.pattern:
            self.accept()


class VideoDetailDialog(QDialog):
    """Sua 1 video: o TIEU DE lon + o MO TA lon (nhieu dong)."""

    def __init__(self, parent, *, file_name, title, description):
        super().__init__(parent)
        self.setWindowTitle("Chi tiết video")
        self.setMinimumSize(600, 480)
        self.result = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18); lay.setSpacing(12)
        head = QLabel(file_name); head.setObjectName("hint"); head.setWordWrap(True)
        lay.addWidget(head)

        lb1 = QLabel("Tiêu đề"); lb1.setObjectName("field"); lay.addWidget(lb1)
        self.title_edit = QLineEdit(title); self.title_edit.setMinimumHeight(48)
        f = self.title_edit.font(); f.setPointSize(13); self.title_edit.setFont(f)
        self.title_edit.setPlaceholderText("Tiêu đề video...")
        lay.addWidget(self.title_edit)

        lb2 = QLabel("Mô tả"); lb2.setObjectName("field"); lay.addWidget(lb2)
        self.desc_edit = QPlainTextEdit(description)
        self.desc_edit.setPlaceholderText("Mô tả video (để trống = dùng mô tả chung)...")
        fd = self.desc_edit.font(); fd.setPointSize(11); self.desc_edit.setFont(fd)
        lay.addWidget(self.desc_edit, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Lưu")
        btns.button(QDialogButtonBox.Ok).setObjectName("primary")
        btns.button(QDialogButtonBox.Cancel).setText("Hủy")
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _ok(self):
        self.result = {"title": self.title_edit.text().strip(),
                       "desc": self.desc_edit.toPlainText().strip()}
        self.accept()


class ChannelVideosDialog(QDialog):
    """Quan ly video gan cho 1 KENH. Bang xem tong quan; nhay dup 1 video mo o
    sua LON (tieu de + mo ta). Co dat tieu de / mo ta HANG LOAT.

    videos = list[{path,title,desc,privacy,mfk}]. Ket qua qua .result_videos.
    """

    VCOL_FILE, VCOL_TITLE, VCOL_DESC = range(3)

    def __init__(self, parent, *, channel_label, videos):
        super().__init__(parent)
        self.setWindowTitle("Video của kênh")
        self.setMinimumSize(820, 540)
        self.result_videos = None
        self._videos = [dict(v) for v in videos]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16); lay.setSpacing(12)

        head = QLabel(f"Kênh: <b>{channel_label}</b>")
        head.setObjectName("hint"); head.setWordWrap(True)
        lay.addWidget(head)

        bar = QHBoxLayout(); bar.setSpacing(8)
        add_btn = QPushButton("Thêm video"); add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add)
        edit_btn = QPushButton("Sửa chi tiết"); edit_btn.setObjectName("ghost")
        edit_btn.clicked.connect(self._edit_selected)
        rm_btn = QPushButton("Xóa dòng"); rm_btn.setObjectName("ghost")
        rm_btn.clicked.connect(self._remove)
        bar.addWidget(add_btn); bar.addWidget(edit_btn); bar.addWidget(rm_btn)
        bar.addStretch(1)
        lay.addLayout(bar)

        bar2 = QHBoxLayout(); bar2.setSpacing(8)
        self.bulk_title = QLineEdit()
        self.bulk_title.setPlaceholderText("Tiêu đề hàng loạt: {n}, {name}")
        title_btn = QPushButton("Đặt tiêu đề"); title_btn.setObjectName("ghost")
        title_btn.clicked.connect(self._bulk_title)
        desc_btn = QPushButton("Đặt mô tả hàng loạt"); desc_btn.setObjectName("ghost")
        desc_btn.clicked.connect(self._bulk_desc)
        bar2.addWidget(self.bulk_title, 1); bar2.addWidget(title_btn); bar2.addWidget(desc_btn)
        lay.addLayout(bar2)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File", "Tiêu đề", "Mô tả"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(lambda idx: self._edit_row(idx.row()))
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self.VCOL_FILE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.VCOL_TITLE, QHeaderView.Stretch)
        h.setSectionResizeMode(self.VCOL_DESC, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        hint = QLabel("Nháy đúp một video để sửa tiêu đề & mô tả trong ô lớn.")
        hint.setObjectName("hint"); lay.addWidget(hint)
        self._render()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Lưu")
        btns.button(QDialogButtonBox.Ok).setObjectName("primary")
        btns.button(QDialogButtonBox.Cancel).setText("Hủy")
        btns.accepted.connect(self._on_ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _render(self):
        self.table.setRowCount(0)
        for v in self._videos:
            row = self.table.rowCount(); self.table.insertRow(row)
            fi = QTableWidgetItem(os.path.basename(v["path"]))
            fi.setToolTip(v["path"])
            self.table.setItem(row, self.VCOL_FILE, fi)
            self.table.setItem(row, self.VCOL_TITLE, QTableWidgetItem(v.get("title") or ""))
            desc = (v.get("desc") or "").replace("\n", " ")
            dcell = QTableWidgetItem(desc if desc else "—")
            if not desc:
                dcell.setForeground(QColor(C_MUTED))
            self.table.setItem(row, self.VCOL_DESC, dcell)

    def _sel_rows(self):
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn video", "", VIDEO_EXTS)
        for p in paths:
            self._videos.append({"path": p, "title": os.path.splitext(os.path.basename(p))[0],
                                 "desc": "", "privacy": None, "mfk": None})
        self._render()

    def _remove(self):
        for r in sorted(self._sel_rows(), reverse=True):
            if 0 <= r < len(self._videos):
                del self._videos[r]
        self._render()

    def _edit_selected(self):
        rows = self._sel_rows()
        if rows:
            self._edit_row(rows[0])

    def _edit_row(self, row):
        if not (0 <= row < len(self._videos)):
            return
        v = self._videos[row]
        dlg = VideoDetailDialog(self, file_name=os.path.basename(v["path"]),
                                title=v.get("title") or "", description=v.get("desc") or "")
        if dlg.exec() == QDialog.Accepted:
            v["title"] = dlg.result["title"] or os.path.splitext(os.path.basename(v["path"]))[0]
            v["desc"] = dlg.result["desc"]
            self._render()

    def _bulk_title(self):
        pat = self.bulk_title.text()
        if not pat.strip():
            return
        for n, v in enumerate(self._videos, 1):
            name = os.path.splitext(os.path.basename(v["path"]))[0]
            v["title"] = pat.replace("{n}", str(n)).replace("{name}", name)
        self._render()

    def _bulk_desc(self):
        if not self._videos:
            return
        rows = self._sel_rows()
        scope = self._videos if not rows else [self._videos[r] for r in rows]
        sub = ("Áp dụng cho TẤT CẢ video của kênh." if not rows
               else f"Áp dụng cho {len(rows)} video đã chọn.")
        dlg = DescriptionDialog(self, subtitle=sub)
        if dlg.exec() == QDialog.Accepted:
            for v in scope:
                v["desc"] = dlg.text
            self._render()

    def _on_ok(self):
        for v in self._videos:
            if not (v.get("title") or "").strip():
                v["title"] = os.path.splitext(os.path.basename(v["path"]))[0]
        self.result_videos = self._videos
        self.accept()


# ==========================================================================
# Workers
# ==========================================================================
class AccountCheckWorker(QThread):
    """Dang nhap + tai kenh cho danh sach account (tuan tu, tranh spam Google)."""
    acc_status = Signal(str, str)          # account_id, status text
    acc_done = Signal(str, object)         # account_id, result dict
    acc_failed = Signal(str, str)          # account_id, error
    finished_all = Signal()

    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts

    def run(self):
        for a in self.accounts:
            self.acc_status.emit(a.id, "Đang kiểm tra…")
            try:
                result = acct.check_account(a)
                self.acc_done.emit(a.id, result)
            except Exception as e:
                self.acc_failed.emit(a.id, str(e))
        self.finished_all.emit()


class RefreshCookieWorker(QThread):
    """Lam moi cookie (login + RotateCookies) cho danh sach account, luu lai file."""
    acc_status = Signal(str, str)     # account_id, text
    acc_result = Signal(str, bool, str)   # account_id, ok, message
    finished_all = Signal(int, int)   # ok, fail

    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts

    def run(self):
        from yt_uploader import YouTubeUploader
        ok = fail = 0
        for a in self.accounts:
            self.acc_status.emit(a.id, "Đang làm mới…")
            try:
                up = YouTubeUploader(a.cookie_path)
                up.login()
                rotated = up.rotate_cookies(min_interval=0)
                up.save_cookies()
                ok += 1
                self.acc_result.emit(a.id, True,
                    "đã xoay vòng cookie" if rotated else "đã làm tươi (kênh cá nhân không xoay được)")
            except Exception as e:
                fail += 1
                self.acc_result.emit(a.id, False, str(e))
        self.finished_all.emit(ok, fail)


class UploadWorker(QThread):
    """Upload danh sach job. Moi job co cookie_path + page_id rieng (dinh tuyen
    da tai khoan). Cache 1 uploader/tai khoan, khoa theo tai khoan (song song
    giua cac tai khoan, tuan tu trong 1 tai khoan)."""
    job_status = Signal(int, str)
    job_progress = Signal(int, int)
    job_done = Signal(int, str)
    job_failed = Signal(int, str)
    log = Signal(str)
    finished_all = Signal(int, int)

    def __init__(self, jobs, schedule=None, concurrency=1):
        super().__init__()
        self.jobs = jobs
        self.schedule = schedule
        self.concurrency = max(1, int(concurrency))
        self._stop = False
        self._uploaders = {}
        self._locks = {}
        self._guard = threading.Lock()

    def stop(self):
        self._stop = True

    def _get_uploader(self, cookie_path):
        with self._guard:
            if cookie_path not in self._uploaders:
                u = YouTubeUploader(cookie_path)
                u.login()
                self._uploaders[cookie_path] = u
                self._locks[cookie_path] = threading.Lock()
            return self._uploaders[cookie_path], self._locks[cookie_path]

    def _wait_until(self, target_ts, row):
        while not self._stop:
            remain = target_ts - time.time()
            if remain <= 0:
                return True
            d = int(remain)
            h, m, s = d // 3600, (d % 3600) // 60, d % 60
            self.job_status.emit(row, f"Hẹn giờ — còn {h:02d}:{m:02d}:{s:02d}")
            time.sleep(min(1.0, remain))
        return False

    def _do_job(self, job, index, total):
        row = job["row"]
        name = os.path.basename(job["path"])
        if self._stop:
            self.job_status.emit(row, "Đã hủy"); return "cancel"
        try:
            uploader, lock = self._get_uploader(job["cookie_path"])
        except Exception as e:
            self.job_failed.emit(row, f"Lỗi đăng nhập: {e}")
            self.log.emit(f"   ✗ {name}: lỗi đăng nhập tài khoản: {e}")
            return "fail"
        self.log.emit(f"▸ [{index}/{total}] {name} → {job['channel_label']}")
        self.job_status.emit(row, "Đang tải lên… 0%")
        last_pct = [-1]

        def on_progress(sent, tot, row=row, last_pct=last_pct):
            pct = int(sent * 100 / tot) if tot else 100
            if pct != last_pct[0]:
                last_pct[0] = pct
                self.job_progress.emit(row, pct)

        try:
            with lock:  # tuan tu trong 1 tai khoan
                result = uploader.upload(
                    job["path"], title=job["title"], description=job["description"],
                    privacy=job["privacy"], page_id=job["page_id"],
                    made_for_kids=job["mfk"], on_progress=on_progress,
                    should_cancel=lambda: self._stop, log=lambda m: None,
                )
            vid = result["videoId"]
            self.job_done.emit(row, vid)
            self.log.emit(f"   ✓ Xong: https://youtu.be/{vid}")
            return "ok"
        except UploadCancelled:
            self.job_status.emit(row, "Đã hủy"); self.log.emit("   ⏹ Đã hủy."); return "cancel"
        except Exception as e:
            self.job_failed.emit(row, str(e)); self.log.emit(f"   ✗ Lỗi: {e}"); return "fail"

    def run(self):
        total = len(self.jobs)
        parallel = self.concurrency > 1 and not self.schedule
        if parallel:
            self.log.emit(f"⚡ Upload đồng thời {self.concurrency} luồng (song song giữa các tài khoản)")
            counter = {"i": 0}
            results = []

            def task(job):
                counter["i"] += 1
                return self._do_job(job, counter["i"], total)

            with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                for res in ex.map(task, self.jobs):
                    results.append(res)
            ok = sum(r == "ok" for r in results)
            failed = sum(r == "fail" for r in results)
        else:
            ok = failed = 0
            for i, job in enumerate(self.jobs):
                if self._stop:
                    self.job_status.emit(job["row"], "Đã hủy"); continue
                if self.schedule:
                    tgt = self.schedule["start"] + i * self.schedule["gap"]
                    if tgt > time.time():
                        when = time.strftime("%d/%m %H:%M:%S", time.localtime(tgt))
                        self.log.emit(f"⏰ [{i + 1}/{total}] {os.path.basename(job['path'])} — hẹn lúc {when}")
                        if not self._wait_until(tgt, job["row"]):
                            self.job_status.emit(job["row"], "Đã hủy"); continue
                res = self._do_job(job, i + 1, total)
                ok += res == "ok"; failed += res == "fail"
                if not self.schedule and not self._stop and i < total - 1:
                    end = time.time() + random.uniform(2, 5)
                    while time.time() < end and not self._stop:
                        time.sleep(0.2)
        self.finished_all.emit(ok, failed)


# ==========================================================================
# Main window
# ==========================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YT Batch Uploader")
        self.resize(1240, 800)
        self.store = acct.AccountStore()
        self.targets = []           # [{key, account_id, account_name, cookie_path, page_id, name, handle, photo, label}]
        self._photo_cache = {}      # key -> bytes
        self.check_worker = None
        self.refresh_worker = None
        self.upload_worker = None
        self._done_count = 0
        self._build_ui()
        self._refresh_accounts_table()
        self.refresh_targets()

    # ------------------------------------------------------------- helpers
    def _card(self, title):
        card = QFrame(); card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 17); layout.setSpacing(11)
        label = QLabel(title); label.setObjectName("cardTitle")
        layout.addWidget(label)
        return card, layout

    def _field(self, text):
        w = QLabel(text); w.setObjectName("field"); return w

    def _repolish(self, w):
        w.style().unpolish(w); w.style().polish(w)

    def log(self, msg):
        self.log_view.appendPlainText(msg)
        sb = self.log_view.verticalScrollBar(); sb.setValue(sb.maximum())

    def _icon_for(self, obj):
        """Icon tu 'photo' bytes (channel dict / target)."""
        photo = obj.get("photo") if isinstance(obj, dict) else None
        if photo:
            pix = QPixmap(); pix.loadFromData(photo); return QIcon(pix)
        return QIcon()

    # ------------------------------------------------------------- UI build
    def _build_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._build_accounts_tab(), "Tài khoản")
        tabs.addTab(self._build_upload_tab(), "Upload video")

    def _build_accounts_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 16, 16, 16); root.setSpacing(12)

        bar = QHBoxLayout(); bar.setSpacing(8)
        add_btn = QPushButton("Dán cookie"); add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.add_account_paste)
        file_btn = QPushButton("Thêm từ file"); file_btn.setObjectName("ghost")
        file_btn.setToolTip("Chọn 1 hoặc nhiều file cookie .json — mỗi file 1 tài khoản")
        file_btn.clicked.connect(self.add_account_files)
        check_btn = QPushButton("Kiểm tra & tải kênh"); check_btn.setObjectName("ghost")
        check_btn.clicked.connect(self.check_accounts)
        refresh_btn = QPushButton("Làm mới cookie"); refresh_btn.setObjectName("ghost")
        refresh_btn.setToolTip("Xoay vòng cookie (RotateCookies) để phiên sống lâu, tránh hết hạn giữa upload")
        refresh_btn.clicked.connect(self.refresh_cookies)
        del_btn = QPushButton("Xóa tài khoản"); del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_accounts)
        bar.addWidget(add_btn); bar.addWidget(file_btn); bar.addWidget(check_btn)
        bar.addWidget(refresh_btn); bar.addWidget(del_btn); bar.addStretch(1)
        all_btn = QPushButton("Tất cả"); all_btn.setObjectName("ghost")
        all_btn.clicked.connect(lambda: self._toggle_all(self.acc_table, self.acc_header))
        tick_btn = QPushButton("Tích dòng bôi đen"); tick_btn.setObjectName("ghost")
        tick_btn.clicked.connect(lambda: set_rows_checked(self.acc_table, selected_rows(self.acc_table), True))
        bar.addWidget(all_btn); bar.addWidget(tick_btn)
        root.addLayout(bar)

        self.acc_table, self.acc_header = make_table(
            ["", "Tài khoản", "Trạng thái", "Số kênh", "Kiểm tra lúc"])
        h = self.acc_header
        h.setSectionResizeMode(ACOL_NAME, QHeaderView.Stretch)
        h.setSectionResizeMode(ACOL_STATUS, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(ACOL_CHANNELS, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(ACOL_TIME, QHeaderView.ResizeToContents)
        self.acc_table.setIconSize(QSize(26, 26))
        root.addWidget(self.acc_table)

        hint = QLabel(
            "Mỗi cookie = 1 tài khoản. Thêm cookie → tích chọn → “Kiểm tra & tải kênh” "
            "để lấy tên + danh sách kênh. Sau đó sang tab Upload video."
        )
        hint.setObjectName("hint"); hint.setWordWrap(True)
        root.addWidget(hint)
        return page

    def _build_upload_tab(self):
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(16, 16, 16, 16); root.setSpacing(16)

        # ---- Left: thiet lap ----
        left = QVBoxLayout(); left.setSpacing(16)

        meta_card, meta = self._card("Thiết lập chung")
        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(6)
        grid.addWidget(self._field("Chế độ hiển thị"), 0, 0)
        grid.addWidget(self._field("Đối tượng"), 0, 1)
        self.privacy_combo = QComboBox()
        for label, value in PRIVACY_OPTIONS:
            self.privacy_combo.addItem(label, value)
        grid.addWidget(self.privacy_combo, 1, 0)
        self.mfk_combo = QComboBox()
        for label, value in MFK_OPTIONS:
            self.mfk_combo.addItem(label, value)
        grid.addWidget(self.mfk_combo, 1, 1)
        meta.addLayout(grid)

        meta.addWidget(self._field("Mô tả chung (khi video không có mô tả riêng)"))
        self.desc_edit = QPlainTextEdit(); self.desc_edit.setPlaceholderText("Mô tả video...")
        self.desc_edit.setFixedHeight(90)
        meta.addWidget(self.desc_edit)

        conc_row = QHBoxLayout()
        conc_row.addWidget(self._field("Số luồng upload đồng thời")); conc_row.addStretch(1)
        self.conc_spin = QSpinBox(); self.conc_spin.setRange(1, 6); self.conc_spin.setValue(1)
        self.conc_spin.setFixedWidth(70)
        conc_row.addWidget(self.conc_spin)
        meta.addLayout(conc_row)
        left.addWidget(meta_card)

        sched_card, sched = self._card("Hẹn giờ đăng")
        self.schedule_check = QCheckBox("Bật hẹn giờ (máy phải mở đến khi đăng xong)")
        self.schedule_check.toggled.connect(self._on_schedule_toggled)
        sched.addWidget(self.schedule_check)
        row_start = QHBoxLayout(); row_start.addWidget(self._field("Bắt đầu"))
        self.start_dt = QDateTimeEdit(); self.start_dt.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.start_dt.setCalendarPopup(True)
        self.start_dt.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.start_dt.setEnabled(False)
        row_start.addWidget(self.start_dt, 1); sched.addLayout(row_start)
        row_gap = QHBoxLayout(); row_gap.addWidget(self._field("Mỗi video cách nhau"))
        self.gap_spin = QSpinBox(); self.gap_spin.setRange(0, 100000); self.gap_spin.setValue(360)
        self.gap_spin.setSuffix(" phút"); self.gap_spin.setEnabled(False)
        row_gap.addWidget(self.gap_spin, 1); sched.addLayout(row_gap)
        left.addWidget(sched_card)
        left.addStretch(1)

        self.start_btn = QPushButton("Bắt đầu upload"); self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start_upload)
        left.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Dừng"); self.stop_btn.setObjectName("danger")
        self.stop_btn.clicked.connect(self.stop_upload); self.stop_btn.setEnabled(False)
        left.addWidget(self.stop_btn)
        self.overall = QProgressBar(); self.overall.setFormat("%v / %m video")
        self.overall.setMaximum(1); self.overall.setValue(0)
        left.addWidget(self.overall)

        left_widget = QWidget(); left_widget.setLayout(left); left_widget.setFixedWidth(360)
        root.addWidget(left_widget)

        # ---- Right: bang KENH (moi dong 1 kenh, gan nhieu video) + log ----
        right = QSplitter(Qt.Vertical)
        table_card, tl = self._card("Kênh & video")

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        assign_sel = QPushButton("Gán video → đã chọn"); assign_sel.setObjectName("primary")
        assign_sel.setToolTip("Chọn video, gán cho các kênh đang tích/bôi đen")
        assign_sel.clicked.connect(lambda: self.assign_videos(False))
        assign_all = QPushButton("Gán video → tất cả"); assign_all.setObjectName("ghost")
        assign_all.setToolTip("Chọn video, gán cho TẤT CẢ kênh")
        assign_all.clicked.connect(lambda: self.assign_videos(True))
        title_sel = QPushButton("Tiêu đề → đã chọn"); title_sel.setObjectName("ghost")
        title_sel.setToolTip("Đặt tiêu đề hàng loạt cho video của các kênh đã chọn")
        title_sel.clicked.connect(lambda: self.assign_title(False))
        title_all = QPushButton("Tiêu đề → tất cả"); title_all.setObjectName("ghost")
        title_all.setToolTip("Đặt tiêu đề hàng loạt cho video của TẤT CẢ kênh")
        title_all.clicked.connect(lambda: self.assign_title(True))
        desc_sel = QPushButton("Mô tả → đã chọn"); desc_sel.setObjectName("ghost")
        desc_sel.setToolTip("Gán mô tả cho video của các kênh đã chọn")
        desc_sel.clicked.connect(lambda: self.assign_desc(False))
        desc_all = QPushButton("Mô tả → tất cả"); desc_all.setObjectName("ghost")
        desc_all.setToolTip("Gán mô tả cho video của TẤT CẢ kênh")
        desc_all.clicked.connect(lambda: self.assign_desc(True))
        manage_btn = QPushButton("Quản lý video…"); manage_btn.setObjectName("ghost")
        manage_btn.clicked.connect(self.manage_videos)
        clearv_btn = QPushButton("Xóa video"); clearv_btn.setObjectName("ghost")
        clearv_btn.setToolTip("Bỏ video khỏi các kênh đã chọn")
        clearv_btn.clicked.connect(self.clear_videos)
        for b in (assign_sel, assign_all, title_sel, title_all, desc_sel, desc_all,
                  manage_btn, clearv_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        all_btn = QPushButton("Tất cả"); all_btn.setObjectName("ghost")
        all_btn.clicked.connect(lambda: self._toggle_all(self.table, self._vheader))
        tick_btn = QPushButton("Tích dòng bôi đen"); tick_btn.setObjectName("ghost")
        tick_btn.clicked.connect(lambda: set_rows_checked(self.table, selected_rows(self.table), True))
        untick_btn = QPushButton("Bỏ tích"); untick_btn.setObjectName("ghost")
        untick_btn.clicked.connect(lambda: set_rows_checked(self.table, list(range(self.table.rowCount())), False))
        btn_row.addWidget(all_btn); btn_row.addWidget(tick_btn); btn_row.addWidget(untick_btn)
        tl.addLayout(btn_row)

        self.table, self._vheader = make_table(
            ["", "Tài khoản", "Kênh", "Video", "Trạng thái"])
        self.table.setIconSize(QSize(24, 24))
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        vh = self._vheader
        vh.setSectionResizeMode(UCOL_ACCOUNT, QHeaderView.Interactive)
        vh.setSectionResizeMode(UCOL_CHANNEL, QHeaderView.Stretch)
        vh.setSectionResizeMode(UCOL_VIDEOS, QHeaderView.Stretch)
        vh.setSectionResizeMode(UCOL_STATUS, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(UCOL_ACCOUNT, 180)
        tl.addWidget(self.table)
        thint = QLabel("Mỗi dòng = 1 kênh. Tích chọn kênh → “Gán video” để thêm video. "
                       "Nháy đúp một kênh để quản lý danh sách video của kênh đó.")
        thint.setObjectName("hint"); thint.setWordWrap(True)
        tl.addWidget(thint)
        right.addWidget(table_card)

        log_card, ll = self._card("Nhật ký")
        self.log_view = QPlainTextEdit(); self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        right.addWidget(log_card)
        right.setSizes([520, 220])
        root.addWidget(right, 1)
        return page

    def _toggle_all(self, table, header):
        want = not checked_rows(table)
        set_rows_checked(table, list(range(table.rowCount())), want)
        header.set_checked(want)

    def _on_schedule_toggled(self, *_):
        on = self.schedule_check.isChecked()
        self.start_dt.setEnabled(on); self.gap_spin.setEnabled(on)
        self.conc_spin.setEnabled(not on)
        self.start_btn.setText("Đặt lịch upload" if on else "Bắt đầu upload")

    # ------------------------------------------------------------- accounts
    def _refresh_accounts_table(self):
        self.acc_table.setRowCount(0)
        for a in self.store.accounts:
            row = self.acc_table.rowCount()
            self.acc_table.insertRow(row)
            add_check_item(self.acc_table, row)
            name_item = QTableWidgetItem(a.name)
            name_item.setData(Qt.UserRole, a.id)
            # icon kenh chinh neu co
            main = next((c for c in a.channels if c.get("is_selected")), None) or \
                (a.channels[0] if a.channels else None)
            if main:
                key = f"{a.id}|{main.get('page_id') or ''}"
                photo = self._photo_cache.get(key) or main.get("photo")
                if photo:
                    pix = QPixmap(); pix.loadFromData(photo); name_item.setIcon(QIcon(pix))
            self.acc_table.setItem(row, ACOL_NAME, name_item)
            self._set_acc_status(row, a.status)
            self.acc_table.setItem(row, ACOL_CHANNELS, QTableWidgetItem(str(a.channel_count)))
            self.acc_table.setItem(row, ACOL_TIME, QTableWidgetItem(a.last_check or "—"))

    _STATUS_TEXT = {acct.STATUS_ALIVE: "Sống", acct.STATUS_DEAD: "Chết",
                    acct.STATUS_CHECKING: "Đang kiểm tra…", acct.STATUS_UNKNOWN: "Chưa kiểm tra"}
    _STATUS_COLOR = {acct.STATUS_ALIVE: C_OK, acct.STATUS_DEAD: C_ERR,
                     acct.STATUS_CHECKING: C_WARN, acct.STATUS_UNKNOWN: C_MUTED}

    def _set_acc_status(self, row, status):
        it = QTableWidgetItem(self._STATUS_TEXT.get(status, status))
        it.setForeground(QColor(self._STATUS_COLOR.get(status, C_MUTED)))
        self.acc_table.setItem(row, ACOL_STATUS, it)

    def _acc_target_rows(self):
        return target_rows(self.acc_table)

    def _account_at(self, row):
        it = self.acc_table.item(row, ACOL_NAME)
        acc_id = it.data(Qt.UserRole) if it else None
        return next((a for a in self.store.accounts if a.id == acc_id), None)

    def add_account_paste(self):
        dlg = CookiePasteDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            account, created = self.store.add_cookies(dlg.cookies)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thêm được: {e}"); return
        self._refresh_accounts_table()
        self.log("✓ Đã thêm tài khoản mới." if created else "↻ Đã cập nhật cookie tài khoản đã có.")

    def add_account_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file cookie", "", "Cookie (*.json *.txt);;Tất cả (*)")
        added = 0
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    _, created = self.store.add_from_text(f.read())
                added += created
            except Exception as e:
                self.log(f"✗ {os.path.basename(p)}: {e}")
        if added or paths:
            self._refresh_accounts_table()
            self.log(f"✓ Đã thêm {added} tài khoản từ file.")

    def check_accounts(self):
        if self.check_worker and self.check_worker.isRunning():
            return
        rows = self._acc_target_rows()
        accounts = [self._account_at(r) for r in rows]
        accounts = [a for a in accounts if a]
        if not accounts:
            QMessageBox.information(self, "Chưa chọn", "Hãy tích hoặc bôi đen tài khoản cần kiểm tra.")
            return
        self.log(f"🔑 Kiểm tra {len(accounts)} tài khoản...")
        self.check_worker = AccountCheckWorker(accounts)
        self.check_worker.acc_status.connect(self._on_acc_status)
        self.check_worker.acc_done.connect(self._on_acc_done)
        self.check_worker.acc_failed.connect(self._on_acc_failed)
        self.check_worker.finished_all.connect(self._on_check_finished)
        self.check_worker.start()

    def refresh_cookies(self):
        if self.refresh_worker and self.refresh_worker.isRunning():
            return
        rows = self._acc_target_rows()
        accounts = [a for a in (self._account_at(r) for r in rows) if a]
        if not accounts:
            QMessageBox.information(self, "Chưa chọn",
                                    "Hãy tích hoặc bôi đen tài khoản cần làm mới cookie.")
            return
        self.log(f"🔄 Làm mới cookie {len(accounts)} tài khoản...")
        self.refresh_worker = RefreshCookieWorker(accounts)
        self.refresh_worker.acc_status.connect(self._on_acc_status)
        self.refresh_worker.acc_result.connect(self._on_refresh_result)
        self.refresh_worker.finished_all.connect(self._on_refresh_finished)
        self.refresh_worker.start()

    def _on_refresh_result(self, acc_id, ok, message):
        account = next((a for a in self.store.accounts if a.id == acc_id), None)
        if account:
            import time as _t
            account.last_check = _t.strftime("%d/%m %H:%M")
            if not ok:
                account.status = acct.STATUS_DEAD
            self.store.save()
        self._refresh_accounts_table()
        name = account.name if account else acc_id
        self.log(f"   {'✓' if ok else '✗'} {name}: {message}")

    def _on_refresh_finished(self, ok, fail):
        self.log(f"🏁 Làm mới cookie xong: {ok} thành công, {fail} lỗi.")

    def _row_of_account(self, acc_id):
        for r in range(self.acc_table.rowCount()):
            it = self.acc_table.item(r, ACOL_NAME)
            if it and it.data(Qt.UserRole) == acc_id:
                return r
        return -1

    def _on_acc_status(self, acc_id, text):
        r = self._row_of_account(acc_id)
        if r >= 0:
            self._set_acc_status(r, acct.STATUS_CHECKING)

    def _on_acc_done(self, acc_id, result):
        account = next((a for a in self.store.accounts if a.id == acc_id), None)
        if not account:
            return
        # cache anh dai dien
        for ch in result["channels"]:
            key = f"{acc_id}|{ch.get('page_id') or ''}"
            if ch.get("photo"):
                self._photo_cache[key] = ch["photo"]
        self.store.set_result(account, name=result["name"],
                              channels=result["channels"], status=result["status"])
        self._refresh_accounts_table()
        self.log(f"   ✓ {result['name']} — {len(result['channels'])} kênh")

    def _on_acc_failed(self, acc_id, err):
        account = next((a for a in self.store.accounts if a.id == acc_id), None)
        if account:
            self.store.set_result(account, status=acct.STATUS_DEAD)
        self._refresh_accounts_table()
        self.log(f"   ✗ Tài khoản lỗi: {err}")

    def _on_check_finished(self):
        self.refresh_targets()
        self.log("🏁 Kiểm tra xong.")

    def delete_accounts(self):
        rows = self._acc_target_rows()
        accounts = [self._account_at(r) for r in rows]
        accounts = [a for a in accounts if a]
        if not accounts:
            QMessageBox.information(self, "Chưa chọn", "Hãy tích hoặc bôi đen tài khoản cần xóa.")
            return
        if QMessageBox.question(self, "Xóa", f"Xóa {len(accounts)} tài khoản đã chọn?") \
                != QMessageBox.Yes:
            return
        for a in accounts:
            self.store.remove(a)
        self._refresh_accounts_table()
        self.refresh_targets()
        self.log(f"Đã xóa {len(accounts)} tài khoản.")

    # ------------------------------------------------------------- targets
    def refresh_targets(self):
        """Danh sach kenh toan cuc (account ALIVE co kenh) + dung lai bang kenh,
        GIU nguyen video da gan theo key kenh."""
        alive = [a for a in self.store.accounts
                 if a.status == acct.STATUS_ALIVE and a.channels]
        multi = len(alive) > 1
        self.targets = []
        for a in alive:
            for ch in a.channels:
                key = f"{a.id}|{ch.get('page_id') or ''}"
                cname = ch.get("name") or "(kênh)"
                label = f"{cname}  ·  {a.name}" if multi else cname
                self.targets.append({
                    "key": key, "account_id": a.id, "account_name": a.name,
                    "cookie_path": a.cookie_path, "page_id": ch.get("page_id"),
                    "name": cname, "handle": ch.get("handle", ""),
                    "photo": self._photo_cache.get(key) or ch.get("photo"),
                    "label": label,
                })
        prev = {}
        for row in range(self.table.rowCount()):
            it = self.table.item(row, UCOL_CHANNEL)
            if it and it.data(ROLE_TARGET):
                prev[it.data(ROLE_TARGET)] = it.data(ROLE_VIDEOS) or []
        self._rebuild_channel_table(prev)

    def _target_by_key(self, key):
        return next((t for t in self.targets if t["key"] == key), None)

    def _rebuild_channel_table(self, prev_videos=None):
        prev_videos = prev_videos or {}
        self.table.setRowCount(0)
        for t in self.targets:
            row = self.table.rowCount(); self.table.insertRow(row)
            add_check_item(self.table, row)
            self.table.setItem(row, UCOL_ACCOUNT, QTableWidgetItem(t["account_name"]))
            ch_item = QTableWidgetItem(t["name"])
            ch_item.setIcon(self._icon_for(t))
            ch_item.setData(ROLE_TARGET, t["key"])
            ch_item.setData(ROLE_VIDEOS, prev_videos.get(t["key"], []))
            self.table.setItem(row, UCOL_CHANNEL, ch_item)
            self.table.setItem(row, UCOL_VIDEOS, QTableWidgetItem())
            st = QTableWidgetItem("—"); st.setForeground(QColor(C_MUTED))
            self.table.setItem(row, UCOL_STATUS, st)
            self._update_video_cell(row)

    def _videos_of(self, row):
        it = self.table.item(row, UCOL_CHANNEL)
        return (it.data(ROLE_VIDEOS) or []) if it else []

    def _set_videos(self, row, videos):
        it = self.table.item(row, UCOL_CHANNEL)
        if it is not None:
            it.setData(ROLE_VIDEOS, videos)
        self._update_video_cell(row)

    def _update_video_cell(self, row):
        videos = self._videos_of(row)
        cell = self.table.item(row, UCOL_VIDEOS)
        if cell is None:
            cell = QTableWidgetItem(); self.table.setItem(row, UCOL_VIDEOS, cell)
        if not videos:
            cell.setText("—"); cell.setForeground(QColor(C_MUTED))
        elif len(videos) == 1:
            cell.setText(f"1 video: {videos[0]['title']}"); cell.setForeground(QColor(C_TEXT))
        else:
            cell.setText(f"{len(videos)} video"); cell.setForeground(QColor(C_TEXT))

    def _target_channel_rows(self, all_rows):
        if all_rows:
            return list(range(self.table.rowCount()))
        return target_rows(self.table)

    def assign_videos(self, all_rows):
        if not self.targets:
            QMessageBox.information(self, "Chưa có kênh",
                                    "Hãy sang tab Tài khoản, kiểm tra & tải kênh trước.")
            return
        rows = self._target_channel_rows(all_rows)
        if not rows:
            QMessageBox.information(self, "Chưa chọn kênh",
                                    "Hãy tích ô hoặc bôi đen các kênh cần gán video.")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn video", "", VIDEO_EXTS)
        if not paths:
            return
        for row in rows:
            videos = [{"path": p, "title": os.path.splitext(os.path.basename(p))[0],
                       "desc": "", "privacy": None, "mfk": None} for p in paths]
            self._set_videos(row, videos)
        self.log(f"Đã gán {len(paths)} video cho {len(rows)} kênh.")

    def clear_videos(self):
        rows = target_rows(self.table)
        if not rows:
            QMessageBox.information(self, "Chưa chọn kênh", "Hãy tích hoặc bôi đen kênh.")
            return
        for row in rows:
            self._set_videos(row, [])
        self.log(f"Đã xóa video khỏi {len(rows)} kênh.")

    def assign_title(self, all_rows):
        """Dat TIEU DE hang loat cho video cac kenh muc tieu. {n} danh so trong
        tung kenh, {name} = ten file."""
        rows = self._target_channel_rows(all_rows)
        if not rows:
            QMessageBox.information(self, "Chưa chọn kênh",
                                    "Hãy tích ô hoặc bôi đen các kênh cần đặt tiêu đề.")
            return
        sub = ("Áp dụng cho video của TẤT CẢ kênh." if all_rows
               else f"Áp dụng cho video của {len(rows)} kênh đã chọn.")
        dlg = TitlePatternDialog(self, subtitle=sub)
        if dlg.exec() != QDialog.Accepted:
            return
        pat = dlg.pattern
        n_ch = n_vid = 0
        for row in rows:
            videos = self._videos_of(row)
            if not videos:
                continue
            for n, v in enumerate(videos, 1):
                name = os.path.splitext(os.path.basename(v["path"]))[0]
                v["title"] = pat.replace("{n}", str(n)).replace("{name}", name)
            self._set_videos(row, videos)
            n_ch += 1; n_vid += len(videos)
        if n_vid:
            self.log(f"Đã đặt tiêu đề cho {n_vid} video ({n_ch} kênh).")
        else:
            QMessageBox.information(self, "Chưa có video",
                                    "Các kênh đã chọn chưa có video. Hãy 'Gán video' trước.")

    def assign_desc(self, all_rows):
        """Gan MO TA hang loat cho toan bo video cua cac kenh muc tieu."""
        rows = self._target_channel_rows(all_rows)
        if not rows:
            QMessageBox.information(self, "Chưa chọn kênh",
                                    "Hãy tích ô hoặc bôi đen các kênh cần gán mô tả.")
            return
        sub = ("Áp dụng cho video của TẤT CẢ kênh." if all_rows
               else f"Áp dụng cho video của {len(rows)} kênh đã chọn.")
        dlg = DescriptionDialog(self, subtitle=sub)
        if dlg.exec() != QDialog.Accepted:
            return
        n_ch = n_vid = 0
        for row in rows:
            videos = self._videos_of(row)
            if not videos:
                continue
            for v in videos:
                v["desc"] = dlg.text
            self._set_videos(row, videos)
            n_ch += 1; n_vid += len(videos)
        if n_vid:
            self.log(f"Đã gán mô tả cho {n_vid} video ({n_ch} kênh).")
        else:
            QMessageBox.information(self, "Chưa có video",
                                    "Các kênh đã chọn chưa có video. Hãy 'Gán video' trước.")

    def _on_cell_double_clicked(self, row, col):
        if col != UCOL_CHECK:
            self._manage_row(row)

    def manage_videos(self):
        rows = selected_rows(self.table) or checked_rows(self.table)
        if not rows:
            QMessageBox.information(self, "Chưa chọn", "Hãy chọn 1 kênh để quản lý video.")
            return
        self._manage_row(rows[0])

    def _manage_row(self, row):
        it = self.table.item(row, UCOL_CHANNEL)
        if it is None:
            return
        dlg = ChannelVideosDialog(self, channel_label=it.text(),
                                  videos=list(self._videos_of(row)))
        if dlg.exec() == QDialog.Accepted:
            self._set_videos(row, dlg.result_videos)

    # ------------------------------------------------------------- upload
    def start_upload(self):
        if self.upload_worker and self.upload_worker.isRunning():
            return
        if not self.targets:
            QMessageBox.warning(self, "Chưa có kênh",
                                "Hãy sang tab Tài khoản, thêm cookie & tải kênh trước.")
            return
        g_privacy = self.privacy_combo.currentData()
        g_mfk = self.mfk_combo.currentData()
        global_desc = self.desc_edit.toPlainText().strip()

        jobs = []
        self._row_total = {}; self._row_done = {}; self._row_fail = {}
        channels_used = 0; accounts_used = set()
        for row in range(self.table.rowCount()):
            videos = self._videos_of(row)
            if not videos:
                continue
            it = self.table.item(row, UCOL_CHANNEL)
            t = self._target_by_key(it.data(ROLE_TARGET))
            if not t:
                continue
            channels_used += 1
            accounts_used.add(t["cookie_path"])
            self._row_total[row] = len(videos)
            self._row_done[row] = 0; self._row_fail[row] = 0
            for v in videos:
                jobs.append({
                    "row": row, "path": v["path"], "title": v["title"],
                    "description": v["desc"] or global_desc,
                    "privacy": v["privacy"] if v["privacy"] is not None else g_privacy,
                    "mfk": v["mfk"] if v["mfk"] is not None else g_mfk,
                    "cookie_path": t["cookie_path"], "page_id": t["page_id"],
                    "channel_label": t["label"],
                })
        if not jobs:
            QMessageBox.information(self, "Chưa có video",
                                    "Chưa kênh nào được gán video. Hãy 'Gán video' trước.")
            return

        concurrency = self.conc_spin.value()
        schedule = None
        if self.schedule_check.isChecked():
            start_ts = self.start_dt.dateTime().toSecsSinceEpoch()
            gap = self.gap_spin.value() * 60
            if start_ts <= time.time() - 60:
                if QMessageBox.question(self, "Giờ ở quá khứ",
                                        "Thời điểm bắt đầu đã qua. Video đầu upload ngay. Tiếp tục?") \
                        != QMessageBox.Yes:
                    return
            schedule = {"start": start_ts, "gap": gap}
            concurrency = 1

        self.log(f"▶ {'Hẹn giờ' if schedule else 'Bắt đầu'} upload {len(jobs)} video "
                 f"→ {channels_used} kênh / {len(accounts_used)} tài khoản")
        self.log(f"   Hiển thị: {self.privacy_combo.currentText()} · "
                 f"Đối tượng: {self.mfk_combo.currentText()}")

        for row in self._row_total:
            self._set_row_status(row, f"0/{self._row_total[row]}", C_WARN)
        self.overall.setMaximum(len(jobs)); self.overall.setValue(0)
        self._done_count = 0
        self.upload_worker = UploadWorker(jobs, schedule, concurrency)
        self.upload_worker.job_status.connect(self.on_job_status)
        self.upload_worker.job_progress.connect(self.on_job_progress)
        self.upload_worker.job_done.connect(self.on_job_done)
        self.upload_worker.job_failed.connect(self.on_job_failed)
        self.upload_worker.log.connect(self.log)
        self.upload_worker.finished_all.connect(self.on_all_finished)
        self.upload_worker.start()
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)

    def stop_upload(self):
        if self.upload_worker and self.upload_worker.isRunning():
            self.upload_worker.stop()
            self.log("⏹ Đang dừng (chờ xong chunk hiện tại)...")
            self.stop_btn.setEnabled(False)

    def _set_row_status(self, row, text, color=None):
        it = self.table.item(row, UCOL_STATUS)
        if it is None:
            return
        it.setText(text)
        it.setForeground(QColor(color) if color else QColor(C_TEXT))

    def _refresh_row_status(self, row):
        done = self._row_done.get(row, 0); fail = self._row_fail.get(row, 0)
        total = self._row_total.get(row, 0)
        txt = f"{done}/{total}"
        if fail:
            txt += f"  ({fail} lỗi)"
        if done + fail >= total:
            color = C_OK if fail == 0 else (C_ERR if done == 0 else C_WARN)
        else:
            color = C_WARN
        self._set_row_status(row, txt, color)

    def on_job_status(self, row, text):
        pass

    def on_job_progress(self, row, pct):
        done = self._row_done.get(row, 0); total = self._row_total.get(row, 0)
        self._set_row_status(row, f"{done}/{total}  ({pct}%)", C_WARN)

    def on_job_done(self, row, video_id):
        self._row_done[row] = self._row_done.get(row, 0) + 1
        self._refresh_row_status(row)
        self._done_count += 1; self.overall.setValue(self._done_count)

    def on_job_failed(self, row, error):
        self._row_fail[row] = self._row_fail.get(row, 0) + 1
        self._refresh_row_status(row)
        self._done_count += 1; self.overall.setValue(self._done_count)

    def on_all_finished(self, ok, failed):
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.log(f"■ Hoàn tất: {ok} thành công, {failed} lỗi.")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

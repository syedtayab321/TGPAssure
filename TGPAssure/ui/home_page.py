from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget
from ui.icons import get_icon

class HomePage(QWidget):
    new_project_requested=Signal(); open_project_requested=Signal(); import_requested=Signal(); magnetic_requested=Signal(); gravity_requested=Signal(); module_requested=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.setObjectName("homePage")
        root=QVBoxLayout(self); root.setContentsMargins(18,16,18,16); root.setSpacing(12)
        banner=QFrame(); banner.setObjectName("homeBanner"); bl=QHBoxLayout(banner); bl.setContentsMargins(24,16,24,16)
        text=QVBoxLayout(); h=QLabel("TGPAssure"); h.setObjectName("homeHeading"); s=QLabel("Integrated Geophysical QA/QC • Processing • Visualization • Decision Support"); s.setObjectName("homeSubheading"); text.addWidget(h); text.addWidget(s); bl.addLayout(text,1)
        for lab,sig,icon in (("New Project",self.new_project_requested,"document-new"),("Open Project",self.open_project_requested,"document-open"),("Import Data",self.import_requested,"document-import")):
            b=QToolButton(); b.setObjectName("homeBannerAction"); b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); b.setText(lab); b.setIcon(get_icon(icon,"#FFFFFF",22)); b.setIconSize(QSize(22,22)); b.clicked.connect(sig.emit); bl.addWidget(b)
        root.addWidget(banner)
        title=QLabel("Core Workspaces"); title.setObjectName("homeSectionTitle"); root.addWidget(title)
        grid=QGridLayout(); grid.setSpacing(10)
        cards=[
            ("SEG-D Viewer","Field-record viewing, trace inspection, spread QC and acquisition tools.","segd","waveform","#126B8D"),
            ("428 Header Scanner","Batch SEG-D/Sercel header audit, source/timebreak and trace-extension summary.","segd_scanner","view-list-details","#0E7490"),
            ("Uphole","SEG-2/OYO import, file-depth assignment, first-break picks and velocity curves.","uphole","seg-2","#6B5BA7"),
            ("Receiver SMT QC","SMT-200/300 geophone tests, limits, failures, serial history and export.","receiver_qc","dialog-ok-apply","#2F8A76"),
            ("SEG-Y QC & Viewer","Standards-aware headers, trace QC, seismic display and frequency analysis.","segy_viewer","office-chart-line","#315E9C"),
            ("SEG-Y → SEG-D","Controlled format conversion with timing, resampling and output validation.","converter","document-export","#7656A5"),
            ("Vibroseis","Sweep design, VAPS/H26 field QC, pilot correlation, ground-force and productivity.","vibroseis","media-playback-start","#B26A21"),
            ("2D / 3D Seismic","Sections, volume/slice views, geometry map, picking and interpretation support.","visualization","applications-graphics","#0F7A72"),
            ("Magnetic QC","Diurnal/base workflows, line QC, leveling, gridding, maps and profiles.","magnetic","office-chart-line","#5E4D91"),
            ("Gravity QC","Standard gravity reduction, drift/tide corrections, anomaly QC and mapping.","gravity","view-statistics","#356859"),
            ("Electrical QC","ERT/IP/VES QC, geometry, reciprocity, pseudosections and reporting.","electrical","network-wired","#9B4D58"),
        ]
        for i,(name,desc,module,icon,color) in enumerate(cards):
            card=QToolButton(); card.setObjectName("homeFeatureCard"); card.setToolButtonStyle(Qt.ToolButtonTextUnderIcon); card.setIcon(get_icon(icon,color,38)); card.setIconSize(QSize(38,38)); card.setText(name+"\n"+desc); card.setToolTip(desc); card.setMinimumHeight(118); card.setCursor(Qt.PointingHandCursor); card.clicked.connect(lambda checked=False,m=module:self.module_requested.emit(m)); grid.addWidget(card,i//4,i%4)
        root.addLayout(grid)
        strip=QFrame(); strip.setObjectName("homeWorkflowStrip"); sl=QHBoxLayout(strip); sl.setContentsMargins(16,10,16,10)
        for i,t in enumerate(("1  Import & Index","2  Validate & QC","3  Process","4  Visualize & Interpret","5  Report & Audit")):
            l=QLabel(t); l.setObjectName("homeWorkflowStep"); l.setAlignment(Qt.AlignCenter); sl.addWidget(l,1)
        root.addWidget(strip); root.addStretch(1)

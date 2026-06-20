from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox,
)


HELP_HTML = """
<style>
    h2 { margin: 0 0 4px 0; }
    h3 { margin: 16px 0 4px 0; }
    p  { margin: 4px 0 8px 0; line-height: 140%; }
    ul { margin: 4px 0 8px 0; }
    li { margin: 4px 0; line-height: 140%; }
    .dot { font-weight: bold; }
</style>

<h2>How to use Light Show Tool</h2>
<p>Copy, rename, and wipe many USB drives at once.</p>

<h3>1 &nbsp;&middot;&nbsp; Pick your drives</h3>
<p>Connected USB drives appear in the list on the left and update automatically
as you plug them in or pull them out. Tick the ones you want to act on, or use
<b>All</b> / <b>None</b> to select in bulk.</p>
<p>The colored dot shows each drive's state:</p>
<ul>
    <li><span class="dot" style="color:#1565c0;">&#9679;</span> &nbsp;Ready &mdash; mounted, not yet copied</li>
    <li><span class="dot" style="color:#2e7d32;">&#9679;</span> &nbsp;Copied successfully</li>
    <li><span class="dot" style="color:#ef6c00;">&#9679;</span> &nbsp;Copy failed</li>
    <li><span class="dot" style="color:#c62828;">&#9679;</span> &nbsp;Unmounted &mdash; use <b>Mount All</b> before selecting it</li>
</ul>

<h3>2 &nbsp;&middot;&nbsp; Choose a mode</h3>
<p>Use the buttons at the top left to switch modes:</p>
<ul>
    <li><b>Copy</b> &mdash; Drag <code>.fseq</code> and audio files into a group;
        matching pairs (one &ldquo;show&rdquo;) are detected automatically. Choose
        how to handle existing files (don't erase / delete / full format),
        optionally tick <b>Eject when done</b>, then copy to all selected drives.
        Mid&#8209;run you can <b>Skip</b> a problem drive or <b>Cancel</b> everything.</li>
    <li><b>Rename</b> &mdash; Give all selected drives the same FAT32 label
        (up to 11 characters).</li>
    <li><b>Wipe</b> &mdash; Erase and reformat selected drives as FAT32.
        This destroys all data and requires confirmation.</li>
</ul>

<h3>Good to know</h3>
<ul>
    <li>Your groups and settings are saved automatically and restored next launch.</li>
    <li>If a drive errors out, check <code>light_show_tool.log</code> in the app folder.</li>
</ul>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.setMinimumSize(520, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(HELP_HTML)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

# -*- coding: utf-8 -*-
"""Stand-alone help window for the GitHub Plugin Sync plugin."""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
)


def tr(message: str) -> str:
    return QCoreApplication.translate("GitHubPluginSync", message)


_HELP_HTML = """
<h1>GitHub Plugin Sync &ndash; Help</h1>

<h2>Overview</h2>
<p><b>GitHub Plugin Sync</b> is a QGIS developer plugin that streamlines
the testing and deployment of other QGIS plugins. It downloads any
branch of any GitHub repository (public or private), validates the
incoming <code>metadata.txt</code>, and either replaces an installed
plugin or creates a new plugin folder inside the active QGIS user
profile. The unload, swap and reload sequence is performed
automatically wherever possible, and a timestamped backup of the
previous plugin folder is written before any destructive change. The
plugin is intended for developers who frequently switch between
different forks, branches or pull requests of a plugin without leaving
QGIS.</p>

<h2>Launching the plugin</h2>
<p>After enabling <i>GitHub Plugin Sync</i> in the QGIS Plugin Manager,
the plugin adds an entry to the <i>Plugins</i> menu and a button to the
toolbar. Clicking either opens the central <i>Sync plugin from
GitHub</i> dialog, which is the entry point for every operation
described below.</p>

<h2>The &ldquo;Installed plugin&rdquo; group</h2>
<p>This group selects the target of the operation &ndash; the plugin
folder that will be created, replaced or installed.</p>
<ul>
  <li><b>Target plugin</b> &ndash; an editable combo box. The drop-down
      lists all plugin folders currently present in your QGIS Python
      plugins directory. Choosing one prepares an in-place replacement.
      To install a plugin that is <i>not</i> yet present, type a fresh
      folder name into the field. Names may contain letters, digits,
      underscores, dots and dashes; spaces and slashes are rejected.</li>
  <li><b>Install hint</b> &ndash; an inline message below the combo.
      When the typed name does not match any installed plugin, the hint
      turns green and announces that a new folder will be created. If
      the name is invalid, the hint turns red and explains what is
      wrong.</li>
  <li><b>Plugins directory</b> &ndash; the absolute path of the QGIS
      user-profile plugins folder that will be modified. It is
      read-only and shown so that you always know where the changes
      will take place.</li>
</ul>

<h2>The &ldquo;GitHub source&rdquo; group</h2>
<p>Here you describe where the plugin code should come from.</p>
<ul>
  <li><b>Repository</b> &ndash; the GitHub repository in any of the
      common forms: <code>owner/name</code>,
      <code>https://github.com/owner/name</code>, or an SSH URL. The
      plugin parses the value when needed; an invalid string raises a
      clear error.</li>
  <li><b>Credential profile</b> &ndash; picks which GitHub credentials
      to use. The default <code>&lt;anonymous / public&gt;</code> entry
      sends unauthenticated requests, which is fine for public
      repositories. To access private repositories, select a saved
      profile. Click <b>Manage&hellip;</b> to open the <i>GitHub
      credentials</i> dialog where profiles can be created, edited and
      deleted.</li>
  <li><b>Branch</b> &ndash; an editable combo box that holds the branch
      name. Type one directly or click <b>Load branches</b> to query
      the GitHub API. The dialog then preselects <code>main</code>,
      falling back to <code>master</code> when neither is currently
      entered.</li>
  <li><b>Sub-directory</b> &ndash; the path inside the repository where
      the plugin lives. Many repositories ship a plugin in a sub-folder
      rather than at the root; leave the field empty to use the
      repository root. Click <b>Detect</b> to scan the chosen branch
      for every folder containing a <code>metadata.txt</code> and
      select the first candidate automatically. Detected paths are
      added to the drop-down so you can switch quickly between several
      plugins inside a monorepo.</li>
  <li><b>Remember this repository for the selected plugin</b> &ndash;
      when checked, the chosen repository and credential profile are
      stored as a mapping for the target plugin. The next time you
      select the same plugin, the fields are pre-filled
      automatically.</li>
</ul>

<h2>Status log and progress bar</h2>
<p>The large read-only text area below the form is the status log.
Every action &ndash; successful or not &ndash; appends a line so you
can follow what the plugin is doing. The animated progress bar appears
underneath the log whenever a network or file operation is running,
and is hidden again when the worker thread finishes.</p>

<h2>Action buttons</h2>
<p>The buttons at the bottom of the dialog drive the workflow.</p>
<ul>
  <li><b>Help</b> &ndash; opens this window. The help text is
      non-modal, so it can remain open beside the main dialog.</li>
  <li><b>Cleanup plugin data&hellip;</b> &ndash; opens the <i>Clean up
      plugin data</i> dialog where you can review and delete data
      stored by this plugin in your QGIS profile.</li>
  <li><b>Restore backup &hellip;</b> &ndash; opens the <i>Restore plugin
      from backup</i> dialog. All plugins that have at least one backup
      are listed; selecting a plugin shows its snapshots in chronological
      order (newest first). The current plugin files are backed up
      automatically before the restore so the operation is fully
      reversible.</li>
  <li><b>Check metadata</b> &ndash; downloads the
      <code>metadata.txt</code> of the current selection and compares
      it with the installed copy (when present). The result is written
      to the status log: errors are flagged with <code>[ERROR]</code>,
      warnings with <code>[WARNING]</code>, and informational lines
      with <code>[INFO]</code>. Typical findings include missing
      required fields, a <code>name</code> that does not match the
      target folder, or a <code>qgisMinimumVersion</code> higher than
      your QGIS build.</li>
  <li><b>&#x21AA; Replace plugin</b> &ndash; the main action. The
      plugin re-runs the metadata check, asks for confirmation,
      downloads the repository tarball, unloads the existing plugin,
      moves its files to a timestamped backup folder, copies the new
      files into place, and triggers a hot reload through QGIS&rsquo;s
      plugin manager. Errors during loading prompt for a manual QGIS
      restart. For a fresh install, the new folder is created and
      activated immediately.</li>
  <li><b>Close</b> &ndash; dismisses the dialog. Any temporary download
      directory is removed automatically.</li>
</ul>

<h2>The &ldquo;GitHub credentials&rdquo; dialog</h2>
<p>Tokens are stored in QGIS&rsquo;s authentication database, protected
by the QGIS master password. If the authentication subsystem is
unavailable, a warning is shown and saving is disabled.</p>
<ul>
  <li><b>Profile</b> &ndash; choose <code>&lt;new profile&gt;</code> to
      create a new entry or pick an existing one to edit.</li>
  <li><b>Delete</b> &ndash; removes the selected profile.</li>
  <li><b>Name</b> &ndash; the identifier of the profile (e.g.
      <code>personal</code> or <code>work</code>). The name is fixed
      once saved.</li>
  <li><b>Username</b> &ndash; your GitHub user name. Optional; the
      GitHub API does not require it when a token is present.</li>
  <li><b>Token</b> &ndash; a GitHub Personal Access Token. The
      <code>repo</code> scope is sufficient for read access to private
      repositories.</li>
  <li><b>Save</b> &ndash; persists the profile. The token field is
      cleared after a successful save.</li>
  <li><b>Close</b> &ndash; closes the dialog.</li>
</ul>

<h2>The &ldquo;Restore plugin from backup&rdquo; dialog</h2>
<p>This dialog gives you a complete overview of every backup that is
available and lets you restore one with a single confirmation step.</p>
<ul>
  <li><b>Plugin with backups</b> &ndash; a combo box listing every plugin
      for which at least one backup exists, together with the number of
      snapshots. If no backups are present at all, the combo is disabled
      and the restore button stays inactive.</li>
  <li><b>Available backups (newest first)</b> &ndash; once a plugin is
      selected, every backup appears as a timestamped entry
      (<code>YYYY-MM-DD&nbsp;&nbsp;HH:MM:SS</code>), sorted from the most
      recent to the oldest. The full path of the highlighted entry is
      shown below the list for reference.</li>
  <li><b>&#x21A9; Restore selected backup</b> &ndash; after a
      confirmation prompt, the current plugin files are backed up to a
      new timestamped snapshot and the selected backup is copied into
      the plugin folder. The plugin is unloaded before and reloaded after
      the swap wherever QGIS supports it; if a clean reload is not
      possible, a restart prompt appears.</li>
  <li><b>Close</b> &ndash; closes the dialog without making any
      changes.</li>
</ul>

<h2>The &ldquo;Clean up plugin data&rdquo; dialog</h2>
<p>The dialog lets you review and remove data that this plugin has
stored on disk.</p>
<ul>
  <li><b>Delete now</b> &ndash; ticks correspond to existing files;
      size hints help you spot large items. Click <b>Delete selected
      items now</b> to remove them after a confirmation.</li>
  <li><b>Automatic cleanup on uninstall</b> &ndash; the items ticked
      here are deleted the next time QGIS closes <i>if the plugin
      folder has been removed in the meantime</i>. Disabling or
      restarting alone does not trigger the cleanup. Click <b>Save
      auto-cleanup settings</b> to persist the choice. The umbrella
      <i>all storage</i> option automatically ticks and locks the
      individual items.</li>
  <li><b>Close</b> &ndash; closes the dialog.</li>
</ul>

<h2>Backups, mappings and safety</h2>
<p>Every replacement produces a timestamped backup at
<code>&lt;qgisSettingsDirPath&gt;/github_plugin_sync/backups/&lt;plugin&gt;_&lt;timestamp&gt;/</code>.
The path is written to the status log. Use <b>Restore backup&nbsp;&hellip;</b>
in the main dialog to restore any snapshot through the UI; because the
current files are backed up before each restore, every step in the
sequence is reversible. Stored mappings live in the same parent folder
and can be removed at any time through the cleanup dialog. The plugin
never modifies the GitHub repository: it only fetches branches, file
contents and tarballs.</p>

<h2>Typical workflow</h2>
<ol>
  <li>Open the dialog and pick an installed plugin or type a new
      folder name to perform a fresh installation.</li>
  <li>Enter the GitHub repository and, if needed, choose a credential
      profile.</li>
  <li>Click <b>Load branches</b>, then select the branch you want to
      test.</li>
  <li>If the plugin lives in a sub-folder, click <b>Detect</b> or type
      the path manually.</li>
  <li>Press <b>Check metadata</b> to validate the incoming
      <code>metadata.txt</code> against your QGIS environment.</li>
  <li>If the check is clean (or you accept the warnings), press
      <b>&#x21AA; Replace plugin</b> and confirm. The status log shows
      every step; a final dialog reports success or asks you to
      restart QGIS.</li>
</ol>

<h2>Process diagram</h2>
<p>The plugin is split into three layers: the QGIS-facing UI, a pure
Python core, and the external systems it talks to (GitHub, the QGIS
authentication database and the user profile on disk). Every arrow in
the diagrams below is an actual interface used at runtime &ndash; the
labels match function and module names in the source tree.</p>

<h3>1. Components and interfaces</h3>
<p>This map shows <i>who talks to whom</i>: the user interacts only
with the UI layer; the UI layer drives the core modules; the core
modules are the only place that touches the outside world.</p>
<pre>
+-----------------------------------------------------------------------------+
|                            USER  (QGIS desktop)                             |
+--+--------------------+-----------------+--------------------+--------------+
   | Plugins menu /     | Help button     | Manage&hellip; / Cleanup&hellip;        |
   | toolbar icon       |                 | buttons in main dialog            |
   v                    v                 v                                   |
+-----------------------------------------------------------------------------+
|                          UI LAYER  (qgis.PyQt)                              |
|                                                                             |
|   plugin.GitHubPluginSyncPlugin                                             |
|        |  initGui() -> QAction -> run()                                     |
|        v                                                                    |
|   MainDialog &lt;---------------------&gt; HelpDialog          (non-modal)        |
|     |   |   |                                                               |
|     |   |   +--&gt; CredentialsDialog          (modal)                          |
|     |   +------&gt; CleanupDialog              (modal)                          |
|     |   +------&gt; RestoreDialog              (modal)                          |
|     |                                                                       |
|     +-- Worker QThreads:  _BranchesWorker  _SubdirWorker  _DownloadWorker   |
+-----+--------+---------+----------+--------+--------+--------+--------------+
      |        |         |          |        |        |        |
      v        v         v          v        v        v        v
+-----------------------------------------------------------------------------+
|                        CORE LAYER  (pure Python)                            |
|                                                                             |
|   CredentialManager   MappingManager   PluginReplacer   GitHubClient        |
|   (credentials.py)    (mappings.py)    (plugin_replacer)(github_client.py)  |
|                                                                             |
|   metadata_check.compare()        cleanup.*           paths.*               |
+-----+-----------------+---------------------+-------------------+-----------+
      |                 |                     |                   |
      v                 v                     v                   v
+--------------+ +-----------------+ +------------------+ +-------------------+
|QgsAuthManager| | storage_dir/    | | qgis.utils       | | GitHub REST API   |
|  (auth.db,   | |  mappings.json  | |  unloadPlugin    | |  api.github.com   |
|  master pwd) | |  backups/&hellip;     | |  loadPlugin      | |  HTTPS via       |
|              | |  auto_cleanup   | |  startPlugin     | |  urllib + SSL    |
|  Personal    | |  *.migrated     | | QSettings        | |  PAT in           |
|  Access Token| |                 | |  PythonPlugins/* | |  Authorization:   |
|  encrypted   | | (under          | |                  | |   Bearer &lt;token&gt;  |
|              | |  qgisSettings   | |                  | |                   |
|              | |   DirPath)      | |                  | |                   |
+--------------+ +-----------------+ +------------------+ +-------------------+
</pre>

<h3>2. Main flow &ndash; &ldquo;Replace plugin&rdquo;</h3>
<p>This is the end-to-end sequence triggered by the
<b>&#x21AA; Replace plugin</b> button. Every box on the left is a
user-visible step, the indented lines on the right name the function
and the external interface that is used.</p>
<pre>
USER clicks "&#x21AA; Replace plugin"
  |
  v
MainDialog._on_replace()
  | validate plugin id (regex), repo (RepoRef.parse), branch
  v
+-- metadata check (also reachable via "Check metadata") ----------------+
|   GitHubClient.get_file(repo, branch, "metadata.txt")                  |
|       HTTPS GET api.github.com/repos/{o}/{n}/contents/metadata.txt     |
|   PluginReplacer.read_metadata(plugin_id)         (local file read)    |
|   metadata_check.compare(installed, incoming, plugin_id)               |
|       -&gt; MetadataReport  ([ERROR] / [WARNING] / [INFO] -&gt; status log)  |
+----------------------------+-------------------------------------------+
                             |
                             v
                       errors?  --yes--&gt; QMessageBox.critical, abort
                             |
                          warnings?  --yes--&gt; QMessageBox.question
                             |                  user "No"  -&gt; abort
                             v
              QMessageBox.question  "Confirm replacement / installation"
                             |
                          user "No"  -----&gt; abort, log
                             |
                             v
   _DownloadWorker  (QThread)
        tempfile.mkdtemp(prefix="gps_")
        GitHubClient.download_tarball(repo, branch, tmp_dir)
            HTTPS GET api.github.com/repos/{o}/{n}/tarball/{branch}
            tarfile + _safe_tar_members()      (path-traversal guard)
            extract -&gt; &lt;tmp&gt;/&lt;root&gt;[/&lt;subdir&gt;]
        emits source_dir
                             |
                             v
   PluginReplacer.replace(plugin_id, source_dir, try_reload=True)
        unload_plugin()        qgis.utils.unloadPlugin(plugin_id)
        _backup()              copytree -&gt; storage_dir/backups/
                                          &lt;plugin&gt;_&lt;YYYYMMDD-HHMMSS&gt;/
        _copy_new_files()      rmtree(target) + copytree(source)
            on error           _rollback(backup) -&gt; re-raise
        if fresh_install:
            enable_plugin_in_qsettings()
                QSettings: PythonPlugins/&lt;plugin_id&gt; = true
        reload_plugin()        qgis.utils.updateAvailablePlugins()
                               qgis.utils.loadPlugin(plugin_id)
                               qgis.utils.startPlugin(plugin_id)
                             |
                             v
   ReplacementResult -&gt; status log
        + remember? -&gt; MappingManager.save(PluginMapping(&hellip;))
                                writes storage_dir/mappings.json
        + shutil.rmtree(tmp_dir)
                             |
                             v
   Final QMessageBox: success | "restart QGIS required"
</pre>

<h3>3. Side flows</h3>
<p>The remaining UI actions follow shorter, self-contained paths.</p>
<pre>
"Load branches"    -&gt; _BranchesWorker
    GitHubClient.list_branches(repo)
        HTTPS GET .../branches?per_page=100
        follows the "Link: rel=next" header for pagination
    -&gt; combo box, preselects "main" / "master"

"Detect" sub-dir   -&gt; _SubdirWorker
    GitHubClient.find_plugin_folders(repo, branch, max_depth=2)
        BFS via list_directory()
        HTTPS GET .../contents/&lt;path&gt;?ref=&lt;branch&gt; per node
    -&gt; combo box, preselects first candidate

"Manage&hellip;"        -&gt; CredentialsDialog
    list   : QgsAuthManager.availableAuthMethodConfigs()
    save   : QgsAuthMethodConfig + storeAuthenticationConfig()
             (master password prompted by QGIS if not yet unlocked)
    load   : loadAuthenticationConfig(id, &hellip;, full=True)
    delete : removeAuthenticationConfig(id)
    one-time migration:
        credentials.json + cred.key  --&gt;  QgsAuthManager
        legacy files renamed to *.migrated

"Cleanup plugin data&hellip;" -&gt; CleanupDialog
    cleanup.list_targets()        -&gt; mappings | backups | legacy | storage
    "Delete selected items now"   -&gt; cleanup.delete_targets(keys)
    "Save auto-cleanup settings"  -&gt; cleanup.save_auto_cleanup_keys(keys)
                                     writes storage_dir/auto_cleanup.json

"Restore backup &hellip;" -&gt; RestoreDialog
    PluginReplacer.list_backups()
        scans storage_dir/backups/ for &lt;plugin&gt;_&lt;YYYYMMDD-HHMMSS&gt;/
        groups by plugin_id, sorts newest-first
        -&gt; plugin combo (with count), backup list (timestamps + paths)
    "&uarr; Restore selected backup" after confirmation:
    PluginReplacer.restore_backup(entry)
        delegates to replace(plugin_id, source_dir=backup_path)
          unload_plugin()        qgis.utils.unloadPlugin(plugin_id)
          _backup()              current files -&gt; new timestamped snapshot
          _copy_new_files()      backup_path -&gt; plugin_dir
          reload_plugin()        qgis.utils.loadPlugin / startPlugin

Plugin start (every QGIS launch):
    GitHubPluginSyncPlugin.__init__
       -&gt; cleanup.register_uninstall_cleanup(plugin_dir)
          atexit handler captures all relevant paths.
QGIS shutdown:
    handler runs; only acts when plugin_dir has disappeared
    (= true uninstall, not a disable / restart) AND
    auto_cleanup.json lists keys -&gt; removes the selected data.
</pre>

<h3>4. External interfaces at a glance</h3>
<table border="1" cellpadding="4" cellspacing="0">
  <tr>
    <th align="left">Interface</th>
    <th align="left">Direction</th>
    <th align="left">Used by</th>
    <th align="left">Purpose</th>
  </tr>
  <tr>
    <td>GitHub REST API <code>api.github.com</code></td>
    <td>plugin &rarr; GitHub (HTTPS, urllib)</td>
    <td><code>GitHubClient</code></td>
    <td>List branches, list directory, fetch <code>metadata.txt</code>,
        download tarball. Optional <code>Authorization: Bearer &lt;PAT&gt;</code>.</td>
  </tr>
  <tr>
    <td><code>QgsAuthManager</code> (auth database)</td>
    <td>plugin &harr; QGIS</td>
    <td><code>CredentialManager</code></td>
    <td>Encrypted storage of GitHub PATs, gated by the QGIS master
        password.</td>
  </tr>
  <tr>
    <td><code>qgis.utils</code> plugin registry</td>
    <td>plugin &rarr; QGIS</td>
    <td><code>PluginReplacer</code></td>
    <td>Unload, reload and start the target plugin without a QGIS
        restart whenever possible.</td>
  </tr>
  <tr>
    <td><code>QSettings</code> (<code>PythonPlugins/&lt;id&gt;</code>)</td>
    <td>plugin &rarr; QGIS</td>
    <td><code>PluginReplacer</code></td>
    <td>Activate a fresh-install plugin so it starts on the next QGIS
        launch.</td>
  </tr>
  <tr>
    <td>QGIS user profile filesystem</td>
    <td>plugin &harr; disk</td>
    <td><code>PluginReplacer</code>, <code>MappingManager</code>,
        <code>cleanup</code>, <code>paths</code></td>
    <td>Plugins directory (replace target), backups, mappings,
        auto-cleanup settings, legacy credential files.</td>
  </tr>
  <tr>
    <td>Qt dialogs &amp; signals</td>
    <td>user &harr; plugin</td>
    <td>UI layer</td>
    <td>All user input/output: form fields, buttons, status log,
        confirmations, progress bar, worker-thread signals.</td>
  </tr>
</table>
"""


class HelpDialog(QDialog):
    """Stand-alone, non-modal window that shows the plugin help text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("GitHub Plugin Sync – Help"))
        self.setModal(False)
        self.setWindowFlag(Qt.Window, True)
        self.resize(720, 640)

        layout = QVBoxLayout(self)

        self.text = QTextBrowser(self)
        self.text.setOpenExternalLinks(True)
        self.text.setHtml(_HELP_HTML)
        layout.addWidget(self.text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.close)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.close)
        layout.addWidget(buttons)

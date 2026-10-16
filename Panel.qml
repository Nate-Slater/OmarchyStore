import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Store

Panel {
  id: root
  moduleName: "nate.omarchystore"
  ipcTarget: "nate.omarchystore"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var bar: null
  property var plugins: []
  property var results: []
  property var installed: Object.create(null)
  property var selectedPlugin: null
  property var catalogRequest: null
  property string generatedAt: ""
  property string query: ""
  property string filterMode: "all"
  property string message: "Open the store to load the marketplace."
  property string pendingAction: ""
  property string activeOperation: ""
  property string actionOutput: ""
  property bool catalogLoading: false
  property bool catalogReady: false
  property bool installedReady: false
  property bool actionRunning: false
  property bool listRunning: false

  readonly property color fg: Color.popups.text
  readonly property color dim: Qt.rgba(fg.r, fg.g, fg.b, 0.68)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var selectedState: selectedPlugin && installedReady ? installed[selectedPlugin.id] : null

  function open() {
    root.pendingAction = ""
    root.controller.show()
    if (!root.catalogReady && !root.catalogLoading) root.loadCatalog()
    if (!root.listRunning) root.loadInstalled()
  }

  function close() {
    root.pendingAction = ""
    root.controller.hide()
  }

  function closeForPopoutSwitch() { root.close() }

  function refreshResults() {
    var matches = Store.searchPlugins(root.plugins, root.query)
    var filtered = []
    for (var r = 0; r < matches.length; r++) {
      var installedState = root.installedReady ? root.installed[matches[r].id] : null
      if (root.filterMode === "installed" && !installedState) continue
      if (root.filterMode === "installable" && (!matches[r].installAvailable || installedState)) continue
      filtered.push(matches[r])
    }
    root.results = filtered
    var found = false
    for (var i = 0; i < root.results.length; i++) {
      if (root.selectedPlugin && root.results[i].id === root.selectedPlugin.id) {
        root.selectedPlugin = root.results[i]
        found = true
        break
      }
    }
    if (!found) root.selectedPlugin = root.results.length ? root.results[0] : null
  }

  function loadCatalog() {
    if (root.catalogRequest) root.catalogRequest.abort()
    root.catalogLoading = true
    root.message = "Loading the marketplace catalog…"
    var request = new XMLHttpRequest()
    root.catalogRequest = request
    request.open("GET", Store.CATALOG_URL)
    request.timeout = 25000
    request.setRequestHeader("Accept", "application/json")
    request.onreadystatechange = function() {
      if (request.readyState !== 4) return
      if (root.catalogRequest !== request) return
      root.catalogRequest = null
      root.catalogLoading = false
      if (request.status < 200 || request.status >= 300) {
        root.message = "Marketplace request failed (HTTP " + request.status + "). Try again."
        return
      }
      if (request.responseText.length > Store.MAX_CATALOG_BYTES) {
        root.message = "The marketplace catalog exceeded the size limit."
        return
      }
      try {
        var data = Store.normalizeCatalog(JSON.parse(request.responseText))
        root.plugins = data.plugins
        root.generatedAt = data.generatedAt
        root.catalogReady = true
        root.refreshResults()
        root.message = data.plugins.length + " community plugins · catalog data from plugins.omarchy.org"
      } catch (e) {
        root.message = "Could not read the marketplace catalog: " + String(e)
      }
    }
    request.ontimeout = function() {
      if (root.catalogRequest !== request) return
      root.catalogRequest = null
      root.catalogLoading = false
      root.message = "Marketplace request timed out. Check your connection and try again."
    }
    request.onerror = function() {
      if (root.catalogRequest !== request) return
      root.catalogRequest = null
      root.catalogLoading = false
      root.message = "Could not reach plugins.omarchy.org. Check your connection and try again."
    }
    request.send()
  }

  function loadInstalled() {
    if (root.listRunning) return
    root.listRunning = true
    installedProcess.running = true
  }

  function receiveInstalled(text) {
    var next = Store.installedMap(text)
    if (next === null) {
      root.installedReady = false
      root.message = "Could not parse `omarchy plugin list --json`."
      return
    }
    root.installed = next
    root.installedReady = true
    root.refreshResults()
  }

  function confirmPendingAction() {
    if (!root.selectedPlugin || root.actionRunning) return
    var args = []
    if (root.pendingAction === "install") args = Store.installArgs(root.selectedPlugin)
    else if (root.pendingAction === "enable") args = Store.enableArgs(root.selectedPlugin)
    else if (root.pendingAction === "remove") args = Store.removeArgs(root.selectedPlugin)
    if (!args.length) {
      root.message = "This listing cannot be installed automatically. Open its source for manual instructions."
      root.pendingAction = ""
      return
    }
    root.activeOperation = root.pendingAction
    root.actionOutput = ""
    root.pendingAction = ""
    actionProcess.command = ["omarchy"].concat(args)
    root.actionRunning = true
    actionProcess.running = true
  }

  function finishAction(exitCode, exitStatus) {
    var operation = root.activeOperation
    root.actionRunning = false
    root.activeOperation = ""
    if (exitCode === 0 && exitStatus === 0) {
      root.message = operation === "remove"
        ? "Plugin removed."
        : operation === "enable"
          ? "Plugin enabled. It is now running in the Omarchy shell."
          : "Plugin installed and enabled. It is now running in the Omarchy shell."
      root.loadInstalled()
    } else {
      root.message = "Omarchy could not complete the " + operation + " action (exit " + exitCode + "). "
        + (root.actionOutput || "Check the terminal/session logs for details.")
    }
  }

  function openSource() {
    if (root.selectedPlugin) Qt.openUrlExternally(root.selectedPlugin.repo.replace(/\.git$/, ""))
  }

  onQueryChanged: searchTimer.restart()
  onFilterModeChanged: searchTimer.restart()
  onOpenedChanged: {
    if (opened && !catalogReady && !catalogLoading) loadCatalog()
    if (opened && !listRunning) loadInstalled()
  }

  Component.onDestruction: {
    if (root.catalogRequest) root.catalogRequest.abort()
  }

  Timer {
    id: searchTimer
    interval: 180
    repeat: false
    onTriggered: root.refreshResults()
  }

  Process {
    id: installedProcess
    command: ["omarchy", "plugin", "list", "--json"]
    stdout: StdioCollector {
      onStreamFinished: root.receiveInstalled(this.text)
    }
    onExited: function(exitCode, exitStatus) {
      root.listRunning = false
      if (exitCode !== 0 || exitStatus !== 0) {
        root.installedReady = false
        root.message = "Could not read installed plugins using `omarchy plugin list --json`."
      }
    }
  }

  Process {
    id: actionProcess
    command: ["omarchy"]
    stdout: StdioCollector {
      onStreamFinished: root.actionOutput = this.text.slice(0, 800)
    }
    stderr: StdioCollector {
      onStreamFinished: {
        if (this.text) root.actionOutput = this.text.slice(0, 800)
      }
    }
    onExited: function(exitCode, exitStatus) {
      root.finishAction(exitCode, exitStatus)
    }
  }

  KeyboardPanel {
    id: surface
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: surface.fittedContentWidth(Style.space(920))
    contentHeight: surface.fittedContentHeight(body.implicitHeight, Style.space(700))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: searchField.activeFocus
      onCloseRequested: root.close()

      Column {
        id: body
        width: parent.width
        spacing: Style.spacing.md

        Row {
          width: parent.width
          height: Style.space(36)
          spacing: Style.spacing.md

          Text {
            text: "OMARCHY STORE"
            color: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
          }

          Item { width: 1; height: 1 }

          Button {
            text: "Refresh"
            foreground: root.fg
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: {
              root.loadCatalog()
              root.loadInstalled()
            }
          }
        }

        Rectangle {
          width: parent.width
          height: warningText.implicitHeight + Style.space(18)
          radius: Style.cornerRadius > 0 ? Style.space(6) : 0
          color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.12)

          Text {
            id: warningText
            anchors.fill: parent
            anchors.margins: Style.spacing.md
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            text: "Security: third-party plugins run unsandboxed with your user permissions. Marketplace verification is not a security audit, and installs use the repository's current HEAD—not a verified commit. Review source before installing."
            color: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Row {
          width: parent.width
          height: Style.space(40)
          spacing: Style.spacing.md

          TextField {
            id: searchField
            width: parent.width - refreshStatus.width - Style.spacing.md
            height: parent.height
            placeholderText: "Search name, author, category, tag, or plugin ID"
            foreground: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            onTextChanged: root.query = text
          }

          Text {
            id: refreshStatus
            width: Style.space(205)
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            text: root.catalogLoading ? "Loading catalog…" : (root.installedReady ? "Installed list ready" : "Checking installed…")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }
        }

        Row {
          width: parent.width
          height: Style.space(34)
          spacing: Style.spacing.sm

          Button {
            text: "All"
            selected: root.filterMode === "all"
            foreground: root.fg
            accent: Color.accent
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: root.filterMode = "all"
          }
          Button {
            text: "Installable"
            selected: root.filterMode === "installable"
            foreground: root.fg
            accent: Color.accent
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: root.filterMode = "installable"
          }
          Button {
            text: "Installed"
            selected: root.filterMode === "installed"
            enabled: root.installedReady
            foreground: root.fg
            accent: Color.accent
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            onClicked: root.filterMode = "installed"
          }

          Text {
            width: parent.width - Style.space(300)
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignRight
            textFormat: Text.PlainText
            text: root.results.length + " results"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Text {
          width: parent.width
          height: Style.space(22)
          textFormat: Text.PlainText
          text: root.message + (root.generatedAt ? "  ·  Updated " + root.generatedAt.slice(0, 10) : "")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }

        Row {
          width: parent.width
          height: Style.space(410)
          spacing: Style.spacing.md

          Rectangle {
            width: Style.space(330)
            height: parent.height
            radius: Style.cornerRadius > 0 ? Style.space(6) : 0
            color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.035)

            ListView {
              id: pluginList
              anchors.fill: parent
              anchors.margins: Style.spacing.xs
              clip: true
              spacing: Style.space(2)
              model: root.results
              boundsBehavior: Flickable.StopAtBounds

              delegate: Item {
                required property var modelData
                width: pluginList.width
                height: Style.space(67)

                Rectangle {
                  anchors.fill: parent
                  radius: Style.cornerRadius > 0 ? Style.space(5) : 0
                  color: root.selectedPlugin && root.selectedPlugin.id === modelData.id
                    ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.17)
                    : (rowMouse.containsMouse ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.07) : "transparent")
                }

                Column {
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.leftMargin: Style.spacing.md
                  anchors.rightMargin: Style.spacing.md
                  spacing: Style.space(3)

                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    text: modelData.name
                    color: root.fg
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                    elide: Text.ElideRight
                  }

                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    text: (root.installed[modelData.id] ? "Installed · " : "") + modelData.category + " · " + modelData.author
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                }

                MouseArea {
                  id: rowMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    root.selectedPlugin = modelData
                    root.pendingAction = ""
                  }
                }
              }
            }
          }

          Rectangle {
            width: parent.width - Style.space(330) - Style.spacing.md
            height: parent.height
            radius: Style.cornerRadius > 0 ? Style.space(6) : 0
            color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.035)

            Flickable {
              anchors.fill: parent
              anchors.margins: Style.spacing.md
              clip: true
              contentWidth: width
              contentHeight: detailColumn.implicitHeight
              boundsBehavior: Flickable.StopAtBounds
              visible: root.selectedPlugin !== null

              Column {
                id: detailColumn
                width: parent.width
                spacing: Style.spacing.md

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: root.selectedPlugin ? root.selectedPlugin.name : ""
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                  wrapMode: Text.WordWrap
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: root.selectedPlugin
                    ? root.selectedPlugin.id + "  ·  " + root.selectedPlugin.version + "  ·  " + root.selectedPlugin.author
                    : ""
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: root.selectedPlugin ? root.selectedPlugin.description : ""
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  wrapMode: Text.WordWrap
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: root.selectedPlugin
                    ? "Category: " + root.selectedPlugin.category
                      + (root.selectedPlugin.kind ? " · Type: " + root.selectedPlugin.kind : "")
                      + "\nLicense: " + root.selectedPlugin.license
                      + "\nTags: " + root.selectedPlugin.tags.join(", ")
                    : ""
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: root.selectedPlugin
                    ? (root.selectedPlugin.verificationStatus === "verified"
                      ? "Marketplace status: Verified listing. This only applies to the listed snapshot; current upstream installs may differ."
                      : "Marketplace status: Unverified. No current verification record is available for the listed snapshot.")
                      + (root.selectedPlugin.upstreamStatus === "failed"
                        ? "\nAutomatic installation is unavailable because the marketplace's compatibility check failed."
                        : "")
                    : ""
                  color: root.selectedPlugin && root.selectedPlugin.verificationStatus === "verified" ? Color.accent : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }

                Row {
                  width: parent.width
                  spacing: Style.spacing.sm

                  Button {
                    text: "View source ↗"
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    fontSize: Style.font.bodySmall
                    onClicked: root.openSource()
                  }

                  Button {
                    text: "Install & enable"
                    visible: root.selectedPlugin && !root.selectedState && root.selectedPlugin.installAvailable
                    enabled: !root.actionRunning && root.installedReady
                    foreground: root.fg
                    accent: Color.accent
                    fontFamily: root.fontFamily
                    fontSize: Style.font.bodySmall
                    onClicked: root.pendingAction = "install"
                  }

                  Button {
                    text: "Enable (runs code)"
                    visible: root.selectedPlugin && root.selectedState && !root.selectedState.enabled
                    enabled: !root.actionRunning
                    foreground: root.fg
                    accent: Color.accent
                    fontFamily: root.fontFamily
                    fontSize: Style.font.bodySmall
                    onClicked: root.pendingAction = "enable"
                  }

                  Button {
                    text: "Remove"
                    visible: root.selectedState && !root.selectedState.firstParty
                    enabled: !root.actionRunning
                    foreground: Color.urgent
                    fontFamily: root.fontFamily
                    fontSize: Style.font.bodySmall
                    onClicked: root.pendingAction = "remove"
                  }
                }

                Text {
                  width: parent.width
                  visible: root.selectedPlugin && !root.selectedPlugin.installAvailable && !root.selectedState
                  textFormat: Text.PlainText
                  text: root.selectedPlugin ? (root.selectedPlugin.installNote || "Automatic installation is unavailable for this repository layout.") : ""
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }

                Rectangle {
                  width: parent.width
                  height: confirmationColumn.implicitHeight + Style.spacing.md * 2
                  visible: root.pendingAction !== ""
                  radius: Style.cornerRadius > 0 ? Style.space(6) : 0
                  color: Qt.rgba(Color.urgent.r, Color.urgent.g, Color.urgent.b, 0.10)

                  Column {
                    id: confirmationColumn
                    anchors.fill: parent
                    anchors.margins: Style.spacing.md
                    spacing: Style.spacing.sm

                    Text {
                      width: parent.width
                      textFormat: Text.PlainText
                      wrapMode: Text.WordWrap
                      text: root.pendingAction === "install"
                        ? "Install " + (root.selectedPlugin ? root.selectedPlugin.name : "this plugin") + " from the current GitHub HEAD and enable it? This runs unsandboxed code with your user permissions. The install is not pinned to the marketplace-checked or verified commit. Review the repository first."
                        : root.pendingAction === "enable"
                          ? "Enable " + (root.selectedPlugin ? root.selectedPlugin.name : "this plugin") + "? Its code will run unsandboxed with your user permissions. Review its installed files first."
                          : "Remove " + (root.selectedPlugin ? root.selectedPlugin.name : "this plugin") + "? Omarchy will disable it and remove its plugin checkout."
                      color: root.fg
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }

                    Row {
                      spacing: Style.spacing.sm
                      Button {
                        text: root.actionRunning ? "Working…" : (root.pendingAction === "remove" ? "Confirm removal" : "I reviewed it — continue")
                        enabled: !root.actionRunning
                        foreground: root.fg
                        accent: Color.urgent
                        fontFamily: root.fontFamily
                        fontSize: Style.font.bodySmall
                        onClicked: root.confirmPendingAction()
                      }
                      Button {
                        text: "Cancel"
                        enabled: !root.actionRunning
                        foreground: root.fg
                        fontFamily: root.fontFamily
                        fontSize: Style.font.bodySmall
                        onClicked: root.pendingAction = ""
                      }
                    }
                  }
                }
              }
            }

            Text {
              anchors.centerIn: parent
              width: parent.width - Style.spacing.lg * 2
              visible: root.selectedPlugin === null
              textFormat: Text.PlainText
              text: root.catalogReady ? "No matching plugins. Try another search." : "The catalog will appear here when it loads."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }
          }
        }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: "Automatic installs are limited to root-level plugin repositories with a valid GitHub URL and an available marketplace install status. Monorepos and suites are source-only."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
      }
    }
  }
}

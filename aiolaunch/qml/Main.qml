import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: win
    width: 1320
    height: 840
    minimumWidth: 760
    minimumHeight: 480
    visible: true
    title: "AIO Launch"
    color: theme.background

    readonly property var theme: app.theme
    property bool tv: startTv
    visibility: tv ? Window.FullScreen : Window.Windowed
    onTvChanged: if (!tv) grid.forceActiveFocus()
    property string selectedKey: ""
    property var selected: ({})

    function select(key) {
        selectedKey = key
        selected = app.game(key)
        if (selected.key) detail.open()
    }
    // Play straight away when it is clear which copy to start; otherwise open the game's panel.
    function activate(key) {
        const target = app.launchTarget(key)
        if (target) { app.play(target); return }
        select(key)
        const g = app.game(key)
        if (g.copies.filter(c => c.installed).length > 1)
            toasts.append({ message: "Installed from several stores: pick the launcher to use" })
    }
    function storeInfo(id) {
        const all = app.storesInfo
        for (let i = 0; i < all.length; i++) if (all[i].id === id) return all[i]
        return {}
    }

    onActiveChanged: if (active) app.refreshLocal()

    Connections {
        target: app
        function onGameChanged(key) {
            if (win.selectedKey && (key === "" || key === win.selectedKey)) {
                const g = app.game(win.selectedKey)
                if (g.key) win.selected = g
                else detail.close()
            }
        }
        function onToast(message) { toasts.append({ message: message }) }
        function onLoginReady(store, url, prompt) {
            login.store = store; login.url = url; login.prompt = prompt
            login.error = ""; login.busy = false
            code.text = ""
            login.open()
            app.openUrl(url)
        }
        function onLoginDone(store, ok, message) {
            login.busy = false
            if (ok) { login.close(); toasts.append({ message: message }) }
            else login.error = message
        }
    }

    Shortcut { sequence: "Ctrl+F"; onActivated: search.forceActiveFocus() }
    Shortcut { sequence: "Ctrl+R"; onActivated: app.refresh() }
    Shortcut { sequence: "F5"; onActivated: app.refresh() }
    Shortcut { sequence: "F11"; onActivated: win.tv = !win.tv }
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }

    TvView {
        anchors.fill: parent
        z: 50
        theme: win.theme
        visible: win.tv
        enabled: win.tv
        focus: win.tv
        onExit: win.tv = false
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: !win.tv
        enabled: !win.tv

        // ---------------------------------------------------------------- sidebar
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 236
            color: theme.surfaceContainerLow

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 4

                RowLayout {
                    Layout.margins: 8
                    Layout.bottomMargin: 16
                    spacing: 10
                    Image { source: "../aiolaunch.svg"; sourceSize: Qt.size(30, 30) }
                    Text { text: "AIO Launch"; color: theme.onSurface; font.pixelSize: 21; font.weight: Font.Bold }
                }

                component NavItem: Rectangle {
                    id: nav
                    readonly property var theme: app.theme
                    property string label
                    property string dot: ""
                    property string count: ""
                    property bool active: false
                    property bool dim: false
                    signal picked()
                    Layout.fillWidth: true
                    height: 40
                    radius: 10
                    color: active ? theme.primaryContainer : navHover.hovered ? theme.surfaceContainerHigh : "transparent"
                    Rectangle {
                        visible: nav.dot !== ""
                        x: 14; anchors.verticalCenter: parent.verticalCenter
                        width: 9; height: 9; radius: 5
                        color: nav.dot || "transparent"
                        opacity: nav.dim ? 0.35 : 1
                    }
                    Text {
                        x: nav.dot !== "" ? 34 : 14
                        anchors.verticalCenter: parent.verticalCenter
                        text: nav.label
                        color: nav.active ? theme.onPrimaryContainer : theme.onSurface
                        opacity: nav.dim ? 0.6 : 1
                        font.pixelSize: 14
                        font.weight: nav.active ? Font.DemiBold : Font.Normal
                    }
                    Text {
                        anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                        text: nav.count
                        color: nav.active ? theme.onPrimaryContainer : theme.onSurfaceVariant
                        font.pixelSize: 12
                    }
                    HoverHandler { id: navHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: nav.picked() }
                }

                NavItem {
                    label: "All games"
                    count: app.totalCount
                    active: library.storeFilter === ""
                    onPicked: library.storeFilter = ""
                }
                Repeater {
                    model: app.storesInfo
                    NavItem {
                        required property var modelData
                        label: modelData.name
                        dot: modelData.color
                        dim: !modelData.loggedIn && modelData.count === 0
                        count: modelData.refreshing ? "…" : modelData.count
                        active: library.storeFilter === modelData.id
                        onPicked: library.storeFilter = modelData.id
                    }
                }

                Rectangle { Layout.fillWidth: true; Layout.margins: 8; height: 1; color: theme.outlineVariant }

                RowLayout {
                    Layout.leftMargin: 14; Layout.rightMargin: 6
                    Text { text: "Installed only"; color: theme.onSurface; font.pixelSize: 14; Layout.fillWidth: true }
                    Switch {
                        id: instSwitch
                        checked: library.installedOnly
                        onToggled: library.installedOnly = checked
                        indicator: Rectangle {
                            implicitWidth: 40; implicitHeight: 22; radius: 11
                            y: parent.height / 2 - height / 2
                            color: instSwitch.checked ? theme.primary : theme.surfaceContainerHighest
                            Rectangle {
                                x: instSwitch.checked ? parent.width - width - 3 : 3
                                y: 3; width: 16; height: 16; radius: 8
                                color: instSwitch.checked ? theme.onPrimary : theme.outline
                                Behavior on x { NumberAnimation { duration: 100 } }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                NavItem { label: "TV mode"; count: "F11"; onPicked: win.tv = true }
                NavItem { label: "Accounts"; onPicked: accounts.open() }
                NavItem { label: "Settings"; onPicked: prefs.open() }
            }
        }

        // ---------------------------------------------------------------- library
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            RowLayout {
                Layout.margins: 20
                Layout.bottomMargin: 8
                spacing: 12
                KField {
                    id: search
                    theme: win.theme
                    Layout.fillWidth: true
                    Layout.maximumWidth: 460
                    placeholderText: "Search your games  (Ctrl+F)"
                    onTextChanged: library.search = text
                    Keys.onDownPressed: grid.forceActiveFocus()
                    Keys.onEscapePressed: { text = ""; grid.forceActiveFocus() }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: grid.count + (grid.count === 1 ? " game" : " games")
                    color: theme.onSurfaceVariant
                    font.pixelSize: 13
                }
                KButton {
                    theme: win.theme
                    text: app.refreshing ? "Refreshing…" : "Refresh"
                    enabled: !app.refreshing
                    onClicked: app.refresh()
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                GridView {
                    id: grid
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    clip: true
                    focus: true
                    model: library
                    readonly property int columns: Math.max(2, Math.floor(width / app.settingsMap.card_size))
                    cellWidth: Math.floor(width / columns)
                    cellHeight: Math.round(cellWidth * 1.46)
                    cacheBuffer: cellHeight * 2
                    keyNavigationEnabled: true
                    highlightFollowsCurrentItem: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { }
                    delegate: GameCard {
                        width: grid.cellWidth
                        height: grid.cellHeight
                        theme: win.theme
                        cornerRadius: app.settingsMap.card_radius
                        showBadge: app.settingsMap.show_badges
                        showTitle: app.settingsMap.show_titles
                        dim: app.settingsMap.dim_uninstalled
                        current: GridView.isCurrentItem && grid.activeFocus
                        onOpened: { grid.currentIndex = index; win.select(key) }
                        onActivated: { grid.currentIndex = index; win.activate(key) }
                        required property int index
                    }
                    Keys.onReturnPressed: {
                        const key = library.keyAt(currentIndex)
                        if (key) win.activate(key)
                    }
                    Keys.onSpacePressed: { const key = library.keyAt(currentIndex); if (key) win.select(key) }
                }

                // Empty state.
                Column {
                    visible: grid.count === 0
                    anchors.centerIn: parent
                    spacing: 14
                    width: Math.min(parent.width - 60, 460)
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        color: theme.onSurface
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        text: app.refreshing ? "Loading your libraries…"
                              : app.totalCount === 0 ? "No games here yet" : "Nothing matches"
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        color: theme.onSurfaceVariant
                        font.pixelSize: 14
                        visible: !app.refreshing
                        text: app.totalCount === 0
                              ? "Connect your stores to see every game you own in one place."
                              : "Try a different search, store, or turn off Installed only."
                    }
                    KButton {
                        theme: win.theme
                        primary: true
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: !app.refreshing && app.totalCount === 0
                        text: "Connect stores"
                        onClicked: accounts.open()
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------- game detail
    KDialog {
        id: detail
        theme: win.theme
        heading: ""
        width: Math.min(win.width - 60, 720)
        topPadding: 24
        onClosed: { win.selectedKey = ""; confirmRemove.armed = false }
        contentItem: RowLayout {
            spacing: 24
            Rectangle {
                Layout.preferredWidth: 220
                Layout.preferredHeight: 320
                radius: 12
                color: theme.surfaceContainerHigh
                clip: true
                Text {
                    anchors.centerIn: parent
                    width: parent.width - 24
                    text: win.selected.title || ""
                    color: theme.onSurfaceVariant
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    visible: detailArt.status !== Image.Ready
                }
                Image {
                    id: detailArt
                    anchors.fill: parent
                    source: win.selected.cover || ""
                    asynchronous: true
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 400
                    onStatusChanged: {
                        const fb = win.selected.coverFallback || ""
                        if (status === Image.Error && fb && source != fb) source = fb
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                Text {
                    Layout.fillWidth: true
                    Layout.rightMargin: 30
                    text: win.selected.title || ""
                    color: theme.onSurface
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                }
                Row {
                    spacing: 8
                    Rectangle { width: 9; height: 9; radius: 5; color: win.selected.storeColor || "gray"; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        color: theme.onSurfaceVariant
                        font.pixelSize: 13
                        text: (win.selected.storeName || "") + "  ·  " + (win.selected.installed ? "Installed" : "Not installed")
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!win.selected.installPath
                    text: win.selected.installPath || ""
                    color: theme.outline
                    font.pixelSize: 12
                    elide: Text.ElideMiddle
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.openFolder(win.selected.installPath) }
                }

                // The same game owned on several stores: choose which copy to use.
                ColumnLayout {
                    visible: (win.selected.copies || []).length > 1
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 8
                    Text {
                        text: "You own this on " + (win.selected.copies || []).length + " stores. Launcher to use:"
                        color: theme.onSurfaceVariant
                        font.pixelSize: 12
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: win.selected.copies || []
                            Chip {
                                required property var modelData
                                label: modelData.storeName + (modelData.installed ? " · installed" : "")
                                dot: modelData.storeColor
                                active: modelData.key === win.selectedKey
                                onPicked: {
                                    const k = modelData.key
                                    app.preferCopy(k)
                                    win.selectedKey = k
                                    win.selected = app.game(k)
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // Job progress.
                ColumnLayout {
                    visible: !!win.selected.job
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        color: theme.onSurface
                        font.pixelSize: 13
                        text: win.selected.job === "uninstall" ? "Removing…"
                              : win.selected.progress < 0 ? "Starting…"
                              : "Installing  " + (win.selected.progress || 0).toFixed(1) + "%"
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 6; radius: 3
                        color: theme.surfaceContainerHighest
                        Rectangle {
                            height: parent.height; radius: 3
                            color: theme.primary
                            width: parent.width * Math.max(0.02, (win.selected.progress || 0) / 100)
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: win.selected.store === "battlenet" && win.selected.key === "battlenet:battlenet-app"
                    wrapMode: Text.WordWrap
                    color: theme.onSurfaceVariant
                    font.pixelSize: 12
                    text: win.selected.installed
                          ? "Sign in and install Blizzard games inside this app; installed games then show up here as their own tiles."
                          : "Installs Blizzard's launcher under Proton. Its own setup window opens; the first run also downloads Proton."
                }

                RowLayout {
                    spacing: 10
                    KButton {
                        theme: win.theme
                        primary: true
                        visible: !win.selected.job
                        text: win.selected.installed ? "Play" : "Install"
                        onClicked: {
                            app.preferCopy(win.selectedKey)
                            win.selected.installed ? app.play(win.selectedKey) : app.install(win.selectedKey)
                        }
                    }
                    KButton {
                        theme: win.theme
                        visible: !!win.selected.job
                        text: "Cancel"
                        onClicked: app.cancel(win.selectedKey)
                    }
                    KButton {
                        theme: win.theme
                        visible: !!win.selected.hasDlc
                        text: "DLC"
                        onClicked: dlc.show(win.selectedKey, win.selected.title)
                    }
                    KButton {
                        theme: win.theme
                        text: "Options"
                        onClicked: gameOpts.show(win.selectedKey)
                    }
                    KButton {
                        id: confirmRemove
                        property bool armed: false
                        theme: win.theme
                        danger: true
                        visible: !!win.selected.installed && !win.selected.job && win.selected.store !== "battlenet"
                        text: armed ? "Really uninstall?" : "Uninstall"
                        onClicked: {
                            if (!armed) { armed = true; return }
                            armed = false
                            app.uninstall(win.selectedKey)
                        }
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------- save conflict
    Connections {
        target: app
        function onSaveConflict(key, local, cloud) {
            conflict.key = key
            conflict.title = app.game(key).title || ""
            conflict.local = local
            conflict.cloud = cloud
            conflict.open()
        }
    }
    KDialog {
        id: conflict
        theme: win.theme
        property string key: ""
        property string title: ""
        property string local: ""
        property string cloud: ""
        heading: "Which saves should " + title + " use?"
        onOpened: useCloud.forceActiveFocus()
        width: Math.min(win.width - 60, 560)
        closePolicy: Popup.CloseOnEscape
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                text: "Saves changed both on this PC and in the cloud since the last sync, probably because you played on another computer. The one you don't pick is replaced."
            }
            KButton {
                id: useCloud
                theme: win.theme; primary: true; Layout.fillWidth: true
                KeyNavigation.down: keepLocal
                Keys.onReturnPressed: clicked()
                text: "Use the cloud save" + (conflict.cloud ? "  (" + conflict.cloud + ")" : "")
                onClicked: { conflict.close(); app.resolveConflict(conflict.key, "cloud") }
            }
            KButton {
                id: keepLocal
                theme: win.theme; Layout.fillWidth: true
                KeyNavigation.up: useCloud
                KeyNavigation.down: skipSync
                Keys.onReturnPressed: clicked()
                text: "Keep this PC's save" + (conflict.local ? "  (" + conflict.local + ")" : "")
                onClicked: { conflict.close(); app.resolveConflict(conflict.key, "local") }
            }
            KButton {
                id: skipSync
                theme: win.theme; Layout.fillWidth: true
                KeyNavigation.up: keepLocal
                Keys.onReturnPressed: clicked()
                text: "Play without syncing this time"
                onClicked: { conflict.close(); app.resolveConflict(conflict.key, "skip") }
            }
        }
    }

    // -------------------------------------------------------------------- DLC
    KDialog {
        id: dlc
        theme: win.theme
        property string key: ""
        property var rows: []
        property string note: ""
        property bool loading: false
        heading: "DLC"
        width: Math.min(win.width - 60, 620)
        function show(k, title) {
            key = k; rows = []; note = ""; loading = true
            heading = "DLC · " + title
            open()
            app.loadDlcs(k)
        }
        Connections {
            target: app
            function onDlcsReady(key, rows, note) {
                if (key !== dlc.key) return
                dlc.rows = rows; dlc.note = note; dlc.loading = false
            }
        }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                Layout.fillWidth: true
                visible: dlc.loading || dlc.rows.length === 0
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                text: dlc.loading ? "Looking up DLC…" : (dlc.note && dlc.rows.length === 0 && !dlc.note.includes("lists") && !dlc.note.includes("only tells") ? dlc.note : "No DLC found for this game.")
            }
            ListView {
                id: dlcList
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 400)
                visible: dlc.rows.length > 0
                clip: true
                spacing: 6
                model: dlc.rows
                ScrollBar.vertical: ScrollBar { }
                delegate: Rectangle {
                    required property var modelData
                    width: dlcList.width - 10
                    height: 46
                    radius: 10
                    color: theme.surfaceContainerHigh
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 14; anchors.rightMargin: 8
                        spacing: 10
                        Text {
                            Layout.fillWidth: true
                            text: modelData.title
                            color: theme.onSurface
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            readonly property bool have: modelData.status !== "available"
                            implicitWidth: st.implicitWidth + 20; implicitHeight: 24; radius: 12
                            color: have ? theme.primaryContainer : "transparent"
                            border.width: have ? 0 : 1
                            border.color: theme.outlineVariant
                            Text {
                                id: st
                                anchors.centerIn: parent
                                font.pixelSize: 11
                                color: parent.have ? theme.onPrimaryContainer : theme.onSurfaceVariant
                                text: ({ installed: "Installed", owned: "Owned", available: "Available" })[modelData.status] || modelData.status
                            }
                        }
                        KButton {
                            theme: win.theme
                            implicitHeight: 30
                            visible: modelData.status === "available" && !!modelData.url
                            text: "Store page"
                            onClicked: app.openUrl(modelData.url)
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: dlc.note !== "" && dlc.rows.length > 0
                wrapMode: Text.WordWrap
                color: theme.outline
                font.pixelSize: 12
                text: dlc.note
            }
        }
    }

    // -------------------------------------------------------------------- accounts
    KDialog {
        id: accounts
        theme: win.theme
        heading: "Accounts"
        width: Math.min(win.width - 60, 620)
        contentItem: ColumnLayout {
            spacing: 10
            Repeater {
                model: app.storesInfo
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    height: 64
                    radius: 12
                    color: theme.surfaceContainerHigh
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16; anchors.rightMargin: 12
                        spacing: 12
                        Rectangle { width: 10; height: 10; radius: 5; color: modelData.color }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { text: modelData.name; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold }
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pixelSize: 12
                                color: modelData.problem ? theme.error : theme.onSurfaceVariant
                                text: modelData.problem ? modelData.problem
                                      : modelData.loggedIn ? ("Connected" + (modelData.account ? " · " + modelData.account : ""))
                                      : modelData.id === "battlenet" ? "Install the Battle.net app from the library first"
                                      : "Not connected"
                            }
                        }
                        KButton {
                            theme: win.theme
                            visible: modelData.loginKind === "paste" && modelData.loggedIn
                            text: "Sign out"
                            onClicked: app.logout(modelData.id)
                        }
                        KButton {
                            theme: win.theme
                            primary: !modelData.loggedIn
                            visible: !(modelData.loginKind === "paste" && modelData.loggedIn)
                            enabled: modelData.id === "gog" || !modelData.problem
                            text: modelData.loginKind === "external" ? "Open" : "Sign in"
                            onClicked: app.loginBegin(modelData.id)
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                wrapMode: Text.WordWrap
                color: theme.outline
                font.pixelSize: 12
                text: "Sign-ins happen in your browser or in the store's own client. AIO Launch never sees your passwords; it only keeps the session tokens the stores hand back."
            }
        }
    }

    // -------------------------------------------------------------------- paste-code sign-in
    KDialog {
        id: login
        theme: win.theme
        property string store: ""
        property string url: ""
        property string prompt: ""
        property string error: ""
        property bool busy: false
        heading: "Sign in to " + (win.storeInfo(store).name || "")
        width: Math.min(win.width - 60, 560)
        closePolicy: Popup.CloseOnEscape
        function submit() {
            if (!code.text.trim() || busy) return
            busy = true; error = ""
            app.loginFinish(store, code.text)
        }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                lineHeight: 1.25
                text: login.prompt
            }
            RowLayout {
                spacing: 10
                KButton { theme: win.theme; text: "Open login page again"; onClicked: app.openUrl(login.url) }
                KButton { theme: win.theme; text: "Copy link"; onClicked: { app.copy(login.url); toasts.append({ message: "Link copied" }) } }
            }
            KField {
                id: code
                theme: win.theme
                Layout.fillWidth: true
                placeholderText: "Paste here"
                onAccepted: login.submit()
            }
            Text {
                Layout.fillWidth: true
                visible: login.error !== ""
                wrapMode: Text.WordWrap
                color: theme.error
                font.pixelSize: 12
                text: login.error
            }
            KButton {
                theme: win.theme
                primary: true
                Layout.alignment: Qt.AlignRight
                enabled: code.text.trim() !== "" && !login.busy
                text: login.busy ? "Checking…" : "Finish sign-in"
                onClicked: login.submit()
            }
        }
    }

    // -------------------------------------------------------------------- settings
    component Row2: ColumnLayout {
        readonly property var theme: app.theme
        property string label
        property string hint: ""
        default property alias body: slot.data
        Layout.fillWidth: true
        spacing: 5
        Text { visible: label !== ""; text: label; color: theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
        ColumnLayout { id: slot; Layout.fillWidth: true }
        Text {
            visible: hint !== ""
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: hint
            color: theme.outline
            font.pixelSize: 12
            linkColor: theme.primary
            onLinkActivated: link => app.openUrl(link)
        }
    }
    component Toggle: RowLayout {
        id: tg
        readonly property var theme: app.theme
        property string label
        property string settingKey
        Layout.fillWidth: true
        Text { text: tg.label; color: theme.onSurface; font.pixelSize: 13; Layout.fillWidth: true }
        Switch {
            id: sw
            checked: app.settingsMap[tg.settingKey] === true
            onToggled: app.setSetting(tg.settingKey, checked)
            indicator: Rectangle {
                implicitWidth: 40; implicitHeight: 22; radius: 11
                y: parent.height / 2 - height / 2
                color: sw.checked ? theme.primary : theme.surfaceContainerHighest
                Rectangle {
                    x: sw.checked ? parent.width - width - 3 : 3
                    y: 3; width: 16; height: 16; radius: 8
                    color: sw.checked ? theme.onPrimary : theme.outline
                }
            }
        }
    }
    component Chip: Rectangle {
        id: chip
        readonly property var theme: app.theme
        property string label
        property bool active: false
        property string dot: ""
        signal picked()
        implicitWidth: chipText.implicitWidth + (dot ? 40 : 26)
        implicitHeight: 32
        radius: 16
        color: active ? theme.primaryContainer : chipHover.hovered ? theme.surfaceContainerHighest : theme.surfaceContainerHigh
        border.width: 1
        border.color: active ? theme.primary : theme.outlineVariant
        Rectangle { visible: chip.dot !== ""; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 9; height: 9; radius: 5; color: chip.dot || "transparent" }
        Text {
            id: chipText
            x: chip.dot ? 28 : 13
            anchors.verticalCenter: parent.verticalCenter
            text: chip.label
            color: chip.active ? theme.onPrimaryContainer : theme.onSurface
            font.pixelSize: 13
        }
        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: chip.picked() }
    }

    KDialog {
        id: prefs
        theme: win.theme
        heading: "Settings"
        width: Math.min(win.width - 60, 640)
        property int tab: 0

        contentItem: ColumnLayout {
            spacing: 18
            RowLayout {
                spacing: 8
                Repeater {
                    model: ["Appearance", "Compatibility", "Library"]
                    Chip {
                        required property string modelData
                        required property int index
                        label: modelData
                        active: prefs.tab === index
                        onPicked: prefs.tab = index
                    }
                }
            }

            StackLayout {
                currentIndex: prefs.tab
                Layout.fillWidth: true

                // ---- Appearance
                ColumnLayout {
                    spacing: 16
                    Row2 {
                        label: "Theme"
                        hint: "Follow wallpaper picks AIO Launch's colours from your desktop wallpaper and changes with it. Works with Ryoku, GNOME, KDE, Xfce, Cinnamon, MATE, Hyprland (hyprpaper, swww) and Sway."
                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            Chip {
                                label: "Follow wallpaper"
                                active: app.settingsMap.theme_mode === "ryoku"
                                onPicked: app.setSetting("theme_mode", "ryoku")
                            }
                            Repeater {
                                model: app.themePresets
                                Chip {
                                    required property string modelData
                                    label: modelData
                                    active: app.settingsMap.theme_mode === modelData
                                    onPicked: app.setSetting("theme_mode", modelData)
                                }
                            }
                            Chip {
                                label: "Custom"
                                active: app.settingsMap.theme_mode === "custom"
                                onPicked: app.setCustomColor("theme_accent", win.theme.primary)
                            }
                        }
                    }
                    Row2 {
                        label: "Accent colour"
                        Swatches {
                            theme: win.theme
                            Layout.fillWidth: true
                            choices: app.accentChoices
                            value: win.theme.primary
                            onPicked: colour => app.setCustomColor("theme_accent", colour)
                        }
                    }
                    Row2 {
                        label: "Background colour"
                        hint: "Picking a colour switches to a custom theme; text and panel shades are worked out from these two."
                        Swatches {
                            theme: win.theme
                            Layout.fillWidth: true
                            choices: app.backgroundChoices
                            value: win.theme.background
                            onPicked: colour => app.setCustomColor("theme_bg", colour)
                        }
                    }
                    Row2 {
                        label: "Cover size"
                        KSlider {
                            theme: win.theme; Layout.fillWidth: true
                            from: 130; to: 320; stepSize: 2
                            value: app.settingsMap.card_size
                            onMoved: app.setSetting("card_size", value)
                        }
                    }
                    Row2 {
                        label: "Corner roundness"
                        KSlider {
                            theme: win.theme; Layout.fillWidth: true
                            from: 0; to: 28; stepSize: 1
                            value: app.settingsMap.card_radius
                            onMoved: app.setSetting("card_radius", value)
                        }
                    }
                    Toggle { label: "Show store badges on covers"; settingKey: "show_badges" }
                    Toggle { label: "Always show game titles"; settingKey: "show_titles" }
                    Toggle { label: "Dim games that are not installed"; settingKey: "dim_uninstalled" }
                }

                // ---- Compatibility
                ColumnLayout {
                    spacing: 16
                    Row2 {
                        label: "Default Proton version"
                        hint: "Used for Epic, GOG, Amazon and Battle.net. Builds found in Steam's compatibilitytools.d folders are listed. Steam games use the version set inside Steam."
                        KCombo {
                            id: protonBox
                            theme: win.theme; Layout.fillWidth: true
                            model: app.protonVersions
                            onModelChanged: select(app.settingsMap.proton)
                            Component.onCompleted: select(app.settingsMap.proton)
                            onActivated: app.setSetting("proton", currentValue)
                        }
                    }
                    Row2 {
                        label: "Or a custom Proton folder"
                        KField {
                            theme: win.theme; Layout.fillWidth: true
                            placeholderText: "/path/to/a/Proton/folder"
                            text: app.settingsMap.proton.startsWith("/") || app.settingsMap.proton.startsWith("~") ? app.settingsMap.proton : ""
                            onEditingFinished: if (text.trim() !== "") app.setSetting("proton", text.trim())
                        }
                    }
                    Toggle { label: "MangoHud overlay"; settingKey: "mangohud" }
                    Toggle { label: "Feral GameMode"; settingKey: "gamemode" }
                    Row2 {
                        label: "Environment variables for every game"
                        hint: "Space separated, for example: DXVK_HUD=fps PROTON_ENABLE_WAYLAND=1. Each game can override all of this from its Options button."
                        KField {
                            theme: win.theme; Layout.fillWidth: true
                            placeholderText: "KEY=value KEY2=value"
                            text: app.settingsMap.env
                            onEditingFinished: app.setSetting("env", text.trim())
                        }
                    }
                }

                // ---- Library
                ColumnLayout {
                    spacing: 16
                    Row2 {
                        label: "Games folder"
                        hint: "Where Epic, GOG and Amazon games and all Proton prefixes are stored. Steam keeps using its own libraries."
                        KField {
                            theme: win.theme; Layout.fillWidth: true
                            text: app.settingsMap.games_dir
                            onEditingFinished: app.setSetting("games_dir", text.trim())
                        }
                    }
                    Toggle { label: "Show a game owned on several stores only once"; settingKey: "merge_duplicates" }
                    Row2 {
                        label: ""
                        hint: "Epic and GOG saves are downloaded before you play and uploaded when the game closes. Steam and Battle.net sync saves in their own apps; Amazon has no cloud saves."
                        Toggle { label: "Sync cloud saves"; settingKey: "cloud_saves" }
                    }
                    Row2 {
                        label: "Steam Web API key (optional)"
                        hint: "Without a key AIO Launch shows the Steam games installed on this PC. With one it also lists everything you own. Get a key at <a href='https://steamcommunity.com/dev/apikey'>steamcommunity.com/dev/apikey</a>."
                        KField {
                            theme: win.theme; Layout.fillWidth: true
                            echoMode: TextInput.PasswordEchoOnEdit
                            text: app.settingsMap.steam_api_key
                            onEditingFinished: { app.setSetting("steam_api_key", text.trim()); app.refresh("steam") }
                        }
                    }
                    Row2 {
                        label: "SteamGridDB API key (optional)"
                        hint: "Games without box art are matched by title against Steam's store. A SteamGridDB key also finds art for games Steam does not sell: <a href='https://www.steamgriddb.com/profile/preferences/api'>steamgriddb.com/profile/preferences/api</a>."
                        KField {
                            theme: win.theme; Layout.fillWidth: true
                            echoMode: TextInput.PasswordEchoOnEdit
                            text: app.settingsMap.steamgriddb_key
                            onEditingFinished: { app.setSetting("steamgriddb_key", text.trim()); app.refresh() }
                        }
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------- per-game options
    KDialog {
        id: gameOpts
        theme: win.theme
        property string key: ""
        property var game: ({})
        property var opts: ({})
        readonly property bool compat: ["epic", "gog", "amazon"].includes(game.store) || key === "battlenet:battlenet-app"
        heading: "Options · " + (game.title || "")
        width: Math.min(win.width - 60, 600)
        function show(k) {
            key = k
            game = app.game(k)
            opts = app.gameOptions(k)
            optProton.select(opts.proton === undefined ? "default" : opts.proton)
            optHud.select(opts.mangohud === undefined ? "default" : opts.mangohud)
            optMode.select(opts.gamemode === undefined ? "default" : opts.gamemode)
            optSaves.select(opts.cloud_saves === undefined ? "default" : opts.cloud_saves)
            optEnv.text = opts.env || ""
            optArgs.text = opts.args || ""
            optCover.text = opts.cover || ""
            open()
        }
        readonly property var triState: [{ label: "Use default", value: "default" }, { label: "On", value: true }, { label: "Off", value: false }]

        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                visible: !gameOpts.compat
                wrapMode: Text.WordWrap
                color: theme.onSurfaceVariant
                font.pixelSize: 12
                text: gameOpts.game.store === "steam"
                      ? "Steam picks Proton and launch options itself: in Steam, open the game's Properties → Compatibility."
                      : "Battle.net games all run inside the Battle.net app, so Proton and overlay options are set on the Battle.net tile."
            }
            Row2 {
                visible: gameOpts.compat
                label: "Proton version"
                KCombo {
                    id: optProton
                    theme: win.theme; Layout.fillWidth: true
                    model: [{ label: "Use default", value: "default" }].concat(app.protonVersions)
                    onActivated: app.setGameOption(gameOpts.key, "proton", currentValue)
                }
            }
            RowLayout {
                visible: gameOpts.compat
                spacing: 14
                Row2 {
                    label: "MangoHud"
                    KCombo { id: optHud; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "mangohud", currentValue) }
                }
                Row2 {
                    label: "GameMode"
                    KCombo { id: optMode; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "gamemode", currentValue) }
                }
            }
            Row2 {
                visible: gameOpts.compat
                label: "Environment variables"
                KField { id: optEnv; theme: win.theme; Layout.fillWidth: true; placeholderText: "KEY=value KEY2=value"
                         onEditingFinished: app.setGameOption(gameOpts.key, "env", text) }
            }
            Row2 {
                visible: gameOpts.compat && gameOpts.game.store !== "battlenet"
                label: "Launch arguments"
                KField { id: optArgs; theme: win.theme; Layout.fillWidth: true; placeholderText: "-windowed -skipintro"
                         onEditingFinished: app.setGameOption(gameOpts.key, "args", text) }
            }
            RowLayout {
                visible: app.cloudSaveStores.includes(gameOpts.game.store)
                spacing: 14
                Row2 {
                    label: "Cloud saves"
                    KCombo { id: optSaves; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "cloud_saves", currentValue) }
                }
                KButton {
                    theme: win.theme
                    Layout.alignment: Qt.AlignBottom
                    text: "Sync saves now"
                    enabled: !!gameOpts.game.installed
                    onClicked: app.syncNow(gameOpts.key)
                }
            }
            Row2 {
                label: "Custom cover"
                hint: "An image file or a web address. Leave empty to use the automatic cover."
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    KField { id: optCover; theme: win.theme; Layout.fillWidth: true; placeholderText: "Automatic"
                             onEditingFinished: app.setGameOption(gameOpts.key, "cover", text) }
                    KButton { theme: win.theme; text: "Choose…"; onClicked: coverPicker.open() }
                    KButton { theme: win.theme; text: "Reset"; enabled: optCover.text !== ""
                              onClicked: { optCover.text = ""; app.setGameOption(gameOpts.key, "cover", "") } }
                }
            }
        }
    }
    FileDialog {
        id: coverPicker
        title: "Choose a cover image"
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: {
            app.setGameOption(gameOpts.key, "cover", selectedFile.toString())
            optCover.text = app.gameOptions(gameOpts.key).cover || ""
        }
    }

    // -------------------------------------------------------------------- toasts
    ListModel { id: toasts }
    Column {
        z: 1000
        parent: Overlay.overlay
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 24 }
        spacing: 8
        Repeater {
            model: toasts
            Rectangle {
                id: toast
                required property string message
                required property int index
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(toastText.implicitWidth + 36, win.width - 80)
                height: toastText.height + 22
                radius: 12
                color: theme.inverseSurface || "#e7e0e8"
                Text {
                    id: toastText
                    anchors.centerIn: parent
                    width: Math.min(implicitWidth, win.width - 116)
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    text: toast.message
                    color: theme.inverseOnSurface || "#322f35"
                    font.pixelSize: 13
                }
                Timer { interval: 5000; running: true; onTriggered: toasts.remove(0) }
                TapHandler { onTapped: toasts.remove(toast.index) }
            }
        }
    }
}
